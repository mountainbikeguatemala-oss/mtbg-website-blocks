"""The page cache's former extension (mtbg_tours_edge_cache), retired into this connector in 19.0.2.0.0 (owner,
2026-11-16: the fewest extensions). The same steps as the website blocks' and the Tours Core's tools/retire.py (this
connector depends on neither, so it carries its own copy of the two it needs):

* ``retire_into(cr, old, new)`` (pre-migrate, or pre_init_hook on a first install): every xml id of the old module is
  COPIED to this one, so this module's data files update the same records (crons, settings, views, access rules,
  models, fields and their tables, the purge log) and nothing is made twice or dropped; its SQL constraints and
  many2many tables are noted as this module's; view keys, t-calls, static paths and JS module names follow; the old
  module is marked 'uninstallable' and its dependency lines go. No uninstall runs: nothing is dropped.
* ``retire_finish(env, old, new)`` (end-migrate, and ``keep_retired`` at every load): the old names go; where the old
  module (its folder still on a server, loaded in that run) made a record again under its own name, that copy goes,
  and its templates' keys are this module's again.
* ``keep_retired(env)``: at every load and after Update Apps List, the old module stays 'uninstallable' while its
  folder may still be on a server (Odoo would list it as installable again), and its leftover names are finished.
"""
import logging

_logger = logging.getLogger(__name__)

OLD = 'mtbg_tours_edge_cache'
NEW = 'cloudflare_connector'


def _module_id(cr, name):
    cr.execute("SELECT id, state FROM ir_module_module WHERE name = %s", [name])
    return cr.fetchone() or (None, None)


def _move_bookkeeping(cr, old_id, new_id):
    """The SQL constraints and many2many tables Odoo notes per module (ir_model_constraint, ir_model_relation): the
    survivor's rows stay where both noted the same name (only the old module's note goes; the constraint or table in
    the database is untouched), the others move."""
    for table in ('ir_model_constraint', 'ir_model_relation'):
        cr.execute(f"""DELETE FROM {table} o USING {table} n
                        WHERE o.module = %s AND n.module = %s AND n.name = o.name""",  # noqa: S608
                   [old_id, new_id])
        cr.execute(f"UPDATE {table} SET module = %s WHERE module = %s", [new_id, old_id])  # noqa: S608


def retire_into(cr, old, new):
    """Hand ``old``'s records to ``new``; mark ``old`` uninstallable. Returns a report dict (counts, orphans).
    A database without ``old`` (or where it is already retired): nothing, an empty report."""
    old_id, old_state = _module_id(cr, old)
    new_id, _new_state = _module_id(cr, new)
    report = {'module': old, 'into': new, 'xmlids': 0, 'conflicts': 0, 'orphans': [], 'views': 0}
    if not old_id or not new_id or old_state in ('uninstallable', 'uninstalled'):
        return report
    # same xml id in both: the survivor's stays; the old module's record (if another one) is reported
    cr.execute("""
        SELECT o.name, o.model, o.res_id, n.res_id FROM ir_model_data o
          JOIN ir_model_data n ON n.module = %s AND n.name = o.name
         WHERE o.module = %s
    """, [new, old])
    conflicts = cr.fetchall()
    for name, model, old_res, new_res in conflicts:
        if old_res != new_res:
            report['orphans'].append((model, old_res, name))
    # a shared id naming another record: the old name keeps its own record for the rest of the run (old code reloaded
    # in the run updates that one, never the survivor's); retire_finish removes it at the end
    report['conflicts'] = len(conflicts)
    # COPIED, not moved (2026-11-08, www): while its folder is still on the server, Odoo upgrades a retired module
    # that depended on the survivor in the same run, and its data refers to its own and its dependencies' old ids
    # (e.g. inherit_id ref="website_review_sync.view_review_review_form"). With both names on the same records it
    # updates those records, never copies of them; retire_finish removes the old names at the end of the run.
    cr.execute("""
        INSERT INTO ir_model_data (module, name, model, res_id, noupdate, create_uid, create_date, write_uid, write_date)
        SELECT %s, name, model, res_id, noupdate, create_uid, create_date, write_uid, write_date
          FROM ir_model_data WHERE module = %s
        ON CONFLICT DO NOTHING
    """, [new, old])
    report['xmlids'] = cr.rowcount
    _move_bookkeeping(cr, old_id, new_id)
    # views: keys, t-calls, static paths and JS module names (site copies too)
    cr.execute("""UPDATE ir_ui_view SET key = %s || substr(key, %s) WHERE key LIKE %s""",
               [new + '.', len(old) + 2, old + '.%'])
    pairs = [('"%s.' % old, '"%s.' % new), ("'%s." % old, "'%s." % new), ('/%s/static/' % old, '/%s/static/' % new),
             ('@%s/' % old, '@%s/' % new)]
    expr = 'arch_db::text'
    params = []
    for before, after in pairs:
        expr = 'replace(%s, %%s, %%s)' % expr
        params += [before, after]
    cr.execute(f"UPDATE ir_ui_view SET arch_db = ({expr})::jsonb WHERE arch_db::text LIKE %s",  # noqa: S608
               params + ['%' + old + '%'])
    report['views'] = cr.rowcount
    cr.execute("UPDATE ir_asset SET path = %s || substr(path, %s) WHERE path LIKE %s",
               [new + '/', len(old) + 2, old + '/%'])
    cr.execute("UPDATE ir_asset SET target = %s || substr(target, %s) WHERE target LIKE %s",
               [new + '/', len(old) + 2, old + '/%'])
    cr.execute("UPDATE ir_attachment SET url = replace(url, %s, %s) WHERE url LIKE %s",
               ['/%s/' % old, '/%s/' % new, '/%s/%%' % old])
    # the old module: never listed, installed or loaded again; its dependency lines go
    cr.execute("DELETE FROM ir_module_module_dependency WHERE module_id = %s OR name = %s", [old_id, old])
    cr.execute("UPDATE ir_module_module SET state = 'uninstallable' WHERE id = %s", [old_id])
    _logger.info("Retired %s into %s: %s xml ids moved, %s shared ids (orphans: %s), %s views updated",
                 old, new, report['xmlids'], report['conflicts'], report['orphans'], report['views'])
    return report


