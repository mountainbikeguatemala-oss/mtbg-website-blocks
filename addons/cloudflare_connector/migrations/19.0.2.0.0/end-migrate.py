"""19.0.2.0.0, end of the run: where the former page cache extension's old folder was still on the server and Odoo
loaded it in this run, any copy it made of this module's records goes, its names are handed over and it is
uninstallable again (tools/retire.py)."""
from odoo import SUPERUSER_ID, api

from odoo.addons.cloudflare_connector.tools.retire import NEW, OLD, retire_finish


def migrate(cr, version):
    retire_finish(api.Environment(cr, SUPERUSER_ID, {}), OLD, NEW)
