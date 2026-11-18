"""The Contact rules page (its Contact rules and Changes tabs; with Tours, on the Alert Feed's page): what the page reads
and saves. Who changes them: the admin look's managers (administrators; with Tours, its managers)."""
from odoo import api, fields, models
from odoo.exceptions import UserError


class MtbgCrmRule(models.Model):
    _inherit = 'mtbg.crm.rule'

    def _check_manager(self):
        if not self.env.user._mtbg_ui_manager():
            raise UserError(self.env._("Only managers change the Contact rules."))

    def _mtbg_page_rule(self):
        triggers = dict(self._fields['trigger']._description_selection(self.env))
        kinds = dict(self.env['mtbg.crm.rule.action']._fields['kind']._description_selection(self.env))
        return {
            'id': self.id, 'code': self.code, 'name': self.name, 'description': self.description or '',
            'icon': self.icon or 'fa-magic', 'enabled': self.enabled, 'ready': self.ready,
            'source': self.source or '', 'trigger': self.trigger, 'trigger_label': triggers.get(self.trigger, ''),
            'days': self.days, 'model': self.model_name,
            'actions': [kinds.get(a.kind, '') for a in self.action_ids],
            'touched': self.touched_count, 'last_run': fields.Datetime.to_string(self.last_run) or '',
        }

    @api.model
    def mtbg_get_crm_rules(self):
        """Everything the Contact rules tab shows: the rules by the records they look at (contacts, leads...)."""
        self._mtbg_sync_sources()
        rules = self.sudo().search([])
        groups = []
        for model in dict.fromkeys(rules.mapped('model_name')):
            mine = rules.filtered(lambda r: r.model_name == model)
            groups.append({'model': model, 'name': mine[:1].model_id.name,
                           'rules': [r._mtbg_page_rule() for r in mine]})
        return {'groups': groups, 'can_edit': self.env.user._mtbg_ui_manager()}

    @api.model
    def mtbg_save_crm_rule(self, rule_id, values):
        """Change a rule from the page: on/off, its days."""
        self._check_manager()
        vals = {k: v for k, v in values.items() if k in ('enabled', 'days')}
        if 'days' in vals:
            vals['days'] = max(int(vals['days'] or 0), 0)
        self.sudo().browse(int(rule_id)).write(vals)
        return self.mtbg_get_crm_rules()

    @api.model
    def mtbg_crm_dry_run(self, rule_id):
        """What the rule would change now (changing nothing): the counts and the first 50 changes."""
        self._check_manager()
        rule = self.sudo().browse(int(rule_id))
        if not rule.ready:
            raise UserError(self.env._("This rule waits for its extension or its records' model."))
        run = rule._mtbg_run(rule._mtbg_dry_records(), 'dry', dry=True)
        result = {'checked': run.checked, 'matched': run.matched, 'changed': run.changed,
                  'changes': [c._mtbg_page_change() for c in run.change_ids[:50]]}
        run.unlink()
        return result

    @api.model
    def mtbg_get_crm_changes(self, limit=200):
        """The latest changes the rules made (newest first)."""
        changes = self.env['mtbg.crm.rule.change'].sudo().search([('dry_run', '=', False)], limit=int(limit))
        return {'changes': [c._mtbg_page_change() for c in changes],
                'can_edit': self.env.user._mtbg_ui_manager()}

    @api.model
    def mtbg_undo_crm_changes(self, change_ids):
        self._check_manager()
        self.env['mtbg.crm.rule.change'].sudo().browse([int(i) for i in change_ids]).action_mtbg_undo()
        return self.mtbg_get_crm_changes()

    @api.model
    def mtbg_resolve_crm_alert(self, change_id):
        self._check_manager()
        self.env['mtbg.crm.rule.change'].sudo().browse(int(change_id)).resolved = True
        return self.mtbg_get_crm_changes()


class MtbgCrmRuleChange(models.Model):
    _inherit = 'mtbg.crm.rule.change'

    def _mtbg_page_change(self):
        kinds = dict(self._fields['kind']._description_selection(self.env))
        return {'id': self.id, 'rule': self.rule_id.name, 'date': fields.Datetime.to_string(self.date) or '',
                'res_model': self.res_model, 'res_id': self.res_id, 'record': self.res_name or '',
                'kind': self.kind, 'kind_label': kinds.get(self.kind, ''), 'field': self.field_label or '',
                'before': self.old_text or '', 'after': self.new_text or '', 'note': self.note or '',
                'undone': self.undone, 'resolved': self.resolved}
