"""The label layout was first part of the bike shop core (bikeshop_shared_extensions 19.0.5.3.0). Where that version
is installed, this module takes over its records (model, fields, views, menu, access, the default layout) before it
loads, so the shop keeps its layout and nothing is created twice."""

OWNED = (
    "view_bsx_label_layout_form", "view_bsx_label_layout_list", "action_bsx_label_layout", "menu_bsx_label_layout",
    "access_bsx_label_layout_user", "access_bsx_label_layout_backend", "label_layout_default",
)


def pre_init_hook(env):
    env.cr.execute(
        """
        UPDATE ir_model_data SET module = 'label_printer'
         WHERE module = 'bikeshop_shared_extensions'
           AND (name = ANY(%s)
                OR (model IN ('ir.model', 'ir.model.fields', 'ir.model.fields.selection', 'ir.model.constraint')
                    AND name LIKE '%%bsx\\_label\\_layout%%'))
        """,
        [list(OWNED)],
    )
