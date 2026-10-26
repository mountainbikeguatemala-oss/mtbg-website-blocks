"""The reusable block model moves here from Tours' Catalog (the website blocks pack needs only the website): the model
keeps its name and rows; its records' external ids (the model, its fields and their selections, its list, form, search
and action) change module from mtbg_tours_catalog to this one, so neither module's update deletes them. Catalog keeps
the tours' block lines (tour_line_ids) and its access rules. Runs before Catalog's update (Catalog now depends on this
module)."""

# Catalog's records of the block model that are this module's now (the fields Catalog keeps stay Catalog's)
MOVED_VIEWS = ('view_content_block_list', 'view_content_block_form', 'view_content_block_search',
               'action_content_block')
KEPT_FIELDS = ('field_mtbg_tours_content_block__tour_line_ids',)
# this module's views the new layout drops (their parents change in this update: they would not validate against the
# new forms); the tour form's note moves to mtbg_tours_page_templates
DROPPED_VIEWS = ('view_content_block_form_usage', 'view_content_block_list_usage', 'view_tour_form_content_blocks')


def migrate(cr, version):
    cr.execute("""
        UPDATE ir_model_data d
           SET module = 'mtbg_tours_content_blocks'
         WHERE d.module = 'mtbg_tours_catalog'
           AND (d.name = 'model_mtbg_tours_content_block'
                OR (d.name LIKE 'field\\_mtbg\\_tours\\_content\\_block\\_\\_%%' AND d.name NOT IN %s)
                OR d.name LIKE 'selection\\_\\_mtbg\\_tours\\_content\\_block\\_\\_%%'
                OR d.name IN %s)
           AND NOT EXISTS (SELECT 1 FROM ir_model_data o
                            WHERE o.module = 'mtbg_tours_content_blocks' AND o.name = d.name)
    """, [KEPT_FIELDS, MOVED_VIEWS])
    cr.execute("""
        SELECT res_id FROM ir_model_data
         WHERE module = 'mtbg_tours_content_blocks' AND model = 'ir.ui.view' AND name IN %s
    """, [DROPPED_VIEWS])
    view_ids = [row[0] for row in cr.fetchall()]
    if view_ids:
        cr.execute("DELETE FROM ir_ui_view WHERE id IN %s", [tuple(view_ids)])
        cr.execute("""DELETE FROM ir_model_data WHERE module = 'mtbg_tours_content_blocks' AND model = 'ir.ui.view'
                       AND name IN %s""", [DROPPED_VIEWS])
