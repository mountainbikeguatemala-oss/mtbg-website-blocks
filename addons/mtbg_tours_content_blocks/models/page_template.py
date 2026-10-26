"""Page templates: named, storable layouts of a kind of page (docs/architecture/page-templates.md). A kind of page
(Tours: the tour page, the rental page) is given by a module through the page kinds protocol below: its insert points
(slots), the elements it can show and sample pages for the preview. A template's lines place those elements and
reusable blocks in the insert points, a Desktop and a Mobile layout. The Default of each kind is the page as its
module draws it. The template editor edits the lines; its preview shows the unsaved draft (draft_layout) to the
person editing.

The page kinds protocol (override on mtbg.page.template, call super()):
    _mtbg_page_kinds()              [(code, label)]
    _mtbg_page_slots(kind)          [{code, name, description}] in page order
    _mtbg_page_registry(kind)       {code: {code, name, template, slot, sequence, kind, icon, description, ...}}
    _mtbg_page_samples(kind)        [{id, name, url, published}]: pages of the kind to preview on
A page of a kind renders ``_mtbg_template_for_kind(kind)._mtbg_layout(layout=...)`` (``_mtbg_request_layout()``:
desktop / mobile; ``_mtbg_request_preview_id()``: the editor's preview)."""
import json

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request
# set by the install hook and the 19.0.0.5.0 migration: the Default templates are made once every module is loaded,
# so they place every extension's elements (a module's own hook runs before the modules that depend on it load)
SYNC_PARAM = 'mtbg_tours_content_blocks.page_templates_sync'


class PageLayout(dict):
    """{slot: [element spec, ...]}, with ``order``: the sections (insert points) in page order."""
    order = ()

BLOCK_TEMPLATE = 'mtbg_tours_content_blocks.tour_el_block'


