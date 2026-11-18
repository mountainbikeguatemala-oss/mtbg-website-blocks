"""The page addresses Cloudflare may keep, in every language (0.9.0): what a purge empties and what is re-filled.

0.9.0 (owner 2026-11-16, PageSpeed check): Cloudflare's "purge everything" also emptied the script and style
bundles and every picture at every Cloudflare location, so the next visitors (and the nightly speed log) met cold
copies. A change now empties only page addresses:

* the website's sitemap (``website._enumerate_pages``: its pages, tours, blog posts... whatever the installed
  extensions list), each in every language of the website: ``/x`` and ``/es/x``, records with a translated name at
  their own address in that language (``/es/blog/diario-1/...``);
* the homepages, the website's published pages (Website › Pages, also those not in the sitemap) and the entries of
  "Pages Cloudflare may keep" (``/blog``, ``/es/blog``).

Never purged: ``/web/assets/...`` (their address changes with their content) and ``/web/image/...`` (a changed
picture gets a new address: ``?unique=`` / ``?v=``, or a new attachment id). A page address that is not on this list
(a blog's page 2, a tag, a filter in the query string) cannot be purged by address: Cloudflare keeps it an hour at
most (ir_http.py ``SHORT_TTL``).
"""
import functools
import logging
import threading
import time
import types

from odoo import api, models

_logger = logging.getLogger(__name__)

LIST_TTL = 900          # seconds a worker keeps the page list it made (ir_http.py: which pages may stay a month)
_lists = {}             # (dbname, website id) -> (time.monotonic(), frozenset of paths)
_lists_lock = threading.Lock()


def forget(dbname):
    """A change: the page lists of this database are made again on their next use."""
    with _lists_lock:
        for key in [k for k in _lists if k[0] == dbname]:
            _lists.pop(key, None)


def _func_key(func):
    if isinstance(func, functools.partial):
        func = func.func
    if isinstance(func, types.MethodType):
        func = func.__func__
    return func


class MtbgEdgeCachePages(models.AbstractModel):
    _inherit = 'mtbg.edge.cache'

    @api.model
    def _mtbg_website(self):
        """The website a purge, check or re-fill is for (2.1.0: each website in turn, ``_mtbg_for``), else the
        current one (a visitor's page: the website they are on)."""
        site = self.env.context.get('mtbg_edge_cache_website')
        if site:
            return self.env['website'].sudo().browse(site)
        return self.env['website'].sudo().get_current_website()

    @api.model
    def _mtbg_languages(self, website=None):
        """[(language code, address prefix)]: the website's default language first ('' prefix), then the others
        ('/es')."""
        website = website or self._mtbg_website()
        default = website.default_lang_id
        return [(default.code or 'en_US', '')] + [
            (lang.code, '/' + lang.url_code) for lang in website.language_ids.sorted('id') if lang != default]

    @api.model
    def _mtbg_in_lang(self, path, prefix):
        """``path`` (default language) under a language prefix: ('/x', '/es') → '/es/x', ('/', '/es') → '/es'."""
        if not prefix:
            return path
        return prefix if path == '/' else prefix + path

    @api.model
    def _mtbg_page_paths(self, website=None):
        """Every page address a purge of "all pages" empties, in every language, sorted."""
        website = website or self._mtbg_website()
        langs = self._mtbg_languages(website)
        found = {'/'}
        try:
            public = website.with_user(website.user_id).with_context(website_id=website.id)
            found.update(page['loc'] for page in public._enumerate_pages() if (page.get('loc') or '').startswith('/'))
        except Exception:  # noqa: BLE001 - an extension's sitemap failing: the other addresses still go
            _logger.exception("Cloudflare page cache: the sitemap's pages could not be listed")
        for entry in self._mtbg_params()['paths']:
            if entry.startswith('/'):
                found.add(self._mtbg_without_lang(entry.rstrip('/') or '/').rstrip('/') or '/')
        pages = self.env['website.page'].sudo().search([
            ('website_id', 'in', (False, website.id)), ('website_published', '=', True), ('visibility', '=', False)])
        found.update(url for url in pages.mapped('url') if url and url.startswith('/'))
        out = set()
        for code, prefix in langs:
            out.update(self._mtbg_in_lang(path, prefix) for path in found)
            if prefix:
                try:
                    out.update(self._mtbg_in_lang(path, prefix) for path in self._mtbg_translated_locs(website, code))
                except Exception:  # noqa: BLE001
                    _logger.exception("Cloudflare page cache: the %s addresses could not be listed", code)
        return sorted(out)

    @api.model
    def _mtbg_translated_locs(self, website, code):
        """The sitemap's controller addresses rebuilt in language ``code`` (without its prefix): a record's address
        carries its name in that language (Odoo lists them in the default language only)."""
        env = website.with_user(website.user_id).with_context(lang=code, website_id=website.id).env
        done = set()
        for rule in env['ir.http'].routing_map().iter_rules():
            sitemap = rule.endpoint.routing.get('sitemap')
            if sitemap is False:
                continue
            if callable(sitemap):
                key = _func_key(sitemap)
                if key in done:
                    continue
                done.add(key)
                for loc in sitemap(env, rule, None):
                    if (loc.get('loc') or '').startswith('/'):
                        yield loc['loc']
                continue
            converters = rule._converters or {}
            if not converters or not website.rule_is_enumerable(rule):
                continue
            values = [{}]
            # (as Odoo: the converters with a domain after the others, they may use them)
            for name, converter in sorted(converters.items(), key=lambda kv: getattr(kv[1], 'domain', '[]') != '[]'):
                if not hasattr(converter, 'generate'):
                    values = []
                    break
                dom = None
                if 'website_id' in env[converter.model]._fields and getattr(converter, 'domain', '[]') in ('', '[]'):
                    dom = [('website_id', 'in', (False, website.id))]
                values = [dict(value, **{name: record.with_context(lang=code)})
                          for value in values for record in converter.generate(env, args=dict(value), dom=dom)]
            for value in values:
                path = rule.build(value, append_unknown=False)[1]
                yield '/' if path == '/' else path.rstrip('/')

    @api.model
    def _mtbg_known_paths(self):
        """The page list (``_mtbg_page_paths``) as a set, kept LIST_TTL seconds by this worker (ir_http.py)."""
        website = self._mtbg_website()
        key = (self.env.cr.dbname, website.id)
        now = time.monotonic()
        with _lists_lock:
            kept = _lists.get(key)
        if kept and now - kept[0] < LIST_TTL:
            return kept[1]
        paths = frozenset(self._mtbg_page_paths(website))
        with _lists_lock:
            _lists[key] = (now, paths)
        return paths

    @api.model
    def _mtbg_scope_paths(self, paths=None):
        """The addresses to purge: every page (``paths`` None), or ``paths`` (as given and in every language)."""
        if paths is None:
            return self._mtbg_page_paths()
        langs = self._mtbg_languages()
        out = set()
        for path in paths:
            if not path or not path.startswith('/'):
                continue
            out.add(path)
            bare = self._mtbg_without_lang(path)
            out.update(self._mtbg_in_lang(bare, prefix) for _code, prefix in langs)
        return sorted(out)

    @api.model
    def _mtbg_lang_of(self, path, website=None):
        """The language code of a page address (its prefix), else the website's default language's."""
        langs = self._mtbg_languages(website)
        first = '/' + path.split('/', 2)[1] if path.count('/') >= 1 and len(path) > 1 else ''
        for code, prefix in langs[1:]:
            if first == prefix:
                return code
        return langs[0][0]
