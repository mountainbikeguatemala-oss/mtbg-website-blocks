import logging
import re

from odoo import models
from odoo.http import request

from .live_values import empty_filled
from .sources import declared

_logger = logging.getLogger(__name__)

AUTH_COOKIE = 'mtbg_auth'          # Cloudflare's rule never serves a cached page to a browser that has it
EDITOR_PARAMS = ('debug', 'enable_editor', 'edit_translations', 'fw', 'website_id')
# Odoo's file routes that hand a new visitor a session cookie (/web/image already does not): the same file for
# everyone, so Cloudflare can keep it (a response with a cookie it never keeps); with the public file addresses the
# extensions declare (``_mtbg_edge_cache_static_prefixes``, 0.8.0)
STATIC_PREFIXES = ('/web/assets/', '/web/content/')
# the files for search engines (0.6.0): the same for everyone, no session for a new visitor either
NO_SESSION_PATHS = ('/sitemap.xml', '/robots.txt', '/favicon.ico')
SITEMAP_PART = re.compile(r'^/sitemap-\d+\.xml$')
# a website page (Website › Pages) is kept wherever it is (0.6.0): published to everyone, not behind a password,
# a login or a group
PAGE_MODELS = ('website.page',)
# while the server is down or updating (502/503/504 or no answer), Cloudflare keeps answering a kept page past its
# time instead of an error, for up to a week (0.6.7; Cloudflare ignores it while its "Always Online" is on)
STALE_IF_ERROR = 7 * 86400


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _post_dispatch(cls, response):
        if request and cls._mtbg_no_session_path(request.httprequest.path) and not request.session.uid \
                and not request.cookies.get('session_id'):
            # (no session for a file: nothing is kept in it; before super(), which saves the session last)
            request.session.can_save = False
            return super()._post_dispatch(response)
        super()._post_dispatch(response)
        if not request:
            return
        cls._mtbg_auth_cookie(response)
        if not request.session.uid:
            cls._mtbg_empty_live_values(response)
        if cls._mtbg_edge_cacheable(response):
            ttl = request.env['mtbg.edge.cache']._mtbg_params()['ttl']
            response.headers['Cache-Control'] = 'public, max-age=0, s-maxage=%d, stale-if-error=%d' % (
                ttl, STALE_IF_ERROR)
            # the same page for every visitor: no cookie (the session is made by /mtbg/session or /mtbg/visit)
            response.headers.remove('Set-Cookie')
            request.future_response.headers.remove('Set-Cookie')
            request.session.can_save = False

    @classmethod
    def _mtbg_static_prefixes(cls):
        env = getattr(request, 'env', None)
        if env is None:
            return STATIC_PREFIXES
        registry = env.registry
        prefixes = getattr(registry, '_mtbg_edge_static_prefixes', None)
        if prefixes is None:
            found = set(STATIC_PREFIXES)
            for value in declared(env, '_mtbg_edge_cache_static_prefixes').values():
                found.update(value)
            prefixes = registry._mtbg_edge_static_prefixes = tuple(sorted(found))
        return prefixes

    @classmethod
    def _mtbg_no_session_path(cls, path):
        return path.startswith(cls._mtbg_static_prefixes()) or path in NO_SESSION_PATHS \
            or bool(SITEMAP_PART.match(path))

    @classmethod
    def _mtbg_empty_live_values(cls, response):
        """A declared live value arrived filled in a visitor's page (live_values.py), e.g. a template saved in the
        website editor with the prices its script had filled in: emptied (the script fills it), logged."""
        if getattr(response, 'mimetype', '') != 'text/html' or getattr(response, 'status_code', 0) != 200:
            return
        if not getattr(request, 'is_frontend', False):
            return
        if hasattr(response, 'flatten'):
            response.flatten()
        page = response.get_data()
        if b'data-mtbg-live="' not in page:
            return
        page, filled = empty_filled(page)
        if filled:
            response.set_data(page)
            _logger.warning("Cloudflare page cache: %s: live values filled in the page, emptied: %s (a template "
                            "saved with them?)", request.httprequest.path,
                            ', '.join('%s "%s"' % kv for kv in filled[:5]))

    @classmethod
    def _mtbg_auth_cookie(cls, response):
        """``mtbg_auth=1`` while the session has a user (login), removed when it has none (logout, expired). On the
        response itself: Odoo has already added its own cookies to it by now."""
        target = response if hasattr(response, 'set_cookie') else request.future_response
        has = request.cookies.get(AUTH_COOKIE)
        if request.session.uid and not has:
            target.set_cookie(AUTH_COOKIE, '1', httponly=True, samesite='Lax')
        elif not request.session.uid and has:
            target.set_cookie(AUTH_COOKIE, '', max_age=0, expires=0, httponly=True, samesite='Lax')

    @classmethod
    def _mtbg_edge_cacheable_request(cls):
        """An anonymous visitor's GET of a page the settings let Cloudflare keep (switch on)."""
        if not request or request.httprequest.method not in ('GET', 'HEAD'):
            return False
        website = getattr(request, 'website', None)
        if not website or not getattr(request, 'is_frontend', False):
            return False
        if request.session.uid or request.cookies.get(AUTH_COOKIE) or request.session.debug:
            return False
        if any(key in request.httprequest.args for key in EDITOR_PARAMS):
            return False
        Cache = request.env['mtbg.edge.cache']
        params = Cache._mtbg_params()
        return params['on'] and params['ttl'] > 0

    @classmethod
    def _mtbg_edge_cacheable(cls, response):
        if not (getattr(response, 'status_code', 0) == 200 and getattr(response, 'mimetype', '') == 'text/html'
                and cls._mtbg_edge_cacheable_request()):
            return False
        Cache = request.env['mtbg.edge.cache']
        return Cache._mtbg_path_allowed(request.httprequest.path) or cls._mtbg_public_page(response)

    @classmethod
    def _mtbg_public_page(cls, response):
        """The response is a website page (Website › Pages: About us, Contact us...) every visitor gets."""
        page = getattr(response, '_cached_page', None)
        if page is None and hasattr(response, 'qcontext'):
            page = response.qcontext.get('main_object')
        if getattr(page, '_name', None) not in PAGE_MODELS:
            return False
        page = page.sudo()
        return bool(page.is_published and not page.visibility)
