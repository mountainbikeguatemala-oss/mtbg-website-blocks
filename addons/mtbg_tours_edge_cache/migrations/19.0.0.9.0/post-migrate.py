"""0.9.0: page addresses only, never "purge everything"; the nightly re-fill takes every re-filled page at the re-fill
time (02:00 in the business's time zone, else UTC). The job file is noupdate: its name and code are set here, the
new re-fill queue job follows the cache switch."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    night = env.ref('mtbg_tours_edge_cache.cron_edge_cache_warm_home', raise_if_not_found=False)
    if night:
        night.write({'name': "Website: re-fill Cloudflare's copies of the pages every night",
                     'code': 'model._mtbg_warm_night()'})
    env['mtbg.edge.cache']._mtbg_schedule_warm()
    env['mtbg.edge.cache']._mtbg_sync_jobs()
