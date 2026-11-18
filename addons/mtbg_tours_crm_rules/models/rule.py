"""A contact rule (a stock contact helper): when something is created, changes, a message comes in or every day, it acts on the
records concerned (its own logic, or its actions).

**The wiring protocol** (like the Alert Feed's sources). Contact Rules declares ``_mtbg_crm_rule_sources`` on every model
(returning ``[]``). An extension announces its rules by overriding it on its own model and adding its specs to
``super()``'s; it never depends on Contact Rules (without it nobody asks)::

    class MtbgBooking(models.Model):
        _inherit = 'mtbg.booking'

        def _mtbg_crm_rule_sources(self):
            return super()._mtbg_crm_rule_sources() + [{
                'code': 'booking_returning', 'name': self.env._("Returning customer"),
                'description': self.env._("..."), 'model': 'res.partner', 'trigger': 'changed',
                'fields': ['email'],
                'actions': [{'kind': 'add_tag', 'field': 'category_id', 'value': 'Returning'}],
                'run': '_mtbg_crm_returning',  # optional
            }]

Contact Rules gives each spec a rule of its own (``mtbg.crm.rule``: switched off until switched on, and its days, changed
on the Rules & Alerts page's Contact rules tab and kept), as soon as the extension is installed or updated; it waits (not
ready) once its extension is gone. Keys of a spec:

* ``code`` (required, unique), ``name``, ``description``, ``icon``, ``sequence``, ``enabled`` (default False)
* ``model`` (the records it looks at, e.g. ``res.partner``, ``crm.lead``), ``trigger`` (``created``, ``changed``,
  ``received``: a message from a contact came in, ``res.partner`` only; or ``daily``), ``fields`` (``changed``: the fields whose change runs it), ``days`` (``daily``: a number of days the
  rule's ``run`` reads)
* ``actions`` (dicts with
  ``kind``, ``field``, ``value``, ``fill_empty``, ``summary``, ``days``, ``match_on``)
* ``once`` (default True: a record it changed is left alone afterwards), ``on_switch`` (a method called with the rule
  when it is switched on or off)
* ``run``: a method of the announcing model, called as ``method(rule, records)`` (``records`` empty for a daily
  rule), returning the records the actions apply to (a recordset), or the changes themselves: a list of
  ``{'record': record, 'values': {field: value}}`` (logged and undoable as field changes)
"""
import json
import logging
from datetime import timedelta

from odoo import api, fields, models, tools
from odoo.exceptions import UserError, ValidationError


_logger = logging.getLogger(__name__)

TRIGGERS = [('created', "Created"), ('changed', "Created or changed"), ('received', "A message comes in"),
            ('daily', "Every day")]
ACTIONS = [('set_field', "Set a field"), ('add_tag', "Add a tag"), ('remove_tag', "Remove a tag"),
           ('assign_salesperson', "Assign a salesperson"), ('activity', "Schedule a to-do"),
           ('note', "Log an internal note"), ('flag_duplicate', "Flag possible duplicates"),
           ('raise_alert', "Raise an Alert Feed item")]
STATE_COLORS = {'on': '#6cc66c', 'off': '#9aa0a6', 'waiting': '#e5a50a'}


class Base(models.AbstractModel):
    _inherit = 'base'

    def _mtbg_crm_rule_sources(self):
        """The Contact rules this model announces (see ``mtbg_tours_crm_rules/models/rule.py``)."""
        return []


