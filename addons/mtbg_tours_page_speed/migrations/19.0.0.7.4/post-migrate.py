"""0.7.4: the speed log measures through the Google connector (owner, 2026-11-08). A PageSpeed key set in Page Speed
(0.7.0-0.7.3) becomes the connector's server API key when the connector has none, then Page Speed's own goes. Only
the two parameters: nothing here needs the connector's code (the modules update in any order)."""
from odoo import SUPERUSER_ID, api

OLD = 'mtbg_page_speed.psi_key'
SERVER = 'google_connector.server_key'


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    ICP = env['ir.config_parameter'].sudo()
    key = (ICP.get_param(OLD) or '').strip()
    if not key:
        ICP.search([('key', '=', OLD)]).unlink()
        return
    cr.execute("SELECT 1 FROM ir_module_module WHERE name = 'google_connector' AND state IN ('installed', 'to upgrade')")
    if not cr.fetchone():
        return  # (no connector here: the key stays until it is installed)
    if not (ICP.get_param(SERVER) or '').strip():
        ICP.set_param(SERVER, key)
    ICP.search([('key', '=', OLD)]).unlink()
