"""The Form Designer's forms: a form is a list of blocks (fields, headings, texts, inline steps and the form's own
"system" blocks), each shown and required always, never or by rules on the other answers and on the visit (a known
visitor, the page variant, the language, a tour page). The website renders a form with ``mtbg_tours_forms.form``
(form.js runs the same rules in the browser); the server checks and records it with ``mtbg_submit``.

A rule: ``{"match": "all" | "any", "conditions": [{"subject": ..., "op": ..., "value": ...}]}``; subjects are
``field:<key>`` (an answer) or a fact of the visit (``known`` / ``known_phone``: a known visitor, with a phone;
``variant``, ``lang``, ``tour``: on a tour page; a form type adds its own, ``_mtbg_visit_subjects``). form.js
``evaluate`` is this module's ``evaluate``: keep them the same.
"""
import json
import re
from datetime import date

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .contact import TERMS_PROMOTIONS, TEXTING_BOXES, _texting_opted, terms_text

# what a block is: fields ask something, the others show something
FIELD_KINDS = [
    ('text', 'Text'), ('textarea', 'Long text'), ('email', 'Email'), ('phone', 'Mobile (country code)'),
    ('number', 'Number'), ('date', 'Date'), ('select', 'Dropdown'), ('radio', 'Choice (one)'),
    ('checkboxes', 'Choices (several)'), ('checkbox', 'Checkbox'),
]
LAYOUT_KINDS = [('step', 'Step'), ('heading', 'Heading'), ('html', 'Text')]
# the form's own blocks (each form type has its own; they can move and be restyled, not deleted)
SYSTEM_KINDS = [('known', 'Known visitor greeting'), ('texting', 'SMS / WhatsApp opt-ins'), ('submit', 'Send button')]
KINDS = FIELD_KINDS + LAYOUT_KINDS + SYSTEM_KINDS
FIELDS = {kind for kind, _label in FIELD_KINDS}
MODES_SHOW = [('always', 'Always'), ('when', 'Only when'), ('unless', 'Except when')]
MODES_REQUIRE = [('never', 'Optional'), ('always', 'Required'), ('when', 'Required when'), ('unless', 'Required except when')]
KEY_RE = re.compile(r'^[a-z][a-z0-9_]{0,39}$')
# a form's look: style tokens (the designer's Style tab) and the CSS variables form.scss reads; empty: the variant's
# built-in look
STYLE_TOKENS = {
    'bg': '--mtbg-form-bg', 'text': '--mtbg-form-text', 'label': '--mtbg-form-label', 'accent': '--mtbg-form-accent',
    'accent_text': '--mtbg-form-accent-text', 'input_bg': '--mtbg-form-input-bg', 'input_text': '--mtbg-form-input-text',
    'input_border': '--mtbg-form-input-border', 'step': '--mtbg-form-step', 'radius': '--mtbg-form-radius',
    'gap': '--mtbg-form-gap', 'padding': '--mtbg-form-padding', 'font_scale': '--mtbg-form-font-scale',
}
COLOR = re.compile(r'^#[0-9a-fA-F]{6}$')
ALIGNS = ('left', 'center', 'right')
HEADER_LEVELS = ('h2', 'h3', 'h4', 'h5')
POPUP_LOOKS = ('full', 'beside')
POPUP_ANIMATIONS = ('fly', 'fade', 'zoom', 'slide', 'none')
POPUP_PAGE_KINDS = ('home', 'tours', 'rentals', 'blog', 'contact')
URL = re.compile(r'^(/|https://)[^\s"\'<>]{1,500}$')


def clean_popup(settings):
    """A popup form's settings as the designer sends them (the owner, 2026-10-26: as the newsletter popup's look,
    on the pages its rule names):
    look (full: the form over its photo / beside: the photo beside the form), images (picture URLs, one per
    opening), rotate (the next picture each time, else always the first), overlay (% of darkness over the photo),
    logo (URL, on the full look), bar (the dark bar at the bottom: its text is the form's popup_bar_text),
    bar_color, bar_text_color; pages (all / only), include and exclude ({kinds: [home, tours, rentals, blog,
    contact], words: [words of the page's address]})."""
    settings = settings if isinstance(settings, dict) else {}

    def pages(value):
        value = value if isinstance(value, dict) else {}
        words = value.get('words') or []
        if isinstance(words, str):
            words = words.split(',')
        return {'kinds': [k for k in value.get('kinds') or [] if k in POPUP_PAGE_KINDS],
                'words': [w.strip().lower() for w in words if isinstance(w, str) and w.strip()][:20]}
    return {
        'look': settings.get('look') if settings.get('look') in POPUP_LOOKS else 'beside',
        'images': [u.strip() for u in settings.get('images') or [] if isinstance(u, str) and URL.match(u.strip())][:12],
        'rotate': bool(settings.get('rotate', True)),
        'overlay': int(min(max(_number(settings.get('overlay')) or 0, 0), 90)),
        'logo': settings.get('logo').strip() if isinstance(settings.get('logo'), str) and URL.match(settings['logo'].strip()) else '',
        'bar': bool(settings.get('bar')),
        'bar_color': settings.get('bar_color') if COLOR.match(str(settings.get('bar_color') or '')) else '#111111',
        'bar_text_color': settings.get('bar_text_color') if COLOR.match(str(settings.get('bar_text_color') or '')) else '#ffffff',
        # how it opens (fly up: as since 2025), and how dark the page behind it gets (%)
        'animation': settings.get('animation') if settings.get('animation') in POPUP_ANIMATIONS else 'fly',
        'backdrop': int(min(max(80 if settings.get('backdrop') in (None, '') else (_number(settings['backdrop']) or 0), 0), 95)),
        'pages': 'only' if settings.get('pages') == 'only' else 'all',
        'include': pages(settings.get('include')),
        'exclude': pages(settings.get('exclude')),
    }


