"""What of this extension the public pages show, for Cloudflare Page Cache (mtbg_tours_edge_cache, where installed:
no dependency either way; its models/sources.py reads these). An edit to a watched model empties Cloudflare's cache."""
from odoo import models


class MtbgContentBlock(models.Model):
    # the reusable blocks: an edit shows on every page using them
    _inherit = 'mtbg.tours.content.block'
    _mtbg_edge_cache_watch = True


class MtbgPageTemplate(models.Model):
    # the page templates laying out the pages (the editor's unsaved preview, draft_layout, is no change to the site)
    _inherit = 'mtbg.page.template'
    _mtbg_edge_cache_watch = {'name', 'kind', 'is_default', 'active', 'line_ids', 'slot_order', 'hidden_slots',
                              'category_ids'}


class MtbgPageTemplateLine(models.Model):
    _inherit = 'mtbg.page.template.line'
    _mtbg_edge_cache_watch = True
