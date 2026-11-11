"""Boards: a model's kanban, laid out by the board chosen above it (its columns: a field to group by; its order, top to
bottom: a field and a direction; each column's total: a number summed over its cards). Each model ships its boards as
data (e.g. Tour stage, Things missing, Time to start); people add their own. Columns fold; a column's header is drawn
in its stage's colour. The cards look as set in the extension's settings, the same on every board.

Two columns any board can use, kept up to date when a board using them loads:

- Things missing: the extensions' card notices name what a record still lacks (``missing``: [{key, label}] on a
  notice, e.g. a guide, a vehicle, a rider's form). A record's ``mtbg_missing_ids`` are those; a record lacking nothing
  is in "Nothing missing". So a board shows what the cards say.
- Time to start: where the record is from its start date (2+ months out ... 24 hours out, in progress, the follow-ups),
  the stages of the customer journey.
"""
import ast
from lxml import etree

from odoo import _, api, fields, models

READY = 'ready'
# (key, label, colour): the journey's time stages, in order (the colours: far off pale, close warm, on tour magenta,
# after it blue)
TIME_STAGES = [
    ('m2', "2+ Months Out", '#f3e19b'),
    ('m1', "1 Month Out", '#f3d36b'),
    ('w3', "3 Weeks Out", '#f1c232'),
    ('w2', "2 Weeks Out", '#f6b03b'),
    ('w1', "1 Week Out", '#f39a3c'),
    ('d3', "3 Days Out", '#f07f3c'),
    ('h48', "48 Hours Out", '#ea6a2f'),
    ('h24', "24 Hours Out", '#e04848'),
    ('on', "Tour in Progress", '#d84fd6'),
    ('f1', "1 Day Follow Up", '#9fd3f5'),
    ('fw', "1 Week Follow Up", '#5bb2e8'),
    ('fm', "1 Month Follow Up", '#2f86c9'),
    ('past', "Past", '#9aa0a6'),
    ('cancelled', "Cancelled", '#d9534f'),
]
LEVEL_COLORS = {'danger': '#e5534b', 'warning': '#f0b429', 'info': '#3fb8d8', 'success': '#43b65a', 'muted': '#9aa0a6'}


def time_stage(start, end, today):
    """The time stage of a record from its start and end dates."""
    if not start:
        return False
    end = end or start
    if start <= today <= end:
        return 'on'
    if today < start:
        days = (start - today).days
        for limit, key in ((60, 'm2'), (30, 'm1'), (21, 'w3'), (14, 'w2'), (7, 'w1'), (3, 'd3'), (2, 'h48')):
            if days >= limit:
                return key
        return 'h24'
    days = (today - end).days
    return 'f1' if days < 7 else 'fw' if days < 30 else 'fm' if days < 90 else 'past'


class MtbgMissingTag(models.Model):
    _name = 'mtbg.missing.tag'
    _description = 'Thing missing'
    _order = 'sequence, id'

    key = fields.Char(required=True, index=True)
    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    color = fields.Char(help="Its column's colour (hex)")

    _key_unique = models.Constraint('UNIQUE(key)', "A thing missing is defined once.")

    @api.model
    def _mtbg_tags(self, items):
        """The tags of ``items`` [{key, label, level?}], created as they first appear (in that order)."""
        keys = list(dict.fromkeys(item['key'] for item in items))
        found = {tag.key: tag for tag in self.sudo().search([('key', 'in', keys)])}
        for item in items:
            if item['key'] not in found:
                found[item['key']] = self.sudo().create({
                    'key': item['key'], 'name': item.get('label') or item['key'],
                    'sequence': 1000 if item['key'] == READY else 10,
                    'color': LEVEL_COLORS.get(item.get('level'), LEVEL_COLORS['danger'])})
        return self.browse([found[key].id for key in keys])


class MtbgBoard(models.Model):
    _name = 'mtbg.board'
    _description = 'Kanban board'
    _order = 'res_model, sequence, id'

    name = fields.Char(required=True, translate=True)
    res_model = fields.Char(string='Model', required=True, index=True)
    group_by = fields.Char(string='Columns', help="The field the columns are, e.g. state, or start_date:month")
    order = fields.Char(string='Order', default='start_date asc', help="Top to bottom, e.g. start_date asc")
    total_field = fields.Char(string='Column total', help="A number summed over each column's cards, e.g. seats")
    domain = fields.Char(string='Filter', help="Which records the board shows (a domain, e.g. "
                                               "[('mtbg_stage', 'in', ['new', 'lead'])]); empty: all of them")
    description = fields.Char(translate=True, help="What the board is for (the settings page shows it)")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    scope = fields.Char(index=True, help="The page the board is for, when a model has more than one (its action's "
                                         "context ``mtbg_scope``, e.g. invoices on the bookings); empty: the model's "
                                         "own page")

    def _mtbg_domain(self):
        """The board's filter as a list (a bad one: none)."""
        self.ensure_one()
        try:
            domain = ast.literal_eval(self.domain or '[]')
        except (ValueError, SyntaxError):
            return []
        return domain if isinstance(domain, list) else []

    def _mtbg_origin(self):
        """Which extension ships the board (a template), or False (made on the page)."""
        self.ensure_one()
        data = self.env['ir.model.data'].sudo().search([('model', '=', 'mtbg.board'), ('res_id', '=', self.id)], limit=1)
        module = data and self.env['ir.module.module'].sudo().search([('name', '=', data.module)], limit=1)
        return (module.shortdesc or data.module) if data else False


