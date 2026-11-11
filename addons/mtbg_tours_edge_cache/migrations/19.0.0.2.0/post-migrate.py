"""The jobs follow the cache switch: 0.1.x's job file switched the catch-up purge off at every upgrade (now noupdate),
and the new pre-fill and nightly jobs start on where the cache is on (no Save in the settings needed)."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    api.Environment(cr, SUPERUSER_ID, {})['mtbg.edge.cache']._mtbg_sync_jobs()
