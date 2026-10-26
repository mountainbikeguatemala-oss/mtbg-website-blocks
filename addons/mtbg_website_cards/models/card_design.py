"""Card designs: how the website draws the cards of a source's records (Card Designer, the Cards building block).

A module gives its sources through the card sources protocol (override on mtbg.website.card.design, call super()):
    _mtbg_card_sources()                    {key: {name, fields: [{key, label, kind, icon, place}],
                                                   filters: [{key, label, options: [{key, label}]}]}}
    _mtbg_card_records(source, filters, limit)   the records a block shows (filters: {key: option key})
    _mtbg_card_values(source, record)            {'url', 'image', field key: text, ...} of one record
    _mtbg_card_samples(source)                   a few records for the designer's preview
Field kinds: title (the theme's heading), text, badge, price, meta (an icon and a short text), rating (stars),
countdown (a booking countdown: its value is {'deadline': ISO datetime, 'label'}).
"""
import json
import re

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

STYLES = [('below', 'Text below the photo'), ('overlay', 'Text over the photo'), ('above', 'Text above the photo')]
RATIOS = [('3-2', '3:2'), ('4-3', '4:3'), ('16-9', '16:9'), ('1-1', 'Square')]
CORNERS = [('none', 'Square'), ('small', 'Rounded'), ('large', 'Very rounded')]
# where a field goes: on the photo (a corner, its bottom) or in the card's text; off: hidden
PLACES = ('top_left', 'top_right', 'image_bottom', 'body', 'off')
COLOR_KEYS = ('card_bg', 'text', 'muted', 'accent', 'accent_text', 'overlay')
COLOR = re.compile(r'^#[0-9a-fA-F]{6}$')


