"""The upgrade steps of the page cache's former extension (mtbg_tours_edge_cache 0.2.0 to 0.9.0), for a database that
had an older version of it when it was retired into this connector (19.0.2.0.0): its own migrations never run again
(its folder is gone), so this connector's post-migrate (or post_init_hook) runs the ones that database had not had,
in order, on the records it now owns (``cloudflare_connector.*`` xml ids). A database at 0.9.0 (www) runs none.

Each step is the former migration as it was, with the module name of the xml ids changed."""
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)

M = 'cloudflare_connector'


def step_020(env):
    """0.2.0: the jobs follow the cache switch."""
    env['mtbg.edge.cache']._mtbg_sync_jobs()


def step_030(env):
    """0.3.0, edit-only: a page stays a month in Cloudflare; the 0.2.0 pre-fill jobs and nightly purge go; the
    homepages' re-fill runs once a night."""
    env['ir.config_parameter'].set_param('mtbg_tours.edge_cache_ttl', '2592000')
    for xmlid in ('cron_edge_cache_warm_all', 'cron_edge_cache_nightly'):
        cron = env.ref('%s.%s' % (M, xmlid), raise_if_not_found=False)
        if cron:
            cron.unlink()
        env['ir.model.data'].search([('module', 'in', (M, 'mtbg_tours_edge_cache')), ('name', '=', xmlid)]).unlink()
    home = env.ref('%s.cron_edge_cache_warm_home' % M, raise_if_not_found=False)
    if home:
        now = datetime.utcnow()
        night = now.replace(hour=6, minute=5, second=0, microsecond=0)  # (00:05 in Guatemala)
        home.write({'name': "Website: re-fill Cloudflare's copy of the homepages", 'interval_number': 1,
                    'interval_type': 'days', 'nextcall': night if night > now else night + timedelta(days=1)})
    env['mtbg.edge.cache']._mtbg_sync_jobs()


def _add_paths(env, added):
    ICP = env['ir.config_parameter']
    paths = (ICP.get_param('mtbg_tours.edge_cache_paths') or '').split()
    added = [path for path in added if path not in paths]
    if added:
        ICP.set_param('mtbg_tours.edge_cache_paths', ' '.join(paths + added))


def step_050(env):
    """0.5.0: the hotel pages join the pages Cloudflare may keep."""
    _add_paths(env, ('/hotels', '/es/hotels'))


def step_060(env):
    """0.6.0: the blog and the tour policies join the pages Cloudflare may keep."""
    _add_paths(env, ('/blog', '/tour-policies'))


def step_061(env):
    """0.6.1: the site notice's check runs with the cache."""
    env['mtbg.edge.cache']._mtbg_sync_jobs()


MOVES = (('mtbg_tours.edge_cache_zone', 'cloudflare_connector.zone_id'),
         ('mtbg_tours.edge_cache_token', 'cloudflare_connector.api_token'))


def step_070(env):
    """0.7.0: the zone and purge token move to this connector's settings (plain SQL: a mtbg_tours.* write through
    the ORM would itself note a cache change); a value moves only where the connector has none; the old token goes."""
    cr = env.cr
    for old, new in MOVES:
        cr.execute("SELECT value FROM ir_config_parameter WHERE key = %s", [old])
        row = cr.fetchone()
        value = (row[0] or '').strip() if row else ''
        cr.execute("SELECT value FROM ir_config_parameter WHERE key = %s", [new])
        have = cr.fetchone()
        if value and not (have and (have[0] or '').strip()):
            if have:
                cr.execute("UPDATE ir_config_parameter SET value = %s WHERE key = %s", [value, new])
            else:
                cr.execute("INSERT INTO ir_config_parameter (key, value, create_uid, write_uid, create_date, "
                           "write_date) VALUES (%s, %s, 1, 1, now() at time zone 'UTC', now() at time zone 'UTC')",
                           [new, value])
        cr.execute("DELETE FROM ir_config_parameter WHERE key = %s", [old])
    env['ir.config_parameter'].invalidate_model()


def step_090(env):
    """0.9.0: page addresses only; the nightly re-fill takes every re-filled page at the re-fill time."""
    night = env.ref('%s.cron_edge_cache_warm_home' % M, raise_if_not_found=False)
    if night:
        night.write({'name': "Website: re-fill Cloudflare's copies of the pages every night",
                     'code': 'model._mtbg_warm_night()'})
    env['mtbg.edge.cache']._mtbg_schedule_warm()
    env['mtbg.edge.cache']._mtbg_sync_jobs()


STEPS = (((0, 2, 0), step_020), ((0, 3, 0), step_030), ((0, 5, 0), step_050), ((0, 6, 0), step_060),
         ((0, 6, 1), step_061), ((0, 7, 0), step_070), ((0, 9, 0), step_090))


def run_missing(env, version):
    """The steps after ``version`` (the former module's, (x, y, z)); None (it never was here): none. Returns the
    versions run."""
    if version is None:
        return []
    done = []
    for since, step in STEPS:
        if version < since:
            step(env)
            done.append(since)
    if done:
        _logger.info("Cloudflare page cache: the former extension's upgrade steps run from %s: %s",
                     '.'.join(map(str, version)), ', '.join('.'.join(map(str, v)) for v in done))
    return done
