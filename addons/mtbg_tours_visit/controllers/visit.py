"""POST /mtbg/visit: the page view of an anonymous visitor, sent by the page's script once it has loaded.

The request is made to look like the page itself (its address, its language, its title) and handed to Odoo's own
``website.visitor._handle_webpage_dispatch``, so the visitor and the page view are recorded exactly as while the page
is built: the same visitor (IP, browser, session), country and city (Cloudflare's headers come with this request),
and every extension's additions (Communication Flows: page title, device, place). Contract with cfd_website_visitors
(coordinator, 2026-10-30): it reads ``request.httprequest.url``, ``request.lang`` and ``request.cfd_page_title``;
since 0.1.4 also ``request.cfd_referrer`` (the page's document.referrer, up to 2048 characters) when the page sent one.
"""
import collections
import json
import logging
import threading
import time
from urllib.parse import parse_qsl, urlsplit

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

# crawlers and page tools, by their browser name (lower case). Narrower than Odoo's own list (ir.http.is_a_bot): a
# visit is sent by the page's script, so it comes from a browser that ran the page, and the apps' own browsers
# (Instagram, Facebook, WhatsApp, Pinterest: "instagram", "whatsapp", "pinterest") are people (0.1.2).
CRAWLERS = (
    "bot", "crawl", "slurp", "spider", "curl", "wget", "facebookexternalhit", "trendsmapresolver",
    "google-pagerenderer", "google-inspectiontool", "googleother", "meta-external", "meta-webindexer",
    "chatgpt-user", "claude-user", "perplexity-user", "headlesschrome", "lighthouse", "chrome-lighthouse",
    "pagespeed", "ptst",
)
RATE_LIMIT = 60          # page views a minute from one address (per worker)
MAX_URL = 2048
_seen = collections.defaultdict(collections.deque)
_lock = threading.Lock()


def _too_many(address):
    now = time.monotonic()
    with _lock:
        if len(_seen) > 10000:
            _seen.clear()
        calls = _seen[address]
        while calls and now - calls[0] > 60:
            calls.popleft()
        if len(calls) >= RATE_LIMIT:
            return True
        calls.append(now)
    return False


class MtbgVisit(http.Controller):

    @http.route('/mtbg/visit', type='http', auth='public', methods=['POST'], csrf=False, website=True,
                sitemap=False)
    def visit(self, **kw):
        done = request.make_response('', status=204)
        data, refused = self._mtbg_check()
        if refused:
            # why, without who (a count per reason in the log: grep "visit refused")
            _logger.info("visit refused: %s", refused)
            return done
        url = data['url']
        parts = urlsplit(url)
        page_id = self._mtbg_page_id(data)
        page = request.env['website.page'].sudo().browse(page_id) if page_id else request.env['website.page']
        # the page's own request, as Odoo and the extensions read it while the page is built
        request.httprequest.url = url
        lang = self._mtbg_page_lang(parts.path)
        request.lang = lang
        request.update_context(lang=lang.code)
        request.cfd_page_title = self._mtbg_title(data.get('title'))
        # the page's referrer (document.referrer), for Visit Analytics' source (cfd_website_visitors 1.3.0)
        referrer = data.get('referrer')
        if isinstance(referrer, str):
            request.cfd_referrer = referrer[:MAX_URL]
        request.env['website.visitor']._handle_webpage_dispatch(page)
        self._mtbg_utm_cookies(done, parts.query)
        return done

    def _mtbg_page_id(self, data):
        try:
            return int(data.get('page_id') or 0)
        except (TypeError, ValueError):
            return 0

    def _mtbg_check(self):
        """(the visit sent, why it is not recorded: '' when it is), the reason as the log shows it."""
        try:
            data = json.loads(request.httprequest.get_data(as_text=True) or '{}')
        except ValueError:
            return {}, 'not json'
        url = data.get('url') if isinstance(data, dict) else None
        if not isinstance(url, str) or len(url) > MAX_URL:
            return data, 'no address'
        parts = urlsplit(url)
        if parts.scheme not in ('http', 'https') or parts.netloc != request.httprequest.host:
            return data, 'another address (%s)' % parts.netloc[:80]
        if not request.env.user._is_public():
            return data, 'logged in'
        if not request.website._mtbg_visit_by_script():
            return data, 'switched off'
        agent = request.httprequest.user_agent.string.lower()
        crawler = next((name for name in CRAWLERS if name in agent), None)
        if crawler:
            return data, 'crawler (%s)' % crawler
        if _too_many(request.httprequest.remote_addr):
            return data, 'too many'
        page_id = self._mtbg_page_id(data)
        if page_id:
            page = request.env['website.page'].sudo().browse(page_id).exists()
            if not page:
                return data, 'no page'
            if not page.view_id.track or not page.is_visible:
                return data, 'page not tracked'
        return data, ''

    def _mtbg_page_lang(self, path):
        """The page's language: its address's prefix (/es/...), else the website's default."""
        first = path.lstrip('/').split('/', 1)[0]
        Lang = request.env['res.lang']
        if first:
            lang = Lang._get_data(url_code=first)
            if lang.id and lang.id in request.website.language_ids.ids:
                return lang
        return Lang._get_data(code=request.website.default_lang_id.code)

    def _mtbg_title(self, title):
        """The browser tab's title without " | <website name>" (as Communication Flows names the pages)."""
        title = title if isinstance(title, str) else ''
        suffix = ' | %s' % request.website.name
        if title.endswith(suffix):
            title = title[:-len(suffix)]
        return title.strip()[:200]

    def _mtbg_utm_cookies(self, response, query):
        """The marketing cookies from the page's address, as utm's ir.http._set_utm sets them on the page."""
        params = dict(parse_qsl(query))
        domain = request.env['ir.http'].get_utm_domain_cookies()
        for url_parameter, __, cookie_name in request.env['utm.mixin'].tracking_fields():
            value = params.get(url_parameter)
            if value and request.cookies.get(cookie_name) != value:
                response.set_cookie(cookie_name, value, max_age=31 * 24 * 3600, domain=domain, cookie_type='optional')