def title_look(size=0, color='', color_dark='', bold=False, upper=False, align=''):
    """A title's own look (the pre-tour header's title, a step's title): {'class', 'style', 'size'} for its element
    (classes and colour variables, form.scss .mtbg-title-look) and its words' span (font-size: size %). Nothing set:
    nothing changes (the theme's font, size, weight and colour)."""
    classes, style = ['mtbg-title-look'], []
    if color and COLOR.match(color):
        classes.append('has-title-color')
        style.append(f"--mtbg-title-color: {color}")
    if color_dark and COLOR.match(color_dark):
        classes.append('has-title-dark')
        style.append(f"--mtbg-title-color-dark: {color_dark}")
    if bold:
        classes.append('is-bold')
    if upper:
        classes.append('is-upper')
    if align in ALIGNS:
        classes.append(f'align-{align}')
    # (no size: the owner, 2026-10-27, "remove text size sliders from all forms": the theme's size)
    return {'class': ' '.join(classes), 'style': '; '.join(style) or None, 'size': None}


def clean_title_look(look):
    """A header / title look as the designer sends it: {level, size, color, color_dark, bold, upper, align}."""
    look = look if isinstance(look, dict) else {}
    return {
        'level': look.get('level') if look.get('level') in HEADER_LEVELS else '',
        'size': int(min(max(_number(look.get('size')) or 0, 0), 200)),
        'color': look.get('color') if COLOR.match(str(look.get('color') or '')) else '',
        'color_dark': look.get('color_dark') if COLOR.match(str(look.get('color_dark') or '')) else '',
        'bold': bool(look.get('bold')), 'upper': bool(look.get('upper')),
        'align': look.get('align') if look.get('align') in ALIGNS else '',
        # the header's subtitle: bold, uppercase, alignment
        'sub_bold': bool(look.get('sub_bold')), 'sub_upper': bool(look.get('sub_upper')),
        'sub_align': look.get('sub_align') if look.get('sub_align') in ALIGNS else '',
        # the tour's name and date under it: bold, uppercase, alignment
        'tour_bold': bool(look.get('tour_bold')), 'tour_upper': bool(look.get('tour_upper')),
        'tour_align': look.get('tour_align') if look.get('tour_align') in ALIGNS else '',
    }
# the backgrounds that may also be transparent (a form on a coloured place, e.g. inside the phone menu)
TRANSPARENT_TOKENS = ('bg', 'input_bg')
NUMBER_TOKENS = {'radius': 'px', 'gap': 'rem', 'padding': 'px', 'font_scale': ''}


def _style_vars(tokens):
    """["--mtbg-form-x: value", ...] of a look's tokens (bad values left out)."""
    out = []
    for token, var in STYLE_TOKENS.items():
        value = tokens.get(token)
        if value in (None, '', False):
            continue
        if token in NUMBER_TOKENS:
            number = _number(value)
            if number is None:
                continue
            out.append(f"{var}: {number / 100:g}" if token == 'font_scale' else f"{var}: {number:g}{NUMBER_TOKENS[token]}")
        elif COLOR.match(str(value)) or (token in TRANSPARENT_TOKENS and value == 'transparent'):
            out.append(f"{var}: {value}")
    return out


# the default forms' texts in Spanish (_mtbg_seed_translations)
SPANISH = {
    "Contact form": "Formulario de contacto", "Let's plan your ride": "Planifiquemos tu ruta",
    "Questions, dates, a custom trip: tell us and we'll get back to you.":
        "Preguntas, fechas, un viaje a la medida: cuéntanos y te responderemos.",
    "Questions about this tour?": "¿Preguntas sobre este tour?", "First name": "Nombre", "Name": "Nombre",
    "Menu Contact Form": "Formulario de contacto del menú", "Last name": "Apellido",
    "Mobile": "Celular", "Email": "Correo electrónico", "Your message": "Tu mensaje", "Send message": "Enviar mensaje",
    "Thanks{name}!": "¡Gracias{name}!",
    "We got your message and will reply soon, usually on WhatsApp.":
        "Recibimos tu mensaje y te responderemos pronto, normalmente por WhatsApp.",
}


def _digits(value):
    return len(re.sub(r'\D', '', str(value or '')))


def _number(value):
    try:
        return float(str(value).replace(',', '.'))
    except (TypeError, ValueError):
        return None


