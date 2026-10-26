from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """The new Website Blocks › Extensions page: which modules are website blocks (from their manifests)."""
    api.Environment(cr, SUPERUSER_ID, {})['ir.module.module']._mtbg_wb_fill()
