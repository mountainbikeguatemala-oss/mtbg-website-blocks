"""(The website blocks pack's copy of Tours Core's tools/retire.py: the blocks do not depend on Tours.)

Retire a module into the one that takes it over (owner, 2026-11-07: fewer modules; never a real uninstall).

Called from the survivor's pre-migrate, in SQL (nothing of either module's code is needed)::

    from odoo.addons.mtbg_tours_content_blocks.tools.retire import retire_into
    retire_into(cr, 'website_review_sync', 'mtbg_tours_reviews')

* Every record of the old module becomes the survivor's: its xml ids (ir_model_data) are copied to the survivor, so
  the survivor's data files update those same records (no copies) and its models, fields, views, menus, crons,
  access rules and data are kept with their ids. The old names stay on the same records until ``retire_finish`` at
  the end of the run (an old module reloaded in that run still finds them). Where both modules had the same xml id, the survivor's stays; the old one's record is
  returned (``orphans``) for the caller to settle.
* SQL constraints and many2many tables (ir_model_constraint, ir_model_relation) move too.
* Views: keys ``old.x`` become ``new.x``; t-calls, static paths (``/old/static/``) and JS modules (``@old/``) in the
  views' arch (site copies included), assets (ir_asset) and attachment urls follow.
* The old module is marked 'uninstallable' (Odoo never lists, installs or auto-installs such a module) and its
  dependency lines go; the suite's RETIRED map (mtbg_tours) keeps it so while its folder may still be on a server.
  No uninstall runs: nothing is dropped.
* ``retire_finish(env, old, new)``, for the survivor's end-migrate: while an old folder is still on the server, Odoo
  upgrades a retired module that depended on the survivor in the same run (its records made again under its name).
  At the end of the run those copies go (the survivor's records stay), any other id moves, and the old module is
  marked uninstallable again.
"""
import logging

_logger = logging.getLogger(__name__)

# the blocks pack's modules merged into another one: {old: survivor}
RETIRED = {
    'mtbg_tours_bullets': 'mtbg_tours_content_blocks',
}


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
    new_id, _state = _module_id(cr, new)
    _move_bookkeeping(cr, old_id, new_id)
    cr.execute("DELETE FROM ir_module_module_dependency WHERE module_id = %s OR name = %s", [old_id, old])
    cr.execute("UPDATE ir_module_module SET state = 'uninstallable' WHERE id = %s", [old_id])
    _logger.info("Retired %s into %s (end of the run): %s copies of its records removed", old, new, removed)
    return removed
