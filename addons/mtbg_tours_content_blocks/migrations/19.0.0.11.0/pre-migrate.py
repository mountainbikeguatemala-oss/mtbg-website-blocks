"""0.11.0 (owner, 2026-11-11): the Menu Designer comes here from Tours Core, so a plain Odoo website installs it without
Tours. Its records change hands with their ids (Tours Core 0.6.0's pre-migrate does the same: the first to run moves):
the menu changes, the added folders and pages, the saved presets and the top bar settings stay as they are. Nothing
is sent."""
from odoo.addons.mtbg_tours_content_blocks.tools.retire import MENU_DESIGNER_MOVE, check_core_without_designer, move_into


def migrate(cr, version):
    check_core_without_designer(cr)
    move_into(cr, 'mtbg_tours_core', 'mtbg_tours_content_blocks', **MENU_DESIGNER_MOVE)
