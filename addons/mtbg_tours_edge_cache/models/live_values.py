"""The live values: every price, availability or status a public page shows, which Cloudflare must never keep (owner,
2026-11-01: "a table of declarations of any live pricing values that need to be excluded from cache global").

A page carries such a value as an empty placeholder, ``data-mtbg-live="<kind>:<id>:<part>"``, or asks for a record's
values with ``data-mtbg-live-<kind>s="<ids>"``; the page's script fills them after load from the extension's own live
route (never cached). Here:

* the declarations, shown on the Cloudflare page cache settings. 0.8.0: each extension answering live values declares
  its own, on one of its models: ``_mtbg_edge_cache_live_values = ((key, English label, Spanish label, kind), ...)``
  (kind: ``price``, ``availability``, ``status`` or ``form``; "<id>" in a key: the record's id). Every class of
  the registry carrying it counts, the extension is the class's module;
* the live answer (``mtbg.live.mtbg_live``, where an extension has it) warns about a key nobody declared (it still
  answers it: a visitor never sees an empty price);
* a placeholder that arrives filled is emptied before the page leaves Odoo (0.6.0; until then such a page was not
  given to Cloudflare), and logged.

A new live value: declare it with the extension answering it (its tests fail on an undeclared key found in a page).
"""
import logging
import re

from markupsafe import Markup, escape

from odoo import api, models

_logger = logging.getLogger(__name__)

PRICE, AVAILABILITY, STATUS, FORM = 'price', 'availability', 'status', 'form'
KINDS = {PRICE: ("Price", "Precio"), AVAILABILITY: ("Availability", "Disponibilidad"), STATUS: ("Status", "Estado"),
         FORM: ("Booking form data", "Datos del formulario de reserva")}

ATTRIBUTE = '_mtbg_edge_cache_live_values'


def declarations(env):
    """[(key, English label, Spanish label, extension, kind)]: every class of the registry that carries the
    attribute in its own body, by extension then as declared; a key once."""
    rows, seen, classes = [], set(), set()
    for name in sorted(env.registry):
        for cls in type(env[name]).__mro__:
            if cls in classes or ATTRIBUTE not in cls.__dict__:
                continue
            classes.add(cls)
            module = getattr(cls, '_module', None) or ''
            for key, label_en, label_es, kind in cls.__dict__[ATTRIBUTE]:
                if key not in seen:
                    seen.add(key)
                    rows.append((key, label_en, label_es, module, kind if kind in KINDS else PRICE))
    return sorted(rows, key=lambda row: row[3])  # (stable: each extension's in its own order)


def _declared_sets(env):
    registry = env.registry
    known = getattr(registry, '_mtbg_edge_live_keys', None)
    if known is None:
        rows = declarations(env)
        known = registry._mtbg_edge_live_keys = (
            {tuple(key.split(':<id>:')) for key, *_ in rows if ':<id>:' in key},
            {key.split('=')[0] for key, *_ in rows if '=' in key})
    return known


HOOK = re.compile(r'^([a-z_]+):\d+:([a-z_]+)$')
HOOK_ATTR = re.compile(rb'data-mtbg-live="([a-z_]+:\d+:[a-z_]+)"')
DATA_ATTR = re.compile(rb'data-mtbg-live-([a-z]+)="')
TAG = re.compile(rb'<(/?)([a-zA-Z][a-zA-Z0-9]*)\b[^>]*?(/?)>')
VOID = {b'br', b'img', b'input', b'hr', b'meta', b'link', b'source', b'wbr', b'area', b'col', b'embed', b'param'}


def declared(env, key):
    """A placeholder's key (``tour:12:from``) or a page's data kind (``forms``) is on the list."""
    hooks, data = _declared_sets(env)
    found = HOOK.match(key)
    if found:
        return found.groups() in hooks
    return key in data


def filled_hooks(page):
    """The placeholders of ``page`` (bytes) that arrive with something in them: [(key, its text)]."""
    out = []
    for found in HOOK_ATTR.finditer(page):
        start = page.rfind(b'<', 0, found.start())
        opening = TAG.match(page, start)
        if not opening or opening.group(1) or opening.group(3) or opening.group(2).lower() in VOID:
            continue
        name, depth, pos = opening.group(2).lower(), 1, opening.end()
        for tag in TAG.finditer(page, pos):
            if tag.group(2).lower() != name or tag.group(3):
                continue
            depth += -1 if tag.group(1) else 1
            if not depth:
                inner = page[pos:tag.start()]
                text = re.sub(rb'<[^>]*>', b'', inner).strip()
                if text:
                    out.append((found.group(1).decode(), text[:60].decode('utf-8', 'replace')))
                break
    return out


