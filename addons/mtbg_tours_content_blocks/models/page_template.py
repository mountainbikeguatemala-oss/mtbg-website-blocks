"""Page templates: named, storable layouts of the tour page (docs/architecture/page-templates.md). A template's lines
place the elements extensions register (mtbg.tour._mtbg_tour_page_blocks()) and reusable blocks in the page's
insert points. The Default of each kind (tour page, rental page) is today's page. The template editor (Catalog ›
Page Templates) edits the lines; its preview shows the unsaved draft (draft_layout) to the person editing."""
import json

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

KINDS = [('tour', 'Tour page'), ('rental', 'Rental page')]
# set by the install hook and the 19.0.0.5.0 migration: the Default templates are made once every module is loaded,
# so they place every extension's elements (a module's own hook runs before the modules that depend on it load)
SYNC_PARAM = 'mtbg_tours_content_blocks.page_templates_sync'
BLOCK_TEMPLATE = 'mtbg_tours_content_blocks.tour_el_block'


class MtbgPageTemplate(models.Model):
    _name = 'mtbg.page.template'
    _inherit = ['mtbg.board.mixin', 'mtbg.card.mixin', 'mtbg.sidebar.mixin']
    _description = 'Page Template'
    _order = 'kind, is_default desc, sequence, name, id'

    name = fields.Char(required=True, translate=True)
    kind = fields.Selection(KINDS, required=True, default='tour',
                            help="The pages this template lays out: tour pages or bike rental pages.")
    is_default = fields.Boolean(string='Default', copy=False,
                                help="Used by every page of its kind that no other template is assigned to.")
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    note = fields.Text(string='Internal Note', help="For the team; never shown on the website")
    line_ids = fields.One2many('mtbg.page.template.line', 'template_id', string='Elements', copy=True,
                               context={'active_test': False})
    line_count = fields.Integer(compute='_compute_line_count', string='Elements Shown')
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

    # ------------------------------------------------------------------ the layout
    @api.model
    def _mtbg_template_for(self, tour):
        """The template laying out ``tour``'s page: the Default of its kind (category assignments: phase 4)."""
        return self.search([('kind', '=', tour._mtbg_tour_page_kind()), ('is_default', '=', True)], limit=1)

    def _mtbg_line_dicts(self):
        """The stored lines as the editor and the layout read them, in page order."""
        self.ensure_one()
        return [{'id': line.id, 'code': line.element_code or False, 'block_id': line.block_id.id, 'slot': line.slot,
                 'sequence': line.sequence, 'active': line.active}
                for line in self.with_context(active_test=False).line_ids]

    def _mtbg_draft_dicts(self):
        self.ensure_one()
        try:
            lines = json.loads(self.sudo().draft_layout or 'null')
        except ValueError:
            lines = None
        return lines if isinstance(lines, list) else None

    def _mtbg_layout(self, draft=False):
        """{slot: [element spec, ...]} for this template (its unsaved draft with ``draft``)."""
        self.ensure_one()
        lines = (draft and self._mtbg_draft_dicts()) or self._mtbg_line_dicts()
        return self._mtbg_layout_of(lines)

    def _mtbg_layout_of(self, lines):
        """{slot: [element spec, ...]} for ``lines`` (dicts: code or block_id, slot, sequence, active). A line whose
        element is gone (its extension switched off) is skipped; an element no line mentions (installed after the
        template was saved) shows at its default place."""
        self.ensure_one()
        Tour = self.env['mtbg.tour']
        registry = Tour._mtbg_tour_page_registry(self.kind)
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
        return Tour._mtbg_layout_from(elements)

    def _mtbg_sync_elements(self):
        """Store a line for each element no line mentions yet, at its default place (the editor and upgrades call
        this; pages only merge them in while rendering)."""
        Line = self.env['mtbg.page.template.line']
        for template in self:
            registry = self.env['mtbg.tour']._mtbg_tour_page_registry(template.kind)
            seen = set(template.with_context(active_test=False).line_ids.mapped('element_code'))
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
            env = self.with_context(lang=lang).env
            return env._("Tour page") if kind == 'tour' else env._("Rental page")
        for kind, _label in KINDS:
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
        if not template:
            template = self.search([('kind', '=', 'tour'), ('is_default', '=', True)], limit=1)
        if not template:
            self.sudo()._mtbg_ensure_defaults()
            template = self.search([('kind', '=', 'tour'), ('is_default', '=', True)], limit=1)
        Tour = self.env['mtbg.tour']
        kinds = dict(self._fields['kind']._description_selection(self.env))
        slots = Tour._mtbg_tour_page_slots()
        slot_order = {s['code']: n for n, s in enumerate(slots)}
        registry = Tour._mtbg_tour_page_registry(template.kind)
        lines = template._mtbg_line_dicts()
        seen = {line['code'] for line in lines if line['code']}
        lines += [{'id': 0, 'code': code, 'block_id': 0, 'slot': spec['slot'], 'sequence': spec['sequence'],
                   'active': True, 'new': True} for code, spec in registry.items() if code not in seen]
        blocks = self.env['mtbg.tours.content.block'].search([], order='name')
        block_names = {b.id: b.name for b in blocks}
        for line in lines:
            line['missing'] = bool(line['code']) and line['code'] not in registry
            if line['block_id']:
                line['block_name'] = block_names.get(line['block_id']) or self.env._("(archived block)")
        lines.sort(key=lambda l: (slot_order.get(l['slot'], len(slots)), l['sequence'], l['id'] or 10 ** 9))
        website = self.env['website'].get_current_website()
        default_lang = website.default_lang_id.code
        langs = [{'code': lang.code, 'name': lang.name,
                  'prefix': '' if lang.code == default_lang else f'/{lang.url_code}'}
                 for lang in website.language_ids or self.env['res.lang'].search([])]
        tours = Tour.sudo().with_context(active_test=False).search(
            [('active', '=', True), ('slug', '!=', False), ('product_kind', '=', template.kind)],
            order='is_published desc, name', limit=300)
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
            'blocks': [{'id': b.id, 'name': b.name} for b in blocks],
            'tours': [{'id': t.id, 'name': t.name, 'slug': t.slug, 'published': t.is_published} for t in tours],
            'langs': langs,
        }

    def _mtbg_clean_lines(self, lines):
        """The editor's lines, checked: known insert points, an element or a block each, an element once; each insert
        point's lines numbered in the order given."""
        self.ensure_one()
        slots = {s['code'] for s in self.env['mtbg.tour']._mtbg_tour_page_slots()}
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

    def mtbg_editor_preview(self, lines):
        """Keep the editor's unsaved lines for its preview (the site keeps the saved ones)."""
        self.ensure_one()
        self._mtbg_check_editor()
        self.draft_layout = json.dumps(self._mtbg_clean_lines(lines))
        return True

    def mtbg_editor_save(self, lines):
        """Store the editor's lines (in the order given) and drop the draft; returns the editor's data."""
        self.ensure_one()
        self._mtbg_check_editor()
        Line = self.env['mtbg.page.template.line']
        existing = {line.id: line for line in self.with_context(active_test=False).line_ids}
        kept = set()
        for line in self._mtbg_clean_lines(lines):
            vals = {'slot': line['slot'], 'sequence': line['sequence'], 'active': line['active'],
                    'element_code': line['code'] or False, 'block_id': line['block_id'] or False}
            if line['id'] in existing:
                existing[line['id']].write(vals)
                kept.add(line['id'])
            else:
                Line.create(dict(vals, template_id=self.id))
        Line.browse([i for i in existing if i not in kept]).unlink()
        self.draft_layout = False
        return self.mtbg_editor_data(self.id)

    # ------------------------------------------------------------------ Core's boards, cards and side bar
    @api.model
    def _mtbg_board_columns(self):
        return [c for c in super()._mtbg_board_columns() if c['key'] not in ('mtbg_time_stage', 'mtbg_missing_ids')]

    def _mtbg_board_dates(self):
        return False, False

    def _mtbg_board_cancelled(self):
        return False

    @api.model
    def _mtbg_sidebar_sections(self, domain):
        return super()._mtbg_sidebar_sections(domain) + [
            {'key': 'kind', 'label': self.env._("Kind"), 'icon': 'fa-columns',
             'nodes': self._mtbg_sidebar_field(domain, 'kind')},
        ]

    @api.model
    def _mtbg_card_fields(self):
        _ = self.env._
        return [
            {'key': 'kind', 'label': _("Kind"), 'icon': 'fa-columns'},
            {'key': 'elements', 'label': _("Elements shown"), 'short': _("Elements")},
            {'key': 'default', 'label': _("Default"), 'icon': 'fa-star'},
        ]

    @api.model
    def _mtbg_card_figures(self):
        return [{'key': 'elements', 'label': self.env._("Elements")}]

    def _mtbg_card_values(self):
        values = super()._mtbg_card_values()
        kinds = dict(self._fields['kind']._description_selection(self.env))
        values.update({
            'titles': {'name': self.name},
            'figures': {'elements': str(self.line_count)},
            'lines': {'kind': kinds.get(self.kind, ''), 'elements': str(self.line_count),
                      'default': self.env._("Default") if self.is_default else ''},
        })
        return values


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

    _element_or_block = models.Constraint(
        'CHECK ((element_code IS NOT NULL) != (block_id IS NOT NULL))',
        "A template line shows either an element or a reusable block.",
    )

    @api.model
    def _selection_slot(self):
        return [(s['code'], s['name']) for s in self.env['mtbg.tour']._mtbg_tour_page_slots()]

    @api.depends('slot')
    def _compute_slot_order(self):
        order = {s['code']: n for n, s in enumerate(self.env['mtbg.tour']._mtbg_tour_page_slots())}
        for line in self:
            line.slot_order = order.get(line.slot, len(order))

    @api.depends('element_code', 'block_id')
    def _compute_element_name(self):
        registry = self.env['mtbg.tour']._mtbg_tour_page_registry()
        for line in self:
            if line.block_id:
                line.element_name = line.block_id.name
            else:
                spec = registry.get(line.element_code)
                line.element_name = spec['name'] if spec else self.env._("%s (not installed)", line.element_code)
