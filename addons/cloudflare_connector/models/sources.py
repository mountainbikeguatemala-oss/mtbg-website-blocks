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

2.0.1 (www, 2026-11-17: "Changes saved · Every page" every hour and after many saves, nothing on the pages changed):
a write or a translation empties the cache only when a watched field's value really changed (the values before and
after compared; a binary field always counts), and not when the only change is a read-only date and time (a stamp
such as a menu's "last rendered" or a record's "synced at": no page shows those). A system parameter written with its
own value notes nothing either. Each change notes what it was (the model, the system parameter's key), shown in the
purge log ("Changed: website.menu"), so a change that keeps emptying the pages can be found.
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


def _cache(env, source):
    """The page cache, told what changed (2.0.1: in the context, so ``_mtbg_changed`` keeps its arguments)."""
    return env['mtbg.edge.cache'].with_context(mtbg_edge_cache_source=source)


def _value(record, name):
    value = record[name]
    if isinstance(value, models.BaseModel):
        return tuple(value.ids)
    return value


def before_write(records, vals, watched=None):
    """{record id: {field: value}} of the watched fields ``vals`` writes, read before the write (2.0.1), or None:
    nothing to compare (a binary or unknown field written, or the values could not be read: the change counts)."""
    if not records or not vals:
        return None
    names = [name for name in vals if watched is None or name in watched]
    if not names:
        return None
    try:
        fields_ = records._fields
        if any(name not in fields_ or fields_[name].type == 'binary' for name in names):
            return None
        return {record.id: {name: _value(record, name) for name in names} for record in records}
    except Exception:  # noqa: BLE001 - never in the way of the save: the change counts
        return None


def _bookkeeping(field):
    """A read-only date and time (a stamp: last rendered, synced at...): never what a page shows."""
    return field.type == 'datetime' and field.readonly


def really_changed(records, vals, before):
    """``vals`` without the fields whose value is the same as ``before`` the write (and without the stamps); ``vals``
    as given when there is nothing to compare (``before`` None)."""
    if before is None or vals is None:
        return vals
    try:
        changed = set()
        for record in records:
            old = before.get(record.id)
            if old is None:
                return vals
            changed.update(name for name, value in old.items() if _value(record, name) != value)
    except Exception:  # noqa: BLE001
        return vals
    return {name: vals[name] for name in vals if name in changed and not _bookkeeping(records._fields[name])}


def before_translation(records, field_name, translations):
    """{(record id, language): value} of ``field_name`` in the languages ``translations`` changes, or None."""
    try:
        if field_name not in records._fields or records._fields[field_name].type == 'binary':
            return None
        return {(record.id, lang): record.with_context(lang=lang)[field_name]
                for record in records for lang in (translations or {})}
    except Exception:  # noqa: BLE001
        return None


def translation_changed(records, field_name, before):
    """A translation changed a value (True when there is nothing to compare)."""
    if before is None:
        return True
    try:
        records.invalidate_recordset([field_name])
        return any(records.browse(rid).with_context(lang=lang)[field_name] != value
                   for (rid, lang), value in before.items())
    except Exception:  # noqa: BLE001
        return True


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

    def _mtbg_edge_changed(self, vals=None, before=None):
        watched = getattr(self, '_mtbg_edge_fields', None)
        vals = really_changed(self, vals, before)
        if vals is not None and not vals:
            return  # (2.0.1: written with the values it had: nothing a page shows changed)
        if vals is None or watched is None or watched & set(vals):
            _cache(self.env, self._name)._mtbg_changed(declared_pages(self, vals))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._mtbg_edge_changed()
        return records

    def write(self, vals):
        before = before_write(self, vals, getattr(self, '_mtbg_edge_fields', None))
        result = super().write(vals)
        self._mtbg_edge_changed(vals, before)
        return result

    def unlink(self):
        self._mtbg_edge_changed()
        return super().unlink()

    def _update_field_translations(self, field_name, translations, digest=None, source_lang=''):
        # (a text translated in the translation dialog or the website editor, not through write)
        before = before_translation(self, field_name, translations)
        result = super()._update_field_translations(field_name, translations, digest=digest, source_lang=source_lang)
        if translation_changed(self, field_name, before):
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

    def _mtbg_edge_changed(self, vals=None, before=None):
        # only the website's templates (the editor's saves, a module's update): not the back office's views
        qweb = self.filtered(lambda view: view.type == 'qweb')
        if not qweb:
            return
        super(IrUiView, qweb)._mtbg_edge_changed(vals, before)

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
        for key in sorted({str(vals.get('key', '')) for vals in vals_list if str(vals.get('key', '')).startswith(
                prefixes)}):
            _cache(self.env, key)._mtbg_changed()
        if any(vals.get('key') == TZ_PARAM for vals in vals_list):
            self.env['mtbg.edge.cache']._mtbg_schedule_warm()
        return records

    def write(self, vals):
        prefixes = param_prefixes(self.env)
        keys = self.mapped('key')
        mine = sorted(key for key in keys if key.startswith(prefixes))
        if mine and set(vals) == {'value'}:
            # (2.0.1: written with its own value: nothing changed)
            same = {param.key for param in self if param.value == (False if vals['value'] is False else
                                                                    str(vals['value']))}
            mine = [key for key in mine if key not in same]
        result = super().write(vals)
        for key in mine:
            _cache(self.env, key)._mtbg_changed()
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


def _note(records, vals=None, watched=None, before=None):
    vals = really_changed(records, vals, before)
    if vals is not None and not vals:
        return  # (2.0.1: written with the values it had)
    if watched is not None and vals is not None and not watched & set(vals):
        return
    try:
        _cache(records.env, records._name)._mtbg_changed(declared_pages(records, vals))
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
                before = before_write(self, vals, watched) if self else None
                result = write(self, vals)
                if self:
                    _note(self, vals, watched, before)
                return result

            def soft_unlink(self):
                if self:
                    _note(self)
                return unlink(self)

            def soft_translate(self, field_name, translations, digest=None, source_lang=''):
                # (a text translated in the translation dialog or the website editor, not through write)
                before = before_translation(self, field_name, translations) if self else None
                result = translate(self, field_name, translations, digest=digest, source_lang=source_lang)
                if self and translation_changed(self, field_name, before):
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
