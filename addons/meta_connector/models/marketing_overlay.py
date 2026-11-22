"""The marketing engine (owner, 2026-11-22: "the marketing template preview should be GLOBAL marketing extension I
don't want to have to code everything twice for two websites"): the story and post templates every marketing app
draws its pictures with, their editor with a live preview, sticker overlays, fonts. Moved here from Tours Marketing
(the same models, tables and ids); the apps plug in as sources.

A template (an "overlay") is one shape (vertical 9:16 for stories, square 1:1 for posts), a photo (cropped to fill, or
whole on a background colour), an optional gradient, layers in order and a QR code:

* text: its English and Spanish text with {placeholders}, font (Odoo's or uploaded: ``mtbg.marketing.font``), size,
  colour, capitals, alignment, anchor, max width with wrapping and shrinking to fit, shadow, outline, background box;
* sticker: a text on a coloured badge, turned a few degrees ("NUEVO INGRESO", "GANGA", "LAST ONE AVAILABLE");
* logo: its own picture, the company's logo or the website's logo.

Any layer may show only when the record has a flag (``show_if``: a new product, a bargain, the last one...).

A source (an app: Tours Marketing, Bike Shop Marketing) registers itself by overriding:

* ``_mtbg_overlay_sources()``: {code: {'label', 'placeholders': [(name, help)], 'flags': [(name, label)]}};
  its code is also added to ``source`` (``selection_add``);
* ``_mtbg_source_values(record, lang, website=None, **options)``: the values of one of its records (texts, and
  booleans for its flags);
* ``_mtbg_source_photo(record, **options)``: (photo bytes or None, vertical: True when the photo is made for the
  shape) of a record;
* ``_mtbg_preview_values(lang)`` / ``_mtbg_preview_photo()``: the editor's preview (its own preview record, or
  sample values).

Every source gets the website's values: {website_name}, {website_domain} ("example.com"), {website_url}; a template
of a website (``website_id``) draws with that website's logo and address, one without with the website it is drawn
for. ``_mtbg_render_record`` draws a record; the preview route (controllers) draws one for a queue's card."""
import base64
import io
import re
from PIL import Image

from odoo import api, fields, models

from . import overlay_render

SHAPES = [('vertical', 'Vertical (9:16)'), ('square', 'Square (1:1)')]
ALIGN = [('left', 'Left'), ('center', 'Centre'), ('right', 'Right')]
VALIGN = [('top', 'Top'), ('middle', 'Middle'), ('bottom', 'Bottom')]
# every source's values: the website's
WEBSITE_PLACEHOLDERS = [
    ('website_name', "The website's name"),
    ('website_domain', "The website's address as people type it: \"example.com\""),
    ('website_url', "The website's address in full: \"https://www.example.com\""),
]


def _font_selection(_model):
    return overlay_render.shipped_fonts()


def sample_photo(shape):
    """A neutral sample photo (a dusk gradient) when there is no photo of the shape anywhere yet."""
    width, height = overlay_render.SIZES[shape]
    top, bottom = (58, 92, 120), (196, 132, 76)
    ramp = Image.linear_gradient('L').resize((width, height))
    image = Image.composite(Image.new('RGB', (width, height), bottom), Image.new('RGB', (width, height), top), ramp)
    out = io.BytesIO()
    image.save(out, format='JPEG', quality=85)
    return out.getvalue()


class MtbgMarketingFont(models.Model):
    """An uploaded font (TTF / OTF) for the templates, beside the fonts Odoo ships."""
    _name = 'mtbg.marketing.font'
    _description = 'Overlay font'
    _order = 'name'

    name = fields.Char(required=True)
    data = fields.Binary(string='Font File', attachment=True, required=True)
    filename = fields.Char()

    def _mtbg_bytes(self):
        self.ensure_one()
        data = self.sudo().with_context(bin_size=False).data
        return base64.b64decode(data) if data else None


