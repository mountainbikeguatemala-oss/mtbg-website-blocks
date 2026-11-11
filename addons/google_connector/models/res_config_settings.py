from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    google_connected_count = fields.Integer(compute="_compute_google")
    google_has_client = fields.Boolean(compute="_compute_google")

    def _compute_google(self):
        has_client = bool(self.env["ir.config_parameter"].sudo().get_param("google_connector.client_id"))
        count = self.env["google.connector.account"].sudo().search_count([("state", "=", "connected")])
        for settings in self:
            settings.google_has_client = has_client
            settings.google_connected_count = count
