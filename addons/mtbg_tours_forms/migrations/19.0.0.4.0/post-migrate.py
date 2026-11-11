from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """The hand-made newsletter popup (2025) becomes a Form Designer form, a popup with the same look and pages."""
    api.Environment(cr, SUPERUSER_ID, {})['mtbg.form']._mtbg_make_newsletter_popup()
