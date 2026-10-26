from .models.page_template import SYNC_PARAM


def post_init_hook(env):
    # the Default page templates: made once every module is loaded (models/page_template.py)
    env['ir.config_parameter'].sudo().set_param(SYNC_PARAM, '1')
