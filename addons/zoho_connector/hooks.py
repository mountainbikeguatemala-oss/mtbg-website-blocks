"""Taking over from the Tours' Zoho extension (2026-11-11, the Zoho connector split; 2026-11-18, the Zoho Books
expenses and vendors): its models, their fields and records, the general settings fields, the jobs and the pages come
here under the SAME record names. Their xml ids are moved to this module before it loads (a new install: the
pre_init hook; an update from 0.1: the 0.2.0 pre-migration), so its data finds them (nothing is created twice,
nothing deleted: the tables and their rows stay as they are, and the login and its token too). The models' table
constraints and many2many tables are handed over too, so removing the Tours' extension one day never drops them. On a
site without it: nothing to do."""
FROM = 'mtbg_tours_zoho'
TO = 'zoho_connector'
MODELS = ('mtbg_zoho_ref', 'mtbg_zoho_log', 'mtbg_zoho_setup', 'mtbg_zoho_subextension',
          # 0.2.0: Import & Sync from Zoho Books
          'mtbg_zoho_books_account', 'mtbg_zoho_books_import', 'mtbg_zoho_books_review')
TABLE_MODELS = ('mtbg.zoho.ref', 'mtbg.zoho.log', 'mtbg.zoho.books.account', 'mtbg.zoho.books.import',
                'mtbg.zoho.books.review')
SETTINGS_FIELDS = ('books_enabled', 'books_writes', 'expense_enabled', 'expense_writes', 'expense_org_id',
                   'shifts_enabled', 'shifts_writes', 'shifts_org_id', 'rate_limit', 'connection_info',
                   'access_info', 'scopes_needed',
                   # 0.2.0
                   'expenses_sync_info')
# 0.2.0: a vendor contact's Zoho Books vendor
PARTNER_FIELDS = ('mtbg_zoho_vendor_id', 'mtbg_zoho_vendor_synced_at', 'mtbg_zoho_vendor_modified',
                  'mtbg_zoho_vendor_details_of')
CRONS = ('cron_zoho_books_import', 'cron_zoho_books_expenses_sync')
RECORDS = ('access_zoho_ref_system', 'access_zoho_log_system', 'cron_zoho_log_cleanup', 'view_zoho_ref_list',
           'view_zoho_ref_form', 'view_zoho_ref_search', 'action_zoho_refs', 'view_zoho_log_list', 'view_zoho_log_search',
           'action_zoho_log',
           # 0.2.0: the Import & Sync pages and jobs (a job's server action has an id of its own)
           'view_books_account_list', 'view_books_account_search', 'action_books_accounts', 'view_books_review_list',
           'view_books_import_form', 'view_books_import_list', 'action_books_import') \
    + CRONS + tuple(f'{cron}_ir_actions_server' for cron in CRONS + ('cron_zoho_log_cleanup',))


def moved_names(cr):
    """The record names of FROM that this module takes over (exact names and per-model patterns)."""
    exact = list(RECORDS) + ['model_%s' % m for m in MODELS] \
        + ['field_res_config_settings__mtbg_zoho_%s' % f for f in SETTINGS_FIELDS] \
        + ['field_%s__%s' % (model, f) for model in ('res_partner', 'res_users') for f in PARTNER_FIELDS]
    patterns = ['field_%s\\_\\_%%' % m.replace('_', '\\_') for m in MODELS] \
        + ['selection\\_\\_%s\\_\\_%%' % m.replace('_', '\\_') for m in MODELS] \
        + ['constraint\\_%s\\_%%' % m.replace('_', '\\_') for m in MODELS]
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


def move_tables(cr, source, target, models):
    """The table constraints and many2many tables of ``models`` that ``source`` registered: registered to ``target``
    (where it has no such row yet). Returns how many moved."""
    moved = 0
    for table in ('ir_model_constraint', 'ir_model_relation'):
        cr.execute(f"""
            UPDATE {table} r SET module = (SELECT id FROM ir_module_module WHERE name = %(target)s)
             WHERE r.module = (SELECT id FROM ir_module_module WHERE name = %(source)s)
               AND r.model IN (SELECT id FROM ir_model WHERE model = ANY(%(models)s))
               AND NOT EXISTS (SELECT 1 FROM {table} t
                                WHERE t.name = r.name
                                  AND t.module = (SELECT id FROM ir_module_module WHERE name = %(target)s))
        """, {'source': source, 'target': target, 'models': list(models)})
        moved += cr.rowcount
    return moved


def take_over(cr):
    """Everything above, from the Tours' Zoho extension when it is installed. Safe to run again."""
    cr.execute("SELECT 1 FROM ir_module_module WHERE name = %s AND state IN ('installed', 'to upgrade')", [FROM])
    if not cr.fetchone():
        return 0
    exact, patterns = moved_names(cr)
    return move_into(cr, FROM, TO, exact, patterns) + move_tables(cr, FROM, TO, TABLE_MODELS)


def pre_init_hook(env):
    take_over(env.cr)
