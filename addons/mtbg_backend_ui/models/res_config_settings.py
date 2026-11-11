from odoo import api, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Settings kept as system parameters that a plain ``config_parameter`` field cannot hold: yes / no switches
    # that are on by default (a config_parameter Boolean deletes the parameter when off, which reads as "on"),
    # and long texts / HTML. Each module lists its own; they are read and saved here.
    @api.model
    def _mtbg_switch_parameters(self):
        """{field: (system parameter, default)}: stored as '1' / '0'."""
        return {}

    @api.model
    def _mtbg_text_parameters(self):
        """{field: system parameter}: long texts and HTML."""
        return {}

    @api.model
    def get_values(self):
        values = super().get_values()
        ICP = self.env['ir.config_parameter'].sudo()
        for name, (key, default) in self._mtbg_switch_parameters().items():
            values[name] = ICP.get_param(key, '1' if default else '0') not in ('0', 'False', 'false', '')
        for name, key in self._mtbg_text_parameters().items():
            values[name] = ICP.get_param(key) or False
        return values

    def set_values(self):
        super().set_values()
        ICP = self.env['ir.config_parameter'].sudo()
        for name, (key, _default) in self._mtbg_switch_parameters().items():
            ICP.set_param(key, '1' if self[name] else '0')
        for name, key in self._mtbg_text_parameters().items():
            ICP.set_param(key, self[name] or False)
