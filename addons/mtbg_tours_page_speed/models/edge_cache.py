"""What of this extension the public pages show, for Cloudflare Connector's page cache (where installed:
no dependency either way; its models/sources.py reads this). A change to a declared system parameter empties
Cloudflare's cache."""
from odoo import models


class MtbgPageSpeedLean(models.AbstractModel):
    _inherit = 'mtbg.page.speed.lean'
    # 0.9.2: the switches that change what the pages carry (lean pages, the first screen first), no longer every
    # mtbg_tours.* (Catalog's until then); its own bookkeeping is kept under mtbg_page_speed.* (never purges)
    _mtbg_edge_cache_param_prefixes = ('mtbg_tours.page_speed_',)