class MtbgBoardMixin(models.AbstractModel):
    _name = 'mtbg.board.mixin'
    _description = 'Boards'

    mtbg_missing_ids = fields.Many2many('mtbg.missing.tag', string='Things missing', copy=False,
                                        help="What the record's card says it still lacks (refreshed by the boards)")
    mtbg_time_stage = fields.Selection([(key, label) for key, label, _color in TIME_STAGES], string='Time to start',
                                       copy=False, index=True, group_expand='_mtbg_expand_time_stages',
                                       help="Where the record is from its start date (refreshed by the boards)")

    @api.model
    def _mtbg_expand_time_stages(self, values, domain):
        """Every stage a column, in order, even when empty (Past and Cancelled only when used)."""
        return [key for key, _label, _color in TIME_STAGES if key not in ('past', 'cancelled')] + \
            [key for key in ('past', 'cancelled') if key in values]

    # ------------------------------------------------------------------
    # What a board can be made of (a model narrows or adds)
    # ------------------------------------------------------------------
    @api.model
    def _mtbg_board_columns(self):
        """[{key, label}]: what columns can be (a field, a date field by month or week)."""
        result = [{'key': 'mtbg_time_stage', 'label': _("Time to start")},
                  {'key': 'mtbg_missing_ids', 'label': _("Things missing")}]
        for name, field in self._fields.items():
            if not field.store or name in ('mtbg_missing_ids', 'mtbg_time_stage', 'create_uid', 'write_uid',
                                           'message_main_attachment_id') \
                    or name.startswith('activity_') or name.startswith('message_'):
                continue
            if field.type in ('selection', 'many2one'):
                result.append({'key': name, 'label': field._description_string(self.env)})
            elif field.type in ('date', 'datetime') and name not in ('create_date', 'write_date'):
                label = field._description_string(self.env)
                result += [{'key': f'{name}:week', 'label': _("%s (week)", label)},
                           {'key': f'{name}:month', 'label': _("%s (month)", label)}]
        return result

    @api.model
    def _mtbg_board_sorts(self):
        """[{key, label}]: what the cards can be ordered by, top to bottom."""
        return [{'key': name, 'label': field._description_string(self.env)}
                for name, field in self._fields.items()
                if field.store and field.type in ('date', 'datetime', 'char', 'integer', 'float', 'monetary', 'selection')
                and name not in ('write_date', 'mtbg_time_stage') and not name.startswith('message_')
                and not name.startswith('activity_')]

    @api.model
    def _mtbg_board_totals(self):
        """[{key, label}]: the numbers a column can total (stored, summed)."""
        return [{'key': name, 'label': field._description_string(self.env)}
                for name, field in self._fields.items()
                if field.store and field.type in ('integer', 'float', 'monetary') and field.aggregator == 'sum'
                and name not in ('id', 'sequence', 'color')]

    @api.model
    def _mtbg_board_field_colors(self):
        """{field: {value: colour}}: a model's stages' colours (hex), e.g. its status: the column headers, the list's
        pills, the side bar's dots and the cards' status pill all drawn in them (super() + yours)."""
        return {'mtbg_time_stage': {key: color for key, _label, color in TIME_STAGES}}

    @api.model
    def _mtbg_board_colors(self):
        """Every column's colour: the stages' and the things missing'."""
        return dict(self._mtbg_board_field_colors(), mtbg_missing_ids={
            tag.id: tag.color for tag in self.env['mtbg.missing.tag'].search([]) if tag.color})

    @api.model
    def mtbg_board_colors(self):
        """The stages' colours, for the pills (widget ``mtbg_board_badge``)."""
        return self._mtbg_board_field_colors()

    def _mtbg_board_color(self, field_name='state'):
        """The colour of this record's ``field_name`` value, if its stages have colours."""
        self.ensure_one()
        return self._mtbg_board_field_colors().get(field_name, {}).get(self[field_name]) or False

    @api.model
    def mtbg_board_settings(self):
        """The kanban's boards and what new ones can be made of."""
        # a page of the model (its action's context ``mtbg_scope``, e.g. Money › Invoices on the bookings) has its own
        boards = self.env['mtbg.board'].search([('res_model', '=', self._name),
                                                ('scope', '=', self.env.context.get('mtbg_scope') or False)])
        return {
            'boards': [{'id': b.id, 'name': b.name, 'group_by': b.group_by or '', 'order': b.order or '',
                        'total_field': b.total_field or '', 'domain': b._mtbg_domain(),
                        'description': b.description or '', 'origin': b._mtbg_origin()} for b in boards],
            'columns': self._mtbg_board_columns(),
            'sorts': self._mtbg_board_sorts(),
            # a column's total: its number of records, or a number summed over its cards
            'totals': [{'key': '__count', 'label': _("Records")}] + self._mtbg_board_totals(),
            'colors': self._mtbg_board_colors(),
            'can_edit': self.env.user._mtbg_ui_manager(),
            'settings_action': self._mtbg_board_settings_action_id(),
            'refreshed': self._mtbg_board_refreshed(),
            # the side bar on Cards and Kanban as on the list (Core's rule: every view has it)
            'has_sidebar': hasattr(self, 'mtbg_sidebar'),
        }

    @api.model
    def _mtbg_settings_xmlid(self):
        """The model's settings page (the kanban's and the list's cog opens it; Import / Export there)."""
        return False

    @api.model
    def _mtbg_board_settings_action_id(self):
        xmlid = self._mtbg_settings_xmlid()
        action = xmlid and self.env.ref(xmlid, raise_if_not_found=False)
        return action.id if action else False

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        """A board kanban loads the numbers its columns can total (and their currencies)."""
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type == 'kanban' and arch is not None and arch.get('js_class', '').endswith('_kanban') \
                and arch.get('js_class', '').startswith('mtbg_'):
            present = {node.get('name') for node in arch.xpath('./field')}
            names = [t['key'] for t in self._mtbg_board_totals()]
            names += [self._fields[n].currency_field for n in names
                      if self._fields[n].type == 'monetary' and self._fields[n].currency_field]
            for name in dict.fromkeys(names):
                if name in self._fields and name not in present:
                    arch.insert(0, etree.Element('field', name=name))
            # the kanban sums them per column (Odoo's sums only a progress bar's)
            arch.set('mtbg_totals', ','.join(t['key'] for t in self._mtbg_board_totals() if t['key'] in self._fields))
        return arch, view

    def _open_groups(self, *, groups, **kwargs):
        """A board's columns: the empty ones folded, every other open (not only the first 10). A column opened or
        folded by hand stays so on a reload (Odoo's opening info comes first). Only on a board (its kanban says so):
        the model's other kanbans and grouped lists as Odoo has them."""
        if not self.env.context.get('mtbg_board'):
            return super()._open_groups(groups=groups, **kwargs)
        for group in groups:
            if not group.get('__count'):
                group['__fold'] = True
        return super(MtbgBoardMixin, self.with_context(max_number_opened_groups=100))._open_groups(
            groups=groups, **kwargs)

    # ------------------------------------------------------------------
    # Things missing, time to start
    # ------------------------------------------------------------------
    def _mtbg_board_dates(self):
        """(start, end) of the record, for its time stage."""
        self.ensure_one()
        return self['start_date'] if 'start_date' in self._fields else False, \
            self['end_date'] if 'end_date' in self._fields else False

    def _mtbg_board_cancelled(self):
        self.ensure_one()
        return 'state' in self._fields and self['state'] == 'cancelled'

    def _mtbg_missing(self):
        """[{key, label, level}]: what the record lacks, as its card's notices say (``missing`` on a notice)."""
        self.ensure_one()
        if not hasattr(self, '_mtbg_card_values'):
            return []
        items = []
        for notice in self._mtbg_card_values().get('notices') or []:
            items += [dict(item, level=notice.get('level')) for item in notice.get('missing') or []]
        return items

    @api.model
    def _mtbg_board_refreshed(self):
        """The columns brought up to date before a board grouped by them loads (an extension adds its own, e.g. a
        band computed from a count kept elsewhere; it refreshes them in ``mtbg_board_refresh``)."""
        return ['mtbg_missing_ids', 'mtbg_time_stage']

    @api.model
    def mtbg_board_refresh(self, domain, columns=None):
        """Bring the records in ``domain`` up to date for a board loading: their time stage and things missing
        (``columns``: which of 'mtbg_time_stage' / 'mtbg_missing_ids', default both)."""
        columns = [c for c in (columns or ['mtbg_time_stage', 'mtbg_missing_ids'])
                   if c in ('mtbg_time_stage', 'mtbg_missing_ids')]
        if not columns:
            return True
        Tag = self.env['mtbg.missing.tag']
        ready = [{'key': READY, 'label': _("Nothing missing"), 'level': 'success'}]
        today = fields.Date.context_today(self)
        for record in self.search(domain or []):
            vals = {}
            if 'mtbg_time_stage' in columns:
                stage = 'cancelled' if record._mtbg_board_cancelled() else time_stage(*record._mtbg_board_dates(), today)
                if stage != record.mtbg_time_stage:
                    vals['mtbg_time_stage'] = stage
            if 'mtbg_missing_ids' in columns:
                tags = Tag._mtbg_tags(record._mtbg_missing() or ready)
                if tags != record.mtbg_missing_ids:
                    vals['mtbg_missing_ids'] = [(6, 0, tags.ids)]
            if vals:
                record.sudo().with_context(tracking_disable=True, mail_notrack=True).write(vals)
        return True