def _test(condition, answers, ctx):
    subject, op, expected = condition.get('subject') or '', condition.get('op') or '', condition.get('value')
    if subject.startswith('field:'):
        value = answers.get(subject[6:])
        text = ' '.join(value) if isinstance(value, list) else ('' if value in (None, False) else str(value))
        if op == 'filled':
            return bool(text.strip()) and value is not False
        if op == 'empty':
            return not text.strip() or value is False
        if op == 'checked':
            return value is True or (isinstance(value, list) and bool(value))
        if op == 'unchecked':
            return not (value is True or (isinstance(value, list) and bool(value)))
        if op in ('is', 'is_not'):
            same = (str(expected) in value) if isinstance(value, list) else text.strip().lower() == str(expected or '').strip().lower()
            return same if op == 'is' else not same
        if op == 'contains':
            return str(expected or '').lower() in text.lower()
        if op == 'min_digits':
            return _digits(text) >= int(_number(expected) or 0)
        if op in ('gte', 'lte'):
            number, limit = _number(text), _number(expected)
            if number is None or limit is None:
                return False
            return number >= limit if op == 'gte' else number <= limit
        return False
    # a fact of the visit (known, known_phone, variant, lang, tour; a form type's own: booker, rental...)
    if op in ('yes', 'no'):
        return bool(ctx.get(subject)) == (op == 'yes')
    if op in ('is', 'is_not'):
        same = str(ctx.get(subject) or '') == str(expected or '')
        return same if op == 'is' else not same
    return False


def evaluate(rule, answers, ctx):
    """Does a rule hold for these answers and this visit? An empty rule holds."""
    conditions = (rule or {}).get('conditions') or []
    if not conditions:
        return True
    results = [_test(c, answers, ctx) for c in conditions]
    return any(results) if (rule or {}).get('match') == 'any' else all(results)


def _rule(text):
    if isinstance(text, dict):
        return text
    try:
        rule = json.loads(text or '{}')
    except ValueError:
        return {}
    return rule if isinstance(rule, dict) else {}