class MtbgCrmRule(models.Model):
    _name = 'mtbg.crm.rule'
    _inherit = ['mtbg.board.mixin', 'mtbg.card.mixin', 'mtbg.sidebar.mixin']
    _description = 'Contact Rule'
    _order = 'sequence, id'

    code = fields.Char(required=True, index=True, copy=False,
                       help="Its key: an extension's rule keeps its code; a rule made here gets one")
    name = fields.Char(required=True, translate=True)
    description = fields.Text(translate=True)
    icon = fields.Char(default='fa-magic')
    sequence = fields.Integer(default=50)
    enabled = fields.Boolean(string='On', default=False, copy=False,
                             help="Off: it never runs (a copy of the database switches every rule off)")
    source = fields.Char(readonly=True, help="The model that announced it (empty: made on this page)")
    ready = fields.Boolean(compute='_compute_ready', help="Its records' model and its source are installed")
    state = fields.Selection([('on', "On"), ('off', "Off"), ('waiting', "Waiting")], compute='_compute_state',
                             store=True, string='Status')
    model_id = fields.Many2one('ir.model', string='Records', required=True, ondelete='cascade',
                               domain=[('transient', '=', False)])
    model_name = fields.Char(related='model_id.model', store=True, string='Model')
    trigger = fields.Selection(TRIGGERS, required=True, default='changed', string='When')
    trigger_field_ids = fields.Many2many('ir.model.fields', 'mtbg_crm_rule_trigger_field_rel', 'rule_id', 'field_id',
                                         string='Fields watched', domain="[('model_id', '=', model_id)]",
                                         help="Created or changed: it runs when one of them changes (none: any)")
    days = fields.Integer(default=0, help="Every day: the days the rule waits (e.g. after an enquiry)")
    action_ids = fields.One2many('mtbg.crm.rule.action', 'rule_id', string='Actions', copy=True)
    once = fields.Boolean(string='Once per record', default=True,
                          help="A record it changed once is left alone afterwards")
    automation_id = fields.Many2one('base.automation', readonly=True, copy=False, ondelete='set null',
                                    help="Odoo's automation rule that runs it (kept by this page)")
    run_ids = fields.One2many('mtbg.crm.rule.run', 'rule_id', string='Runs')
    last_run = fields.Datetime(readonly=True, copy=False)
    touched_count = fields.Integer(compute='_compute_touched_count', string='Records changed')

    _code_unique = models.Constraint('unique(code)', "Each contact rule has its own code.")

    @api.constrains('trigger', 'model_id')
    def _check_received_model(self):
        for rule in self:
            if rule.trigger == 'received' and rule.model_name != 'res.partner':
                raise ValidationError(self.env._("\"A message comes in\" runs on contacts only."))

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    def _compute_ready(self):
        specs = self._mtbg_source_specs()
        for rule in self:
            model_ok = bool(rule.model_name) and rule.model_name in self.env
            rule.ready = model_ok and (not rule.source or rule.code in specs)

    @api.depends('enabled', 'model_name', 'source')
    def _compute_state(self):
        specs = self._mtbg_source_specs()
        for rule in self:
            ready = rule.model_name in self.env and (not rule.source or rule.code in specs)
            rule.state = 'waiting' if not ready else 'on' if rule.enabled else 'off'

    def _compute_touched_count(self):
        groups = self.env['mtbg.crm.rule.change']._read_group(
            [('rule_id', 'in', self.ids), ('dry_run', '=', False), ('undone', '=', False)], ['rule_id'],
            ['res_id:count_distinct'])
        counts = {rule.id: count for rule, count in groups}
        for rule in self:
            rule.touched_count = counts.get(rule.id, 0)

    # ------------------------------------------------------------------
    # Sources
    # ------------------------------------------------------------------
    @api.model
    @tools.ormcache()
    def _mtbg_source_models(self):
        """Names of the models that announce Contact rules (they override ``_mtbg_crm_rule_sources``)."""
        own = Base._mtbg_crm_rule_sources
        return tuple(sorted(name for name in self.env.registry
                            if getattr(type(self.env[name]), '_mtbg_crm_rule_sources', own) is not own))

    @api.model
    def _mtbg_source_specs(self):
        """{code: spec} of every installed source (``source`` added); the first model to announce a code wins."""
        specs = {}
        for name in self._mtbg_source_models():
            for spec in self.env[name]._mtbg_crm_rule_sources() or []:
                if spec.get('code') and spec['code'] not in specs and spec.get('model') in self.env:
                    specs[spec['code']] = dict(spec, source=name)
        return specs

    @api.model
    def _mtbg_sync_sources(self):
        """A rule for each installed source that has none yet (the spec's name, texts and actions, in
        every language of the site); rules already there keep what was changed on them."""
        specs = self._mtbg_source_specs()
        Rule = self.sudo().with_context(active_test=False)
        known = set(Rule.search([]).mapped('code'))
        for code, spec in specs.items():
            if code in known:
                continue
            english = self.env[spec['source']].with_context(lang='en_US')._mtbg_crm_rule_sources()
            spec_en = next((s for s in english if s.get('code') == code), spec)
            rule = Rule.with_context(lang='en_US').create(self._mtbg_spec_vals(spec_en, spec['source']))
            for lang in [c for c, _n in self.env['res.lang'].get_installed() if c != 'en_US']:
                local = next((s for s in self.env[spec['source']].with_context(lang=lang)._mtbg_crm_rule_sources()
                              if s.get('code') == code), None)
                if local:
                    rule.with_context(lang=lang).write({k: local[k] for k in ('name', 'description') if local.get(k)})
                    for line, action in zip(rule.action_ids, local.get('actions') or []):
                        if action.get('summary'):
                            line.with_context(lang=lang).summary = action['summary']
            if rule.enabled:
                rule._mtbg_sync_automation()
        return specs

    @api.model
    def _mtbg_spec_vals(self, spec, source):
        model = self.env['ir.model']._get(spec['model'])
        Fields = self.env['ir.model.fields']

        def field(name):
            return Fields._get(spec['model'], name) if name and name in self.env[spec['model']]._fields else Fields

        actions = []
        for seq, action in enumerate(spec.get('actions') or []):
            vals = {'sequence': seq * 10, 'kind': action['kind'], 'value': action.get('value') or False,
                    'fill_empty': action.get('fill_empty', True), 'summary': action.get('summary') or False,
                    'days': action.get('days') or 0, 'match_on': action.get('match_on') or 'both',
                    'field_id': field(action.get('field')).id or False}
            actions.append((0, 0, vals))
        return {
            'code': spec['code'], 'name': spec.get('name') or spec['code'], 'description': spec.get('description'),
            'icon': spec.get('icon') or 'fa-magic', 'sequence': spec.get('sequence', 50), 'source': source,
            'enabled': spec.get('enabled', False), 'model_id': model.id, 'trigger': spec.get('trigger') or 'changed',
            'trigger_field_ids': [(6, 0, [field(f).id for f in spec.get('fields') or [] if field(f)])],
            'days': spec.get('days') or 0, 'once': spec.get('once', True),
            'action_ids': actions,
        }

    def _mtbg_spec(self):
        self.ensure_one()
        return self._mtbg_source_specs().get(self.code) if self.source else None

    # ------------------------------------------------------------------
    # Odoo's automation rule underneath (created / changed)
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('code'):
                vals['code'] = 'rule_%s' % fields.Datetime.now().strftime('%Y%m%d%H%M%S%f')
        rules = super().create(vals_list)
        rules.filtered('enabled')._mtbg_sync_automation()
        return rules

    def write(self, vals):
        result = super().write(vals)
        if {'enabled', 'trigger', 'trigger_field_ids', 'model_id', 'name'} & set(vals):
            self._mtbg_sync_automation()
        if 'enabled' in vals:
            for rule in self:
                rule._mtbg_switched()
        return result

    def unlink(self):
        automations = self.automation_id
        result = super().unlink()
        automations.sudo().unlink()
        return result

    def _mtbg_switched(self):
        """A source may act when its rule is switched on or off (``on_switch``: a method called with the rule)."""
        spec = self._mtbg_spec()
        if spec and spec.get('on_switch'):
            getattr(self.env[spec['source']].sudo(), spec['on_switch'])(self)

    def _mtbg_sync_automation(self):
        """Keep the hidden automation rule in step: on (created / changed) runs it; off or daily: none or off."""
        for rule in self.sudo():
            wanted = rule.enabled and rule.ready and rule.trigger in ('created', 'changed')
            automation = rule.automation_id
            if not wanted:
                if automation:
                    automation.active = False
                continue
            vals = {
                'name': f"contact rule: {rule.with_context(lang='en_US').name}", 'model_id': rule.model_id.id,
                'trigger': 'on_create' if rule.trigger == 'created' else 'on_create_or_write',
                'active': True,
            }
            if automation:
                automation.write(vals)
            else:
                automation = self.env['base.automation'].sudo().create(vals)
                self.env['ir.model.data'].sudo().create({
                    'module': 'mtbg_tours_crm_rules', 'name': f"automation_{rule.id}", 'model': 'base.automation',
                    'res_id': automation.id, 'noupdate': True})
                rule.automation_id = automation
            automation.trigger_field_ids = [(6, 0, rule.trigger_field_ids.ids if rule.trigger == 'changed' else [])]
            code = f"env['mtbg.crm.rule'].browse({rule.id})._mtbg_run_on(records, '{rule.trigger}')"
            action = automation.action_server_ids[:1]
            if action:
                action.write({'code': code, 'model_id': rule.model_id.id})
            else:
                self.env['ir.actions.server'].sudo().create({
                    'name': f"contact rule {rule.code}", 'model_id': rule.model_id.id, 'state': 'code', 'code': code,
                    'usage': 'base_automation', 'base_automation_id': automation.id})

    # ------------------------------------------------------------------
    # Board and side bar
    # ------------------------------------------------------------------
    @api.model
    def _mtbg_board_field_colors(self):
        return dict(super()._mtbg_board_field_colors(), state=STATE_COLORS)

    def _mtbg_board_dates(self):
        self.ensure_one()
        return False, False

    def _mtbg_board_cancelled(self):
        self.ensure_one()
        return self.state == 'waiting'

    @api.model
    def _mtbg_sidebar_sections(self, domain):
        _ = self.env._
        return super()._mtbg_sidebar_sections(domain) + [
            {'key': 'state', 'label': _("Status"), 'icon': 'fa-toggle-on',
             'nodes': self._mtbg_sidebar_field(domain, 'state', colors=STATE_COLORS)},
            {'key': 'trigger', 'label': _("When"), 'icon': 'fa-bolt',
             'nodes': self._mtbg_sidebar_field(domain, 'trigger')},
            {'key': 'model', 'label': _("Records"), 'icon': 'fa-address-book-o',
             'nodes': self._mtbg_sidebar_field(domain, 'model_id')},  # the many2one: Core groups by it (not the Char)
        ]

    @api.model
    def _mtbg_settings_xmlid(self):
        return 'mtbg_tours_crm_rules.action_crm_rule_settings'

    @api.model
    def _mtbg_card_fields(self):
        _ = self.env._
        return [
            {'key': 'when', 'label': _("When"), 'icon': 'fa-bolt'},
            {'key': 'records', 'label': _("Records"), 'icon': 'fa-address-book-o'},
            {'key': 'actions', 'label': _("Actions"), 'icon': 'fa-magic'},
            {'key': 'last_run', 'label': _("Last run"), 'icon': 'fa-clock-o', 'show': False},
            {'key': 'touched', 'label': _("Records changed"), 'icon': 'fa-pencil', 'show': False},
        ]

    @api.model
    def _mtbg_card_default_look(self):
        return dict(super()._mtbg_card_default_look(), pill_status=True)

    @api.model
    def _mtbg_card_samples(self):
        return self.search([], limit=40)

    @api.model
    def _mtbg_card_sample_values(self):
        _ = self.env._
        return {
            'titles': {'name': _("Possible duplicates by phone or email")}, 'image': '',
            'status': {'text': _("On"), 'level': 'success'},
            'lines': {'when': _("Created or changed"), 'records': _("Contact"), 'actions': _("Flag possible duplicates"),
                      'last_run': '25 Oct 2026', 'touched': '12'},
            'notices': [],
        }

    def _mtbg_card_values(self):
        values = super()._mtbg_card_values()
        triggers = dict(self._fields['trigger']._description_selection(self.env))
        states = dict(self._fields['state']._description_selection(self.env))
        kinds = dict(self.env['mtbg.crm.rule.action']._fields['kind']._description_selection(self.env))
        notices = []
        if self.state == 'waiting':
            notices.append({'level': 'warning', 'text': self.env._("Waits for its extension")})
        values.update({
            'titles': {'name': self.name or ''}, 'image': '',
            'status': {'text': states.get(self.state, ''),
                       'level': {'on': 'success', 'off': 'muted', 'waiting': 'warning'}.get(self.state, 'muted')},
            'lines': {'when': triggers.get(self.trigger, ''), 'records': self.model_id.name or '',
                      'actions': ", ".join(kinds.get(a.kind, '') for a in self.action_ids)
                      or (self.env._("Its own") if self.source else ''),
                      'last_run': self._mtbg_card_day(self.last_run.date()) if self.last_run else '',
                      'touched': str(self.touched_count or '')},
            'notices': notices,
        })
        return values

    # ------------------------------------------------------------------
    # The page's buttons
    # ------------------------------------------------------------------
    def action_mtbg_dry_run(self):
        """What it would change now (on the records a daily run takes, or the last 200 records), changing nothing."""
        self.ensure_one()
        if not self.ready:
            raise UserError(self.env._("This rule waits for its extension or its records' model."))
        run = self._mtbg_run(self._mtbg_dry_records(), 'dry', dry=True)
        return run.action_mtbg_open()

    def action_mtbg_run_now(self):
        """Run it now on the records a daily run takes (or the last 200 records): the changes are made and logged."""
        self.ensure_one()
        if not (self.enabled and self.ready):
            raise UserError(self.env._("Switch the rule on first."))
        run = self._mtbg_run(self._mtbg_dry_records(), 'manual')
        return run.action_mtbg_open()

    def action_mtbg_runs(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': self.env._("Runs: %s", self.name),
                'res_model': 'mtbg.crm.rule.run', 'view_mode': 'list,form', 'domain': [('rule_id', '=', self.id)]}

    def action_mtbg_changes(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': self.env._("Changes: %s", self.name),
                'res_model': 'mtbg.crm.rule.change', 'view_mode': 'list,form',
                'domain': [('rule_id', '=', self.id), ('dry_run', '=', False)]}

    def _mtbg_dry_records(self):
        """The records a manual run or a dry run looks at."""
        if self.trigger == 'received':
            partners = self.env['mtbg.crm.rule.inbox'].sudo().search([], limit=200).partner_id
            return partners or self.env['res.partner'].search([('phone', '!=', False)], order='id desc', limit=200)
        if self.trigger == 'daily':
            return self.env[self.model_name]
        return self.env[self.model_name].search([], order='id desc', limit=200)

    # ------------------------------------------------------------------
    # Daily
    # ------------------------------------------------------------------
    @api.model
    def _cron_mtbg_daily(self):
        for rule in self.search([('enabled', '=', True), ('trigger', '=', 'daily')]):
            if not rule.ready:
                continue
            try:
                with self.env.cr.savepoint():
                    rule._mtbg_run(self.env[rule.model_name], 'daily')
            except Exception as error:  # noqa: BLE001  one rule's failure never stops the others
                _logger.exception("contact rule %s failed", rule.code)
                self.env['mtbg.crm.rule.run'].create({'rule_id': rule.id, 'trigger': 'daily',
                                                      'error': str(error)[:1000]})

    # ------------------------------------------------------------------
    # A message comes in
    # ------------------------------------------------------------------
    @api.model
    def _mtbg_message_received(self, partner, phone=None, channel=None):
        """A message from this contact came in (from its number, on that channel): queued for the rules that run
        when a message comes in (the cron takes it within minutes). Cheap and safe to call from a channel's hook: it
        only creates a queue row."""
        if not partner:
            return
        self.env['mtbg.crm.rule.inbox'].sudo().create({'partner_id': partner.id, 'phone': phone or False,
                                                       'channel': channel or False})

    @api.model
    def _cron_mtbg_received(self):
        Inbox = self.env['mtbg.crm.rule.inbox'].sudo()
        rows = Inbox.search([('done', '=', False)], order='id', limit=500)
        if rows:
            phones = {}
            for row in rows:
                if row.phone:
                    phones[row.partner_id.id] = row.phone
            partners = rows.partner_id.exists()
            for rule in self.search([('enabled', '=', True), ('trigger', '=', 'received')]):
                if not rule.ready:
                    continue
                try:
                    with self.env.cr.savepoint():
                        rule.with_context(mtbg_crm_phones=phones)._mtbg_run(partners, 'received')
                except Exception as error:  # noqa: BLE001  one rule's failure never stops the others
                    _logger.exception("contact rule %s failed", rule.code)
                    self.env['mtbg.crm.rule.run'].create({'rule_id': rule.id, 'trigger': 'received',
                                                          'error': str(error)[:1000]})
            rows.done = True
        Inbox.search([('done', '=', True), ('create_date', '<', fields.Datetime.now() - timedelta(days=7))]).unlink()

    # ------------------------------------------------------------------
    # Running
    # ------------------------------------------------------------------
    def _mtbg_run_on(self, records, trigger):
        """Called by the automation rule (created / changed) on the records concerned."""
        rule = self.sudo()
        if not (rule.exists() and rule.enabled and rule.ready) or self.env.context.get('mtbg_crm_rule_running'):
            return
        records = records.exists()
        if records:
            rule._mtbg_run(records.sudo(), trigger)

    def _mtbg_touched_ids(self, model):
        changes = self.env['mtbg.crm.rule.change'].search([('rule_id', '=', self.id), ('res_model', '=', model),
                                                           ('dry_run', '=', False)])
        return set(changes.mapped('res_id'))

    def _mtbg_run(self, records, trigger, dry=False):
        """Act on the records (its own logic, or its actions): a run, its changes logged."""
        self.ensure_one()
        rule = self.sudo().with_context(mtbg_crm_rule_running=True)
        records = records.sudo().with_context(mtbg_crm_rule_running=True)
        run = self.env['mtbg.crm.rule.run'].sudo().create({'rule_id': rule.id, 'trigger': trigger, 'dry_run': dry})
        spec = rule._mtbg_spec()
        planned = None
        if spec and spec.get('run'):
            found = getattr(self.env[spec['source']].sudo().with_context(mtbg_crm_rule_running=True),
                            spec['run'])(rule, records)
            if isinstance(found, list):
                planned = found
                records = self.env[rule.model_name].browse([c['record'].id for c in found])
            else:
                records = found
        elif trigger == 'daily' and not records:
            records = self.env[rule.model_name].search([], order='id desc', limit=1000)
        checked = len(records)
        if rule.once:
            touched = rule._mtbg_touched_ids(rule.model_name)
            records = records.filtered(lambda r: r.id not in touched)
        passed = records
        Change = self.env['mtbg.crm.rule.change'].sudo()
        changes = Change
        if planned is not None:
            for item in planned:
                record = item['record']
                if record in passed:
                    changes |= Change._mtbg_set_values(run, record, item['values'], fill_empty=item.get(
                        'fill_empty', True), dry=dry)
        else:
            for record in passed:
                for action in rule.action_ids:
                    changes |= action._mtbg_apply(run, record, dry=dry)
        run.write({'checked': checked, 'matched': len(passed), 'changed': len(set(changes.mapped('res_id')))})
        if not dry:
            rule.last_run = fields.Datetime.now()
        return run