def retire_finish(env, old, new):
    """End of the upgrade run: the records ``old`` made again (its folder still on the server, upgraded with its
    dependency) are removed where ``new`` has the same xml id; its other xml ids move to ``new``; ``old`` is
    uninstallable again. Returns the number of copies removed."""
    cr = env.cr
    env.flush_all()  # what the run wrote through the ORM, before the SQL below reads it
    old_id, _state = _module_id(cr, old)
    if not old_id:
        return 0
    cr.execute("""
        SELECT o.id, o.model, o.res_id FROM ir_model_data o
          JOIN ir_model_data n ON n.module = %s AND n.name = o.name
         WHERE o.module = %s AND o.res_id IS NOT NULL AND o.res_id != n.res_id
    """, [new, old])
    copies = cr.fetchall()
    removed = 0
    for _data_id, model, res_id in copies:
        if model in env:
            record = env[model].sudo().with_context(active_test=False).browse(res_id).exists()
            if record:
                record.unlink()
                removed += 1
    cr.execute("""
        DELETE FROM ir_model_data o USING ir_model_data n
         WHERE o.module = %s AND n.module = %s AND n.name = o.name
    """, [old, new])
    cr.execute("UPDATE ir_model_data SET module = %s WHERE module = %s", [new, old])
    # (its old folder reloaded in the run gave its templates their old keys back)
    cr.execute("""UPDATE ir_ui_view SET key = %s || substr(key, %s) WHERE key LIKE %s""",
               [new + '.', len(old) + 2, old + '.%'])
    new_id, _state = _module_id(cr, new)
    _move_bookkeeping(cr, old_id, new_id)
    cr.execute("DELETE FROM ir_module_module_dependency WHERE module_id = %s OR name = %s", [old_id, old])
    cr.execute("UPDATE ir_module_module SET state = 'uninstallable' WHERE id = %s", [old_id])
    _logger.info("Retired %s into %s (end of the run): %s copies of its records removed", old, new, removed)
    return removed



def old_version(cr, old=OLD):
    """The former module's version in this database, as (x, y, z) without the Odoo series (None: it never was)."""
    cr.execute("SELECT latest_version FROM ir_module_module WHERE name = %s", [old])
    row = cr.fetchone()
    if not row or not row[0]:
        return None
    parts = [int(p) for p in row[0].split('.') if p.isdigit()]
    return tuple(parts[2:5]) if len(parts) >= 5 else tuple(parts[:3])


def keep_retired(env, old=OLD, new=NEW):
    """The former module not installed: 'uninstallable' (a write only when it differs), and its xml ids left over
    (a copy made by its old folder in an update run, or Odoo's ir.model.inherit rows made at the end of a run) handed
    over. A database that never had it: one query, nothing."""
    cr = env.cr
    cr.execute("SELECT id, state FROM ir_module_module WHERE name = %s", [old])
    row = cr.fetchone()
    if not row or row[1] in ('installed', 'to upgrade', 'to remove'):
        return
    if row[1] != 'uninstallable':
        cr.execute("UPDATE ir_module_module SET state = 'uninstallable' WHERE id = %s", [row[0]])
        env['ir.module.module'].invalidate_model(['state'])
    cr.execute("SELECT 1 FROM ir_model_data WHERE module = %s LIMIT 1", [old])
    if cr.fetchone():
        retire_finish(env, old, new)
