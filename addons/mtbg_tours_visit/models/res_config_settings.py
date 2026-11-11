from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    mtbg_visit_by_script = fields.Boolean(
        string="Visits recorded by the page's script", config_parameter='mtbg_tours.visit_by_script',
        help="On: an anonymous visitor's page view is recorded by a light script once the page has loaded, so pages "
             "can be cached. Off: recorded while the page is built (Odoo's way).")