class MtbgCrmRuleInbox(models.Model):
    _name = 'mtbg.crm.rule.inbox'
    _description = 'Contact Rules: messages received'
    _order = 'id desc'

    partner_id = fields.Many2one('res.partner', required=True, ondelete='cascade', index=True)
    phone = fields.Char(help="The number the message came from")
    channel = fields.Char()
    done = fields.Boolean(index=True)


class MtbgCrmRuleAction(models.Model):
    _name = 'mtbg.crm.rule.action'
    _description = 'Contact Rule Action'
    _order = 'sequence, id'

    rule_id = fields.Many2one('mtbg.crm.rule', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    model_id = fields.Many2one(related='rule_id.model_id')
    kind = fields.Selection(ACTIONS, required=True, default='set_field', string='Action')
    field_id = fields.Many2one('ir.model.fields', string='Field', ondelete='cascade',
                               domain="[('model_id', '=', model_id), ('store', '=', True), ('readonly', '=', False)]",
                               help="Set a field: the field; a tag: the tags field (e.g. Tags)")
    value = fields.Char(help="Set a field: the value (a related record by its name); a tag: its name; "
                             "a note or an alert: its text")
    fill_empty = fields.Boolean(string='Only when empty', default=True,
                                help="Set a field / a salesperson: only records where it is empty")
    user_id = fields.Many2one('res.users', string='Salesperson / to-do for', domain=[('share', '=', False)])
    summary = fields.Char(translate=True, help="A to-do: its summary")
    days = fields.Integer(help="A to-do: due in so many days")
    activity_type_id = fields.Many2one('mail.activity.type', string='To-do type')
    match_on = fields.Selection([('both', "Phone or email"), ('phone', "Phone"), ('email', "Email")],
                                default='both', string='Duplicates by')

    def _mtbg_apply(self, run, record, dry=False):
        """This action on one record: the changes it made (or would make), logged."""
        Change = self.env['mtbg.crm.rule.change'].sudo()
        kind = self.kind
        if kind == 'set_field' and self.field_id:
            return Change._mtbg_set_values(run, record, {self.field_id.name: self._mtbg_value(record)},
                                           fill_empty=self.fill_empty, dry=dry)
        if kind == 'assign_salesperson' and 'user_id' in record._fields and self.user_id:
            return Change._mtbg_set_values(run, record, {'user_id': self.user_id.id}, fill_empty=self.fill_empty,
                                           dry=dry)
        if kind in ('add_tag', 'remove_tag'):
            return Change._mtbg_tag(run, record, self._mtbg_tag_field(record), self.value, kind == 'add_tag', dry)
        if kind == 'activity' and hasattr(record, 'activity_schedule'):
            return Change._mtbg_activity(run, record, self, dry)
        if kind == 'note' and hasattr(record, 'message_post') and self.value:
            return Change._mtbg_note(run, record, self.value, dry)
        if kind == 'flag_duplicate':
            return self.env['mtbg.crm.duplicate'].sudo()._mtbg_flag(run, record, self.match_on, dry)
        if kind == 'raise_alert':
            return Change._mtbg_log(run, record, 'alert', note=self.value or run.rule_id.name, dry=dry)
        return Change

    def _mtbg_tag_field(self, record):
        if self.field_id and self.field_id.ttype == 'many2many':
            return self.field_id.name
        return next((n for n in ('category_id', 'tag_ids') if n in record._fields
                     and record._fields[n].type == 'many2many'), None)

    def _mtbg_value(self, record):
        """The value as the field takes it."""
        field = record._fields[self.field_id.name]
        value = self.value
        if field.type == 'many2one':
            if not value:
                return False
            comodel = self.env[field.comodel_name]
            found = comodel.search([('display_name', '=ilike', value)], limit=1) if value else comodel
            if not found and value.isdigit():
                found = comodel.browse(int(value)).exists()
            return found.id or False
        if field.type == 'boolean':
            return str(value).strip().lower() in ('1', 'true', 'yes', 'si', 'sí')
        if field.type == 'integer':
            return int(float(value or 0))
        if field.type in ('float', 'monetary'):
            return float(value or 0)
        if field.type == 'selection':
            keys = dict(field._description_selection(self.env))
            return value if value in keys else next((k for k, v in keys.items() if v == value), False)
        if field.type == 'date':
            return fields.Date.to_date(value) if value else False
        return value or False


def _plain(record, name):
    """A field's value as kept in the log (JSON): an id for a related record, ids for tags."""
    field = record._fields[name]
    value = record[name]
    if field.type == 'many2one':
        return value.id or False
    if field.type in ('many2many', 'one2many'):
        return value.ids
    if field.type in ('date', 'datetime'):
        return str(value) if value else False
    return value


def _empty(value):
    return value in (False, None, '', 0, [], 0.0)


class MtbgCrmRuleRun(models.Model):
    _name = 'mtbg.crm.rule.run'
    _description = 'Contact Rule Run'
    _order = 'id desc'

    rule_id = fields.Many2one('mtbg.crm.rule', required=True, ondelete='cascade', index=True)
    date = fields.Datetime(default=fields.Datetime.now, required=True)
    trigger = fields.Selection([('created', "Created"), ('changed', "Changed"), ('received', "Message"),
                                ('daily', "Daily"), ('manual', "Run now"), ('dry', "Dry run")], required=True)
    dry_run = fields.Boolean()
    checked = fields.Integer(string='Records checked')
    matched = fields.Integer(string='Records acted on')
    changed = fields.Integer(string='Records changed')
    error = fields.Text()
    change_ids = fields.One2many('mtbg.crm.rule.change', 'run_id', string='Changes')

    def _compute_display_name(self):
        for run in self:
            run.display_name = f"{run.rule_id.name} · {fields.Datetime.to_string(run.date)}"

    def action_mtbg_open(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id, 'view_mode': 'form',
                'name': self.env._("Dry run") if self.dry_run else self.env._("Run"), 'target': 'new'}

    def action_mtbg_undo(self):
        self.change_ids.filtered(lambda c: not c.undone and not c.dry_run).action_mtbg_undo()


class MtbgCrmRuleChange(models.Model):
    _name = 'mtbg.crm.rule.change'
    _description = 'Contact Rule Change'
    _order = 'id desc'

    run_id = fields.Many2one('mtbg.crm.rule.run', required=True, ondelete='cascade', index=True)
    rule_id = fields.Many2one('mtbg.crm.rule', required=True, ondelete='cascade', index=True)
    dry_run = fields.Boolean(related='run_id.dry_run', store=True)
    date = fields.Datetime(related='run_id.date', store=True)
    res_model = fields.Char(required=True, index=True)
    res_id = fields.Many2oneReference(model_field='res_model', required=True, index=True)
    res_name = fields.Char(string='Record')
    kind = fields.Selection([('field', "Field"), ('tag_add', "Tag added"), ('tag_remove', "Tag removed"),
                             ('activity', "To-do"), ('note', "Note"), ('duplicate', "Possible duplicate"),
                             ('alert', "Alert")], required=True)
    field_name = fields.Char(string='Field')
    field_label = fields.Char(string='Field label')
    old_value = fields.Json()
    new_value = fields.Json()
    old_text = fields.Char(string='Before')
    new_text = fields.Char(string='After')
    note = fields.Char()
    ref_id = fields.Integer(help="The to-do, note or duplicate flag made")
    undone = fields.Boolean(readonly=True)
    resolved = fields.Boolean(help="An alert: dealt with (it leaves the Alert Feed)")

    @api.model
    def _mtbg_base(self, run, record):
        return {'run_id': run.id, 'rule_id': run.rule_id.id, 'res_model': record._name, 'res_id': record.id,
                'res_name': record.display_name}

    @api.model
    def _mtbg_text(self, record, name, value):
        field = record._fields[name]
        if field.type == 'many2one':
            return self.env[field.comodel_name].browse(value).display_name if value else ''
        if field.type == 'many2many':
            return ", ".join(self.env[field.comodel_name].browse(value).mapped('display_name'))
        if field.type == 'selection':
            return dict(field._description_selection(self.env)).get(value, value or '')
        return '' if value in (False, None) else str(value)

    @api.model
    def _mtbg_set_values(self, run, record, values, fill_empty=True, dry=False):
        """Field changes (only empty fields with ``fill_empty``; unchanged values skipped), logged with what was
        there."""
        changes = self
        write = {}
        for name, value in values.items():
            if name not in record._fields:
                continue
            old = _plain(record, name)
            if fill_empty and not _empty(old):
                continue
            new = value.id if isinstance(value, models.BaseModel) else value
            new = str(new) if hasattr(new, 'isoformat') else new
            if old == new or (_empty(old) and _empty(new)):
                continue
            write[name] = new
            changes |= self.create(dict(self._mtbg_base(run, record), kind='field', field_name=name,
                                        field_label=record._fields[name].get_description(self.env)['string'],
                                        old_value=old, new_value=new, old_text=self._mtbg_text(record, name, old),
                                        new_text=self._mtbg_text(record, name, new)))
        if write and not dry:
            record.write(write)
        return changes

    @api.model
    def _mtbg_tag(self, run, record, field_name, name, add, dry):
        if not field_name or not name:
            return self
        comodel = self.env[record._fields[field_name].comodel_name]
        tag = comodel.search([('name', '=ilike', name)], limit=1)
        has = tag and tag in record[field_name]
        if (add and has) or (not add and not has):
            return self
        if not tag:
            if dry:
                tag_id = 0
            else:
                tag = comodel.browse(comodel.name_create(name)[0])
                tag_id = tag.id
        else:
            tag_id = tag.id
        if not dry:
            record.write({field_name: [(4 if add else 3, tag_id)]})
        return self.create(dict(self._mtbg_base(run, record), kind='tag_add' if add else 'tag_remove',
                                field_name=field_name, new_value=tag_id, new_text=name))

    @api.model
    def _mtbg_activity(self, run, record, action, dry):
        user = action.user_id or ('user_id' in record._fields and record.user_id) or self.env.user
        summary = action.summary or run.rule_id.name
        ref = 0
        if not dry:
            kind = action.activity_type_id or self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
            activity = record.activity_schedule(
                activity_type_id=kind.id if kind else False, summary=summary, user_id=user.id,
                date_deadline=fields.Date.context_today(self) + timedelta(days=action.days or 0))
            ref = activity.id
        return self.create(dict(self._mtbg_base(run, record), kind='activity', note=summary, ref_id=ref,
                                new_text=user.name))

    @api.model
    def _mtbg_note(self, run, record, body, dry):
        ref = 0
        if not dry:
            ref = record.message_post(body=body, subtype_xmlid='mail.mt_note').id
        return self.create(dict(self._mtbg_base(run, record), kind='note', note=body[:250], ref_id=ref))

    @api.model
    def _mtbg_log(self, run, record, kind, note=False, ref_id=0, dry=False):
        return self.create(dict(self._mtbg_base(run, record), kind=kind, note=note, ref_id=ref_id))

    def action_mtbg_open_record(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': self.res_model, 'res_id': self.res_id,
                'view_mode': 'form'}

    def action_mtbg_undo(self):
        """Put back what the rule changed: a field (only if nobody changed it since), a tag, a to-do, a note, a
        duplicate flag."""
        for change in self.sudo().filtered(lambda c: not c.undone and not c.dry_run):
            record = self.env[change.res_model].browse(change.res_id).exists().sudo() \
                if change.res_model in self.env else None
            if record is None or not record:
                change.undone = True
                continue
            if change.kind == 'field':
                if _plain(record, change.field_name) != change.new_value:
                    raise UserError(self.env._("%(record)s: %(field)s was changed since; it is left as it is.",
                                               record=change.res_name, field=change.field_label))
                record.with_context(mtbg_crm_rule_running=True).write({change.field_name: change.old_value})
            elif change.kind in ('tag_add', 'tag_remove') and change.new_value:
                record.with_context(mtbg_crm_rule_running=True).write(
                    {change.field_name: [(3 if change.kind == 'tag_add' else 4, change.new_value)]})
            elif change.kind == 'activity' and change.ref_id:
                self.env['mail.activity'].browse(change.ref_id).exists().unlink()
            elif change.kind == 'note' and change.ref_id:
                self.env['mail.message'].browse(change.ref_id).exists().unlink()
            elif change.kind == 'duplicate' and change.ref_id:
                self.env['mtbg.crm.duplicate'].browse(change.ref_id).exists().unlink()
            change.undone = True
        return True


class MtbgCrmDuplicate(models.Model):
    _name = 'mtbg.crm.duplicate'
    _description = 'Possible Duplicate'
    _order = 'id desc'

    rule_id = fields.Many2one('mtbg.crm.rule', ondelete='set null', index=True)
    res_model = fields.Char(required=True, index=True)
    res_id = fields.Many2oneReference(model_field='res_model', required=True, index=True)
    other_id = fields.Many2oneReference(model_field='res_model', required=True, index=True)
    res_name = fields.Char(string='Record')
    other_name = fields.Char(string='Same as')
    reason = fields.Selection([('phone', "Same phone"), ('email', "Same email")], required=True)
    value = fields.Char(string='Shared')
    state = fields.Selection([('open', "To check"), ('same', "Same person (merge by hand)"),
                              ('different', "Different people")], default='open', required=True)

    _pair_unique = models.Constraint('unique(res_model, res_id, other_id, reason)', "This pair is flagged already.")

    @api.model
    def _mtbg_keys(self, record, match_on):
        """(reason, normalised value) of a record: the phone's digits (last 8 at least), the email lower-cased."""
        keys = []
        if match_on in ('both', 'phone'):
            phone = next((record[n] for n in ('phone', 'mobile', 'phone_sanitized') if n in record._fields
                          and record[n]), '')
            digits = ''.join(ch for ch in str(phone) if ch.isdigit())
            if len(digits) >= 8:
                keys.append(('phone', digits[-8:]))
        if match_on in ('both', 'email'):
            email = next((record[n] for n in ('email', 'email_from') if n in record._fields and record[n]), '')
            email = tools.email_normalize(email) if email else False
            if email:
                keys.append(('email', email))
        return keys

    @api.model
    def _mtbg_others(self, record, reason, value):
        Model = self.env[record._name].with_context(active_test=True)
        if reason == 'email':
            field = 'email' if 'email' in record._fields else 'email_from'
            found = Model.search([(field, '=ilike', value), ('id', '!=', record.id)], limit=20)
            return found.filtered(lambda r: tools.email_normalize(r[field] or '') == value)
        field = 'phone' if 'phone' in record._fields else 'phone_sanitized'
        found = Model.search([(field, 'like', value[-4:]), ('id', '!=', record.id)], limit=200)
        return found.filtered(lambda r: ''.join(ch for ch in str(r[field] or '') if ch.isdigit())[-8:] == value)

    @api.model
    def _mtbg_flag(self, run, record, match_on, dry):
        """A flag for each other record with the same phone or email (never merged): logged as changes."""
        Change = self.env['mtbg.crm.rule.change'].sudo()
        changes = Change
        if record._name == 'res.partner' and (record.parent_id or not record.active):
            return changes
        for reason, value in self._mtbg_keys(record, match_on):
            for other in self._mtbg_others(record, reason, value):
                if record._name == 'res.partner' and (other.parent_id == record or record.parent_id == other
                                                      or other.commercial_partner_id == record.commercial_partner_id):
                    continue
                low, high = sorted((record.id, other.id))
                exists = self.search_count([('res_model', '=', record._name), ('res_id', '=', low),
                                            ('other_id', '=', high), ('reason', '=', reason)])
                if exists:
                    continue
                ref = 0
                if not dry:
                    first, second = self.env[record._name].browse([low, high])
                    ref = self.create({'rule_id': run.rule_id.id, 'res_model': record._name, 'res_id': low,
                                       'other_id': high, 'res_name': first.display_name,
                                       'other_name': second.display_name, 'reason': reason, 'value': value}).id
                changes |= Change._mtbg_log(run, record, 'duplicate', note=f"{other.display_name} ({value})",
                                            ref_id=ref)
        return changes

    def action_mtbg_open_record(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': self.res_model, 'res_id': self.res_id,
                'view_mode': 'form'}

    def action_mtbg_open_other(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': self.res_model, 'res_id': self.other_id,
                'view_mode': 'form'}

    def action_mtbg_same(self):
        self.state = 'same'

    def action_mtbg_different(self):
        self.state = 'different'
