"""Taking over the contact pipeline from Tours (0.4.0, owner 2026-11-18: the same pipeline on every site): the
contact type, its stage, lost, the lead flag and the source channel, from Tours Communications and Tours Core, under
the SAME names. Their xml ids (the fields, their choices, the source channels, the list and search views, the daily
job) are moved to this module before it loads (an update from 0.3: the 0.4.0 pre-migration; a new install on a site
with Tours: the pre_init hook), so nothing is created twice and nothing is deleted: the columns and their values stay
as they are. Tours then adds its own stages and types on top (Past client, Repeat client, Partner agency). On a site
without Tours: nothing to move, the columns are made."""
TO = 'mtbg_tours_crm_rules'
FIELDS = {
    'mtbg_tours_communications': ('mtbg_contact_type', 'mtbg_contact_type_manual', 'mtbg_is_lead', 'mtbg_stage',
                                  'mtbg_lost'),
    'mtbg_tours_core': ('mtbg_lead_source_id', 'mtbg_is_lead'),
}
SELECTIONS = {
    'mtbg_tours_communications': {'mtbg_contact_type': ('lead', 'client', 'staff', 'vendor', 'internal'),
                                  'mtbg_stage': ('new', 'lead', 'customer', 'lost')},
}
RECORDS = {
    'mtbg_tours_communications': ('view_partner_tree_stage', 'view_partner_search_stage',
                                  'ir_cron_mtbg_classify_suppliers', 'ir_cron_mtbg_classify_suppliers_ir_actions_server'),
    'mtbg_tours_core': ('field_utm_source__mtbg_contact_count',) + tuple(
        f'lead_source_{key}' for key in ('whatsapp', 'facebook', 'instagram', 'webchat', 'phone', 'email', 'referral',
                                         'newsletter', 'other')),
}


def moved_names(source):
    names = [f'field_res_partner__{name}' for name in FIELDS.get(source, ())]
    names += [f'selection__res_partner__{field}__{value}'
              for field, values in SELECTIONS.get(source, {}).items() for value in values]
    return names + list(RECORDS.get(source, ()))


def take_over(cr):
    """Every xml id above, from the Tours modules installed. Safe to run again. Returns how many moved."""
    moved = 0
    for source in FIELDS.keys() | RECORDS.keys():
        cr.execute("SELECT 1 FROM ir_module_module WHERE name = %s AND state IN ('installed', 'to upgrade')", [source])
        if not cr.fetchone():
            continue
        cr.execute("""
            UPDATE ir_model_data d SET module = %(target)s
             WHERE d.module = %(source)s AND d.name = ANY(%(names)s)
               AND NOT EXISTS (SELECT 1 FROM ir_model_data t WHERE t.module = %(target)s AND t.name = d.name)
        """, {'source': source, 'target': TO, 'names': moved_names(source)})
        moved += cr.rowcount
    return moved


def tours_pipeline(cr):
    """Tours computes the stages here (its Communications installed): the contacts already have their types."""
    cr.execute("SELECT 1 FROM ir_module_module WHERE name = 'mtbg_tours_communications' "
               "AND state IN ('installed', 'to upgrade', 'to install')")
    return bool(cr.fetchone())


def pre_init_hook(env):
    take_over(env.cr)


def post_init_hook(env):  # the sources of modules installed together with it
    """A rule for each source installed (Contact Rules' own and the extensions'), off until switched on; the contact
    types of a site without Tours (every contact a lead until now) from what is on record."""
    env['mtbg.crm.rule']._mtbg_sync_sources()
    if not tours_pipeline(env.cr):
        env['res.partner']._mtbg_classify_on_install()
