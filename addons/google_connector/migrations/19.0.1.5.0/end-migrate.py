"""19.0.1.5.0, end of the run: the Tours' Google glue (mtbg_tours_google), upgraded in this run while its old folder
is still on the server, is uninstallable again and any copy it made of the connector's records goes (the Tours
Core's retire_finish, where it is on the server)."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    try:
        from odoo.addons.mtbg_tours_core.tools.retire import retire_finish
    except ImportError:
        return
    retire_finish(api.Environment(cr, SUPERUSER_ID, {}), 'mtbg_tours_google', 'google_connector')
