"""What a cached page shows: an edit to any of it empties Cloudflare's cache once the save is committed
(edge_cache.py ``_mtbg_changed``).

Edits only (0.3.0, owner 2026-11-01: "99% of the page is static"): prices, seats left and statuses come to the pages
live (data-mtbg-live, never cached), so bookings and price rules never empty the cache.

Watched here: Odoo's own website (its settings, pages, menus, templates) and blog. Every other extension says itself
what of it a page shows (0.8.0: no dependency either way), on its own models:

* ``_mtbg_edge_cache_watch = True`` (any change) or ``= {'field', ...}`` (only those fields): the model's create,
  write, unlink and translations empty the cache;
* ``_mtbg_edge_cache_param_prefixes = ('prefix.',)``: a system parameter whose key starts so does too;
* ``_mtbg_edge_cache_static_prefixes = ('/path/',)``: addresses of public files given without a session cookie
  (ir_http.py);
* ``_mtbg_edge_cache_fingerprint()``: what pages show that changes by itself (edge_cache.py, the one-minute check);
* ``_mtbg_edge_cache_pages(vals)`` (0.9.0, optional) on a watched model's records: the only page addresses (in the
  default language: each is purged in every language) that show what was just changed (``vals``: the values
  written, None for a create or delete), or None for every page (the default: a record shown in a menu, on cards, in
  a list...). Without it a change empties every page.

0.9.0: a change empties Cloudflare's copies of page addresses only (pages.py), never its scripts, styles or
pictures. Here, an edit to a website page's own content (its template, in the editor or translated) empties that page
alone; everything else (menus, the website's settings, other templates, a module update) every page.
"""
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

# (this module's own settings: a change empties the cache as before 0.8.0)
OWN_PARAM_PREFIXES = ('mtbg_tours.edge_cache',)
TZ_PARAM = 'mtbg_tours.operator_tz'  # (a Tours site's time zone: the nightly re-fill follows it)


def declared(env, attribute):
    """{model name: value} of the models in this registry whose class carries ``attribute`` (set or inherited from
    one of its extensions), its value not empty."""
    out = {}
    for name in list(env.registry):
        value = getattr(env.registry[name], attribute, None)
        if value:
            out[name] = value
    return out


def declared_pages(records, vals=None):
    """The page addresses ``records`` declare for a change (``_mtbg_edge_cache_pages``), None: every page."""
    method = getattr(records, '_mtbg_edge_cache_pages', None)
    if not callable(method) or not records:
        return None
    try:
        paths = method(vals)
    except Exception:  # noqa: BLE001 - a declaration failing: every page
        _logger.exception("Cloudflare page cache: the pages of a change to %s could not be read", records._name)
        return None
    return None if paths is None else list(paths)


# a website page's own template: these fields are its content (an edit in the editor, a translation)
VIEW_CONTENT = {'arch', 'arch_db', 'arch_base', 'arch_prev', 'arch_updated'}


def param_prefixes(env):
    """The system parameter prefixes whose change empties the cache, kept per registry."""
    registry = env.registry
    prefixes = getattr(registry, '_mtbg_edge_param_prefixes', None)
    if prefixes is None:
        found = set(OWN_PARAM_PREFIXES)
        for value in declared(env, '_mtbg_edge_cache_param_prefixes').values():
            found.update(value)
        prefixes = registry._mtbg_edge_param_prefixes = tuple(sorted(found))
    return prefixes


class _MtbgEdgeCacheSource(models.AbstractModel):
    _name = 'mtbg.edge.cache.source.mixin'
    _description = 'Shown on cached pages'

    def _mtbg_edge_changed(self, vals=None):
        watched = getattr(self, '_mtbg_edge_fields', None)
        if vals is None or watched is None or watched & set(vals):
            self.env['mtbg.edge.cache']._mtbg_changed(declared_pages(self, vals))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._mtbg_edge_changed()
        return records

    def write(self, vals):
        result = super().write(vals)
        self._mtbg_edge_changed(vals)
        return result

    def unlink(self):
        self._mtbg_edge_changed()
        return super().unlink()

    def _update_field_translations(self, field_name, translations, digest=None, source_lang=''):
        # (a text translated in the translation dialog or the website editor, not through write)
        result = super()._update_field_translations(field_name, translations, digest=digest, source_lang=source_lang)
        self._mtbg_edge_changed({field_name: True})
        return result


class WebsitePage(models.Model):
    _name = 'website.page'
    _inherit = ['website.page', 'mtbg.edge.cache.source.mixin']


class Website(models.Model):
    # the website's own settings shown on every page (the chat tab, the cookie bar, the social links...)
    _name = 'website'
    _inherit = ['website', 'mtbg.edge.cache.source.mixin']


class WebsiteMenu(models.Model):
    _name = 'website.menu'
    _inherit = ['website.menu', 'mtbg.edge.cache.source.mixin']