class MtbgWebsiteCardDesign(models.Model):
    _name = 'mtbg.website.card.design'
    _description = 'Website card design'
    _order = 'source, is_default desc, sequence, name, id'

    name = fields.Char(required=True, translate=True)
    source = fields.Selection(selection='_selection_source', required=True,
                              help="What the cards show (the records of a source a module gives)")
    is_default = fields.Boolean(string='Default', help="The design of its source's cards where none is chosen")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    style = fields.Selection(STYLES, required=True, default='below')
    ratio = fields.Selection(RATIOS, string='Photo frame', required=True, default='3-2')
    corners = fields.Selection(CORNERS, required=True, default='small')
    shadow = fields.Boolean(default=True)
    hover_zoom = fields.Boolean(string='Zoom the photo on hover', default=True)
    hover_darken = fields.Boolean(string='Darken the photo on hover')
    look = fields.Json(help="{'parts': [{key, place}], 'light': {colour: #hex}, 'dark': {colour: #hex}}")
    draft = fields.Json(copy=False, groups='website.group_website_designer',
                        help="The designer's unsaved settings, shown only in its preview")

    # ------------------------------------------------------------------ the card sources protocol
    @api.model
    def _mtbg_card_sources(self):
        """{key: {name, fields, filters}} of the sources the modules give (none here)."""
        return {}

    @api.model
    def _selection_source(self):
        return [(key, spec['name']) for key, spec in self._mtbg_card_sources().items()]

    @api.model
    def _mtbg_card_records(self, source, filters, limit):
        return []

    @api.model
    def _mtbg_card_values(self, source, record):
        return {}

    @api.model
    def _mtbg_card_samples(self, source):
        return self._mtbg_card_records(source, {}, 6)

    # ------------------------------------------------------------------ settings
    def _mtbg_settings(self, draft=False):
        """The design's settings as the designer and the renderer read them (its draft with ``draft``)."""
        self.ensure_one()
        saved = {'style': self.style, 'ratio': self.ratio, 'corners': self.corners, 'shadow': self.shadow,
                 'hover_zoom': self.hover_zoom, 'hover_darken': self.hover_darken, 'look': self.look or {}}
        if draft and isinstance(self.sudo().draft, dict):
            saved = dict(saved, **self._mtbg_clean(self.sudo().draft))
        saved['look'] = self._mtbg_clean_look(saved.get('look'))
        return saved

    def _mtbg_clean_look(self, look):
        """The parts (every field of the source once, in order, each with its place) and the colours."""
        self.ensure_one()
        look = look if isinstance(look, dict) else {}
        spec = self._mtbg_card_sources().get(self.source) or {}
        fields_by_key = {f['key']: f for f in spec.get('fields', [])}
        parts, seen = [], set()
        for part in look.get('parts') or []:
            key = part.get('key') if isinstance(part, dict) else None
            if key in fields_by_key and key not in seen:
                seen.add(key)
                parts.append({'key': key, 'place': part.get('place') if part.get('place') in PLACES else 'body'})
        parts += [{'key': key, 'place': f.get('place', 'off')} for key, f in fields_by_key.items() if key not in seen]
        colors = {}
        for mode in ('light', 'dark'):
            values = look.get(mode) if isinstance(look.get(mode), dict) else {}
            colors[mode] = {k: v for k, v in values.items() if k in COLOR_KEYS and COLOR.match(str(v or ''))}
        return {'parts': parts, **colors}

    @api.model
    def _mtbg_clean(self, vals):
        out = {}
        for key, choices in (('style', STYLES), ('ratio', RATIOS), ('corners', CORNERS)):
            if vals.get(key) in dict(choices):
                out[key] = vals[key]
        for key in ('shadow', 'hover_zoom', 'hover_darken'):
            if key in vals:
                out[key] = bool(vals[key])
        if 'look' in vals:
            out['look'] = vals['look'] if isinstance(vals['look'], dict) else {}
        return out

    # ------------------------------------------------------------------ rendering
    @api.model
    def _mtbg_design_for(self, source, design_id=0):
        """The design asked for (if it is the source's), else the source's Default, else any of its designs."""
        design = self.sudo().browse(int(design_id or 0)).exists()
        if design and design.source == source:
            return design
        return self.sudo().search([('source', '=', source), ('is_default', '=', True)], limit=1) \
            or self.sudo().search([('source', '=', source)], limit=1)

    def _mtbg_card_context(self, values, settings):
        """What the card template needs for one record: its parts by place, in order, with their values."""
        spec = self._mtbg_card_sources().get(self.source) or {}
        fields_by_key = {f['key']: f for f in spec.get('fields', [])}
        places = {place: [] for place in PLACES if place != 'off'}
        for part in settings['look']['parts']:
            field = fields_by_key.get(part['key'])
            value = values.get(part['key'])
            if part['place'] == 'off' or not field or value in (None, '', False, []):
                continue
            places[part['place']].append({'key': part['key'], 'kind': field.get('kind', 'text'),
                                          'icon': field.get('icon') or '', 'value': value})
        return {'values': values, 'places': places}

    def _mtbg_style_vars(self, settings):
        """The design's colours as CSS variables: the light ones, and the dark ones (used on dark pages)."""
        out = []
        for mode, prefix in (('light', '--mtbg-card-'), ('dark', '--mtbg-card-dark-')):
            for key, value in (settings['look'].get(mode) or {}).items():
                out.append(f"{prefix}{key.replace('_', '-')}: {value}")
        return '; '.join(out)

    def mtbg_render(self, records=None, values_list=None, draft=False, columns=3):
        """The cards (HTML) of ``records`` (or of ready ``values_list``) in this design."""
        self.ensure_one()
        settings = self._mtbg_settings(draft=draft)
        if values_list is None:
            values_list = [self._mtbg_card_values(self.source, record) for record in records or []]
        cards = [self._mtbg_card_context(values, settings) for values in values_list]
        return self.env['ir.qweb']._render('mtbg_website_cards.cards', {
            'design': self, 'settings': settings, 'cards': cards, 'columns': columns,
            'style_vars': self._mtbg_style_vars(settings)})

    # ------------------------------------------------------------------ the designer
    @api.model
    def _mtbg_check_designer(self):
        if not self.env.user.has_group('website.group_website_designer'):
            raise AccessError(self.env._("Only website designers can design cards."))

    @api.model
    def mtbg_designer_data(self, design_id=0):
        """The Card Designer: the designs, the one shown (settings, its source's fields), the sources."""
        self._mtbg_check_designer()
        sources = self._mtbg_card_sources()
        design = self.browse(int(design_id or 0)).exists() or self.search([], limit=1)
        return {
            'designs': [{'id': d.id, 'name': d.name, 'source': d.source, 'is_default': d.is_default}
                        for d in self.search([])],
            'sources': [{'key': key, 'name': spec['name']} for key, spec in sources.items()],
            'design': design and dict(design._mtbg_settings(), id=design.id, name=design.name, source=design.source,
                                      is_default=design.is_default),
            'fields': (sources.get(design.source) or {}).get('fields', []) if design else [],
            'places': [{'key': 'top_left', 'label': self.env._("Photo, top left")},
                       {'key': 'top_right', 'label': self.env._("Photo, top right")},
                       {'key': 'image_bottom', 'label': self.env._("Photo, bottom")},
                       {'key': 'body', 'label': self.env._("Text")},
                       {'key': 'off', 'label': self.env._("Hidden")}],
        }

    def mtbg_designer_draft(self, settings):
        """The designer's unsaved settings, for its preview only."""
        self.ensure_one()
        self._mtbg_check_designer()
        self.sudo().draft = self._mtbg_clean(settings or {})
        return True

    def mtbg_designer_save(self, settings):
        self.ensure_one()
        self._mtbg_check_designer()
        vals = self._mtbg_clean(settings or {})
        if 'look' in vals:
            vals['look'] = self._mtbg_clean_look(vals['look'])
        self.write(vals)
        self.sudo().draft = False
        return self.mtbg_designer_data(self.id)

    @api.model
    def mtbg_designer_create(self, name, source, copy_of=0):
        """A new design of ``source`` (a copy of ``copy_of``'s settings when given)."""
        self._mtbg_check_designer()
        if source not in self._mtbg_card_sources():
            raise ValidationError(self.env._("Unknown source: %s", source))
        base = self.browse(int(copy_of or 0)).exists()
        vals = {'name': (name or '').strip() or self.env._("New card design"), 'source': source}
        if base and base.source == source:
            vals.update(base._mtbg_settings())
        design = self.create(vals)
        if not self.search_count([('source', '=', source), ('is_default', '=', True), ('id', '!=', design.id)]):
            design.is_default = True
        return self.mtbg_designer_data(design.id)

    def action_make_default(self):
        self.ensure_one()
        self.search([('source', '=', self.source), ('id', '!=', self.id)]).write({'is_default': False})
        self.is_default = True

    @api.model
    def mtbg_block_data(self):
        """The Cards block's options: the sources (their filters) and the designs of each."""
        sources = self._mtbg_card_sources()
        return {'sources': [{'key': key, 'name': spec['name'], 'filters': spec.get('filters', []),
                             'designs': [{'id': d.id, 'name': d.name}
                                         for d in self.search([('source', '=', key)])]}
                            for key, spec in sources.items()]}

    @api.model
    def mtbg_parse_filters(self, raw):
        try:
            filters = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except ValueError:
            filters = {}
        return {str(k): str(v) for k, v in (filters or {}).items() if v not in (None, '')}
