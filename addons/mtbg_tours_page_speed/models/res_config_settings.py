from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """Kept (0.7.3): the switch moved to Page Speed's own settings page in 0.7.2, but a site updating from an older
    version still has 0.6.x's General Settings view naming this field until the update ends, and other modules' views
    of the General Settings page are checked against it meanwhile (www, release -17: the update failed in Edge Cache's
    view). Not on the General Settings page any more; the same parameter as the settings page's switch."""
    _inherit = 'res.config.settings'

    mtbg_page_speed_lean = fields.Boolean(
        string="Visitor pages without Odoo's extras", config_parameter='mtbg_tours.page_speed_lean')
