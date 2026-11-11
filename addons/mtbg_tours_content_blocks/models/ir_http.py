from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        info = super().session_info()
        if self.env.user._is_internal():
            info['mtbg_topbar'] = self.env['mtbg.topbar'].mtbg_topbar_settings()  # the top bar icons (models/topbar.py)
        return info
