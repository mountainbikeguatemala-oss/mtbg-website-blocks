"""Reviews presets: the look, the reviews and the layout of a Reviews block, set once on the Reviews page.

A block on a page only names its preset (``<section class="s_review_preset" data-preset="site">``): the block is
drawn from the preset on each visit (``/review_sync/preset``), so changing a preset changes every block using it.
"""
import json
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .review import PLATFORMS

COLOR_RE = re.compile(r'^#[0-9a-fA-F]{6}$')
KEY_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,40}$')
# the parts of a block, top to bottom (``reviews`` always shows)
BLOCK_PARTS = {
    'slider': ['heading', 'stars', 'total', 'reviews', 'button'],
    'wall': ['heading', 'stars', 'total', 'filters', 'reviews'],
}
# the parts of a review card, in order; with speech bubbles two dividers set what is above the bubble, in it and
# under it (bubble_start / bubble_end, always "shown"); the date: the reviewer's line, or a part of its own
CARD_PARTS = ['rating', 'title', 'text', 'photos', 'link', 'reviewer', 'date', 'bubble_start', 'bubble_end']
MARKERS = ('bubble_start', 'bubble_end')
COLORS = ['bg', 'text', 'bubble', 'bubble_text', 'star', 'link', 'button', 'button_text']
# the five-star total's count-up: how its speed changes on the way to the total
EASINGS = ['linear', 'smooth', 'slow', 'slower', 'log']
TEXTS = ['heading', 'total_label', 'button_text']
SORTS = ['recent', 'featured', 'best', 'photos']


def _parts(value, names, default_hidden=()):
    """A saved part list ([{key, show}]) cleaned: known parts only, each once, missing ones added (hidden)."""
    seen, parts = set(), []
    value = list(value or [])
    keys = [item.get('key') for item in value if isinstance(item, dict)]
    if 'stars' in names and 'total' in keys and 'stars' not in keys:
        # saved before the stars were a part of their own: they stay just above the total
        total = value[keys.index('total')]
        value.insert(keys.index('total'), {'key': 'stars', 'show': total.get('show', True)})
    for item in value:
        key = item.get('key') if isinstance(item, dict) else None
        if key in names and key not in seen:
            seen.add(key)
            parts.append({'key': key, 'show': bool(item.get('show', True)) or key == 'reviews'})
    for key in names:
        if key not in seen:
            parts.append({'key': key, 'show': key not in default_hidden})
    return parts


def _card_parts(value):
    """A review card's parts cleaned (_parts). Saved before the dividers: they go where the bubble was, the reviewer
    above it when it was first (shown), under it otherwise; the date part starts hidden (the reviewer's line has it)."""
    value = [item for item in (value or []) if isinstance(item, dict)]
    keys = [item.get('key') for item in value]
    if value and not any(marker in keys for marker in MARKERS):
        shown = [item.get('key') for item in value if item.get('show', True)]
        reviewer = next((item for item in value if item.get('key') == 'reviewer'), None)
        rest = [item for item in value if item.get('key') != 'reviewer']
        start, end = {'key': 'bubble_start', 'show': True}, {'key': 'bubble_end', 'show': True}
        if reviewer and shown[:1] == ['reviewer']:
            value = [reviewer, start, *rest, end]
        else:
            value = [start, *rest, end] + ([reviewer] if reviewer else [])
    elif not value:
        value = [{'key': 'bubble_start', 'show': True}] + [{'key': key, 'show': key != 'date'} for key in CARD_PARTS
                 if key not in MARKERS and key != 'reviewer'] + [{'key': 'bubble_end', 'show': True},
                                                                  {'key': 'reviewer', 'show': True}]
    parts = _parts(value, CARD_PARTS, ('date',))
    for part in parts:
        if part['key'] in MARKERS:
            part['show'] = True
    return parts


def _card_zones(parts):
    """Speech bubbles: the shown parts above the bubble, in it and under it, by the two dividers."""
    keys = [p['key'] for p in parts if p['show']]
    start, end = sorted((keys.index('bubble_start'), keys.index('bubble_end')))
    zone = lambda part_keys: [k for k in part_keys if k not in MARKERS]
    return {'above': zone(keys[:start]), 'inside': zone(keys[start + 1:end]), 'below': zone(keys[end + 1:])}