class MtbgPageTemplate(models.Model):
    _name = 'mtbg.page.template'
    _description = 'Page Template'
    _order = 'kind, is_default desc, sequence, name, id'

    name = fields.Char(required=True, translate=True)
    kind = fields.Selection(selection='_selection_kind', required=True, default=lambda self: self._default_kind(),
                            help="The pages this template lays out (e.g. tour pages, bike rental pages).")
    is_default = fields.Boolean(string='Default', copy=False,
                                help="Used by every page of its kind that no other template is assigned to.")
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    note = fields.Text(string='Internal Note', help="For the team; never shown on the website")
    line_ids = fields.One2many('mtbg.page.template.line', 'template_id', string='Elements', copy=True,
                               context={'active_test': False})
    line_count = fields.Integer(compute='_compute_line_count', string='Elements Shown')
    slot_order = fields.Json(string='Section Order', copy=True,
                             help="{layout: [insert point codes]}: the sections in page order, Desktop and Mobile (the "
                                  "editor moves whole sections within their area)")
    hidden_slots = fields.Json(string='Hidden Sections', copy=True,
                               help="{layout: [insert point codes]}: whole sections left out of the page, Desktop and "
                                    "Mobile each (their blocks stay in the template)")
    draft_layout = fields.Text(copy=False, groups='website.group_website_designer',
                               help="The editor's unsaved lines (JSON), shown only in its preview")

    @api.depends('line_ids.active')
    def _compute_line_count(self):
        for template in self:
            template.line_count = len(template.line_ids.filtered('active'))

    @api.constrains('is_default', 'kind', 'active')
    def _check_one_default(self):
        for template in self.filtered('is_default'):
            if not template.active:
                raise ValidationError(self.env._("The Default template of a kind cannot be archived."))
            if self.search_count([('kind', '=', template.kind), ('is_default', '=', True),
                                  ('id', '!=', template.id)]):
                raise ValidationError(self.env._("There is already a Default template for this kind of page."))

    def copy_data(self, default=None):
        vals_list = super().copy_data(default)
        for template, vals in zip(self, vals_list):
            if 'name' not in (default or {}):
                vals['name'] = self.env._("%s (copy)", template.name)
        return vals_list

    def action_make_default(self):
        self.ensure_one()
        self.search([('kind', '=', self.kind), ('is_default', '=', True), ('id', '!=', self.id)]).is_default = False
        self.write({'is_default': True, 'active': True})

    # ------------------------------------------------------------------ the page kinds protocol
    @api.model
    def _mtbg_page_kinds(self):
        """[(code, label)] of the kinds of page templates lay out (none here: the modules that draw pages add theirs)."""
        return []

    @api.model
    def _selection_kind(self):
        return self._mtbg_page_kinds()

    @api.model
    def _default_kind(self):
        kinds = self._mtbg_page_kinds()
        return kinds[0][0] if kinds else False

    @api.model
    def _mtbg_page_slots(self, kind=None):
        """[{code, name, description}]: a kind's insert points in page order (every kind's, once each, without one)."""
        return []

    @api.model
    def _mtbg_page_registry(self, kind=None):
        """{code: element spec}: the elements a kind of page can show (every kind's, without one)."""
        return {}

    @api.model
    def _mtbg_page_samples(self, kind):
        """[{id, name, url, published}]: pages of a kind the editor previews the template on."""
        return []

    @api.model
    def _mtbg_layout_from(self, elements, kind=None):
        """{slot: [element, ...]} in page order from ``elements`` (specs carrying their slot and sequence)."""
        slots = {s['code'] for s in self._mtbg_page_slots(kind)}
        layout = {}
        for el in sorted(elements, key=lambda e: (e['sequence'], e.get('line_id') or 0, e['code'])):
            if el['slot'] in slots:
                layout.setdefault(el['slot'], []).append(el)
        return layout

    # ------------------------------------------------------------------ the layout
    @api.model
    def _mtbg_template_for_kind(self, kind):
        """The template laying out a page of ``kind``: the Default of the kind (category assignments: phase 4)."""
        return self.search([('kind', '=', kind), ('is_default', '=', True)], limit=1)

    @api.model
    def _mtbg_request_layout(self):
        """'mobile' for a phone (its browser says "Mobi"; the template editor's phone preview: ?mtbg_layout=mobile),
        else 'desktop' (tablets and computers)."""
        if not request or not getattr(request, 'httprequest', None):
            return 'desktop'
        asked = request.httprequest.args.get('mtbg_layout')
        if asked in ('desktop', 'mobile'):
            return asked
        return 'mobile' if 'Mobi' in (request.httprequest.headers.get('User-Agent') or '') else 'desktop'

    @api.model
    def _mtbg_request_preview_id(self):
        """The template the editor previews (?mtbg_template_preview=<id>, website designers only), else 0."""
        if not request or not getattr(request, 'httprequest', None):
            return 0
        raw = request.httprequest.args.get('mtbg_template_preview', '')
        if not raw.isdigit() or not request.env.user.has_group('website.group_website_designer'):
            return 0
        return int(raw)

    @api.model
    def _mtbg_page_layout(self, kind):
        """{slot: [element spec, ...]} of a page of ``kind`` for this request: the editor's preview (its unsaved
        draft), else the kind's template, Desktop or Mobile; None without a template (the page's own defaults)."""
        Template = self.sudo()
        layout = self._mtbg_request_layout()
        preview = Template.browse(self._mtbg_request_preview_id()).exists()
        if preview and preview.kind == kind:
            return preview._mtbg_layout(draft=True, layout=layout)
        template = Template._mtbg_template_for_kind(kind)
        return template._mtbg_layout(layout=layout) if template else None

    def _mtbg_line_dicts(self, layout='desktop'):
        """The stored lines of a layout (desktop / mobile) as the editor and the page read them, in page order."""
        self.ensure_one()
        return [{'id': line.id, 'code': line.element_code or False, 'block_id': line.block_id.id, 'slot': line.slot,
                 'sequence': line.sequence, 'active': line.active}
                for line in self.with_context(active_test=False).line_ids if (line.layout or 'desktop') == layout]

    def _mtbg_has_mobile(self):
        """Does the template have a Mobile layout of its own (else phones show the Desktop one)?"""
        self.ensure_one()
        return bool(self.with_context(active_test=False).line_ids.filtered(lambda l: l.layout == 'mobile'))

    def _mtbg_draft_dicts(self, layout='desktop'):
        """The editor's unsaved lines of a layout, or None (the mobile layout: None while it follows Desktop)."""
        self.ensure_one()
        try:
            draft = json.loads(self.sudo().draft_layout or 'null')
        except ValueError:
            draft = None
        if isinstance(draft, list):  # (a draft kept before the Mobile layout: Desktop only)
            draft = {'desktop': draft}
        lines = (draft or {}).get(layout)
        return lines if isinstance(lines, list) else None

    def _mtbg_draft_order(self):
        """The editor's unsaved section orders ({layout: [codes]}), or None."""
        try:
            draft = json.loads(self.sudo().draft_layout or 'null')
        except ValueError:
            return None
        return draft.get('order') if isinstance(draft, dict) and isinstance(draft.get('order'), dict) else None

    def _mtbg_draft_hidden(self):
        try:
            draft = json.loads(self.sudo().draft_layout or 'null')
        except ValueError:
            return None
        return draft.get('hidden') if isinstance(draft, dict) and isinstance(draft.get('hidden'), dict) else None

    def _mtbg_hidden_slots(self, layout='desktop', draft=False):
        """The sections a layout leaves out of the page (Mobile without its own list: Desktop's)."""
        self.ensure_one()
        hidden = (draft and self._mtbg_draft_hidden()) or self.hidden_slots or {}
        codes = hidden.get('mobile') if layout == 'mobile' and hidden.get('mobile') is not None else hidden.get('desktop')
        return list(codes or [])

    def _mtbg_slot_sequence(self, layout='desktop', draft=False):
        """The sections (insert point codes) in page order for a layout: its own order, Mobile without one Desktop's,
        the kind's default order for the rest (insert points added since come at their default place)."""
        self.ensure_one()
        orders = (draft and self._mtbg_draft_order()) or self.slot_order or {}
        order = orders.get(layout) if layout == 'mobile' and orders.get('mobile') else orders.get('desktop')
        default = [s['code'] for s in self._mtbg_page_slots(self.kind)]
        return self._mtbg_merge_order(order or [], default)

    @api.model
    def _mtbg_merge_order(self, order, default):
        """``order`` (known codes, once each) with the codes of ``default`` it lacks put after their default
        predecessor."""
        known = [code for i, code in enumerate(order) if code in default and code not in order[:i]]
        for index, code in enumerate(default):
            if code in known:
                continue
            before = next((default[i] for i in range(index - 1, -1, -1) if default[i] in known), None)
            known.insert(known.index(before) + 1 if before else 0, code)
        return known

    def _mtbg_layout(self, draft=False, layout='desktop'):
        """{slot: [element spec, ...]} for this template (its unsaved draft with ``draft``): the Mobile layout when asked
        and the template has one, else the Desktop one (a PageLayout: ``order``, the sections in page order)."""
        self.ensure_one()
        lines = None
        if layout == 'mobile':
            if draft and self.sudo().draft_layout:
                lines = self._mtbg_draft_dicts('mobile')
            elif self._mtbg_has_mobile():
                lines = self._mtbg_line_dicts('mobile')
        if lines is None:
            lines = (draft and self._mtbg_draft_dicts()) or self._mtbg_line_dicts()
        hidden = set(self._mtbg_hidden_slots(layout, draft))
        result = PageLayout({slot: els for slot, els in self._mtbg_layout_of(lines).items() if slot not in hidden})
        result.order = self._mtbg_slot_sequence(layout, draft)
        return result

    def _mtbg_layout_of(self, lines):
        """{slot: [element spec, ...]} for ``lines`` (dicts: code or block_id, slot, sequence, active). A line whose
        element is gone (its extension switched off) is skipped; an element no line mentions (installed after the
        template was saved) shows at its default place."""
        self.ensure_one()
        registry = self._mtbg_page_registry(self.kind)
        block_ids = [line['block_id'] for line in lines if line.get('block_id')]
        blocks = {b.id: b for b in self.env['mtbg.tours.content.block'].sudo().browse(block_ids).exists()}
        elements, seen = [], set()
        for line in lines:
            code = line.get('code')
            if code:
                seen.add(code)
            if not line.get('active', True):
                continue
            block = blocks.get(line.get('block_id'))
            if block:
                if block.active:
                    elements.append({'code': f'block_{block.id}', 'name': block.name, 'template': BLOCK_TEMPLATE,
                                     'slot': line['slot'], 'sequence': line['sequence'], 'kind': 'section',
                                     'block_id': block.id, 'line_id': line.get('id') or 0})
            elif code in registry:
                spec = registry[code]
                elements.append(dict(spec, slot=line.get('slot') or spec['slot'], sequence=line['sequence'],
                                     line_id=line.get('id') or 0))
        elements += [spec for code, spec in registry.items() if code not in seen]
        return self._mtbg_layout_from(elements, self.kind)

    def _mtbg_sync_elements(self):
        """Store a line for each element no line mentions yet, at its default place (the editor and upgrades call
        this; pages only merge them in while rendering)."""
        Line = self.env['mtbg.page.template.line']
        for template in self:
            registry = template._mtbg_page_registry(template.kind)
            seen = set(template.with_context(active_test=False).line_ids.filtered(
                lambda l: (l.layout or 'desktop') == 'desktop').mapped('element_code'))
            Line.create([{'template_id': template.id, 'element_code': code, 'slot': spec['slot'],
                          'sequence': spec['sequence']} for code, spec in registry.items() if code not in seen])

    def _register_hook(self):
        super()._register_hook()
        params = self.env['ir.config_parameter'].sudo()
        if params.get_param(SYNC_PARAM) and not getattr(self.env.cr, 'readonly', False):
            self.sudo()._mtbg_ensure_defaults()
            params.search([('key', '=', SYNC_PARAM)]).unlink()

    @api.model
    def _mtbg_ensure_defaults(self):
        """A Default template per kind, laid out as the registry places its elements (today's page)."""
        langs = [code for code, _name in self.env['res.lang'].get_installed()]

        def name(kind, lang):
            return dict(self.with_context(lang=lang)._mtbg_page_kinds()).get(kind) or kind
        for kind, _label in self._mtbg_page_kinds():
            template = self.with_context(active_test=False).search([('kind', '=', kind), ('is_default', '=', True)],
                                                                   limit=1)
            if not template:
                template = self.with_context(lang='en_US').create(
                    {'name': name(kind, 'en_US'), 'kind': kind, 'is_default': True})
                template.update_field_translations('name', {lang: name(kind, lang) for lang in langs
                                                            if lang != 'en_US'})
            template._mtbg_sync_elements()

    # ------------------------------------------------------------------ the template editor
    def action_open_editor(self):
        self.ensure_one()
        return {'type': 'ir.actions.client', 'tag': 'mtbg_page_template_editor', 'name': self.env._("Page Templates"),
                'context': {'template_id': self.id}}

    @api.model
    def _mtbg_check_editor(self):
        if not self.env.user.has_group('website.group_website_designer'):
            raise AccessError(self.env._("Only website designers can lay out pages."))

    @api.model
    def mtbg_editor_data(self, template_id=0):
        """Everything the editor shows for a template (the Default tour page when none): the templates, the insert
        points, the elements its kind of page can show, its lines (with the elements no line places yet, at their
        usual place), the reusable blocks, sample pages for the preview and the languages."""
        self._mtbg_check_editor()
        Template = self.with_context(active_test=False)
        template = Template.browse(int(template_id or 0)).exists()
        first = (self._mtbg_page_kinds() or [(False, '')])[0][0]
        if not template:
            template = self.search([('kind', '=', first), ('is_default', '=', True)], limit=1)
        if not template:
            self.sudo()._mtbg_ensure_defaults()
            template = self.search([('kind', '=', first), ('is_default', '=', True)], limit=1)
        kinds = dict(self._fields['kind']._description_selection(self.env))
        slots = self._mtbg_page_slots(template.kind)
        slot_order = {s['code']: n for n, s in enumerate(slots)}
        registry = self._mtbg_page_registry(template.kind)
        blocks = self.env['mtbg.tours.content.block'].search([], order='name')
        block_names = {b.id: b.name for b in blocks}

        def complete(lines):
            """A layout's lines, with the elements no line places yet at their usual place, in page order."""
            seen = {line['code'] for line in lines if line['code']}
            lines += [{'id': 0, 'code': code, 'block_id': 0, 'slot': spec['slot'], 'sequence': spec['sequence'],
                       'active': True, 'new': True} for code, spec in registry.items() if code not in seen]
            for line in lines:
                line['missing'] = bool(line['code']) and line['code'] not in registry
                if line['block_id']:
                    line['block_name'] = block_names.get(line['block_id']) or self.env._("(archived block)")
            lines.sort(key=lambda l: (slot_order.get(l['slot'], len(slots)), l['sequence'], l['id'] or 10 ** 9))
            return lines

        lines = complete(template._mtbg_line_dicts())
        # the Mobile layout: None while phones show the Desktop one (the editor starts it as a copy)
        mobile_lines = complete(template._mtbg_line_dicts('mobile')) if template._mtbg_has_mobile() else None
        website = self.env['website'].get_current_website()
        default_lang = website.default_lang_id.code
        langs = [{'code': lang.code, 'name': lang.name,
                  'prefix': '' if lang.code == default_lang else f'/{lang.url_code}'}
                 for lang in website.language_ids or self.env['res.lang'].search([])]
        return {
            'templates': [{'id': t.id, 'name': t.name, 'kind': t.kind, 'kind_label': kinds.get(t.kind),
                           'is_default': t.is_default, 'active': t.active}
                          for t in Template.search([], order='kind, is_default desc, active desc, sequence, name')],
            'template': {'id': template.id, 'name': template.name, 'kind': template.kind,
                         'kind_label': kinds.get(template.kind), 'is_default': template.is_default,
                         'active': template.active, 'note': template.note or ''},
            'kinds': [{'key': key, 'label': label} for key, label in kinds.items()],
            'slots': slots,
            'elements': [{key: spec.get(key) for key in ('code', 'name', 'icon', 'kind', 'description', 'slot', 'group',
                                                         'group_name', 'panel')}
                         for spec in registry.values()],
            'lines': lines,
            'mobile_lines': mobile_lines,
            'hidden_slots': {'desktop': template._mtbg_hidden_slots('desktop') if template else [],
                             'mobile': template._mtbg_hidden_slots('mobile')
                             if template and (template.hidden_slots or {}).get('mobile') is not None else None},
            'slot_order': {'desktop': template._mtbg_slot_sequence('desktop') if template else [],
                           'mobile': (template.slot_order or {}).get('mobile') and template._mtbg_slot_sequence('mobile')
                           if template else None},
            'blocks': [{'id': b.id, 'name': b.name} for b in blocks],
            'samples': self._mtbg_page_samples(template.kind) if template else [],
            'langs': langs,
        }

    def _mtbg_clean_lines(self, lines):
        """The editor's lines, checked: known insert points, an element or a block each, an element once; each insert
        point's lines numbered in the order given."""
        self.ensure_one()
        slots = {s['code'] for s in self._mtbg_page_slots(self.kind)}
        clean, counters, codes = [], {}, set()
        for raw in lines or []:
            slot, code, block_id = raw.get('slot'), raw.get('code') or False, int(raw.get('block_id') or 0)
            if slot not in slots or bool(code) == bool(block_id) or (code and code in codes):
                continue
            if code:
                codes.add(code)
            counters[slot] = counters.get(slot, 0) + 10
            clean.append({'id': int(raw.get('id') or 0), 'code': code, 'block_id': block_id, 'slot': slot,
                          'sequence': counters[slot], 'active': bool(raw.get('active', True))})
        return clean

    def _mtbg_clean_order(self, order):
        """{layout: [codes]} of the editor's section orders (known insert points, once each)."""
        self.ensure_one()
        known = {s['code'] for s in self._mtbg_page_slots(self.kind)}
        clean = {}
        for layout in ('desktop', 'mobile'):
            codes = (order or {}).get(layout)
            if isinstance(codes, list):
                clean[layout] = [c for i, c in enumerate(codes) if c in known and c not in codes[:i]]
        return clean

    def _mtbg_clean_hidden(self, hidden):
        self.ensure_one()
        known = {s['code'] for s in self._mtbg_page_slots(self.kind)}
        clean = {}
        for layout in ('desktop', 'mobile'):
            codes = (hidden or {}).get(layout)
            if isinstance(codes, list):
                clean[layout] = sorted({c for c in codes if c in known})
        return clean

    def mtbg_editor_preview(self, lines, mobile_lines=None, order=None, hidden=None):
        """Keep the editor's unsaved lines (Desktop, and Mobile unless it follows Desktop) for its preview (the site
        keeps the saved ones)."""
        self.ensure_one()
        self._mtbg_check_editor()
        self.draft_layout = json.dumps({
            'desktop': self._mtbg_clean_lines(lines),
            'mobile': self._mtbg_clean_lines(mobile_lines) if mobile_lines is not None else None,
            'order': self._mtbg_clean_order(order),
            'hidden': self._mtbg_clean_hidden(hidden)})
        return True

    def mtbg_editor_save(self, lines, mobile_lines=None, order=None, hidden=None):
        """Store the editor's lines (in the order given), Desktop and Mobile (None: phones show Desktop), and drop the
        draft; returns the editor's data."""
        self.ensure_one()
        self._mtbg_check_editor()
        Line = self.env['mtbg.page.template.line']
        existing = {line.id: line for line in self.with_context(active_test=False).line_ids}
        kept = set()
        layouts = [('desktop', lines)] + ([('mobile', mobile_lines)] if mobile_lines is not None else [])
        for layout, layout_lines in layouts:
            for line in self._mtbg_clean_lines(layout_lines):
                vals = {'slot': line['slot'], 'sequence': line['sequence'], 'active': line['active'],
                        'element_code': line['code'] or False, 'block_id': line['block_id'] or False,
                        'layout': layout}
                if line['id'] in existing and line['id'] not in kept \
                        and (existing[line['id']].layout or 'desktop') == layout:
                    existing[line['id']].write(vals)
                    kept.add(line['id'])
                else:
                    Line.create(dict(vals, template_id=self.id))
        Line.browse([i for i in existing if i not in kept]).unlink()
        if order is not None:
            clean = self._mtbg_clean_order(order)
            if mobile_lines is None:
                clean.pop('mobile', None)  # phones follow Desktop: its order too
            self.slot_order = clean or False
        if hidden is not None:
            clean = self._mtbg_clean_hidden(hidden)
            if mobile_lines is None:
                clean.pop('mobile', None)
            self.hidden_slots = clean or False
        self.draft_layout = False
        return self.mtbg_editor_data(self.id)

