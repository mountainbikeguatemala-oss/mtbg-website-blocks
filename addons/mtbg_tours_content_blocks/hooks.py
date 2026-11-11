from .models.page_template import SYNC_PARAM
from .tools.retire import MENU_DESIGNER_MOVE, check_core_without_designer, move_into


def pre_init_hook(env):
    # the Menu Designer (0.11.0): never beside a Tours Core that still has it; a site's own layout (Tours Core's
    # records, if any are still its) comes along with its ids
    check_core_without_designer(env.cr)
    move_into(env.cr, 'mtbg_tours_core', 'mtbg_tours_content_blocks', **MENU_DESIGNER_MOVE)


def post_init_hook(env):
    # the Default page templates: made once every module is loaded (models/page_template.py)
    env['ir.config_parameter'].sudo().set_param(SYNC_PARAM, '1')
    # the Website Blocks › Extensions page: which modules are website blocks
    env['ir.module.module']._mtbg_wb_fill()
