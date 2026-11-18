"""0.3.0 (owner, 2026-11-18: contact rules go global): the Tours parts go to the Alert Feed (mtbg_tours_alerts 0.4.0),
which brings them from now on: the Tours menus (Operations > Possible Duplicates, Configuration > Rules & Alerts), the
Rules & Alerts page action and the Tours groups' access. Their xml ids are handed over before this version's data is
loaded, so the records stay as they are (same ids: the Menu Designer's changes, the menu presets) and the end of the
update does not delete them while the Alert Feed is still on its older version."""
import logging

_logger = logging.getLogger(__name__)

GLUE = 'mtbg_tours_alerts'
HANDED_OVER = (
    'menu_crm_duplicate', 'menu_crm_rule', 'action_crm_rule_page',
    'access_crm_rule_user', 'access_crm_rule_manager', 'access_crm_rule_action_user',
    'access_crm_rule_action_manager', 'access_crm_rule_run_user', 'access_crm_rule_run_manager',
    'access_crm_rule_change_user', 'access_crm_rule_change_manager', 'access_crm_duplicate_user',
    'access_crm_duplicate_manager', 'access_crm_rule_inbox_manager',
)


def migrate(cr, version):
    cr.execute("SELECT 1 FROM ir_module_module WHERE name = %s AND state IN ('installed', 'to upgrade', 'to install')",
               [GLUE])
    if not cr.fetchone():
        return  # no Tours: these records go with the update (the module's own menu and access replace them)
    cr.execute("""
        UPDATE ir_model_data d SET module = %s
         WHERE d.module = 'mtbg_tours_crm_rules' AND d.name = ANY(%s)
           AND NOT EXISTS (SELECT 1 FROM ir_model_data o WHERE o.module = %s AND o.name = d.name)
    """, [GLUE, list(HANDED_OVER), GLUE])
    moved = cr.rowcount
    cr.execute("SELECT to_regclass('mtbg_menu_override')")
    if cr.fetchone()[0]:  # the Menu Designer's changes keep the menu's xml id (to find it again after a reinstall)
        for name in ('menu_crm_duplicate', 'menu_crm_rule'):
            cr.execute("UPDATE mtbg_menu_override SET menu_xmlid = %s WHERE menu_xmlid = %s",
                       ['%s.%s' % (GLUE, name), 'mtbg_tours_crm_rules.%s' % name])
    _logger.info("Contact Rules 0.3.0: %s Tours records handed over to %s", moved, GLUE)
