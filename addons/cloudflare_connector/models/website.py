"""Each website its own Cloudflare zone (19.0.2.1.0, owner 2026-11-18: one database, two websites, each its own
Cloudflare zone): the zone its pages are purged in and kept by the page cache. Empty: the zone saved by Set up
Cloudflare, for the website it is for (models/connector.py ``cloudflare.api.zone``)."""
from odoo import fields, models


class Website(models.Model):
    _inherit = "website"

    cloudflare_zone_name = fields.Char(
        "Cloudflare zone", groups="base.group_system",
        help="This website's zone in Cloudflare (its domain, e.g. example.com). Empty: the zone of Settings › "
             "Cloudflare, when this website's address is in it (or it is the website that zone was set up for).")
    cloudflare_zone_id = fields.Char(
        "Cloudflare zone ID", groups="base.group_system",
        help="The zone's ID (Cloudflare › the domain's Overview › API › Zone ID). The cache-purge token of Settings › "
             "Cloudflare must be allowed to purge this zone too (Zone › Cache Purge › Purge).")
