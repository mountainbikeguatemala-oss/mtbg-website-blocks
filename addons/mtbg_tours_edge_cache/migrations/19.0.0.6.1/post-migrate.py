"""The site notice's check (0.6.1) runs with the cache: on where the cache is on (the job file is noupdate)."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    api.Environment(cr, SUPERUSER_ID, {})['mtbg.edge.cache']._mtbg_sync_jobs()
