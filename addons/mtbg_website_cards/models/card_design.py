"""Card designs: how the website draws the cards of a source's records (Card Designer, the Cards building block).

A module gives its sources through the card sources protocol (override on mtbg.website.card.design, call super()):
    _mtbg_card_sources()                    {key: {name, fields: [{key, label, kind, icon}],
                                                   filters: [{key, label, options: [{key, label}]}]}}
    _mtbg_card_records(source, filters, limit)   the records a block shows (filters: {key: option key})
    _mtbg_card_values(source, record)            {'url', 'image', field key: value, ...} of one record
    _mtbg_card_samples(source)                   a few records for the designer's preview
Field kinds: title (the theme's heading), text, badge, price, meta (an icon and a short text), rating (stars),
icons (a row of icons per rating: [{'icon', 'value', 'of', 'tip'}]), countdown (a booking countdown: {'deadline':
ISO datetime, 'label'}), button (a link to the record). Every source also has the Book button (field ``book``).

A value is its text, or a dict: {'text', 'class' (extra classes), 'attrs' ({data-*: value}), 'inner_class' (the
text's own span)}; a countdown's dict may also give 'label_class' and 'clock_class' (another module's script then
ticks it, e.g. Tours' early bird). Other modules' scripts thus keep working on the cards (Tours' price currency).

A design's look: six regions, each with the fields placed in it, in order (a field may be placed twice):
    header   above the card (no colour)
    top      the photo's top strip     (Always / On hover, its colours)
    center   the middle of the photo   (Always / On hover)
    bottom   the photo's bottom strip  (Always / On hover, its colours, or a shade)
    below    under the photo
    footer   below's last line: its fields side by side (e.g. the price left, Book right)
A placed field (an item): {'uid', 'field', 'look' (plain / pill / button / bar), 'show' ('' = its region's,
'always', 'hover'), 'text' (its words: {value} is the field, {<field key>} any other field, e.g. "Book (from
{price})"; empty: the value), 'icon' (a Font Awesome class, '' none)}.
"""
import json
import re
import uuid

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

STYLES = [('below', 'Text below the photo'), ('overlay', 'Text over the photo'), ('above', 'Text above the photo')]
RATIOS = [('3-2', '3:2'), ('4-3', '4:3'), ('16-9', '16:9'), ('1-1', 'Square')]
CORNERS = [('none', 'Square'), ('small', 'Rounded'), ('large', 'Very rounded')]
REGIONS = ('header', 'top', 'center', 'bottom', 'below', 'footer')
PHOTO_REGIONS = ('top', 'center', 'bottom')
LOOKS = ('plain', 'pill', 'button', 'bar')
SHOWS = ('', 'always', 'hover')
COLOR_KEYS = ('card_bg', 'text', 'muted', 'accent', 'accent_text', 'overlay', 'top_bg', 'top_text', 'bottom_bg',
              'bottom_text', 'footer_bg', 'early_bg', 'early_text')
COLOR = re.compile(r'^#[0-9a-fA-F]{6}$')
ICON = re.compile(r'^fa-[a-z0-9-]+$')
PLACEHOLDER = re.compile(r'\{(\w+)\}')
# the fields every source has
BOOK = 'book'
# 0.1.x places -> regions
OLD_PLACES = {'top_left': 'top', 'top_right': 'top', 'image_bottom': 'bottom', 'body': 'below'}