class MtbgForm(models.Model):
    _name = 'mtbg.form'
    _description = 'Website form'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    key = fields.Char(required=True, help="What the website asks for: contact, newsletter, chat, booking")
    sequence = fields.Integer(default=10)
    handler = fields.Selection([('contact', 'Contact form')], required=True, default='contact',
                               help="What a sent form does (a contact and a CRM lead...)")
    variants = fields.Char(default='page', help="Where the form shows, comma separated (page,popup,sidebar): the "
                                                  "designer's preview and the Style tab offer each")
    block_ids = fields.One2many('mtbg.form.block', 'form_id', string='Blocks', copy=True)
    style = fields.Json(default=dict, help="{variant: {token: value}} (the designer's Style tab)")
    thanks_title = fields.Char(translate=True, default=lambda self: self.env._("Thanks{name}!"),
                               help="After sending; {name} is \", <first name>\" when we know it")
    thanks_text = fields.Char(translate=True, default=lambda self: self.env._(
        "We got your message and will reply soon, usually on WhatsApp."))
    # a form with a header of its own (the pre-tour forms): its title, subtitle and logo
    header_title = fields.Char(translate=True, help="Empty: the form's name")
    header_subtitle = fields.Char(translate=True)
    step_by_step = fields.Boolean(string='One step at a time',
                                  help="The form's steps one at a time: their progress on top, Back / Next under the form")
    header_logo = fields.Image(max_width=800, max_height=300, help="Empty: the website's logo")
    # the header's title: its level (empty: H1, as before), size, colours, bold, uppercase, alignment
    header_look = fields.Json(help="{level (h2-h5, empty: h1), size (%), color, color_dark, bold, upper, align}")
    # sending the form signs the person up for the newsletter (as the newsletter popup always did)
    newsletter = fields.Boolean(string='Signs up for the newsletter',
                                help="Sending it subscribes the person to the newsletter (tagged Newsletter)")
    # the form as a website popup (opening after 3 minutes or on leaving the page, once a visit): its look and the
    # pages it opens on (models: clean_popup); on a page, only the first matching popup (popup_sequence) opens
    popup = fields.Boolean(string='Show as a popup')
    popup_sequence = fields.Integer(string='Popup order', default=10)
    popup_settings = fields.Json(help="clean_popup(): look, images, rotate, overlay, logo, bar, bar colours, pages")
    # the lead source of the people it brings in (owner, 2026-11-08: "web form (which webform)"): "Web form: <name>",
    # made with the form and renamed with it (Core's lead source, first touch)
    lead_source_id = fields.Many2one('utm.source', string='Lead Source', copy=False, ondelete='set null',
                                     help="New contacts from this form get it as their lead source")

    @api.model_create_multi
    def create(self, vals_list):
        forms = super().create(vals_list)
        forms._mtbg_lead_source()
        return forms

    def write(self, vals):
        res = super().write(vals)
        if 'name' in vals:
            for form in self.filtered('lead_source_id'):
                name = form._mtbg_lead_source_name()
                if form.lead_source_id.name != name:
                    taken = self.env['utm.source'].sudo().search([('name', '=ilike', name)], limit=1)
                    if taken:
                        form.lead_source_id = taken
                    else:
                        form.lead_source_id.sudo().name = name
        return res

    def _mtbg_lead_source_name(self):
        self.ensure_one()
        return self.env._("Web form: %s", self.with_context(lang='en_US').name or self.key)

    def _mtbg_lead_source(self):
        """The form's lead source ("Web form: <name>"), made when missing."""
        for form in self.filtered(lambda f: not f.lead_source_id):
            form.sudo().lead_source_id = self.env['utm.source']._mtbg_forms_source(form._mtbg_lead_source_name())
        return self[:1].lead_source_id
    popup_bar_text = fields.Char(string='Popup bar text', translate=True, help="The dark bar at the bottom of the popup")

    _key_unique = models.Constraint('UNIQUE(key)', "A form with this key already exists.")

    @api.model
    def _mtbg_seed_translations(self, forms=None):
        """The default forms' Spanish, as the site had it before the designer (data hook, once at install; an update
        that brings a new default form: that form's only)."""
        if not self.env['res.lang']._lang_get('es_ES'):
            return
        forms = self.sudo().search([]) if forms is None else (
            forms if isinstance(forms, models.BaseModel) else self.sudo().browse(forms))
        for record in list(forms) + list(self.env['mtbg.form.block'].sudo().search([('form_id', 'in', forms.ids)])):
            for name in ('name', 'label', 'help', 'placeholder', 'thanks_title', 'thanks_text'):
                if name not in record._fields:
                    continue
                source = record.with_context(lang='en_US')[name]
                if source in SPANISH:
                    record.update_field_translations(name, {'es_ES': SPANISH[source]})

    def _mtbg_visit_subjects(self):
        """The facts of the visit a rule of this form can test: [{key, label, ops: 'bool' | 'variant' | 'lang',
        choices, preview}] (``preview``: a yes / no fact's value in the designer's preview, until switched)."""
        self.ensure_one()
        return [
            {'key': 'known', 'label': _("A known visitor"), 'ops': 'bool', 'preview': False},
            {'key': 'known_phone', 'label': _("A known visitor with a mobile"), 'ops': 'bool', 'preview': False},
            {'key': 'variant', 'label': _("Where the form shows"), 'ops': 'variant'},
            {'key': 'lang', 'label': _("The language"), 'ops': 'lang'},
            {'key': 'tour', 'label': _("On a tour page"), 'ops': 'bool', 'preview': False},
        ]

    def _mtbg_known_answers(self):
        """Answers of the form's own blocks a rule can test too: [{key, label, kind, choices}]."""
        return []

    def _mtbg_required_blocks(self):
        """{kind: message}: the blocks this form type cannot do without (the designer refuses to save without)."""
        return {'submit': _("The form needs its Send button.")}

    def _mtbg_has_header(self):
        """Does the form show a header of its own (title, subtitle, logo: the designer's Messages tab)?"""
        return False

    # ------------------------------------------------------------------ the form as a website popup
    def mtbg_popup(self):
        self.ensure_one()
        return clean_popup(self.popup_settings)

    @api.model
    def _mtbg_page_kinds(self, path, main_object=None):
        """What kind of page this is, for the popups' page rules: home, tours, rentals, blog, contact."""
        kinds = set()
        if path in ('', '/'):
            kinds.add('home')
        # (tour and rental pages: Booking Form adds them)
        if path.startswith('/blog'):
            kinds.add('blog')
        if path.rstrip('/') in ('/contactus', '/contact-us'):
            kinds.add('contact')
        return kinds

    @api.model
    def _mtbg_subject(self, record_id):
        """What a form on a page is about (the page's record, e.g. a tour: "Question about ..."), from the id the form
        sends (``tour_id``); None: nothing. Forms knows no such record; Tours' Booking Form gives the tour."""
        return None

    def _mtbg_popup_matches(self, path, kinds):
        settings = self.mtbg_popup()

        def hit(rule):
            return bool(set(rule['kinds']) & kinds) or any(word in path for word in rule['words'])
        if settings['pages'] == 'only' and not hit(settings['include']):
            return False
        return not hit(settings['exclude'])

    @api.model
    def mtbg_popup_for(self, path, main_object=None):
        """The popup form of this page: the first popup (in their order) whose page rule takes it, else nothing.
        ``path``: the page's address without its language."""
        path = (path or '/').lower()
        kinds = self._mtbg_page_kinds(path, main_object)
        for form in self.sudo().search([('popup', '=', True)], order='popup_sequence, id'):
            if form._mtbg_popup_matches(path, kinds):
                return form
        return self.browse()

    @api.model
    def mtbg_popup_for_request(self, main_object=None):
        """The popup form of the page being drawn (its address without the language: /es/blog is /blog)."""
        from odoo.http import request
        if not request:
            return self.browse()
        path = request.httprequest.path or '/'
        codes = set(self.env['res.lang'].sudo().search([('active', '=', True)]).mapped('url_code'))
        parts = path.split('/', 2)
        if len(parts) > 1 and parts[1] in codes:
            path = '/' + (parts[2] if len(parts) > 2 else '')
        return self.mtbg_popup_for(path, main_object)

    def mtbg_popup_images(self):
        """The popup's pictures (its own, else the contact popup's: the mtbg_tours.contact_popup_images setting)."""
        self.ensure_one()
        return self.mtbg_popup()['images'] or self.env['mtbg.form.fields'].sudo().mtbg_popup_backgrounds()

    def mtbg_header_look(self):
        """The header's title: its tag (h1 when no level is set, as before) and title_look()."""
        self.ensure_one()
        look = clean_title_look(self.header_look)
        return dict(title_look(look['size'], look['color'], look['color_dark'], look['bold'], look['upper'],
                               look['align']), tag=look['level'] or 'h1',
                    subtitle=title_look(bold=look['sub_bold'], upper=look['sub_upper'], align=look['sub_align']),
                    tour=title_look(bold=look['tour_bold'], upper=look['tour_upper'], align=look['tour_align']))

    def _mtbg_extra_texts(self):
        """More texts of this form type the designer's Messages tab edits (translatable fields of mtbg.form):
        [{name, label, help, rows}] (``rows`` > 1: a text area)."""
        return []

    @api.model
    def _mtbg_look_schemas(self):
        """{kind: schema}: the blocks with a look of their own (the designer shows their settings). A schema:
        {title, parts: [{key, label}] (each part its own look, linked by default), defaults: {part: {field: value}},
        fields: [{key, label, type: bool | select | range | color, options: [{key, label}], min, max, step, unit,
        default}]}. The look saved on the block: {linked, parts: {part: {field: value}}}."""
        return {}

    @api.model
    def _mtbg_clean_look(self, kind, look):
        """A block's look as its schema allows (anything else dropped), or False (no look of its own)."""
        schema = self._mtbg_look_schemas().get(kind)
        if not schema or not isinstance(look, dict):
            return False
        parts = {}
        for part in schema['parts']:
            values = ((look.get('parts') or {}).get(part['key'])) or {}
            clean = {}
            for field in schema['fields']:
                value = values.get(field['key']) if isinstance(values, dict) else None
                if value is None:
                    continue
                if field['type'] == 'bool':
                    clean[field['key']] = bool(value)
                elif field['type'] == 'select' and value in [o['key'] for o in field['options']]:
                    clean[field['key']] = value
                elif field['type'] == 'range' and _number(value) is not None:
                    clean[field['key']] = int(min(max(_number(value), field['min']), field['max']))
                elif field['type'] == 'color' and (value == '' or COLOR.match(str(value))):
                    clean[field['key']] = value
            parts[part['key']] = clean
        return {'linked': look.get('linked', True) is not False, 'parts': parts}

    @api.model
    def _mtbg_look_values(self, kind, look, part):
        """One part's look: the block's own values over the schema's defaults."""
        schema = self._mtbg_look_schemas().get(kind) or {}
        values = {f['key']: f.get('default') for f in schema.get('fields', ())}
        values.update((schema.get('defaults') or {}).get(part) or {})
        values.update(((look or {}).get('parts') or {}).get(part) or {})
        return values

    def _mtbg_extra_text_names(self):
        return tuple(text['name'] for text in self._mtbg_extra_texts())

    @api.model
    def _mtbg_sample_answers(self, blocks):
        """A made-up answer in every field of ``blocks`` (the designer's full preview)."""
        samples = {'name': 'Ana Torres', 'first_name': 'Ana', 'last_name': 'Torres', 'email': 'ana@example.com', 'message': _(
            "Hi! We are four friends looking for three days of singletrack in March. What would you suggest?")}
        by_kind = {'text': _("Sample answer"), 'textarea': _("A longer sample answer, as a rider would write it."),
                   'email': 'ana@example.com', 'phone': '5555 1234', 'number': '3',
                   'date': date.today().replace(day=1).isoformat(), 'checkbox': True}
        answers = {}
        for block in blocks:
            if block.kind not in FIELDS or not block.key:
                continue
            choices = block._mtbg_choices()
            if block.kind in ('select', 'radio'):
                answers[block.key] = choices[0] if choices else ''
            elif block.kind == 'checkboxes':
                answers[block.key] = choices[:2]
            else:
                answers[block.key] = samples.get(block.key, by_kind.get(block.kind, ''))
        return answers

    def mtbg_logo_url(self):
        """The header's logo inlined in the page (a small image; no request, readable by every visitor), or ''."""
        self.ensure_one()
        data = self.header_logo
        if not data:
            return ''
        data = data.decode() if isinstance(data, bytes) else data
        mime = 'image/svg+xml' if data.startswith('PHN2') else 'image/jpeg' if data.startswith('/9j/') else 'image/png'
        return f'data:{mime};base64,{data}'

    def _mtbg_has_style(self):
        """Does the Style tab apply to this form (its look follows the style tokens)?"""
        return True

    def _mtbg_designer_preview(self, view, variant):
        """The designer's preview page (template, values) for the saved form's ``view``."""
        return 'mtbg_tours_forms.form_preview', {'form_view': view, 'variant': variant}

    def _mtbg_designer_render(self, view, variant, lang):
        """The designer's live preview of ``view`` (an mtbg_view of the unsaved form)."""
        return self.env['ir.qweb'].with_context(lang=lang)._render('mtbg_tours_forms.form', {
            'form_view': view, 'variant': variant})

    @api.model
    def mtbg_get(self, key):
        return self.sudo().search([('key', '=', key)], limit=1)

    @api.model
    def mtbg_block_forms(self):
        """The forms a Form block can show (website editor): the website's, not the ones an extension shows itself
        (pre-tour forms...)."""
        own_pages = self.env['mtbg.form.designer']._mtbg_own_page_handlers()
        return [{'key': f.key, 'name': f.name} for f in self.sudo().search([('handler', 'not in', own_pages)])]

    def mtbg_style(self, variant, style=None):
        """The CSS variables of the form's look in this variant (inline style of the form): the Light look's, and the
        Dark look's (``<variant>:dark``, for dark pages: form.scss puts them over the Light ones inside
        .mtbg-theme-dark)."""
        self.ensure_one()
        style = (style if style is not None else self.style) or {}
        out = _style_vars(style.get(variant) or {})
        out += [f"{var.replace('--mtbg-form-', '--mtbg-form-dark-')}: {value}"
                for var, value in (v.split(': ', 1) for v in _style_vars(style.get(f'{variant}:dark') or {}))]
        return '; '.join(out)

    def _mtbg_style_classes(self, variant, style=None):
        """The form's classes for its look: the button's colours set (Light), and each token the Dark look sets."""
        style = (style if style is not None else self.style) or {}
        light, dark = style.get(variant) or {}, style.get(f'{variant}:dark') or {}
        classes = [f'mtbg-form--{token}' for token in ('accent', 'accent_text') if light.get(token)]
        classes += [f'mtbg-form--dark-{token}' for token in STYLE_TOKENS if dark.get(token) not in (None, '', False)]
        return ' '.join(classes)

    def mtbg_view(self, variant='page', tour=None, blocks=None, style=None, placeholder=None, known=False,
                  preview=False, answers=None, ctx=None, show_all=False, sample=False, walk=False):
        """What ``mtbg_tours_forms.form`` renders: the blocks in order (steps numbered, each block in its step's
        section), their rules as JSON for form.js, the blocks hidden / required before anything is typed (the
        rules, for this visit) and the look. ``preview``: the designer's (``known``: as for a known visitor;
        ``show_all``: the blocks their rules hide shown too, marked; ``sample``: a made-up answer in every field;
        ``walk``: one step at a time, whatever the form's setting: the full preview)."""
        self.ensure_one()
        blocks = blocks if blocks is not None else self.block_ids.filtered('active').sorted(lambda b: (b.sequence, b.id))
        ctx = dict({'variant': variant, 'lang': self.env.lang, 'tour': bool(tour), 'known': known, 'known_phone': known},
                   **(ctx or {}))
        answers = dict(self._mtbg_sample_answers(blocks), **(answers or {})) if sample else (answers or {})
        sections, current, number = [], {'step': None, 'blocks': []}, 0
        defs = []
        for index, block in enumerate(blocks):
            if block.kind == 'step':
                if current['step'] or current['blocks']:
                    sections.append(current)
                shown = block._mtbg_shown(answers, ctx) or show_all
                number += 1 if shown else 0  # the steps shown, numbered 1, 2, 3...
                current = {'step': block, 'index': index, 'number': number, 'blocks': []}
            else:
                current['blocks'].append((index, block))
            defs.append(block._mtbg_def())
        if current['step'] or current['blocks']:
            sections.append(current)
        ruled_off = {index for index, block in enumerate(blocks) if not block._mtbg_shown(answers, ctx)}
        hidden = set() if show_all else ruled_off
        required = {index for index, block in enumerate(blocks) if block._mtbg_required(answers, ctx)}
        return {
            'hidden': hidden, 'ruled_off': ruled_off if show_all else set(), 'show_all': show_all,
            'required': required, 'known': known, 'answers': answers, 'ctx': json.dumps(ctx),
            'phone_picker': self.env['res.country'].mtbg_phone_picker() if any(b.kind == 'phone' for b in blocks) else None,
            'form': self, 'variant': variant, 'tour': tour, 'sections': sections, 'placeholder': placeholder,
            'defs': json.dumps(defs), 'style': self.mtbg_style(variant, style),
            'style_classes': self._mtbg_style_classes(variant, style),
            # the promotional messaging terms by a newsletter form's texting box (the others have none)
            'texting_terms': terms_text(self.env, TERMS_PROMOTIONS) if self.newsletter else '',
            'preview': preview, 'sample': sample, 'steps': bool(walk or self.step_by_step) and not show_all,
            'thanks_title': (self.thanks_title or '').split('{name}'),
        }

    # ------------------------------------------------------------------ submit
    def _mtbg_validate(self, values, ctx):
        """{key: clean value} of the visible fields and {key: error} (required, kind checks), by the rules."""
        self.ensure_one()
        check = self.env['mtbg.form.fields']._mtbg_check
        answers = {k: v for k, v in values.items() if isinstance(k, str)}
        blocks = self.block_ids.filtered('active').sorted(lambda b: (b.sequence, b.id))
        clean, errors, step_shown = {}, {}, True
        for block in blocks:
            shown = block._mtbg_shown(answers, ctx)
            if block.kind == 'step':
                step_shown = shown
                continue
            if not (shown and step_shown) or block.kind not in FIELDS:
                continue
            value = answers.get(block.key)
            required = block._mtbg_required(answers, ctx)
            if block.kind in ('checkbox',):
                value = bool(value)
                if required and not value:
                    errors[block.key] = _("Please tick \"%s\"", block.label or block.key)
                clean[block.key] = value
                continue
            if block.kind == 'checkboxes':
                options = block._mtbg_choices()
                value = [v for v in (value if isinstance(value, list) else []) if v in options]
                if required and not value:
                    errors[block.key] = _("Please choose at least one: %s", block.label or block.key)
                clean[block.key] = value
                continue
            text = ('' if value in (None, False) else str(value)).strip()
            if not text:
                if required:
                    errors[block.key] = _("Please fill in \"%s\"", block.label or block.key)
                continue
            if block.kind == 'email':
                text, error = check('email', text)
            elif block.kind == 'phone':
                text, error = check('phone', text)
            elif block.kind in ('select', 'radio'):
                error = None if text in block._mtbg_choices() else _("Please choose \"%s\"", block.label or block.key)
            elif block.kind == 'number':
                error = None if _number(text) is not None else _("\"%s\" needs a number", block.label or block.key)
            elif block.kind == 'date':
                try:
                    date.fromisoformat(text[:10])
                    error = None
                except ValueError:
                    error = _("\"%s\" needs a date", block.label or block.key)
            else:
                error = None
            if error:
                errors[block.key] = error
            else:
                clean[block.key] = text
        return clean, errors

    def mtbg_submit(self, values, ctx=None):
        """Check a sent form by its blocks and rules, then hand it to its handler. Returns {'ok': True, ...} or
        {'ok': False, 'errors': {key: message}}."""
        self.ensure_one()
        values = dict(values or {})
        ctx = dict(ctx or {})
        return getattr(self, f'_mtbg_submit_{self.handler}')(values, ctx)

    def _mtbg_extra_answers(self, clean, standard):
        """The answers to the form's own questions (not the handler's standard keys): [(label, text)]."""
        labels = {b.key: b.label or b.key for b in self.block_ids if b.key}
        extra = []
        for key, value in clean.items():
            if key in standard:
                continue
            if isinstance(value, bool):
                value = _("Yes") if value else _("No")
            elif isinstance(value, list):
                value = ', '.join(value)
            extra.append((labels.get(key, key), value))
        return extra

    def _mtbg_submit_contact(self, values, ctx):
        """The contact forms: the client (known, or by phone then email), the SMS / WhatsApp opt-ins and a CRM lead
        with the message and the form's own questions."""
        Fields = self.env['mtbg.form.fields']
        # only the box this form shows (a newsletter form: promotions; the others: none), so the wording kept is the
        # one the visitor read
        shown = ('sms_marketing_optin',) if self.newsletter else ()
        values = {key: value for key, value in values.items() if key not in TEXTING_BOXES or key in shown}
        partner = Fields._mtbg_known_contact() if values.get('use_known') else self.env['res.partner']
        ctx.update(known=bool(partner), known_phone=bool(partner and partner.phone))
        clean, errors = self._mtbg_validate(values, ctx)
        name = None
        if not partner:
            # a new contact needs a name and a way to reach them, whatever the form asks (one Name field, or first and
            # last name together)
            name, error = Fields._mtbg_check('name', clean.get('name') or ' '.join(
                filter(None, [clean.get('first_name'), clean.get('last_name')])))
            keys = {b.key for b in self.block_ids}
            if error and not errors.keys() & {'name', 'first_name', 'last_name'}:
                errors[next((k for k in ('name', 'last_name') if k in keys), 'first_name')] = error
            if not clean.get('email') and not clean.get('phone') and 'email' not in errors and 'phone' not in errors:
                errors['email'] = Fields._mtbg_check('email', '')[1]
        if _texting_opted(values) and not (clean.get('phone') or partner.phone) and 'phone' not in errors:
            errors['phone'] = _("Please enter your mobile number for SMS / WhatsApp updates")
        if errors:
            return {'ok': False, 'errors': errors}
        if not partner:
            tour_given = str(values.get('tour_id') or '').isdigit()
            partner = Fields._mtbg_find_or_create_contact(dict(clean, name=name, email=clean.get('email') or ''),
                                                          'newsletter' if self.newsletter else
                                                          'question' if tour_given else 'contact')
        Fields._mtbg_set_opt_ins(partner, values)
        source = partner._mtbg_forms_set_source(self._mtbg_lead_source())  # first touch only (Core, where installed)
        Fields._mtbg_link_visitor(partner)
        partner._mtbg_fill_country(values.get('phone_country'), clean.get('phone'))  # the country picked with the mobile (the latest they chose)
        tour = self._mtbg_subject(values.get('tour_id'))
        where = {'page': _("contact page"), 'popup': _("contact popup"), 'sidebar': _("tour page"),
                 'menu': _("phone menu")}.get(
            ctx.get('variant'), _("website"))
        title = _("Question about %s", tour.name) if tour else _("Website message")
        if self.newsletter:
            # a newsletter form (e.g. the newsletter popup): subscribed, tagged, its lead as the popup's always was
            Fields._mtbg_subscribe_newsletter(partner, values)
            title, where = _("Newsletter signup"), 'Newsletter Form'
        standard = {'name', 'first_name', 'last_name', 'email', 'phone', 'message', 'sms_optin', 'whatsapp_optin',
                    'sms_marketing_optin'}
        extra = self._mtbg_extra_answers(clean, standard)
        description = Markup('<p>%s</p>') % (clean.get('message') or '')
        if extra:
            description += Markup('<ul>%s</ul>') % Markup('').join(
                Markup('<li><b>%s:</b> %s</li>') % (label, value) for label, value in extra)
        lead = self.env['crm.lead']._mtbg_forms_lead(partner, {  # one open lead per person (Core)
            'name': '%s: %s' % (title, partner.name), 'type': 'lead', 'partner_id': partner.id,
            'contact_name': partner.name, 'email_from': partner.email, 'phone': partner.phone,
            'description': description if (clean.get('message') or extra or not self.newsletter) else
            _("Signed up for the newsletter (%s).", self.name), 'referred': where,
            'mtbg_form_answers': {key: value for key, value in clean.items() if key not in standard} or False,
            'source_id': source.id or False,
        })
        if not lead.source_id and source:  # their open lead, from before without a source
            lead.source_id = source
        # the automatic reply (Communications' "Website Contact" flow, when installed; never for a newsletter signup)
        if not self.newsletter and hasattr(lead, '_mtbg_contact_form_submitted'):
            lead._mtbg_contact_form_submitted()
        return {'ok': True, 'first_name': (partner.name or '').split(' ')[0]}