def empty_filled(page):
    """``page`` (bytes) with its filled placeholders emptied (0.6.0: a page saved in the website editor while its
    script had filled them keeps that day's prices in its template): (the page, [(key, the text taken out)]). The
    page's script fills them from /mtbg_tours/live as always."""
    out, filled, cut = [], [], 0
    for found in HOOK_ATTR.finditer(page):
        start = page.rfind(b'<', 0, found.start())
        if start < cut:
            continue  # (inside a placeholder already emptied)
        opening = TAG.match(page, start)
        if not opening or opening.group(1) or opening.group(3) or opening.group(2).lower() in VOID:
            continue
        name, depth, pos = opening.group(2).lower(), 1, opening.end()
        for tag in TAG.finditer(page, pos):
            if tag.group(2).lower() != name or tag.group(3):
                continue
            depth += -1 if tag.group(1) else 1
            if not depth:
                inner = page[pos:tag.start()]
                text = re.sub(rb'<[^>]*>', b'', inner).strip()
                if text:  # (as filled_hooks: empty markup the script works in stays)
                    filled.append((found.group(1).decode(), ' '.join(text[:60].decode('utf-8', 'replace').split())))
                    out.append(page[cut:pos])
                    cut = tag.start()
                break
    if not filled:
        return page, []
    out.append(page[cut:])
    return b''.join(out), filled


def page_keys(page):
    """The live keys a page carries: (placeholder keys, data kinds)."""
    hooks = {m.group(1).decode() for m in HOOK_ATTR.finditer(page)}
    kinds = {m.group(1).decode() for m in DATA_ATTR.finditer(page)}
    return hooks, kinds


def watch_live_answer(env):
    """Wrap the live answer (``mtbg.live.mtbg_live``, an extension's, where installed: no dependency), once: a key
    nobody declared is answered all the same, and said in the log (the tests: so it is declared before it reaches
    the site)."""
    if 'mtbg.live' not in env:
        return
    cls = type(env['mtbg.live'])
    if cls.__dict__.get('_mtbg_edge_live_soft') or not hasattr(cls, 'mtbg_live'):
        return
    original = cls.mtbg_live

    def mtbg_live(self, keys='', *args, **kwargs):
        try:
            for key in (keys or '').split(',')[:200]:
                if key.count(':') == 2 and not declared(self.env, key):
                    _logger.warning("undeclared live key: %s (declare it in the extension answering it: "
                                    "_mtbg_edge_cache_live_values)", key)
        except Exception:  # noqa: BLE001 - never in the way of the answer
            _logger.exception("Cloudflare page cache: the live keys could not be checked")
        return original(self, keys, *args, **kwargs)
    if getattr(original, '_api_model', False):
        mtbg_live = api.model(mtbg_live)
    cls.mtbg_live = mtbg_live
    cls._mtbg_edge_live_soft = original


class MtbgEdgeCacheLiveValues(models.AbstractModel):
    _name = 'mtbg.edge.cache.live.values'
    _description = 'Cloudflare page cache: the live values'

    @api.model
    def mtbg_rows(self):
        """The declarations in the reader's language: [{key, label, module, module_name, kind}]."""
        es = (self.env.lang or '').startswith('es')
        rows = declarations(self.env)
        names = dict(self.env['ir.module.module'].sudo().search(
            [('name', 'in', list({d[3] for d in rows}))]).mapped(lambda m: (m.name, m.shortdesc)))
        return [{'key': key, 'label': label_es if es else label_en, 'module': module,
                 'module_name': names.get(module) or module, 'kind': KINDS[kind][1 if es else 0]}
                for key, label_en, label_es, module, kind in rows]

    @api.model
    def mtbg_table_html(self):
        es = (self.env.lang or '').startswith('es')
        heads = ("Clave", "Valor", "Extensión", "Tipo") if es else ("Key", "Value", "Extension", "Kind")
        if not declarations(self.env):
            return Markup('<p class="text-muted o_mtbg_live_values">%s</p>') % (
                "Ninguna extensión instalada muestra valores en vivo." if es else
                "No installed extension shows live values.")
        rows = Markup('').join(
            Markup('<tr><td><code>%s</code></td><td>%s</td><td>%s</td><td>%s</td></tr>')
            % (r['key'], r['label'], r['module_name'], r['kind']) for r in self.mtbg_rows())
        return Markup('<table class="table table-sm o_mtbg_live_values"><thead><tr>%s</tr></thead><tbody>%s</tbody>'
                      '</table>') % (Markup('').join(Markup('<th>%s</th>') % escape(h) for h in heads), rows)
