"""Page templates: named, storable layouts of the tour page (docs/architecture/page-templates.md). A template's lines
place the elements extensions register (mtbg.tour._mtbg_tour_page_blocks()) and reusable blocks in the page's
insert points. The Default of each kind (tour page, rental page) is today's page."""
from odoo import api, fields, models
from odoo.exceptions import ValidationError

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

    def _mtbg_layout(self):
        """{slot: [element spec, ...]} for this template. A line whose element is gone (its extension switched off) is
        skipped; an element no line mentions (installed after the template was saved) shows at its default place."""
        self.ensure_one()
        Tour = self.env['mtbg.tour']
        registry = Tour._mtbg_tour_page_registry(self.kind)
        elements, seen = [], set()
        for line in self.with_context(active_test=False).line_ids:
            if line.element_code:
                seen.add(line.element_code)
            if not line.active:
                continue
            if line.block_id:
                if line.block_id.active:
                    elements.append({'code': f'block_{line.block_id.id}', 'name': line.block_id.name,
                                     'template': BLOCK_TEMPLATE, 'slot': line.slot, 'sequence': line.sequence,
                                     'kind': 'section', 'block_id': line.block_id.id, 'line_id': line.id})
            elif line.element_code in registry:
                spec = registry[line.element_code]
                elements.append(dict(spec, slot=line.slot or spec['slot'], sequence=line.sequence, line_id=line.id))
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