class MtbgFormBlock(models.Model):
    _name = 'mtbg.form.block'
    _description = 'Website form block'
    _order = 'sequence, id'

    form_id = fields.Many2one('mtbg.form', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    kind = fields.Selection(KINDS, required=True, default='text')
    key = fields.Char(help="The answer's name (letters, digits, _); the form's standard ones (first_name, email, "
                           "phone, message...) go to the contact, the others to the lead")
    label = fields.Char(translate=True)
    placeholder = fields.Char(translate=True)
    help = fields.Char(translate=True, help="Small text under the field (a step or heading: its subtitle)")
    content = fields.Html(translate=True, sanitize_attributes=True, help="Text blocks")
    choices = fields.Text(translate=True, help="Dropdown / choices: one per line")
    width = fields.Selection([('full', 'Full width'), ('half', 'Half width')], default='full', required=True)
    system = fields.Boolean(help="One of the form's own blocks: it can move, not be deleted")
    active = fields.Boolean(default=True)
    show_mode = fields.Selection(MODES_SHOW, default='always', required=True)
    show_rule = fields.Json(default=dict)
    require_mode = fields.Selection(MODES_REQUIRE, default='never', required=True)
    require_rule = fields.Json(default=dict)
    look = fields.Json(help="The block's own look (a form type's block with settings: _mtbg_look_schemas)")
    # the block's text (the designer's block settings): its size (% of the form's text, 0: the form's), colour on light
    # pages and on dark pages (empty: the form's); a heading's level (its font and size: the website theme's)
    text_size = fields.Integer(default=0, help="% of the form's text size; 0: the form's")
    text_color = fields.Char(help="The block's text colour (#rrggbb) on light pages; empty: the form's")
    text_color_dark = fields.Char(help="The block's text colour (#rrggbb) on dark pages; empty: its light one")
    heading_level = fields.Selection([('h3', 'H3'), ('h4', 'H4'), ('h5', 'H5')], default='h3', required=True)
    # a step's title: bold, uppercase, alignment (with its size and colours above); empty: the theme's
    # a heading's line spacing (its title and subtitle: % of the font size, 0: the theme's)
    line_height = fields.Integer(help="A heading's line spacing in % (e.g. 120); 0: the theme's")
    text_bold = fields.Boolean()
    text_upper = fields.Boolean()
    text_align = fields.Selection([('left', 'Left'), ('center', 'Center'), ('right', 'Right')])

    @api.constrains('key', 'kind', 'form_id')
    def _check_key(self):
        for block in self:
            if block.kind not in FIELDS:
                continue
            if not block.key or not KEY_RE.match(block.key):
                raise ValidationError(_("The field \"%s\" needs a name of lower-case letters, digits and _.",
                                        block.label or block.key or ''))
            others = block.form_id.block_ids.filtered(lambda b: b.id != block.id and b.key == block.key and b.kind in FIELDS)
            if isinstance(block.id, int) and others:
                raise ValidationError(_("Two fields of the form share the name \"%s\".", block.key))

    def _mtbg_choices(self):
        return [line.strip() for line in (self.choices or '').splitlines() if line.strip()]

    def _mtbg_shown(self, answers, ctx):
        if self.show_mode == 'always':
            return True
        held = evaluate(_rule(self.show_rule), answers, ctx)
        return held if self.show_mode == 'when' else not held

    def _mtbg_required(self, answers, ctx):
        if self.require_mode in ('never', 'always'):
            return self.require_mode == 'always'
        held = evaluate(_rule(self.require_rule), answers, ctx)
        return held if self.require_mode == 'when' else not held

    def mtbg_title_look(self):
        """A step's title look (its size, colours, bold, uppercase, alignment): title_look()."""
        self.ensure_one()
        return title_look(self.text_size, self.text_color, self.text_color_dark, self.text_bold, self.text_upper,
                          self.text_align)

    def _mtbg_text_look(self):
        """(classes, inline style) of the block's own text size and colours (form.scss)."""
        classes, style = [], []
        # (a block's own text size: no longer applied, the owner 2026-10-27: "remove text size sliders from all forms")
        if self.kind == 'heading' and self.line_height:
            classes.append('has-line-height')
            style.append(f"--mtbg-block-line: {min(max(self.line_height, 80), 250) / 100:g}")
        if self.text_color and COLOR.match(self.text_color):
            classes.append('has-text-color')
            style.append(f"--mtbg-block-text: {self.text_color}")
        if self.text_color_dark and COLOR.match(self.text_color_dark):
            classes.append('has-dark-color')
            style.append(f"--mtbg-block-text-dark: {self.text_color_dark}")
        return ' '.join(classes), '; '.join(style)

    def _mtbg_def(self):
        """What form.js needs of the block: its rules, kind and label (for its messages)."""
        return {'kind': self.kind, 'key': self.key or '',
                'label': self.label or '', 'show': [self.show_mode, _rule(self.show_rule)],
                'require': [self.require_mode, _rule(self.require_rule)], 'choices': self._mtbg_choices()}


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    mtbg_form_answers = fields.Json(string='Form Answers', help="The answers to a website form's own questions")
