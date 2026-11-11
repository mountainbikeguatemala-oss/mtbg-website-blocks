from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        info = super().session_info()
        if self.env.user._is_internal():
            info['mtbg_user_prefs'] = self.env['mtbg.user.pref']._mtbg_prefs()  # screen choices (models/user_prefs.py)
        return info

    def color_scheme(self):
        """The admin light or dark: the user's switch (a cookie), else light. Odoo serves its dark bundle for 'dark'."""
        scheme = request and request.httprequest.cookies.get('color_scheme')
        return 'dark' if scheme == 'dark' else super().color_scheme()