class ReviewPreset(models.Model):
    _name = 'review.preset'
    _description = 'Reviews Block Preset'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    key = fields.Char(required=True, copy=False, help="The name blocks use to find it (data-preset)")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    kind = fields.Selection([('slider', 'Slider'), ('wall', 'Wall (every review, filters, endless scroll)')],
                            required=True, default='slider')
    # look
    style = fields.Selection([('bubbles', 'Speech bubbles'), ('cards', 'Cards')], required=True, default='bubbles')
    tail = fields.Selection([('left', 'Left'), ('center', 'Centre'), ('right', 'Right'), ('none', 'None')],
                            string='Bubble Tail', required=True, default='left')
    radius = fields.Integer(string='Corner Radius', default=22)
    shadow = fields.Boolean(default=True)
    theme = fields.Selection([('light', 'Light'), ('dark', 'Dark'), ('site', "Website colours")], required=True,
                             default='light')
    site_cc = fields.Selection([(str(n), str(n)) for n in range(1, 6)], string='Colour Combination', default='5',
                               required=True, help="The website's colour combination (theme colours), 1 to 5")
    color_bg = fields.Char(string='Background')
    color_text = fields.Char(string='Text')
    color_bubble = fields.Char(string='Bubble')
    color_bubble_text = fields.Char(string='Bubble Text')
    color_star = fields.Char(string='Stars')
    color_link = fields.Char(string='Links')
    color_button = fields.Char(string='Button')
    color_button_text = fields.Char(string='Button Text Colour')
    width = fields.Selection([('full', 'Full width'), ('boxed', 'Boxed')], required=True, default='full')
    corners = fields.Selection([('square', 'Square'), ('rounded', 'Rounded'), ('rounded_lg', 'Very rounded')],
                               required=True, default='square', help="The block's own corners (boxed blocks)")
    side_padding = fields.Integer(help="Space at the left and right inside the block, in px (0: the default)")
    spacing = fields.Integer(string='Top / Bottom Space', default=48, help="In px")
    # which reviews
    platform = fields.Selection([('all', 'All')] + [p for p in PLATFORMS if p[0] != 'manual'], required=True,
                                default='all')
    source_ids = fields.Many2many('review.source', string='Sources', help="Empty: every source")
    min_rating = fields.Integer(default=4)
    limit = fields.Integer(string='Reviews', default=12)
    sort = fields.Selection([('recent', 'Most recent'), ('featured', 'Featured first'), ('best', 'Highest rated'),
                             ('photos', 'With photos first')], required=True, default='recent')
    page_only = fields.Boolean(string="This Page's Reviews Only", help="Reviews linked to the page's item, e.g. a tour")
    autoplay = fields.Boolean(default=True)
    arrows = fields.Boolean(default=True)
    # layout and texts
    layout = fields.Json(help="The block's parts in order: [{key, show}]")
    card_parts = fields.Json(help="A review card's parts in order: [{key, show}]")
    total_style = fields.Selection([('stacked', 'Stacked (big number)'), ('inline', 'One line')], required=True,
                                   default='stacked')
    count_ms = fields.Integer(string='Count-Up Time', default=5000,
                              help="How long the five-star total takes to count up, in milliseconds (0: no count-up)")
    count_ease = fields.Selection([('linear', 'Steady'), ('smooth', 'Smooth'), ('slow', 'Slows near the top'),
                                   ('slower', 'Crawls to the top'), ('log', 'Logarithmic')], string='Count-Up Speed',
                                  required=True, default='slow')
    heading = fields.Char(translate=True)
    total_label = fields.Char(string='Five-Star Label', translate=True)
    button_text = fields.Char(translate=True)
    button_url = fields.Char(default='/reviews')
    button_style = fields.Selection([('primary', 'Solid'), ('outline', 'Outline')], required=True, default='outline')
    button_size = fields.Selection([('sm', 'Small'), ('md', 'Medium'), ('lg', 'Large')], required=True, default='md')
    logo = fields.Selection([('reviewer', 'Beside the reviewer'), ('bubble', 'Top right of the bubble'),
                             ('none', 'Hidden')], string='Platform Logo', required=True, default='reviewer',
                            help="Where a review shows the logo of its platform (Google, Tripadvisor…)")

    _key_unique = models.Constraint('UNIQUE(key)', 'Each preset needs its own key.')

    @api.constrains('key')
    def _check_key(self):
        for preset in self:
            if not KEY_RE.match(preset.key or ''):
                raise ValidationError(_("A preset's key may only use lowercase letters, digits, - and _."))

    @api.constrains(*['color_' + c for c in COLORS])
    def _check_colors(self):
        for preset in self:
            for color in COLORS:
                value = preset['color_' + color]
                if value and not COLOR_RE.match(value):
                    raise ValidationError(_("Colours are written #rrggbb (%s).", value))

    @api.model
    def _new_key(self, name):
        base = re.sub(r'[^a-z0-9]+', '-', (name or '').lower()).strip('-')[:30] or 'preset'
        key, n = base, 1
        while self.with_context(active_test=False).search_count([('key', '=', key)]):
            n += 1
            key = f'{base}-{n}'
        return key

    # ------------------------------------------------------------------ rendering
    def _values(self):
        """The preset as plain values (the Reviews page edits these; drafts come back in the same shape)."""
        self.ensure_one()
        return {
            'id': self.id, 'name': self.name, 'key': self.key, 'kind': self.kind, 'style': self.style,
            'tail': self.tail, 'radius': self.radius, 'shadow': self.shadow, 'theme': self.theme, 'site_cc': self.site_cc,
            'colors': {c: self['color_' + c] or '' for c in COLORS}, 'width': self.width, 'corners': self.corners,
            'side_padding': self.side_padding, 'spacing': self.spacing, 'platform': self.platform,
            'source_ids': self.source_ids.ids, 'min_rating': self.min_rating, 'limit': self.limit, 'sort': self.sort,
            'page_only': self.page_only, 'autoplay': self.autoplay, 'arrows': self.arrows,
            'layout': _parts(self.layout, BLOCK_PARTS[self.kind], ('heading',)),
            'card_parts': _card_parts(self.card_parts), 'total_style': self.total_style,
            'count_ms': self.count_ms, 'count_ease': self.count_ease,
            'button_url': self.button_url or '', 'button_style': self.button_style, 'button_size': self.button_size,
            'logo': self.logo,
        }

    @api.model
    def _clean(self, data):
        """Draft values from the Reviews page, checked; returns field values (texts apart)."""
        kind = data.get('kind') if data.get('kind') in BLOCK_PARTS else 'slider'
        colors = data.get('colors') or {}
        vals = {}
        for name in ('style', 'tail', 'theme', 'site_cc', 'width', 'corners', 'platform', 'sort', 'total_style',
                     'button_style', 'count_ease', 'button_size', 'logo'):
            value = data.get(name)
            if value not in dict(self._fields[name]._description_selection(self.env)):
                raise ValidationError(_("Unknown choice for %s.", self._fields[name].string))
            vals[name] = value
        for color in COLORS:
            value = (colors.get(color) or '').strip()
            if value and not COLOR_RE.match(value):
                raise ValidationError(_("Colours are written #rrggbb (%s).", value))
            vals['color_' + color] = value.lower() or False
        bounds = {'radius': (0, 60), 'side_padding': (0, 240), 'spacing': (0, 200), 'min_rating': (1, 5),
                  'limit': (1, 50), 'count_ms': (0, 20000)}
        for name, (low, high) in bounds.items():
            vals[name] = min(max(int(data.get(name) or 0), low), high)
        sources = self.env['review.source'].browse([int(s) for s in data.get('source_ids') or []]).exists()
        url = (data.get('button_url') or '').strip()
        if url and not re.match(r'^(/|https?://|#|mailto:|tel:)', url):
            raise ValidationError(_("The button's link must start with /, http(s)://, # or mailto:"))
        vals.update({
            'name': (data.get('name') or '').strip() or _("Reviews"), 'kind': kind,
            'shadow': bool(data.get('shadow')), 'page_only': bool(data.get('page_only')),
            'autoplay': bool(data.get('autoplay')), 'arrows': bool(data.get('arrows')),
            'source_ids': [(6, 0, sources.ids)], 'button_url': url or False,
            'layout': _parts(data.get('layout'), BLOCK_PARTS[kind], ('heading',)),
            'card_parts': _card_parts(data.get('card_parts')),
        })
        return vals

    @api.model
    def _render_context(self, vals, texts):
        """What the block template needs, from cleaned values and the texts of one language."""
        hidden = {p['key'] for p in vals['card_parts'] if not p['show']}
        order = {key: i for i, key in enumerate(p['key'] for p in vals['card_parts'] if p['key'] not in MARKERS)}
        classes = ['s_review_ordered', 's_review_wall' if vals['kind'] == 'wall' else 's_review_slider',
                   's_review_' + vals['style']]
        if vals['theme'] == 'dark':
            classes.append('s_review_dark')
        elif vals['theme'] == 'site':
            classes += ['s_review_site', 'o_cc', 'o_cc' + vals['site_cc']]
        if vals['width'] == 'boxed':
            classes.append('s_review_boxed')
        if vals['corners'] != 'square':
            classes.append('s_review_' + vals['corners'])
        if vals['tail'] != 'left':
            classes.append('rv-tail-' + vals['tail'])
        if not vals['shadow']:
            classes.append('rv-flat')
        if vals['logo'] != 'reviewer':
            classes.append('rv-logo-' + vals['logo'])
        if vals['arrows'] and vals['kind'] == 'slider':
            classes.append('rv-arrows')  # the arrows beside the reviews, not over them
        # speech bubbles: the dividers set what sits above the bubble, in it and under it (the tail points up when
        # the reviewer is above); the date part shown: the reviewer's line leaves its date out
        zones = _card_zones(vals['card_parts']) if vals['style'] == 'bubbles' else None
        if zones and 'reviewer' in zones['above']:
            classes.append('s_review_reviewer_top')
        if 'date' not in hidden:
            classes.append('s_review_date_apart')
        classes += ['s_review_hide_' + key for key in sorted(hidden)]
        style = [f'--rv-o-{key}: {index}' for key, index in order.items()]
        style.append(f"--rv-radius: {vals['radius']}px")
        style.append(f"padding-top: {vals['spacing']}px; padding-bottom: {vals['spacing']}px")
        if vals['side_padding']:
            style.append(f"--mtbg-side-pad: {vals['side_padding']}px")
        for color in COLORS:
            value = vals.get('color_' + color)
            if value:
                classes.append('rv-' + color.replace('_', '-'))
                style.append(f"--rv-{color.replace('_', '-')}: {value}")
        sources = vals['source_ids'][0][2] if vals.get('source_ids') else []
        # the stars and the total next to each other share one banner (one line, or stacked as before)
        parts = []
        for key in (p['key'] for p in vals['layout'] if p['show']):
            if key in ('stars', 'total'):
                if parts and parts[-1]['key'] == 'banner' and key not in parts[-1]['items']:
                    parts[-1]['items'].append(key)
                else:
                    parts.append({'key': 'banner', 'items': [key]})
            else:
                parts.append({'key': key})
        return {
            'kind': vals['kind'], 'classes': ' '.join(classes), 'style': '; '.join(style),
            'parts': parts, 'total_style': vals['total_style'],
            'data': {
                'data-platform': vals['platform'], 'data-source-id': ','.join(map(str, sources)) or 'all',
                'data-min-rating': vals['min_rating'], 'data-limit': vals['limit'], 'data-sort': vals['sort'],
                'data-autoplay': 'true' if vals['autoplay'] else 'false',
                'data-arrows': 'true' if vals['arrows'] else 'false',
                'data-scope': 'page' if vals['page_only'] else None,
                'data-count-ms': vals['count_ms'], 'data-count-ease': vals['count_ease'],
                'data-rv-zones': json.dumps({'above': zones['above'], 'below': zones['below']}) if zones else None,
            },
            'heading': texts.get('heading') or '', 'total_label': texts.get('total_label') or '',
            'button_text': texts.get('button_text') or '', 'button_url': vals.get('button_url') or '/reviews',
            'button_class': ' '.join(filter(None, [
                'btn', 'btn-primary' if vals['button_style'] == 'primary' else 'btn-outline-primary',
                {'sm': 'btn-sm', 'lg': 'btn-lg'}.get(vals['button_size'])])),
        }

    @api.model
    def _render(self, vals, texts):
        return self.env['ir.qweb']._render('website_review_sync.preset_block', {'p': self._render_context(vals, texts)})

    def _render_saved(self):
        """The block of a saved preset, in the context's language."""
        self.ensure_one()
        vals = self._clean(self._values())
        return self._render(vals, {name: self[name] for name in TEXTS})

    @api.model
    def render_block(self, key):
        """A page's Reviews block (``data-preset``): its HTML, '' when the preset is gone."""
        preset = self.sudo().search([('key', '=', key or '')], limit=1)
        return str(preset._render_saved()) if preset else ''

    def _usage(self):
        """The website pages showing this preset (their views)."""
        self.ensure_one()
        # (not the Reviews blocks' own templates, which name the built-in presets)
        return self.env['ir.ui.view'].sudo().search_count([('arch_db', 'like', f'data-preset="{self.key}"'),
                                                            ('key', 'not like', 'website_review_sync.%')])
