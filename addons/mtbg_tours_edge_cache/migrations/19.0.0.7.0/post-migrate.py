"""0.7.0: the Cloudflare zone and purge token move to Cloudflare Connector's settings.

Plain SQL on ir_config_parameter (no ORM write: a mtbg_tours.* parameter write would itself note a cache change).
A value is moved only where the connector has none yet (an administrator who already ran Set up Cloudflare keeps
the connector's own). The connector reads these keys whether it is installed before or after this upgrade. The old
token is removed either way: it is no longer read, and a secret should not linger.
"""
import logging

_logger = logging.getLogger(__name__)

MOVES = (('mtbg_tours.edge_cache_zone', 'cloudflare_connector.zone_id'),
         ('mtbg_tours.edge_cache_token', 'cloudflare_connector.api_token'))


def migrate(cr, version):
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
            _logger.info("Edge Cache 0.7.0: %s moved to %s", old, new)
        cr.execute("DELETE FROM ir_config_parameter WHERE key = %s", [old])
