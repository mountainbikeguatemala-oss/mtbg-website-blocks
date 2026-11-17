"""19.0.2.0.0 (owner, 2026-11-16: the fewest extensions): the page cache's former extension (mtbg_tours_edge_cache)
is merged in. Before this version's code loads, its records become this module's with their ids (crons, settings,
views, access rules, models, fields and their tables, the purge log) and it is marked uninstallable (tools/retire.py).
Nothing removed, nothing sent. A database that never had it: nothing."""
from odoo.addons.cloudflare_connector.tools.retire import NEW, OLD, retire_into


def migrate(cr, version):
    retire_into(cr, OLD, NEW)