class MtbgMarketingOverlay(models.Model):
    _name = 'mtbg.marketing.overlay'
    _description = 'Marketing overlay template'
    _order = 'shape, sequence, id'

    name = fields.Char(required=True)
    shape = fields.Selection(SHAPES, required=True, default='vertical',
                             help="Vertical: 1080 x 1920 (stories). Square: 1080 x 1080 (posts).")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    # who supplies the values (an app adds itself: selection_add); its placeholders and flags in the editor
    source = fields.Selection([('any', 'Any')], string='Used By', default='any', required=True,
                              help="The app whose records this template draws: its placeholders and stickers.")
    website_id = fields.Many2one('website', string='Website', ondelete='cascade', index=True,
                                 help="Its website's logo and address. Empty: the website it is drawn for.")
    layer_ids = fields.One2many('mtbg.marketing.overlay.layer', 'overlay_id', string='Layers', copy=True)
    # the photo: it fills the picture (cut to fit), or shows whole in a box on a background colour (a product's
    # square picture on a story), or "auto": fills when the photo is made for the shape, else whole
    fit = fields.Selection([('cover', 'Fill (cut to fit)'), ('contain', 'Whole, on the background'),
                            ('auto', 'Fill when made for the shape, else whole')], default='cover', required=True,
                           string='Photo')
    background_color = fields.Char(string='Background', default='#222222',
                                   help="Around a photo shown whole, and without a photo.")
    contain_top = fields.Float(string='Photo Box Top (%)', default=0.0)
    contain_bottom = fields.Float(string='Photo Box Bottom (%)', default=100.0)
    contain_margin = fields.Float(string='Photo Box Side Margin (%)', default=0.0)
    # the scrim: a gradient from the edge so the text reads on any photo
    scrim = fields.Selection([('none', 'None'), ('top', 'From the top'), ('bottom', 'From the bottom'),
                              ('both', 'Top and bottom')], default='bottom', required=True, string='Gradient')
    scrim_color = fields.Char(string='Gradient Colour', default='#000000')
    scrim_opacity = fields.Float(string='Gradient Opacity', default=0.75, help="At the edge, 0 to 1.")
    scrim_height = fields.Integer(string='Gradient Height (%)', default=50)
    # the preview: a photo (empty: the source's, else a sample), a language, a headline
    sample_image = fields.Image(string='Preview Photo', max_width=2160, max_height=3840)
    preview_lang = fields.Selection([('en', 'English'), ('es', 'Spanish')], default='en', string='Preview In')
    preview_headline = fields.Char(default='NEW CONFIRMED GROUP DEPARTURE {date_long}!',
                                   help="The preview's {headline} (a hype rule gives its own).")
    preview_website_id = fields.Many2one('website', string='Preview For',
                                         help="The website whose logo and address the preview shows (empty: this "
                                              "template's website, else the current one).")
    # the QR code of a link (Meta's API cannot add a link sticker to a story): on for a story by default
    qr_enabled = fields.Boolean(string='QR Code', help="The short link as a QR code (black on white, scans on any "
                                                        "photo).")
    qr_size = fields.Float(string='QR Size (%)', default=20.0, help="Its side, a share of the short edge, its white "
                                                                    "quiet zone included.")
    qr_anchor = fields.Selection(overlay_render.ANCHORS, string='QR Position', default='bottom', required=True)
    qr_offset_x = fields.Float(string='QR Offset X (%)', default=4.0)
    qr_offset_y = fields.Float(string='QR Offset Y (%)', default=9.0)
    qr_quiet = fields.Integer(string='QR Quiet Zone', default=3, help="White modules round the code (3-4 scan best).")
    preview_image = fields.Binary(compute='_compute_preview_image', string='Preview')
    placeholders_help = fields.Html(compute='_compute_placeholders_help', sanitize=False)

    # ------------------------------------------------------------------ the registry
    @api.model
    def _mtbg_overlay_sources(self):
        """{code: {'label', 'placeholders': [(name, help)], 'flags': [(name, label)]}}: the apps drawing with these
        templates (each adds itself)."""
        return {'any': {'label': self.env._('Any'), 'placeholders': [], 'flags': []}}

    @api.model
    def _mtbg_flag_selection(self):
        """Every flag a layer may wait for, of every source."""
        seen, out = set(), []
        for source in self._mtbg_overlay_sources().values():
            for name, label in source.get('flags') or []:
                if name not in seen:
                    seen.add(name)
                    out.append((name, label))
        return out

    def _mtbg_source(self):
        self.ensure_one()
        sources = self._mtbg_overlay_sources()
        return sources.get(self.source) or sources['any']

    def _mtbg_placeholders(self):
        """[(name, help)]: what this template's texts may hold (its source's, then the website's)."""
        self.ensure_one()
        return list(self._mtbg_source().get('placeholders') or []) + [
            (name, self.env._(label)) for name, label in WEBSITE_PLACEHOLDERS]

    @api.model
    def _mtbg_source_values(self, record, lang, website=None, **options):
        """The values of ``record`` for this template's texts and flags (a source fills them)."""
        return {}

    @api.model
    def _mtbg_source_photo(self, record, **options):
        """(photo bytes or None, made for the shape) of ``record`` (a source gives it)."""
        return None, True

    # ------------------------------------------------------------------ the website
    def _mtbg_website(self, website=None):
        """The website a drawing is for: this template's, else the one given, else the current one."""
        if self and self.website_id:
            return self.website_id
        if website:
            return website
        Website = self.env['website']
        return Website.get_current_website() if hasattr(Website, 'get_current_website') else Website.browse()

    def _mtbg_website_values(self, website=None):
        """{website_name, website_domain, website_url} of the website drawn for ('' without one)."""
        website = self._mtbg_website(website)
        if not website:
            return {'website_name': '', 'website_domain': '', 'website_url': ''}
        website = website.sudo()
        url = website.domain or website.get_base_url() or ''
        if url and '//' not in url:
            url = 'https://' + url
        return {'website_name': website.name or '', 'website_domain': overlay_render.domain_text(url),
                'website_url': url.rstrip('/'), '_website_id': website.id}

    # ------------------------------------------------------------------ values and drawing
    def _mtbg_values_for(self, record, lang, website=None, **options):
        """The values a drawing of ``record`` fills: the website's, then its source's."""
        self.ensure_one()
        values = self._mtbg_website_values(website)
        values.update(self._mtbg_source_values(record, lang, website=self._mtbg_website(website), **options) or {})
        return values

    def _mtbg_render_record(self, record, lang, website=None, fmt='JPEG', preview_width=None, photo=None,
                            **options):
        """``record`` drawn with this template (its values, its photo): image bytes."""
        self.ensure_one()
        values = self._mtbg_values_for(record, lang, website=website, **options)
        vertical = True
        if photo is None:
            photo, vertical = self._mtbg_source_photo(record, **options)
        values.setdefault('vertical', bool(vertical))
        values.setdefault('no_vertical', not vertical)
        return self._mtbg_render(photo, values, lang, fmt=fmt, preview_width=preview_width)

    def _compute_placeholders_help(self):
        from markupsafe import Markup
        for overlay in self:
            overlay.placeholders_help = Markup('<ul class="mb-0 small">%s</ul>') % Markup('').join(
                Markup('<li><code>{%s}</code>: %s</li>') % (name, self.env._(label))
                for name, label in overlay._mtbg_placeholders())

    def _mtbg_preview_values(self, lang):
        """The editor's values: the website's (a source adds its own record's, or sample values)."""
        self.ensure_one()
        return self._mtbg_website_values(self.preview_website_id or None)

    def _mtbg_preview_photo(self):
        """The editor's photo: its own preview photo, else a sample (a source gives one of its own)."""
        self.ensure_one()
        own = self.with_context(bin_size=False).sample_image
        if own:
            return base64.b64decode(own)
        return sample_photo(self.shape)

    @api.depends('shape', 'scrim', 'scrim_color', 'scrim_opacity', 'scrim_height', 'sample_image', 'source',
                 'website_id', 'fit', 'background_color', 'contain_top', 'contain_bottom', 'contain_margin',
                 'preview_lang', 'preview_headline', 'preview_website_id',
                 'layer_ids', 'layer_ids.sequence', 'layer_ids.active', 'layer_ids.kind', 'layer_ids.text_en',
                 'layer_ids.text_es', 'layer_ids.font', 'layer_ids.font_id', 'layer_ids.size', 'layer_ids.min_size',
                 'layer_ids.color', 'layer_ids.uppercase', 'layer_ids.align', 'layer_ids.valign', 'layer_ids.x',
                 'layer_ids.y', 'layer_ids.max_width', 'layer_ids.max_lines', 'layer_ids.line_height',
                 'layer_ids.shadow', 'layer_ids.shadow_color', 'layer_ids.outline', 'layer_ids.outline_color',
                 'layer_ids.box', 'layer_ids.box_color', 'layer_ids.box_opacity', 'layer_ids.box_padding',
                 'layer_ids.box_radius', 'layer_ids.box_border', 'layer_ids.box_border_color', 'layer_ids.rotate',
                 'layer_ids.show_if', 'layer_ids.logo', 'layer_ids.logo_source', 'layer_ids.logo_size',
                 'layer_ids.opacity', 'qr_enabled', 'qr_size', 'qr_anchor', 'qr_offset_x', 'qr_offset_y', 'qr_quiet')
    def _compute_preview_image(self):
        """The template drawn at full size on the preview photo, made 360 px wide (PNG)."""
        for overlay in self:
            lang = overlay.preview_lang or 'en'
            values = dict(overlay._mtbg_preview_values(lang), headline=overlay.preview_headline or '')
            photo = overlay._mtbg_preview_photo()
            try:
                png = overlay._mtbg_render(photo, values, lang, fmt='PNG', preview_width=360)
            except Exception:  # noqa: BLE001 - a half-typed layer never breaks the form
                png = False
            overlay.preview_image = base64.b64encode(png) if png else False

    def _mtbg_logo(self, layer, values):
        """A logo layer's picture: its own, else the website's (logo from the website) or the company's."""
        own = layer.with_context(bin_size=False).logo
        if own:
            return base64.b64decode(own)
        if layer.logo_source == 'website':
            website = self.env['website'].sudo().browse(values.get('_website_id') or []).exists() \
                or self._mtbg_website()
            logo = website and website.sudo().with_context(bin_size=False).logo
            if logo:
                return base64.b64decode(logo)
        logo = self.env.company.with_context(bin_size=False).logo
        return base64.b64decode(logo) if logo else None

    def _mtbg_layers(self, values, lang):
        """The layers ready to draw: texts filled in ``lang`` (Spanish empty: the English), fonts and logos as
        bytes; a layer waiting for a flag the values do not have is left out."""
        self.ensure_one()
        spanish = (lang or 'en').startswith('es')
        values = dict(values)
        upper_values = dict(values)
        # {headline} is itself a text with placeholders
        headline = values.get('headline') or ''
        values['headline'] = overlay_render.fill(headline, values)
        upper_values['headline'] = overlay_render.fill(headline, values, upper=True)
        layers = []
        for layer in self.layer_ids.filtered('active').sorted(lambda l: (l.sequence, l.id)):
            if layer.show_if and not values.get(layer.show_if):
                continue
            if layer.kind == 'logo':
                layers.append({'kind': 'logo', 'image': self._mtbg_logo(layer, values),
                               'size': layer.logo_size, 'x': layer.x, 'y': layer.y, 'align': layer.align,
                               'valign': layer.valign, 'opacity': layer.opacity})
                continue
            raw = (layer.text_es if spanish and layer.text_es else layer.text_en) or ''
            if layer.uppercase:
                # {headline} already filled: its capitals keep the ordinal small ("OCTOBER 2nd")
                text = overlay_render.fill(raw.replace('{headline}', '\x00'), values, upper=True).replace(
                    '\x00', upper_values['headline'])
            else:
                text = overlay_render.fill(raw, values)
            # an empty value between separators ("Nov 20 ·  · From USD 300"): one separator, none at the ends
            text = re.sub(r'[ \t]*·(?:[ \t]*·)+[ \t]*', ' · ', text)
            text = '\n'.join(re.sub(r'^[ \t]*·[ \t]*|[ \t]*·[ \t]*$', '', line) for line in text.split('\n'))
            sticker = layer.kind == 'sticker'
            layers.append({
                'kind': 'text', 'text': text,
                'font': layer.font_id._mtbg_bytes() if layer.font_id else layer.font,
                'size': layer.size, 'min_size': layer.min_size, 'color': layer.color, 'align': layer.align,
                'valign': layer.valign, 'x': layer.x, 'y': layer.y, 'max_width': layer.max_width,
                'max_lines': layer.max_lines, 'line_height': layer.line_height, 'shadow': layer.shadow,
                'shadow_color': layer.shadow_color, 'outline': layer.outline, 'outline_color': layer.outline_color,
                'box': layer.box or sticker, 'box_color': layer.box_color, 'box_opacity': layer.box_opacity,
                'box_padding': layer.box_padding, 'box_radius': layer.box_radius,
                'box_border': layer.box_border, 'box_border_color': layer.box_border_color,
                'rotate': layer.rotate,
            })
        if self.qr_enabled and values.get('short_url'):
            layers.append({'kind': 'qr', 'data': values['short_url'], 'size': self.qr_size, 'anchor': self.qr_anchor,
                           'offset_x': self.qr_offset_x, 'offset_y': self.qr_offset_y, 'quiet': self.qr_quiet})
        return layers

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'qr_enabled' not in vals:  # on for a story, off for a square post
                vals['qr_enabled'] = (vals.get('shape') or 'vertical') == 'vertical'
        return super().create(vals_list)

    def _mtbg_fit(self, values):
        """How the photo goes: the template's; "auto": it fills when made for the shape (``values['vertical']``)."""
        self.ensure_one()
        if self.fit == 'auto':
            return 'cover' if values.get('vertical', True) else 'contain'
        return self.fit or 'cover'

    def _mtbg_render(self, photo, values, lang, fmt='JPEG', preview_width=None):
        """The template on ``photo`` (bytes) with ``values``, in ``lang``: image bytes."""
        self.ensure_one()
        margin = self.contain_margin or 0.0
        return overlay_render.render(
            photo, self.shape, self._mtbg_layers(values, lang),
            scrim={'where': self.scrim, 'color': self.scrim_color, 'opacity': self.scrim_opacity,
                   'height': self.scrim_height}, fmt=fmt, preview_width=preview_width,
            fit=self._mtbg_fit(values), background=self.background_color or '#222222',
            box=(margin, self.contain_top or 0.0, 100.0 - margin,
                 self.contain_bottom if self.contain_bottom else 100.0))

    def _mtbg_preview_url(self, record, **options):
        """The address of ``record`` drawn with this template, 360 px wide (a queue's card)."""
        self.ensure_one()
        from urllib.parse import urlencode
        stamp = int(self.write_date.timestamp()) if self.write_date else 0
        query = dict({k: v for k, v in options.items() if v not in (None, False, '')}, unique=stamp)
        return '/meta_connector/overlay/%s/preview/%s/%s?%s' % (self.id, record._name, record.id, urlencode(query))


