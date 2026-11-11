"""Record cards: a compact card for a record (a departure, a booking...), defined once per model and drawn the same
everywhere (its kanban, another record's page), always the same width (about a phone's). Core owns the card; a model
says what can go on it; extensions add fields and notices; the operator sets its look in the card editor (client
action ``mtbg_card_editor``, params {model}): the extension's own settings page (its tile in Configuration ›
Extensions).

A model inherits ``mtbg.card.mixin`` and implements:

    _mtbg_card_fields()   [{key, label, short?, icon?, show?, small?}]  the lines the card may show under its title, in
                          their default order: ``label`` names it in the editor, ``short`` labels it on the card
                          (renamable per language), ``show`` False: off until switched on, ``small``: in the small
                          stats row by default. Extensions add theirs.
    _mtbg_card_titles()   [{key, label}]  what the title may be (the first: the default)
    _mtbg_card_figures()  [{key, label}]  what the big figure top right may show (a price...); values['figures']
    _mtbg_card_detail_columns()  [{key, label, kind, show?}]  the columns of its dropdown table (a booking's riders),
                          kind: text (or {text, icon}), flag (a country code), check ({ok, icon?, title?, url?}),
                          pills ([{abbr, color?, title?}]); details may carry ``check_style`` {size, mark_size,
                          mark_position} (how the checks draw)
    _mtbg_card_link_formats()  [{key, label, pattern}]  the link's text, from its parts ({name}, {tour}, {date}: the
                          date in the look's date format), e.g. '{date} – {tour}'
    _mtbg_card_values()   {titles: {key: text}, link: {text, model, id, parts?: {name, tour, date}}?, link_field?: the
                           field the link is (it shows where that field is, or not at all), image, status: {text, level}?, countdown: {text, level}?, countdown_to?: the start
                           (UTC, ISO), lines: {key: text}, line_links?: {key: {model, id}} (a field that opens a
                           record), small_lines?: {key: text} (shorter texts for the small stats row), accent?: a colour
                           (an outline: e.g. a multi-day trip's day), band?: {text, color, icon?, link?: {model, id}} (a band
                           under the title; with a link, a click opens that record), notices: [{level, text}], details?: {title, rows: [{column
                           key: value}]}}; extensions add their lines, notices and details

The look (one per model, an ir.config_parameter): the photo (shown, beside or on top, small / medium / large), the
title (what it is; beside the photo, or across the card with the pills and the photo under it), the status pill,
the countdown pill (and live), the fields' order and which show, icons instead of labels, the notices, the fields'
labels in each language.
"""
import json
from datetime import datetime, time

import pytz

from babel.dates import format_date

from odoo import _, api, fields, models
from odoo.tools.misc import babel_locale_parse
from odoo.exceptions import UserError

LOOK_PARAM = 'mtbg_tours.card.%s'
# title_position bar (owner, 2026-11-07): the title a bar across the card's top, the pills under it on the right, the
# fields beside them and, once under them, to the card's right edge
CHOICES = {'photo_position': ('left', 'top'), 'photo_size': ('s', 'm', 'l'),
           'title_position': ('beside', 'top', 'across', 'bar'),
           'badge': ('none', 'icon', 'full', 'large')}  # the badge bottom right (e.g. the card paid with): off, its icon,
# icon and text, or large (a small card in its brand's colours, its text on it)
DATE_FORMATS = ('short', 'medium', 'long', 'numeric')  # Jul 15th, Wed, Jul 15, Wed 15 Jul 2026, 15/07/2026
CORNER = ('figure', 'status', 'countdown')  # the top right: the big figure and the pills, in the look's order
# line_icons (owner, 2026-11-07: "the card has very limited space"): a field with an icon shows it instead of its label
# bar_status (owner, 2026-11-07): a bar card's title bar in its status colour (instead of the status pill)
SWITCHES = ('photo', 'pill_status', 'pill_countdown', 'pill_live', 'notices', 'details', 'line_icons', 'bar_status')



def ink_for(color):
    """Text dark or light, to read on ``color`` (hex)."""
    try:
        r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    except (TypeError, ValueError):
        return False
    return '#1b1d26' if 0.299 * r + 0.587 * g + 0.114 * b > 160 else '#ffffff'

