from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _get_translation_frontend_modules_name(cls):
        """Public pages load this module's JavaScript translations (Tiled Gallery block)."""
        mods = super()._get_translation_frontend_modules_name()
        return mods + ['mtbg_tours_gallery']