class IrUiView(models.Model):
    _name = 'ir.ui.view'
    _inherit = ['ir.ui.view', 'mtbg.edge.cache.source.mixin']

    def _mtbg_edge_changed(self, vals=None):
        # only the website's templates (the editor's saves, a module's update): not the back office's views
        qweb = self.filtered(lambda view: view.type == 'qweb')
        if not qweb:
            return
        super(IrUiView, qweb)._mtbg_edge_changed(vals)

    def _mtbg_edge_cache_pages(self, vals):
        """0.9.0: the content of website pages' own templates (Website › Pages) changed: those pages alone;
        anything else (a shared template, the header, a page created or deleted): every page."""
        if vals is None or not set(vals) <= VIEW_CONTENT:
            return None
        pages = self.sudo().page_ids
        if not pages or any(not view.page_ids for view in self.sudo()):
            return None
        return [url for url in pages.mapped('url') if url]


class IrConfigParameter(models.Model):
    _inherit = 'ir.config_parameter'

    # the site's own settings and texts, under the prefixes the extensions declare
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        prefixes = param_prefixes(self.env)
        if any(str(vals.get('key', '')).startswith(prefixes) for vals in vals_list):
            self.env['mtbg.edge.cache']._mtbg_changed()
        if any(vals.get('key') == TZ_PARAM for vals in vals_list):
            self.env['mtbg.edge.cache']._mtbg_schedule_warm()
        return records

    def write(self, vals):
        prefixes = param_prefixes(self.env)
        keys = self.mapped('key')
        mine = any(key.startswith(prefixes) for key in keys)
        result = super().write(vals)
        if mine:
            self.env['mtbg.edge.cache']._mtbg_changed()
        if 'value' in vals and TZ_PARAM in keys:
            # (the business's time zone changed: the nightly re-fill keeps to its time in the new one)
            self.env['mtbg.edge.cache']._mtbg_schedule_warm()
        return result


# Odoo's blog (optional: no dependency): watched where installed, its create, write and unlink wrapped when the
# registry loads (0.6.0); with the models the extensions declare (0.8.0)
SOFT_SOURCES = {
    # posts, blogs, their categories (a post's view count: not a write)
    'blog.post': None,
    'blog.blog': None,
    'blog.tag': None,
}


def sources(env):
    """{model: watched fields or None (any change)}: the blog and every model declaring
    ``_mtbg_edge_cache_watch``."""
    out = dict(SOFT_SOURCES)
    for name, value in declared(env, '_mtbg_edge_cache_watch').items():
        if not env.registry[name]._abstract:
            out[name] = None if value is True else set(value)
    return out


def _note(records, vals=None, watched=None):
    if watched is not None and vals is not None and not watched & set(vals):
        return
    try:
        records.env['mtbg.edge.cache']._mtbg_changed(declared_pages(records, vals))
    except Exception:  # noqa: BLE001 - never in the way of the save
        _logger.exception("Cloudflare page cache: a change to %s could not be noted", records._name)


def watch_softly(env, watch=None):
    """Wrap the create, write, unlink and translations of the ``watch`` models present in this registry (default:
    ``sources(env)``), once each."""
    for name, watched in (sources(env) if watch is None else watch).items():
        if name not in env:
            continue
        cls = type(env[name])
        if cls.__dict__.get('_mtbg_edge_soft'):
            continue
        create, write, unlink = cls.create, cls.write, cls.unlink
        translate = cls._update_field_translations

        def make(create, write, unlink, translate, watched):
            @api.model_create_multi
            def soft_create(self, vals_list):
                records = create(self, vals_list)
                _note(records)
                return records

            def soft_write(self, vals):
                result = write(self, vals)
                if self:
                    _note(self, vals, watched)
                return result

            def soft_unlink(self):
                if self:
                    _note(self)
                return unlink(self)

            def soft_translate(self, field_name, translations, digest=None, source_lang=''):
                # (a text translated in the translation dialog or the website editor, not through write)
                result = translate(self, field_name, translations, digest=digest, source_lang=source_lang)
                if self:
                    _note(self, {field_name: True}, watched)
                return result
            return soft_create, soft_write, soft_unlink, soft_translate

        cls.create, cls.write, cls.unlink, cls._update_field_translations = make(create, write, unlink, translate,
                                                                                 watched)
        cls._mtbg_edge_soft = (create, write, unlink, translate)


def unwatch(env, names):
    """The wrapping undone (tests)."""
    for name in names:
        if name in env:
            cls = type(env[name])
            original = cls.__dict__.get('_mtbg_edge_soft')
            if original:
                cls.create, cls.write, cls.unlink, cls._update_field_translations = original
                del cls._mtbg_edge_soft


class MtbgEdgeCacheSoftSources(models.AbstractModel):
    _inherit = 'mtbg.edge.cache'

    def _register_hook(self):
        super()._register_hook()
        self.env.registry._mtbg_edge_param_prefixes = None
        self.env.registry._mtbg_edge_static_prefixes = None
        self.env.registry._mtbg_edge_live_keys = None
        watch_softly(self.env)
        from .live_values import watch_live_answer
        watch_live_answer(self.env)