def new_uid():
    return uuid.uuid4().hex[:8]


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
    # (0.1.x: where the text went; the regions say it now)
    style = fields.Selection(STYLES, required=True, default='below')
    ratio = fields.Selection(RATIOS, string='Photo frame', required=True, default='3-2')
    corners = fields.Selection(CORNERS, required=True, default='small')
    shadow = fields.Boolean(default=True)
    hover_zoom = fields.Boolean(string='Zoom the photo on hover', default=True)
    hover_darken = fields.Boolean(string='Darken the photo on hover')
    look = fields.Json(help="{'regions': {region: {'show', 'shade', 'items': [...]}}, 'light': {colour: #hex}, "
                            "'dark': {colour: #hex}}")
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

    @api.model
    def _mtbg_source_fields(self, source):
        """The source's fields, and the Book button every source has: {key: field}, in order."""
        spec = self._mtbg_card_sources().get(source) or {}
        out = {f['key']: f for f in spec.get('fields', [])}
        out.setdefault(BOOK, {'key': BOOK, 'label': self.env._("Book button"), 'kind': 'button',
                              'icon': '', 'text': self.env._("Book")})
        return out

    # ------------------------------------------------------------------ settings
    def _mtbg_settings(self, draft=False):
        """The design's settings as the designer and the renderer read them (its draft with ``draft``)."""
        self.ensure_one()
        saved = {'ratio': self.ratio, 'corners': self.corners, 'shadow': self.shadow,
                 'hover_zoom': self.hover_zoom, 'hover_darken': self.hover_darken, 'look': self.look or {}}
        if draft and isinstance(self.sudo().draft, dict):
            saved = dict(saved, **self._mtbg_clean(self.sudo().draft))
        saved['look'] = self._mtbg_clean_look(saved.get('look'), style=self.style)
        return saved

    def _mtbg_clean_item(self, item, region, fields_by_key):
        if not isinstance(item, dict) or item.get('field') not in fields_by_key:
            return None
        field = fields_by_key[item['field']]
        look = item.get('look') if item.get('look') in LOOKS else ('button' if field.get('kind') == 'button' else 'plain')
        icon = item.get('icon', field.get('icon') or '')
        return {
            'uid': str(item.get('uid') or new_uid())[:16],
            'field': item['field'],
            'look': look,
            'show': item.get('show') if region in PHOTO_REGIONS and item.get('show') in SHOWS else '',
            'text': str(item.get('text') or '')[:120],
            'icon': icon if isinstance(icon, str) and (icon == '' or ICON.match(icon)) else '',
        }

    def _mtbg_from_parts(self, look, style):
        """A 0.1.x look ({'parts': [{key, place}]}) as regions."""
        regions = {key: {'items': []} for key in REGIONS}
        body = 'header' if style == 'above' else 'bottom' if style == 'overlay' else 'below'
        for part in look.get('parts') or []:
            place = part.get('place') if isinstance(part, dict) else None
            if place in OLD_PLACES:
                region = body if place == 'body' else OLD_PLACES[place]
                regions[region]['items'].append({'field': part.get('key')})
        return regions

    def _mtbg_clean_look(self, look, style='below'):
        """The regions (their items, cleaned, unknown fields dropped) and the colours."""
        self.ensure_one()
        look = look if isinstance(look, dict) else {}
        fields_by_key = self._mtbg_source_fields(self.source)
        raw = look.get('regions') if isinstance(look.get('regions'), dict) else self._mtbg_from_parts(look, style)
        regions, uids = {}, set()
        for key in REGIONS:
            spec = raw.get(key) if isinstance(raw.get(key), dict) else {}
            items = []
            for item in spec.get('items') or []:
                clean = self._mtbg_clean_item(item, key, fields_by_key)
                if clean:
                    if clean['uid'] in uids:
                        clean['uid'] = new_uid()
                    uids.add(clean['uid'])
                    items.append(clean)
            region = {'items': items}
            if key in PHOTO_REGIONS:
                region['show'] = spec.get('show') if spec.get('show') in ('always', 'hover') else \
                    ('always' if key == 'top' else 'hover')
            if key == 'bottom':
                region['shade'] = bool(spec.get('shade'))
            regions[key] = region
        colors = {}
        for mode in ('light', 'dark'):
            values = look.get(mode) if isinstance(look.get(mode), dict) else {}
            colors[mode] = {k: v for k, v in values.items() if k in COLOR_KEYS and COLOR.match(str(v or ''))}
        return {'regions': regions, **colors}

    @api.model
    def _mtbg_clean(self, vals):
        out = {}
        for key, choices in (('ratio', RATIOS), ('corners', CORNERS)):
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

    @staticmethod
    def _mtbg_value(value):
        """A field's value as {'text', 'class', 'attrs', 'inner_class', ...} (None: nothing to show)."""
        if value in (None, '', False, []):
            return None
        if isinstance(value, dict):
            out = dict(value)
            out.setdefault('text', '')
            out['attrs'] = {k: v for k, v in (out.get('attrs') or {}).items()
                            if isinstance(k, str) and k.startswith('data-') and v not in (None, False)}
            return out
        if isinstance(value, list):
            return {'text': '', 'list': value, 'attrs': {}}
        return {'text': str(value), 'attrs': {}}

    def _mtbg_segments(self, template, field_key, values):
        """The item's words as segments: text, and the values of the fields it names ({value}, {price}...)."""
        if not template:
            return [{'value': values.get(field_key)}] if values.get(field_key) else []
        out, at = [], 0
        for match in PLACEHOLDER.finditer(template):
            if match.start() > at:
                out.append({'text': template[at:match.start()]})
            key = field_key if match.group(1) == 'value' else match.group(1)
            if values.get(key):
                out.append({'value': values[key]})
            at = match.end()
        if at < len(template):
            out.append({'text': template[at:]})
        return out

    def _mtbg_card_context(self, raw_values, settings):
        """What the card template needs for one record: each region's items with their values (an item whose value
        is empty is left out; a button always shows, it links to the record)."""
        fields_by_key = self._mtbg_source_fields(self.source)
        values = {key: self._mtbg_value(value) for key, value in raw_values.items() if key not in ('url', 'image')}
        values[BOOK] = values.get(BOOK) or {'text': fields_by_key[BOOK].get('text') or '', 'attrs': {}}
        regions = {}
        for key, region in settings['look']['regions'].items():
            items = []
            for item in region['items']:
                field = fields_by_key.get(item['field']) or {}
                kind = field.get('kind', 'text')
                if kind == 'button' and not item['text']:
                    segments = [{'text': field.get('text') or self.env._("Book")}]
                else:
                    segments = self._mtbg_segments(item['text'], item['field'], values)
                value = values.get(item['field'])
                if not segments and kind not in ('countdown', 'rating', 'icons'):
                    continue
                if kind in ('countdown', 'rating', 'icons') and not value:
                    continue
                items.append(dict(item, kind=kind, value=value or {}, segments=segments,
                                  show=item['show'] or region.get('show') or 'always'))
            regions[key] = dict(region, items=items)
        return {'url': raw_values.get('url') or '', 'image': raw_values.get('image') or '',
                'name': raw_values.get('name') or '', 'regions': regions}

    def _mtbg_style_vars(self, settings):
        """The design's colours as CSS variables: the light ones, and the dark ones (used on dark pages)."""
        out = []
        for mode, prefix in (('light', '--mtbg-card-'), ('dark', '--mtbg-card-dark-')):
            for key, value in (settings['look'].get(mode) or {}).items():
                out.append(f"{prefix}{key.replace('_', '-')}: {value}")
        return '; '.join(out)

    def mtbg_render(self, records=None, values_list=None, draft=False, columns=3, layout='grid'):
        """The cards (HTML) of ``records`` (or of ready ``values_list``) in this design: a grid, or a slider (one row
        scrolled sideways)."""
        self.ensure_one()
        settings = self._mtbg_settings(draft=draft)
        if values_list is None:
            values_list = [self._mtbg_card_values(self.source, record) for record in records or []]
        cards = [self._mtbg_card_context(values, settings) for values in values_list]
        return self.env['ir.qweb']._render('mtbg_website_cards.cards', {
            'design': self, 'settings': settings, 'cards': cards, 'columns': columns,
            'layout': 'slider' if layout == 'slider' else 'grid',
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
        _ = self.env._
        sources = self._mtbg_card_sources()
        design = self.browse(int(design_id or 0)).exists() or self.search([], limit=1)
        if design and design.sudo().draft:
            design.sudo().draft = False  # the designer opens on the saved design: its preview too
        return {
            'designs': [{'id': d.id, 'name': d.name, 'source': d.source, 'is_default': d.is_default}
                        for d in self.search([])],
            'sources': [{'key': key, 'name': spec['name']} for key, spec in sources.items()],
            'design': design and dict(design._mtbg_settings(), id=design.id, name=design.name, source=design.source,
                                      is_default=design.is_default),
            'fields': list(self._mtbg_source_fields(design.source).values()) if design else [],
            'regions': [{'key': 'header', 'label': _("Header"), 'help': _("Above the card")},
                        {'key': 'top', 'label': _("Top strip"), 'help': _("On the photo, at its top")},
                        {'key': 'center', 'label': _("Center"), 'help': _("On the photo, in its middle")},
                        {'key': 'bottom', 'label': _("Bottom strip"), 'help': _("On the photo, at its bottom")},
                        {'key': 'below', 'label': _("Below"), 'help': _("Under the photo")},
                        {'key': 'footer', 'label': _("Footer line"), 'help': _("Below's last line, side by side")}],
            'looks': [{'key': 'plain', 'label': _("Plain")}, {'key': 'pill', 'label': _("Pill")},
                      {'key': 'button', 'label': _("Button")}, {'key': 'bar', 'label': _("Bar")}],
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