class MtbgCardMixin(models.AbstractModel):
    _name = 'mtbg.card.mixin'
    _description = 'Record card'

    # ------------------------------------------------------------------
    # What a model puts on its card (to implement)
    # ------------------------------------------------------------------
    @api.model
    def _mtbg_card_fields(self):
        return []

    @api.model
    def _mtbg_card_detail_columns(self):
        return []

    @api.model
    def _mtbg_card_figures(self):
        return []

    @api.model
    def _mtbg_card_link_formats(self):
        return []

    @api.model
    def _mtbg_card_titles(self):
        return [{'key': 'name', 'label': self.env._("Name")}]

    def _mtbg_card_values(self):
        self.ensure_one()
        return {'titles': {'name': self.display_name}, 'image': '', 'lines': {}, 'notices': []}

    # ------------------------------------------------------------------
    # The look
    # ------------------------------------------------------------------
    @api.model
    def _mtbg_card_default_look(self):
        fields_ = self._mtbg_card_fields()
        return {'photo': True, 'photo_position': 'left', 'photo_size': 'm', 'title_position': 'beside',
                'title': self._mtbg_card_titles()[0]['key'], 'figure': '', 'stat': '', 'corner': list(CORNER),
                'link_format': (self._mtbg_card_link_formats() or [{'key': ''}])[0]['key'], 'link_date': 'short',
                'pill_status': False, 'pill_countdown': True, 'pill_live': False, 'notices': True, 'details': True,
                'line_icons': False, 'bar_status': False,
                # the small stats: short fields side by side in one row under the fields (owner, 2026-11-07: riders,
                # paid, pending, spaces available), in the fields' order; a field marked 'small' starts there
                'small': [f['key'] for f in fields_ if f.get('small')],
                'lines': [{'key': f['key'], 'show': f.get('show', True)} for f in fields_],
                'detail_columns': [{'key': c['key'], 'show': c.get('show', True)} for c in self._mtbg_card_detail_columns()],
                'labels': {f['key']: {} for f in fields_ if f.get('short')},
                'badge': 'full' if self._mtbg_card_badge_label() else 'none'}

    @api.model
    def _mtbg_card_badge_label(self):
        """What the badge bottom right shows, if the model has one (values['badge']: {icon, text, title, brand?, link?};
        e.g. Invoicing's payment method: the card's brand and last 4); False: no badge."""
        return False

    @api.model
    def _mtbg_card_look(self, look=None):
        """The card's look: the saved one (or ``look``, a draft) over the defaults, cleaned."""
        if look is None:
            try:
                look = json.loads(self.env['ir.config_parameter'].sudo().get_param(LOOK_PARAM % self._name) or '{}')
            except ValueError:
                look = {}
        clean = self._mtbg_card_default_look()
        if 'pill' in look and 'pill_countdown' not in look:  # a look saved before the two pills
            look = dict(look, pill_countdown=look['pill'])
        for key in SWITCHES:
            if key in look:
                clean[key] = bool(look[key])
        if look.get('link_format') in {f['key'] for f in self._mtbg_card_link_formats()}:
            clean['link_format'] = look['link_format']
        if look.get('link_date') in DATE_FORMATS:
            clean['link_date'] = look['link_date']
        corner = [key for key in (look.get('corner') or []) if key in CORNER]
        clean['corner'] = list(dict.fromkeys(corner)) + [key for key in CORNER if key not in corner]
        if look.get('title') in {t['key'] for t in self._mtbg_card_titles()}:
            clean['title'] = look['title']
        if 'figure' in look and (not look['figure'] or look['figure'] in {f['key'] for f in self._mtbg_card_figures()}):
            clean['figure'] = look['figure'] or ''
        # the number bottom right: one of the fields, its label over it, big (taken out of the lines)
        if 'stat' in look and (not look['stat'] or look['stat'] in {f['key'] for f in self._mtbg_card_fields()}):
            clean['stat'] = look['stat'] or ''
        for key, allowed in CHOICES.items():
            if look.get(key) in allowed:
                clean[key] = look[key]
        defaults = {ln['key']: ln['show'] for ln in clean['lines']}
        lines = [ln for ln in (look.get('lines') or []) if isinstance(ln, dict) and ln.get('key') in defaults]
        seen = {ln['key'] for ln in lines}
        clean['lines'] = [{'key': ln['key'], 'show': bool(ln.get('show', True))} for ln in lines] + \
            [ln for ln in clean['lines'] if ln['key'] not in seen]  # a field an extension added since: its default
        if isinstance(look.get('small'), list):
            keys = {ln['key'] for ln in clean['lines']}
            clean['small'] = list(dict.fromkeys(k for k in look['small'] if k in keys))
        known = {c['key'] for c in clean['detail_columns']}
        picked = [c for c in (look.get('detail_columns') or []) if isinstance(c, dict) and c.get('key') in known]
        seen = {c['key'] for c in picked}
        clean['detail_columns'] = [{'key': c['key'], 'show': bool(c.get('show', True))} for c in picked] + \
            [c for c in clean['detail_columns'] if c['key'] not in seen]
        for key in clean['labels']:
            texts = (look.get('labels') or {}).get(key) or {}
            clean['labels'][key] = {code: str(text)[:40] for code, text in texts.items() if text}
        return clean

    def _mtbg_card(self, look):
        """One record's card drawn with ``look``, in the user's language."""
        self.ensure_one()
        return self._mtbg_card_draw(self._mtbg_card_values(), look, self.id)

    @api.model
    def _mtbg_card_sample_values(self):
        """Made-up values filling every field, pill, figure, notice and dropdown column: the editor's preview
        (False: the model has none)."""
        return False

    @api.model
    def _mtbg_card_draw(self, values, look, record_id=0):
        """A card from ``values`` (a record's, or the sample's) drawn with ``look``."""
        lang = self.env.lang or 'en_US'
        fields_ = {f['key']: f for f in self._mtbg_card_fields()}
        shown = {ln['key'] for ln in look['lines'] if ln['show']}
        lines = []
        link = values.get('link') or False
        stat = False
        if look.get('stat') and (values.get('lines') or {}).get(look['stat']):
            field = fields_.get(look['stat'], {})
            stat = {'label': look['labels'].get(look['stat'], {}).get(lang) or field.get('short') or field.get('label', ''),
                    'text': values['lines'][look['stat']]}
        small_keys = set(look.get('small') or [])
        line_links = values.get('line_links') or {}  # a field that opens a record (e.g. the leader: the contact)
        small = []
        for line in look['lines']:
            if line['key'] not in shown or (stat and line['key'] == look['stat']):
                continue
            if line['key'] in small_keys:
                field = fields_.get(line['key'], {})
                # a shorter text for the row if the values give one (``small_lines``: e.g. an amount without cents)
                text = (values.get('small_lines') or {}).get(line['key']) or (values.get('lines') or {}).get(line['key'])
                if text:
                    small.append({'key': line['key'], 'icon': field.get('icon') or '', 'text': text,
                                  'label': look['labels'].get(line['key'], {}).get(lang) or field.get('short')
                                  or field.get('label') or '', 'link': line_links.get(line['key']) or False})
                continue
            field = fields_.get(line['key'], {})
            short = look['labels'].get(line['key'], {}).get(lang) or field.get('short') or ''
            hint = short or field.get('label') or ''  # its name when hovered
            if look.get('line_icons') and field.get('icon'):
                short = ''  # its icon instead
            if link and line['key'] == values.get('link_field'):
                # the link: where its field is, its text in the look's format
                text = self._mtbg_card_link_text(link, look)
                if text:
                    lines.append({'key': line['key'], 'icon': field.get('icon') or '', 'label': short, 'hint': hint,
                                  'text': text, 'link': {'model': link.get('model'), 'id': link.get('id')}})
                continue
            text = (values.get('lines') or {}).get(line['key'])
            if text:
                lines.append({'key': line['key'], 'icon': field.get('icon') or '', 'label': short, 'hint': hint,
                              'text': text, 'link': line_links.get(line['key']) or False})
        # fields marked 'pair' next to each other in the look share a row (two halves)
        paired, i = [], 0
        while i < len(lines):
            if fields_.get(lines[i]['key'], {}).get('pair') and i + 1 < len(lines) \
                    and fields_.get(lines[i + 1]['key'], {}).get('pair'):
                paired.append({'key': f"{lines[i]['key']}+{lines[i + 1]['key']}", 'pair': [lines[i], lines[i + 1]]})
                i += 2
            else:
                paired.append(lines[i])
                i += 1
        lines = paired
        link = False  # drawn as a line
        titles = values.get('titles') or {}
        title = titles.get(look['title']) or next((t for t in titles.values() if t), '') or values.get('title') or ''
        figure = (values.get('figures') or {}).get(look['figure']) or '' if look['figure'] else ''
        def status_of():
            status = dict(values['status'], key='status')
            if 'state' in self._fields and len(self) == 1 and self.state == 'confirmed':
                # confirmed is always green (owner, 2026-11-07), whatever the board's colour
                status.update(level='success', color=False)
                return status
            if not status.get('color') and len(self) == 1 and hasattr(self, '_mtbg_board_color') \
                    and 'state' in self._fields:
                status['color'] = self._mtbg_board_color('state')
            if status.get('color'):
                status['ink'] = ink_for(status['color'])
            return status

        has_status = bool((values.get('status') or {}).get('text'))
        bar_status = status_of() if look['title_position'] == 'bar' and look.get('bar_status') and has_status else False
        corner = []  # the big figure and the pills, in the look's order
        for key in look['corner']:
            if key == 'figure' and figure:
                corner.append({'key': 'figure', 'text': figure})
            elif key == 'status' and look['pill_status'] and has_status and not bar_status:
                corner.append(status_of())
            elif key == 'countdown' and look['pill_countdown'] and \
                    ((values.get('countdown') or {}).get('text') or values.get('countdown_to')):
                corner.append(dict(values.get('countdown') or {'text': ''}, key='countdown',
                                   countdown_to=values.get('countdown_to') if look['pill_live'] else False))
        badge = values.get('badge') if look.get('badge', 'none') != 'none' and self._mtbg_card_badge_label() else False
        if badge:
            badge = dict(badge, style=look['badge'], text=badge.get('text') if look['badge'] in ('full', 'large') else '')
        return {
            'id': record_id, 'model': self._name, 'title': title, 'link': link, 'badge': badge or False,
            # a title on one line, cut (``values['title_lines']``: 1; else two lines at most)
            'title_lines': values.get('title_lines') or 2,
            'image': values.get('image') if look['photo'] else '', 'photo': look['photo'],
            'photo_position': look['photo_position'], 'photo_size': look['photo_size'],
            'title_position': look['title_position'],
            'corner': corner, 'stat': stat, 'small': small, 'bar_status': bar_status,
            # an outline in this colour (``values['accent']``, e.g. a multi-day trip's day: the trip's colour)
            'accent': values.get('accent') or False,
            # a band under the title (``values['band']``: {text, color, icon?}, e.g. a multi-day trip's: "Multi-day ·
            # BK26-00549 · Nov 10-12, 2026" in the multi-day colour)
            'band': dict(values['band'], ink=ink_for(values['band'].get('color')) or '#fff')
            if (values.get('band') or {}).get('text') else False,
            'details': self._mtbg_card_details(values.get('details'), look),
            'lines': lines, 'notices': values.get('notices', []) if look['notices'] else [],
            'actions': self._mtbg_card_actions_clean(values.get('actions')),
        }

    @api.model
    def _mtbg_card_actions_clean(self, actions):
        """The card's buttons, from its values' ``actions``: ``[{key, label, icon?, confirm?, primary?, method}]``
        (``method``: a public method of the record, called by ``mtbg_card_action``; ``confirm``: a question asked
        first). Never sent to the browser: the method; a card without actions has none."""
        return [{'key': a['key'], 'label': a.get('label') or '', 'icon': a.get('icon') or '',
                 'confirm': a.get('confirm') or '', 'primary': bool(a.get('primary'))}
                for a in actions or [] if a.get('key') and a.get('method')]

    def mtbg_card_action(self, key):
        """One of the card's buttons: the record's own method named by its card values (so only what its card
        offers can run, with the user's access rights). Returns what the method returns (an action, or None)."""
        self.ensure_one()
        action = next((a for a in self._mtbg_card_values().get('actions') or [] if a.get('key') == key), None)
        method = (action or {}).get('method') or ''
        if not method or method.startswith('_') or not callable(getattr(type(self), method, None)):
            raise UserError(self.env._("This button is not available on this card any more."))
        result = getattr(self, method)()
        return result if isinstance(result, dict) else False

    @api.model
    def _mtbg_card_details(self, details, look):
        """The dropdown: its title, the columns the look shows, its rows (False: none, or switched off). A row
        ``{'_group': text, '_link'?: {model, id}}`` divides them (a band across the columns). A row's or band's
        ``_link``: a click on it opens that record."""
        if not details or not look['details'] or not details.get('rows'):
            return False
        columns = {c['key']: c for c in self._mtbg_card_detail_columns()}
        shown = [dict(columns[c['key']]) for c in look['detail_columns'] if c['show'] and c['key'] in columns]
        return {'title': details.get('title') or '', 'columns': [{'key': c['key'], 'label': c.get('short', c['label']),
                                                                  'kind': c.get('kind', 'text')} for c in shown],
                # a row with '_group' is a band across the columns (a departure's manifest: one per booking)
                'rows': [{'_group': row['_group'], '_link': row.get('_link') or False} if row.get('_group')
                         else dict({c['key']: row.get(c['key']) for c in shown}, _link=row.get('_link') or False)
                         for row in details['rows']],
                'check_style': details.get('check_style') or {}}

    def mtbg_card_data(self):
        """The records' cards: [{id, model, title, link, image, photo..., title_position, corner: [{key: figure / status
        / countdown, text, level?, countdown_to?}],
        lines: [{key, icon, label, text}], notices}] (widget ``mtbg_record_card``)."""
        look = self._mtbg_card_look()
        return [rec._mtbg_card(look) for rec in self.exists()]

    # ------------------------------------------------------------------
    # Presets: a starting point in the editor (a model may add its own)
    # ------------------------------------------------------------------
    @api.model
    def _mtbg_card_presets(self):
        """[{key, name, look}]: a preset's look sets what it names; ``fields``: the fields it shows (``'default'``:
        the model's defaults, ``'all'``, or a number: the first ones in their order)."""
        _t = self.env._
        def preset(key, name, **look):
            return {'key': key, 'name': name, 'look': dict({
                'photo': True, 'photo_position': 'left', 'photo_size': 'm', 'title_position': 'beside',
                'pill_status': False, 'pill_countdown': True, 'pill_live': False, 'notices': True,
                'fields': 'default'}, **look)}

        return [
            preset('standard', _t("Standard")),
            preset('headline', _t("Title across, photo under"), title_position='top', photo_size='s'),
            preset('compact', _t("Compact"), photo_size='s', title_position='top', fields=3),
            preset('hero', _t("Photo on top, live countdown"), photo_position='top', photo_size='l',
                   title_position='top', pill_live=True),
            preset('text', _t("Text only"), photo=False, title_position='top', pill_status=True),
            preset('everything', _t("Everything"), title_position='top', pill_status=True, pill_live=True,
                   fields='all'),
        ]

    @api.model
    def mtbg_card_preset(self, key, look):
        """``look`` (a draft) with preset ``key`` applied: its options, and its fields shown in the default order
        (the labels kept)."""
        preset = next((p for p in self._mtbg_card_presets() if p['key'] == key), None)
        clean = self._mtbg_card_look(look)
        if not preset:
            return clean
        chosen = dict(preset['look'])
        which = chosen.pop('fields', None)
        clean.update(chosen)
        if which is not None:
            fields_ = self._mtbg_card_fields()
            default = {f['key']: f.get('show', True) for f in fields_}
            shown = [f['key'] for f in fields_ if default[f['key']]]
            clean['lines'] = [{'key': f['key'], 'show': (which == 'all' or (which == 'default' and default[f['key']])
                                                          or (isinstance(which, int) and f['key'] in shown[:which]))}
                              for f in fields_]
        return self._mtbg_card_look(clean)

    # ------------------------------------------------------------------
    # The card editor (the extension's settings page)
    # ------------------------------------------------------------------
    @api.model
    def _mtbg_card_samples(self):
        """The records to preview the card on (the most recent first)."""
        return self.search([], limit=40)

    @api.model
    def _mtbg_transfer_models(self):
        """The settings page's Import / Export: [{model, label}] (this model; a model adds its own, e.g. riders)."""
        return [{'model': self._name, 'label': self._description}]

    @api.model
    def mtbg_card_settings(self):
        fields_ = self._mtbg_card_fields()
        return {
            'model': self._name, 'title': _("%s card", self._description),
            'transfer': self._mtbg_transfer_models() if self.env.user._mtbg_ui_manager() else [],
            'look': self._mtbg_card_look(),
            'fields': [{'key': f['key'], 'label': f['label'], 'short': f.get('short') or ''} for f in fields_],
            'titles': self._mtbg_card_titles(),
            'link_formats': [{'key': f['key'], 'label': f['label']} for f in self._mtbg_card_link_formats()],
            'date_formats': [{'key': key, 'label': self._mtbg_card_date(fields.Date.context_today(self).replace(day=15), key)}
                             for key in DATE_FORMATS],
            'figures': self._mtbg_card_figures(),
            'badge_label': self._mtbg_card_badge_label(),
            'detail_columns': [{'key': c['key'], 'label': c['label']} for c in self._mtbg_card_detail_columns()],
            'presets': [{'key': p['key'], 'name': p['name']} for p in self._mtbg_card_presets()],
            'langs': [{'code': code, 'name': name} for code, name in self.env['res.lang'].get_installed()],
            'records': ([{'id': 0, 'name': _("Sample (every field filled)")}] if self._mtbg_card_sample_values() else [])
            + [{'id': r.id, 'name': r.display_name} for r in self._mtbg_card_samples()],
            'can_edit': self.env.user._mtbg_ui_manager(),
        }

    @api.model
    def mtbg_card_preview(self, record_id, look, lang=False):
        """A record's card drawn with a draft ``look``, in ``lang`` (``record_id`` 0: the sample)."""
        records = self.with_context(lang=lang) if lang else self
        if not int(record_id or 0):
            sample = records._mtbg_card_sample_values()
            return records._mtbg_card_draw(sample, records._mtbg_card_look(look)) if sample else False
        record = records.browse(int(record_id)).exists()
        return record._mtbg_card(records._mtbg_card_look(look)) if record else False

    @api.model
    def mtbg_save_card_look(self, look):
        if not self.env.user._mtbg_ui_manager():
            raise UserError(_("Only a manager changes a card's look."))
        clean = self._mtbg_card_look(look)
        self.env['ir.config_parameter'].sudo().set_param(LOOK_PARAM % self._name, json.dumps(clean))
        return clean

    # ------------------------------------------------------------------
    # Helpers for the models' values
    # ------------------------------------------------------------------
    @api.model
    def _mtbg_card_day(self, day):
        return day.strftime('%a %d %b %Y') if day else ''

    @api.model
    def _mtbg_card_hour(self, hour):
        return f"{int(hour):02d}:{int(round((hour % 1) * 60)) % 60:02d}" if hour else ''

    @api.model
    def _mtbg_card_utc(self, day, hour=0.0):
        """A day and hour in the operator's time zone, as UTC ISO (the live countdown's target)."""
        if not day:
            return False
        tz_name = self.env['ir.config_parameter'].sudo().get_param('mtbg_tours.operator_tz') or self.env.user.tz or 'UTC'
        try:
            tz = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            tz = pytz.utc
        hours = int(hour or 0)
        minutes = int(round(((hour or 0) % 1) * 60)) % 60
        local = tz.localize(datetime.combine(day, time(hours % 24, minutes)))
        return local.astimezone(pytz.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    @api.model
    def _mtbg_card_countdown(self, day, end=False, closed=False):
        """The countdown pill to ``day``: {text, level} (Today / Tomorrow / 5 days / 3 weeks / 2 months; past)."""
        if not day:
            return False
        from odoo import fields as odoo_fields
        today = odoo_fields.Date.context_today(self)
        delta = (day - today).days
        _t = self.env._
        if closed or (end or day) < today:
            return {'text': _t("Past") if (end or day) < today else '', 'level': 'muted'}
        if delta < 0:
            return {'text': _t("In progress"), 'level': 'success'}
        text = (_t("Today") if delta == 0 else _t("Tomorrow") if delta == 1 else _t("%s days", delta) if delta < 14
                else _t("%s weeks", delta // 7) if delta < 60 else _t("%s months", delta // 30))
        return {'text': text, 'level': 'success' if delta <= 0 else 'warning' if delta < 14 else 'muted'}

    @api.model
    def _mtbg_card_sample_soon(self, days=5, hour=8.0):
        """The sample's start: in a few days (for its countdown)."""
        from datetime import timedelta
        from odoo import fields as odoo_fields
        day = odoo_fields.Date.context_today(self) + timedelta(days=days)
        return day, self._mtbg_card_utc(day, hour)

    @api.model
    def _mtbg_card_date(self, day, fmt='short'):
        """A date in one of the card's formats, in the user's language: short 'Jul 15th' (the day's suffix in English
        only), medium 'Wed, Jul 15', long 'Wed 15 Jul 2026', numeric '15/07/2026'."""
        if not day:
            return ''
        lang = self.env.lang or 'en_US'
        locale = babel_locale_parse(lang)
        if fmt == 'numeric':
            return day.strftime('%d/%m/%Y')
        if fmt == 'long':
            return format_date(day, 'EEE d MMM y', locale=locale)
        if fmt == 'medium':
            return format_date(day, 'EEE, MMM d', locale=locale)
        if lang.startswith('en'):
            n = day.day
            suffix = 'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
            return f"{format_date(day, 'MMM', locale=locale)} {n}{suffix}"
        return format_date(day, 'd MMM', locale=locale)

    @api.model
    def _mtbg_card_date_tour(self, day, tour):
        """A record named by its day and tour (owner, 2026-11-06/07: bookings and departures): "Nov 12th - Top of the
        World" (its first day, short, and its tour)."""
        return ' - '.join(p for p in (self._mtbg_card_date(day, 'short') if day else '', tour or '') if p)

    @api.model
    def _mtbg_card_dates(self, start, end):
        """Start and end on one line: one day "Thursday Nov 12th"; several "Nov 12-13, 2026" (another month: "Nov
        30 - Dec 2, 2026"; another year: "Dec 30, 2026 - Jan 2, 2027"), in the user's language."""
        if not start:
            return ''
        end = end or start
        lang = self.env.lang or 'en_US'
        locale = babel_locale_parse(lang)
        if end == start:
            return f"{format_date(start, 'EEEE', locale=locale)} {self._mtbg_card_date(start, 'short')}"
        month = lambda d: format_date(d, 'MMM', locale=locale)  # noqa: E731
        if lang.startswith('en'):
            if (start.year, start.month) == (end.year, end.month):
                return f"{month(start)} {start.day}-{end.day}, {end.year}"
            if start.year == end.year:
                return f"{month(start)} {start.day} - {month(end)} {end.day}, {end.year}"
            return f"{month(start)} {start.day}, {start.year} - {month(end)} {end.day}, {end.year}"
        if (start.year, start.month) == (end.year, end.month):
            return f"{start.day}-{end.day} {month(end)} {end.year}"
        if start.year == end.year:
            return f"{start.day} {month(start)} - {end.day} {month(end)} {end.year}"
        return f"{start.day} {month(start)} {start.year} - {end.day} {month(end)} {end.year}"

    @api.model
    def _mtbg_card_link_text(self, link, look):
        """The link's text: its parts in the look's format (else its own text)."""
        parts = link.get('parts')
        pattern = next((f['pattern'] for f in self._mtbg_card_link_formats() if f['key'] == look.get('link_format')),
                       None)
        if not parts or not pattern:
            return link.get('text') or ''
        values = {'name': parts.get('name') or '', 'tour': parts.get('tour') or '',
                  'date': self._mtbg_card_date(parts.get('date'), look.get('link_date') or 'short')}
        text = pattern.format(**values).strip(' –·-')
        return text or link.get('text') or ''
