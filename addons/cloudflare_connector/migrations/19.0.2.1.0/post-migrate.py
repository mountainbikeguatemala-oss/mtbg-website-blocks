"""19.0.2.1.0 (owner 2026-11-18: each website its own Cloudflare zone): the zone saved by Set up Cloudflare stays as it
is (Settings › Cloudflare: zone, its ID, the cache-purge token) and stays the zone of the website it was for, named
here once (``cloudflare_connector.zone_website_id``): the first website whose address is in it, else the first website.
The other websites have no zone until one is given them (Website › Settings › Cloudflare page cache). Nothing sent."""
from odoo import SUPERUSER_ID, api

from odoo.addons.cloudflare_connector.models.connector import P


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    ICP = env['ir.config_parameter'].sudo()
    if not (ICP.get_param(P + 'zone_id') or '').strip() or ICP.get_param(P + 'zone_website_id'):
        return
    website = env['cloudflare.api']._default_zone_website()
    if website:
        ICP.set_param(P + 'zone_website_id', str(website.id))
