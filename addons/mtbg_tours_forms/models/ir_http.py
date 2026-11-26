from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _get_translation_frontend_modules_name(cls):
        """Public pages load this module's JavaScript translations (contact, newsletter and chat forms: their checks
        and steps), and Odoo's reCAPTCHA's when it is installed (its form messages: Odoo registers them nowhere)."""
        mods = super()._get_translation_frontend_modules_name() + ['mtbg_tours_forms']
        installed = request.registry._init_modules if request else ()
        if 'google_recaptcha' in installed and 'google_recaptcha' not in mods:
            mods.append('google_recaptcha')
        return mods
