"""Card designs: how the website draws the cards of a source's records (Card Designer, the Cards building block).

A module gives its sources through the card sources protocol (override on mtbg.website.card.design, call super()):
    _mtbg_card_sources()                    {key: {name, fields: [{key, label, kind, icon}],
                                                   filters: [{key, label, options: [{key, label}]}]}}
    _mtbg_card_records(source, filters, limit)   the records a block shows (filters: {key: option key})
    _mtbg_card_values(source, record)            {'url', 'image', field key: value, ...} of one record
    _mtbg_card_samples(source)                   a few records for the designer's preview
Field kinds: title (the theme's heading), text, badge, price, meta (an icon and a short text; the value's 'icon'
replaces the field's), rating (stars), icons (a row of icons per rating: [{'icon', 'value', 'of', 'tip'}], each
rating's meaning shown on hover), countdown (a booking countdown: {'deadline': ISO datetime, 'label'}), button (a
link to the record), compare (a "Compare" box: the value is the record's id), avatar (a round photo, else the name's
initial: {'image', 'text'}), photos (a strip of photos opening in a lightbox: [{'thumb', 'full', 'alt'}]), logo (an
icon only: {'icon', 'tip'}). A text value may carry another text ({'text', 'alt', 'alt_label', 'label'}: e.g. a
review's original language, a link toggles them). Every source also has the Book button (field ``book``).

A design's frame: a card (its background, border and shadow), none (the photo and the words alone, e.g. a mega
menu's row of photos), or a speech bubble (the photo's regions and "below" in a bubble with its tail at the bottom
left, the footer under it: e.g. a review and its author). Its words left aligned or centred; its photo's size (the
source picks the image at that size).

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

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.tools import html2plaintext

STYLES = [('below', 'Text below the photo'), ('overlay', 'Text over the photo'), ('above', 'Text above the photo')]
RATIOS = [('3-2', '3:2'), ('4-3', '4:3'), ('16-9', '16:9'), ('1-1', 'Square')]
FRAMES = [('card', 'Card'), ('none', 'No frame'), ('bubble', 'Speech bubble')]
ALIGNS = [('start', 'Left'), ('center', 'Centred')]
IMAGE_SIZES = [('512x288', 'Small (512 x 288)'), ('600x400', 'Medium (600 x 400)'), ('900x600', 'Large (900 x 600)'),
               ('none', 'No photo')]
TITLE_TAGS = ('h3', 'h4', 'h5')                  # (empty: h3)
WEIGHTS = ('bold', 'normal')                     # (empty: the theme's)
CASES = ('upper', 'lower', 'capitalize')         # (empty: as written)
CORNERS = [('none', 'Square'), ('small', 'Rounded'), ('large', 'Very rounded')]
REGIONS = ('header', 'banners', 'top', 'center', 'bottom', 'below', 'footer')  # banners: over the card's top
PHOTO_REGIONS = ('top', 'center', 'bottom')
LOOKS = ('plain', 'pill', 'button', 'bar', 'inline', 'strong', 'corner', 'banner', 'badge')  # inline: plain, on one line with the next inline ones; strong: bold
# banners (owner, 2026-10-30: "corner banner, top banner, badge banner"): wherever placed, drawn over the card's top: a
# ribbon across its top right corner, a band across its top, a tag in its top left corner
BANNERS = ('corner', 'banner', 'badge')
# each banner's styles (the first: as it was), its side, its own colours (owner, 2026-10-30: "corner badge needs to
# have many options for style")
BANNER_STYLES = {
    'corner': ('ribbon', 'triangle', 'tab', 'circle', 'ribbon3d', 'fold3d', 'fold45'),
    'banner': ('solid', 'shade', 'bevel3d', 'wrap3d', 'wrapband'),
    'badge': ('flag', 'pill', 'square', 'rounded', 'tag', 'circle', 'bevel3d', 'seal3d', 'wrap3d', 'bookmark',
              'bookmarkpoint', 'sidetag', 'sidepoint'),
}
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
    frame = fields.Selection(FRAMES, required=True, default='card')
    align = fields.Selection(ALIGNS, string='Words', required=True, default='start')
    image_size = fields.Selection(IMAGE_SIZES, string='Photo size', required=True, default='900x600',
                                  help="The size of the photo the source gives (smaller: a faster page)")
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
        # (the Book button's words: the website's card settings, Website Blocks › Card Settings)
        book = self.env['mtbg.website.card.settings']._mtbg_get()
        out.setdefault(BOOK, {'key': BOOK, 'label': self.env._("Book button"), 'kind': 'button',
                              'icon': '', 'text': book.book_text or self.env._("Book")})
        return out

    # ------------------------------------------------------------------ settings
    def _mtbg_settings(self, draft=False):
        """The design's settings as the designer and the renderer read them (its draft with ``draft``)."""
        self.ensure_one()
        saved = {'ratio': self.ratio, 'corners': self.corners, 'shadow': self.shadow,
                 'hover_zoom': self.hover_zoom, 'hover_darken': self.hover_darken, 'frame': self.frame,
                 'align': self.align, 'image_size': self.image_size, 'look': self.look or {}}
        if draft and isinstance(self.sudo().draft, dict):
            saved = dict(saved, **self._mtbg_clean(self.sudo().draft))
        saved['look'] = self._mtbg_clean_look(saved.get('look'), style=self.style)
        return saved

    def _mtbg_clean_item(self, item, region, fields_by_key):
        if not isinstance(item, dict) or item.get('field') not in fields_by_key:
            return None
        field = fields_by_key[item['field']]
        look = item.get('look') if item.get('look') in LOOKS else ('button' if field.get('kind') == 'button' else 'plain')
        # the banners' own section (owner, 2026-10-30: "banner should have its own section inside the main card"):
        # there, a banner look only; elsewhere, none
        if region == 'banners' and look not in BANNERS:
            look = 'corner'
        elif region != 'banners' and look in BANNERS:
            look = 'plain'
        icon = item.get('icon', field.get('icon') or '')
        return {
            'uid': str(item.get('uid') or new_uid())[:16],
            'field': item['field'],
            'look': look,
            'show': item.get('show') if region in PHOTO_REGIONS and item.get('show') in SHOWS else '',
            'text': str(item.get('text') or '')[:120],
            'icon': icon if isinstance(icon, str) and (icon == '' or ICON.match(icon)) else '',
            # a text cut after so many lines (0: whole), with "Read more" to open it in place
            'lines': max(0, min(int(item.get('lines') or 0), 20)) if str(item.get('lines') or 0).isdigit() else 0,
            'more': bool(item.get('more')),
            # icons (e.g. the ratings): their size and spacing in % of the text (0: as designed), moved up / down in px
            # (owner, 2026-10-30: "their own size, spacing v-height adjustments")
            'size': max(0, min(int(item.get('size') or 0), 300)) if str(item.get('size') or 0).lstrip('-').isdigit() else 0,
            'gap': max(0, min(int(item.get('gap') or 0), 200)) if str(item.get('gap') or 0).lstrip('-').isdigit() else 0,
            'lift': max(-20, min(int(item.get('lift') or 0), 20)) if str(item.get('lift') or 0).lstrip('-').isdigit() else 0,
            # a text at most so many words, then "…" (0: all; owner, 2026-10-30)
            'words': max(0, min(int(item.get('words') or 0), 200)) if str(item.get('words') or 0).isdigit() else 0,
            # the name (a title): its heading level (for search engines: its size is the Text size); any field's
            # words: bold and capitals (owner, 2026-10-30: "h3-h5 option for tour name ... bold upper cases lowercase
            # settings"; "H is just for style once we have size setting")
            # icon rows (the ratings): each row's name before its icons (owner, 2026-10-30: "optional label")
            'labels': bool(item.get('labels')),
            # banners: their style, side (left / right) and own colours (empty: the design's accent)
            'bstyle': item.get('bstyle') if item.get('bstyle') in BANNER_STYLES.get(look, ()) else '',
            'bside': item.get('bside') if item.get('bside') in ('left', 'right') else '',
            'bbg': item.get('bbg') if isinstance(item.get('bbg'), str) and COLOR.match(item['bbg']) else '',
            'btext': item.get('btext') if isinstance(item.get('btext'), str) and COLOR.match(item['btext']) else '',
            # every field: its text size in % of the design's own (0: as designed; owner, 2026-10-30: "every text on
            # the editor should have text size setting")
            'fsize': max(0, min(int(item.get('fsize') or 0), 300)) if str(item.get('fsize') or 0).isdigit() else 0,
            'tag': item.get('tag') if item.get('tag') in TITLE_TAGS else '',
            'weight': item.get('weight') if item.get('weight') in WEIGHTS else '',
            'case': item.get('case') if item.get('case') in CASES else '',
            # its line height in % (0: as designed; owner, 2026-10-30: "need line height for text")
            'lh': max(0, min(int(item.get('lh') or 0), 300)) if str(item.get('lh') or 0).isdigit() else 0,
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
        # (banners placed in another section, before the banners had their own: moved into it)
        moved = [item for key in REGIONS if key != 'banners' and isinstance(raw.get(key), dict)
                 for item in raw[key].get('items') or [] if isinstance(item, dict) and item.get('look') in BANNERS]
        for key in REGIONS:
            spec = raw.get(key) if isinstance(raw.get(key), dict) else {}
            items = []
            listed = [i for i in spec.get('items') or [] if not (key != 'banners' and isinstance(i, dict) and i.get('look') in BANNERS)]
            if key == 'banners':
                listed += moved
            for item in listed:
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
        for key, choices in (('ratio', RATIOS), ('corners', CORNERS), ('frame', FRAMES), ('align', ALIGNS),
                             ('image_size', IMAGE_SIZES)):
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

    @staticmethod
    def _mtbg_cut_words(segments, limit):
        """The words of ``segments`` (texts and values, their formatting dropped) cut at ``limit`` words, "…"
        added when cut."""
        text = ' '.join(
            html2plaintext(str(part)) if isinstance(part, Markup) else str(part)
            for seg in segments for part in [seg.get('text') if 'text' in seg else (seg.get('value') or {}).get('text') or '']
        )
        words = text.split()
        if len(words) <= limit:
            return [{'text': ' '.join(words)}]
        return [{'text': ' '.join(words[:limit]).rstrip(',.;:') + '…'}]

    def _mtbg_card_context(self, raw_values, settings):
        """What the card template needs for one record: each region's items with their values (an item whose value
        is empty is left out; a button always shows, it links to the record)."""
        fields_by_key = self._mtbg_source_fields(self.source)
        book_icon = self.env['mtbg.website.card.settings']._mtbg_get().book_icon or ''
        values = {key: self._mtbg_value(value) for key, value in raw_values.items() if key not in ('url', 'image')}
        values[BOOK] = values.get(BOOK) or {'text': fields_by_key[BOOK].get('text') or '', 'attrs': {}}
        regions = {}
        banners = []
        for key, region in settings['look']['regions'].items():
            items = []
            for item in region['items']:
                field = fields_by_key.get(item['field']) or {}
                kind = field.get('kind', 'text')
                if kind == 'button' and not item['text']:
                    segments = [{'text': field.get('text') or self.env._("Book")}]
                else:
                    segments = self._mtbg_segments(item['text'], item['field'], values)
                if item.get('words') and segments and kind in ('text', 'title', 'meta', 'badge'):
                    segments = self._mtbg_cut_words(segments, item['words'])
                value = values.get(item['field'])
                wordless = ('countdown', 'rating', 'icons', 'compare', 'avatar', 'photos', 'logo')
                if not segments and kind not in wordless:
                    continue
                if kind in wordless and not value:
                    continue
                entry = dict(item, kind=kind, value=value or {}, segments=segments,
                              show=item['show'] or region.get('show') or 'always')
                if item['field'] == BOOK and not entry['icon']:
                    entry['icon'] = book_icon  # (the website's card settings)
                if item['look'] in BANNERS:
                    banners.append(dict(entry, show='always'))
                    continue
                # inline fields side by side: one row of them (e.g. "1 day · Beginner · 25 km")
                if item['look'] == 'inline':
                    if items and items[-1].get('kind') == '_row':
                        items[-1]['items'].append(entry)
                    else:
                        items.append({'kind': '_row', 'field': '_row', 'look': 'plain', 'show': entry['show'],
                                      'uid': entry['uid'] + 'r', 'items': [entry]})
                    continue
                items.append(entry)
            regions[key] = dict(region, items=items)
        return {'url': raw_values.get('url') or '', 'image': raw_values.get('image') or '',
                'name': raw_values.get('name') or '', 'regions': regions, 'banners': banners}

    def _mtbg_style_vars(self, settings):
        """The design's colours as CSS variables: the light ones, and the dark ones (used on dark pages)."""
        out = []
        for mode, prefix in (('light', '--mtbg-card-'), ('dark', '--mtbg-card-dark-')):
            for key, value in (settings['look'].get(mode) or {}).items():
                out.append(f"{prefix}{key.replace('_', '-')}: {value}")
        return '; '.join(out)

    def mtbg_render(self, records=None, values_list=None, draft=False, columns=3, layout='grid', use=None):
        """The cards (HTML) of ``records`` (or of ready ``values_list``) in this design: a grid, a slider (the one
        slider), a masonry wall or one under another; ``use`` (a card use) gives the columns and the slider's
        options, else ``columns`` (2 on tablets, 1 on phones)."""
        self.ensure_one()
        settings = self._mtbg_settings(draft=draft)
        if values_list is None:
            Design = self.with_context(mtbg_card_image_size=settings['image_size'])
            values_list = [Design._mtbg_card_values(self.source, record) for record in records or []]
        cards = [self._mtbg_card_context(values, settings) for values in values_list]
        layout = layout if layout in ('grid', 'slider', 'masonry', 'stack') else 'grid'
        if use:
            layout_values = use._mtbg_layout_values(layout)
        else:
            per = {'lg': str(columns or 3), 'md': '2', 'sm': '1.22' if layout == 'slider' else '1'}
            layout_values = {'per': per, 'gap': '1.5rem', 'use_class': '', 'slider_per': per, 'slider_gap': '1.5rem',
                             'slider_class': ''}
        book = self.env['mtbg.website.card.settings']._mtbg_get()._mtbg_book()
        style_vars = '; '.join(v for v in (self._mtbg_style_vars(settings), book['style']) if v)
        return self.env['ir.qweb']._render('mtbg_website_cards.cards', dict(
            layout_values, design=self, settings=settings, cards=cards, columns=columns, layout=layout,
            style_vars=style_vars, book=book,
            # a page's first cards (context ``mtbg_cards_eager``: the catalog; never the menus, hidden until opened):
            # the first row's photos load at once, the first one first (speed work phase 4)
            eager=bool(self.env.context.get('mtbg_cards_eager'))))

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
                        {'key': 'banners', 'label': _("Ribbons"), 'help': _("Over the card's corner or top")},
                        {'key': 'top', 'label': _("Top strip"), 'help': _("On the photo, at its top")},
                        {'key': 'center', 'label': _("Center"), 'help': _("On the photo, in its middle")},
                        {'key': 'bottom', 'label': _("Bottom strip"), 'help': _("On the photo, at its bottom")},
                        {'key': 'below', 'label': _("Below"), 'help': _("Under the photo")},
                        {'key': 'footer', 'label': _("Footer line"), 'help': _("Below's last line, side by side")}],
            'looks': [{'key': 'plain', 'label': _("Plain")}, {'key': 'pill', 'label': _("Pill")},
                      {'key': 'button', 'label': _("Button")}, {'key': 'bar', 'label': _("Bar")},
                      {'key': 'inline', 'label': _("Same line")}, {'key': 'strong', 'label': _("Bold")},
                      {'key': 'corner', 'label': _("Corner ribbon")}, {'key': 'banner', 'label': _("Top ribbon")},
                      {'key': 'badge', 'label': _("Badge ribbon")}],
            'banner_styles': {
                'corner': [{'key': 'ribbon', 'label': _("Diagonal ribbon")}, {'key': 'triangle', 'label': _("Triangle")},
                           {'key': 'tab', 'label': _("Tab")}, {'key': 'circle', 'label': _("Circle")},
                           {'key': 'ribbon3d', 'label': _("3D ribbon")},
                           {'key': 'fold3d', 'label': _("3D ribbon folded round the corner")},
                           {'key': 'fold45', 'label': _("Ribbon across the corner, ends folded")}],
                'banner': [{'key': 'solid', 'label': _("Solid band")}, {'key': 'shade', 'label': _("See-through band")},
                           {'key': 'bevel3d', 'label': _("3D raised band")},
                           {'key': 'wrap3d', 'label': _("3D band folded round the sides")},
                           {'key': 'wrapband', 'label': _("Band wrapped round the sides, notched ends")}],
                'badge': [{'key': 'flag', 'label': _("Flag")}, {'key': 'pill', 'label': _("Pill")},
                          {'key': 'square', 'label': _("Square")}, {'key': 'rounded', 'label': _("Rounded")},
                          {'key': 'tag', 'label': _("Tag (from the edge)")}, {'key': 'circle', 'label': _("Circle")},
                          {'key': 'bevel3d', 'label': _("3D raised badge")}, {'key': 'seal3d', 'label': _("3D seal")},
                          {'key': 'wrap3d', 'label': _("3D tag folded round the edge")},
                          {'key': 'bookmark', 'label': _("Bookmark from the top, notched")},
                          {'key': 'bookmarkpoint', 'label': _("Bookmark from the top, pointed")},
                          {'key': 'sidetag', 'label': _("Ribbon from the side, notched")},
                          {'key': 'sidepoint', 'label': _("Ribbon from the side, pointed")}],
            },
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
