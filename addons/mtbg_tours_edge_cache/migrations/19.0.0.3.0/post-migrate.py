"""Edit-only (0.3.0): a page stays a month in Cloudflare (every edit purges, prices are live); the two pre-fill jobs
and the nightly purge of 0.2.0 go, the homepages' re-fill runs once a night (the job file is noupdate: done here)."""
from datetime import datetime, timedelta

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['ir.config_parameter'].set_param('mtbg_tours.edge_cache_ttl', '2592000')
    for xmlid in ('cron_edge_cache_warm_all', 'cron_edge_cache_nightly'):
        cron = env.ref('mtbg_tours_edge_cache.%s' % xmlid, raise_if_not_found=False)
        if cron:
            cron.unlink()
        env['ir.model.data'].search([('module', '=', 'mtbg_tours_edge_cache'), ('name', '=', xmlid)]).unlink()
    home = env.ref('mtbg_tours_edge_cache.cron_edge_cache_warm_home', raise_if_not_found=False)
    if home:
        now = datetime.utcnow()
        night = now.replace(hour=6, minute=5, second=0, microsecond=0)  # (00:05 in Guatemala)
        home.write({'name': "Website: re-fill Cloudflare's copy of the homepages", 'interval_number': 1,
                    'interval_type': 'days', 'nextcall': night if night > now else night + timedelta(days=1)})
    env['mtbg.edge.cache']._mtbg_sync_jobs()