class MtbgMarketingOverlayLayer(models.Model):
    _name = 'mtbg.marketing.overlay.layer'
    _description = 'Marketing overlay layer'
    _order = 'overlay_id, sequence, id'

    overlay_id = fields.Many2one('mtbg.marketing.overlay', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True, string='On')
    name = fields.Char(string='Layer', help="What it is, for you (e.g. Headline).")
    kind = fields.Selection([('text', 'Text'), ('sticker', 'Sticker'), ('logo', 'Logo')], default='text',
                            required=True,
                            help="Sticker: a text on a coloured badge (its background box always on), turned a few "
                                 "degrees.")
    show_if = fields.Selection('_selection_show_if', string='Only When',
                               help="Drawn only when the record has this (e.g. a new product, the last one). Empty: "
                                    "always.")
    text_en = fields.Text(string='Text (English)', help="{placeholders}: see the list on the right.")
    text_es = fields.Text(string='Text (Spanish)', help="Empty: the English.")
    font = fields.Selection(_font_selection, default=overlay_render.DEFAULT_FONT, string='Font')
    font_id = fields.Many2one('mtbg.marketing.font', string='Uploaded Font', help="Instead of the font above.")
    size = fields.Integer(string='Size (px)', default=96, help="At full size (the image is 1080 px wide).")
    min_size = fields.Integer(string='Smallest (px)', default=48,
                              help="Shrunk down to this to fit its max width and lines.")
    color = fields.Char(string='Colour', default='#FFFFFF')
    uppercase = fields.Boolean(string='Capitals', default=False)
    align = fields.Selection(ALIGN, default='center', required=True, string='Alignment')
    valign = fields.Selection(VALIGN, default='middle', required=True, string='Hangs From',
                              help="The anchor is the block's top, middle or bottom.")
    x = fields.Float(string='Anchor X (%)', default=50)
    y = fields.Float(string='Anchor Y (%)', default=50)
    max_width = fields.Float(string='Max Width (%)', default=88)
    max_lines = fields.Integer(string='Max Lines', default=3, help="0: as many as it needs.")
    line_height = fields.Float(default=1.05)
    rotate = fields.Float(string='Turn (°)', default=0.0, help="Counter-clockwise; a sticker: -8 or 8.")
    shadow = fields.Boolean(default=True)
    shadow_color = fields.Char(default='#000000')
    outline = fields.Integer(string='Outline (px)', default=0)
    outline_color = fields.Char(default='#000000')
    box = fields.Boolean(string='Background Box')
    box_color = fields.Char(default='#000000')
    box_opacity = fields.Float(default=0.6)
    box_padding = fields.Integer(default=24)
    box_radius = fields.Integer(default=16)
    box_border = fields.Integer(string='Box Border (px)', default=0)
    box_border_color = fields.Char(string='Box Border Colour', default='#000000')
    logo = fields.Image(max_width=1024, max_height=1024, help="Empty: the logo below.")
    logo_source = fields.Selection([('company', "The company's logo"), ('website', "The website's logo")],
                                   string='Logo From', default='company', required=True,
                                   help="When no picture of its own is uploaded.")
    logo_size = fields.Float(string='Logo Width (%)', default=28)
    opacity = fields.Float(default=1.0)
    # the template editor's layers (owner, 2026-11-21: "clicking on a template should open the template editor"):
    # the text in the language of the editor's English | Español switch (text_en / text_es)
    text = fields.Text(string='Text', compute='_compute_text', inverse='_inverse_text',
                       help="In the language of the switch above. {placeholders}: {headline}, {tour}, {date_long}...")

    @api.model
    def _selection_show_if(self):
        return self.env['mtbg.marketing.overlay']._mtbg_flag_selection()

    @api.onchange('kind')
    def _onchange_kind_sticker(self):
        """A new sticker: a red badge, white capitals, turned a little."""
        for layer in self:
            if layer.kind == 'sticker' and not layer.box:
                layer.update({'box': True, 'box_color': '#E0262B', 'box_opacity': 1.0, 'box_padding': 26,
                              'box_radius': 14, 'color': '#FFFFFF', 'uppercase': True, 'shadow': False,
                              'rotate': layer.rotate or -6.0, 'size': 72, 'min_size': 40, 'max_lines': 1})

    def _edit_short(self):
        return 'es' if (self.env.lang or 'en').startswith('es') else 'en'

    @api.depends_context('lang')
    @api.depends('text_en', 'text_es')
    def _compute_text(self):
        short = self._edit_short()
        for layer in self:
            layer.text = layer['text_%s' % short]

    def _inverse_text(self):
        name = 'text_%s' % self._edit_short()
        for layer in self:
            if layer[name] != layer.text:
                layer[name] = layer.text
