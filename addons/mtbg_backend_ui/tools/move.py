"""The admin look's records, from Tours Core (0.6.x) to this module (owner, 2026-11-11: one universal admin module, so
Core and the universal modules share the lists, boards, cards, settings pages and text settings without Tours).

``move_into`` runs in SQL before either module's code loads: from this module's pre_init_hook (it installs before
Core 0.7.0, which depends on it) and from Core 0.7.0's pre-migrate (the first to run moves; the second finds nothing
left). Only these records change hands, with their ids: the tables and their rows stay (the boards, things missing,
the users' screen choices). The cards' looks and the texts are system parameters: they stay as they are.
(The same helper as the website blocks' tools/retire.py ``move_into``, with name patterns: this module needs no
website.)
"""
import logging

_logger = logging.getLogger(__name__)

OLD = 'mtbg_tours_core'
NEW = 'mtbg_backend_ui'

BACKEND_UI_MOVE = {
    # the models: their ir.model rows, fields, selections, SQL constraints and many2many tables
    'models': ('mtbg.board', 'mtbg.missing.tag', 'mtbg.user.pref', 'mtbg.board.mixin', 'mtbg.sidebar.mixin',
               'mtbg.card.mixin', 'mtbg.text.setting', 'mtbg.data.transfer'),
    # the access rows that are not Core's managers' (those stay in Core, on its group)
    'names': ('access_board_user', 'access_missing_tag_user', 'access_mtbg_user_pref_system'),
    # the boards' "Time to start" values on every model with boards (the mixin's selection: one xml id per model and
    # value, Core's until now; left there, Core's update would delete them and empty the records' stage)
    'data_like': ('selection\\_\\_%\\_\\_mtbg\\_time\\_stage\\_\\_%',),
    # the "Things missing" tables of every model with boards and their foreign keys (noted under Core)
    'sql_like': ('%mtbg\\_missing\\_tag%',),
}

# Core's version that hands these over (and no longer has them)
CORE_SINCE = (0, 7, 0)


def _module_id(cr, name):
    cr.execute("SELECT id, state FROM ir_module_module WHERE name = %s", [name])
    return cr.fetchone() or (None, None)


def move_into(cr, old, new, models=(), names=(), data_like=(), sql_like=()):
    """Hand ``models`` (and the xml ids ``names``, and those matching ``data_like``) of ``old`` to ``new``, with the
    SQL constraints and many2many tables noted for those models (and those named like ``sql_like``). Where ``new``
    already has the same xml id or note, ``old``'s goes. Works whether ``new`` is installed or not. Returns the number
    of xml ids moved."""
    old_id, _old_state = _module_id(cr, old)
    new_id, _new_state = _module_id(cr, new)
    if not old_id or not new_id:
        return 0
    cr.execute("SELECT id FROM ir_model WHERE model IN %s", [tuple(models) or ('',)])
    model_ids = tuple(row[0] for row in cr.fetchall()) or (0,)
    cr.execute("SELECT id FROM ir_model_fields WHERE model_id IN %s", [model_ids])
    field_ids = tuple(row[0] for row in cr.fetchall()) or (0,)
    cr.execute("SELECT id FROM ir_model_fields_selection WHERE field_id IN %s", [field_ids])
    selection_ids = tuple(row[0] for row in cr.fetchall()) or (0,)
    cr.execute("SELECT id FROM ir_model_constraint WHERE model IN %s", [model_ids])
    constraint_ids = tuple(row[0] for row in cr.fetchall()) or (0,)
    like = ' OR '.join(['name LIKE %s'] * len(data_like)) or 'FALSE'
    cr.execute(f"""
        SELECT id, name FROM ir_model_data
         WHERE module = %s AND ((model = 'ir.model' AND res_id IN %s) OR (model = 'ir.model.fields' AND res_id IN %s)
                OR (model = 'ir.model.fields.selection' AND res_id IN %s)
                OR (model = 'ir.model.constraint' AND res_id IN %s) OR name IN %s OR {like})
    """, [old, model_ids, field_ids, selection_ids, constraint_ids, tuple(names) or ('',), *data_like])  # noqa: S608
    rows = cr.fetchall()
    moved = 0
    if rows:
        ids = tuple(r[0] for r in rows)
        cr.execute("""DELETE FROM ir_model_data o USING ir_model_data n
                       WHERE o.id IN %s AND n.module = %s AND n.name = o.name""", [ids, new])
        cr.execute("UPDATE ir_model_data SET module = %s WHERE id IN %s AND module = %s", [new, ids, old])
        moved = cr.rowcount
    sql_where = ' OR '.join(['o.name LIKE %s'] * len(sql_like))
    for table in ('ir_model_constraint', 'ir_model_relation'):
        which = f"(o.model IN %s{' OR ' + sql_where if sql_where else ''})"
        cr.execute(f"""DELETE FROM {table} o USING {table} n
                        WHERE o.module = %s AND n.module = %s AND n.name = o.name AND {which}""",  # noqa: S608
                   [old_id, new_id, model_ids, *sql_like])
        cr.execute(f"UPDATE {table} o SET module = %s WHERE o.module = %s AND {which}",  # noqa: S608
                   [new_id, old_id, model_ids, *sql_like])
    if moved:
        _logger.info("Moved %s xml ids from %s to %s", moved, old, new)
    return moved


def module_version_on_disk(name):
    """A module's version in its folder on this server, as (x, y, z) without the Odoo series (None: no folder)."""
    from odoo.modules.module import get_manifest
    manifest = get_manifest(name)
    if not manifest:
        return None
    parts = [int(p) for p in manifest.get('version', '0').split('.') if p.isdigit()]
    return tuple(parts[2:5]) if len(parts) >= 5 else tuple(parts[:3])


def check_core_hands_over(cr):
    """Refuse this module beside an installed Tours Core whose folder is older than 0.7.0 (it still has the boards,
    cards and text settings itself: both would define them): the update stops before anything changes (the updater
    puts everything back)."""
    _id, state = _module_id(cr, OLD)
    if state not in ('installed', 'to upgrade', 'to install'):
        return
    version = module_version_on_disk(OLD)
    if version is not None and version < CORE_SINCE:
        raise RuntimeError(
            "The admin look (mtbg_backend_ui) takes the boards, cards and text settings over from Tours Core 0.7.0, "
            "but this server has Tours Core %s: update Tours Core in the same update." % '.'.join(map(str, version)))