class MtbgPageTemplateLine(models.Model):
    _name = 'mtbg.page.template.line'
    _description = 'Page Template Element'
    _order = 'template_id, slot_order, sequence, id'

    template_id = fields.Many2one('mtbg.page.template', required=True, ondelete='cascade', index=True)
    kind = fields.Selection(related='template_id.kind')
    sequence = fields.Integer(default=100)
    slot = fields.Selection(selection='_selection_slot', string='Insert Point', required=True)
    slot_order = fields.Integer(compute='_compute_slot_order', store=True, help="The insert point's place on the page")
    element_code = fields.Char(string='Element Code', help="An element an extension places on the page")
    block_id = fields.Many2one('mtbg.tours.content.block', string='Reusable Block', ondelete='cascade')
    element_name = fields.Char(compute='_compute_element_name', string='Element')
    active = fields.Boolean(default=True, help="Off: removed from the page (the template remembers it).")
    layout = fields.Selection([('desktop', 'Desktop'), ('mobile', 'Mobile')], default='desktop', required=True,
                              help="Desktop: every screen; Mobile: phones, once the template has a Mobile layout")

    _element_or_block = models.Constraint(
        'CHECK ((element_code IS NOT NULL) != (block_id IS NOT NULL))',
        "A template line shows either an element or a reusable block.",
    )

    @api.model
    def _selection_slot(self):
        return [(s['code'], s['name']) for s in self.env['mtbg.page.template']._mtbg_page_slots()]

    @api.depends('slot')
    def _compute_slot_order(self):
        order = {s['code']: n for n, s in enumerate(self.env['mtbg.page.template']._mtbg_page_slots())}
        for line in self:
            line.slot_order = order.get(line.slot, len(order))

    @api.depends('element_code', 'block_id')
    def _compute_element_name(self):
        registry = self.env['mtbg.page.template']._mtbg_page_registry()
        for line in self:
            if line.block_id:
                line.element_name = line.block_id.name
            else:
                spec = registry.get(line.element_code)
                line.element_name = spec['name'] if spec else self.env._("%s (not installed)", line.element_code)
