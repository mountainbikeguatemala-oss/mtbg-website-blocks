"""19.0.0.3.10: one Name field (the owner: never first and last name apart). In every website form, First name and
Last name become one Name block (the first one's place and show rule, required when either was; a label still the
old default becomes "Name" / "Nombre"), and rules on either answer test the name."""
from odoo import SUPERUSER_ID, api

OLD_LABELS = {'First name', 'Last name', ''}


def _rule(rule):
    """The rule with field:first_name / field:last_name conditions on field:name (once)."""
    if not isinstance(rule, dict) or not rule.get('conditions'):
        return rule
    conditions, seen = [], set()
    for condition in rule['conditions']:
        if condition.get('subject') in ('field:first_name', 'field:last_name'):
            condition = dict(condition, subject='field:name')
        marker = (condition.get('subject'), condition.get('op'), condition.get('value'))
        if marker not in seen:
            seen.add(marker)
            conditions.append(condition)
    return dict(rule, conditions=conditions)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {'active_test': False})
    own_pages = env['mtbg.form.designer']._mtbg_own_page_handlers()
    for form in env['mtbg.form'].search([('handler', 'not in', own_pages)]):
        blocks = form.block_ids
        first = blocks.filtered(lambda b: b.key == 'first_name')[:1]
        last = blocks.filtered(lambda b: b.key == 'last_name')[:1]
        keep = first or last
        if not keep or blocks.filtered(lambda b: b.key == 'name'):
            continue
        required = 'always' if 'always' in (first | last).mapped('require_mode') else keep.require_mode
        keep.write({'key': 'name', 'width': 'full', 'require_mode': required})
        if (keep.with_context(lang='en_US').label or '') in OLD_LABELS:
            keep.with_context(lang='en_US').label = 'Name'
            if env['res.lang']._lang_get('es_ES'):
                keep.update_field_translations('label', {'es_ES': 'Nombre'})
        gone = (first | last) - keep
        if gone:
            env['ir.model.data'].search([('model', '=', 'mtbg.form.block'), ('res_id', 'in', gone.ids)]).unlink()
            gone.unlink()
        for block in form.block_ids:
            if block.show_rule or block.require_rule:
                block.write({'show_rule': _rule(block.show_rule), 'require_rule': _rule(block.require_rule)})
