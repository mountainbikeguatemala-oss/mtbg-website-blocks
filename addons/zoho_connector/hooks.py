"""Taking over from the Tours' Zoho extension (2026-11-11, the Zoho connector split): its models, their fields and
records, the general settings fields, the sync log's job and the pages come here under the SAME record names. Their
xml ids are moved to this module before it loads, so its data finds them (nothing is created twice, nothing deleted:
the tables and their rows stay as they are, and the login and its token too). On a site without it: nothing to do."""
FROM = 'mtbg_tours_zoho'
TO = 'zoho_connector'
MODELS = ('mtbg_zoho_ref', 'mtbg_zoho_log', 'mtbg_zoho_setup', 'mtbg_zoho_subextension')
SETTINGS_FIELDS = ('books_enabled', 'books_writes', 'expense_enabled', 'expense_writes', 'expense_org_id',
                   'shifts_enabled', 'shifts_writes', 'shifts_org_id', 'rate_limit', 'connection_info',
                   'access_info', 'scopes_needed')
RECORDS = ('access_zoho_ref_system', 'access_zoho_log_system', 'cron_zoho_log_cleanup', 'view_zoho_ref_list',
           'view_zoho_ref_form', 'view_zoho_ref_search', 'action_zoho_refs', 'view_zoho_log_list', 'view_zoho_log_search',
           'action_zoho_log')


def moved_names(cr):
    """The record names of FROM that this module takes over (exact names and per-model patterns)."""
    exact = list(RECORDS) + ['model_%s' % m for m in MODELS] \
        + ['field_res_config_settings__mtbg_zoho_%s' % f for f in SETTINGS_FIELDS]
    patterns = ['field_%s\\_\\_%%' % m.replace('_', '\\_') for m in MODELS] \
        + ['selection\\_\\_%s\\_\\_%%' % m.replace('_', '\\_') for m in MODELS]
    return exact, patterns


def move_into(cr, source, target, exact, patterns):
    """Rename ``source``'s xml ids in ``exact`` or matching ``patterns`` to ``target`` (where ``target`` has no such
    name yet). Returns how many moved."""
    cr.execute("""
        UPDATE ir_model_data d SET module = %(target)s
         WHERE d.module = %(source)s AND (d.name = ANY(%(exact)s) OR d.name LIKE ANY(%(patterns)s))
           AND NOT EXISTS (SELECT 1 FROM ir_model_data t WHERE t.module = %(target)s AND t.name = d.name)
    """, {'source': source, 'target': target, 'exact': list(exact), 'patterns': list(patterns)})
    return cr.rowcount


def pre_init_hook(env):
    cr = env.cr
    cr.execute("SELECT 1 FROM ir_module_module WHERE name = %s AND state IN ('installed', 'to upgrade')", [FROM])
    if not cr.fetchone():
        return
    exact, patterns = moved_names(cr)
    move_into(cr, FROM, TO, exact, patterns)
