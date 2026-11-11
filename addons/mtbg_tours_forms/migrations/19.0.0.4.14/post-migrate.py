"""Every form gets its lead source, "Web form: <name>" (Core 0.5.49's lead sources)."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['mtbg.form'].with_context(active_test=False).search([])._mtbg_lead_source()
