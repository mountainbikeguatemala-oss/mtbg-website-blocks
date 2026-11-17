"""19.0.2.0.0: a database whose page cache was older than 0.9.0 gets the former extension's upgrade steps it had not
had (tools/page_cache_upgrades.py; www at 0.9.0: none)."""
from odoo import SUPERUSER_ID, api

from odoo.addons.cloudflare_connector.tools.page_cache_upgrades import run_missing
from odoo.addons.cloudflare_connector.tools.retire import old_version


def migrate(cr, version):
    run_missing(api.Environment(cr, SUPERUSER_ID, {}), old_version(cr))
