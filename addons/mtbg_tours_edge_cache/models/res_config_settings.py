from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    mtbg_edge_cache = fields.Boolean(
        string="Cloudflare page cache", config_parameter='mtbg_tours.edge_cache',
        help="Anonymous visitors get the listed pages from Cloudflare's cache; any change empties it. Off: every page "
             "is built for every visitor (Cloudflare keeps nothing).")
    mtbg_edge_cache_connection = fields.Char(
        string="Cloudflare connection", compute='_compute_mtbg_edge_cache_connection',
        help="The zone and its cache-purge token come from Cloudflare Connector (Settings › Cloudflare › Set up "
             "Cloudflare).")
    mtbg_edge_cache_ttl = fields.Integer(
        string="Seconds Cloudflare keeps a page", config_parameter='mtbg_tours.edge_cache_ttl', default=2592000,
        help="Every edit in Odoo empties Cloudflare's cache at once, and prices, seats and dates come to the pages "
             "live: a page can stay a month (Cloudflare drops copies nobody asks for sooner).")
    mtbg_edge_cache_paths = fields.Char(
        string="Pages Cloudflare may keep", config_parameter='mtbg_tours.edge_cache_paths',
        help="Addresses separated by spaces, each in every language too (/blog is /es/blog as well). Ending in /: "
             "that address alone; else the address and everything under it (/blog: the blog and every post). The website's own pages (Website › Pages) are kept wherever they are, unless "
             "they are behind a password, a login or a group.")

    mtbg_edge_cache_live_values = fields.Html(
        string="Live values", compute='_compute_mtbg_edge_cache_live_values', sanitize=False,
        help="The prices, spaces and statuses the pages load after they open: never kept by Cloudflare.")

    def _compute_mtbg_edge_cache_connection(self):
        if 'cloudflare.api' not in self.env:
            text = self.env._("Cloudflare Connector is not installed")
        else:
            zone = self.env['cloudflare.api'].sudo().zone()
            ICP = self.env['ir.config_parameter'].sudo()
            if zone['id'] and ICP.get_param('cloudflare_connector.api_token'):
                text = self.env._("Zone %s (Settings › Cloudflare)", zone['name'] or zone['id'])
            else:
                text = self.env._("Not set up: Settings › Cloudflare › Set up Cloudflare")
        for settings in self:
            settings.mtbg_edge_cache_connection = text

    def _compute_mtbg_edge_cache_live_values(self):
        table = self.env['mtbg.edge.cache.live.values'].mtbg_table_html()
        for settings in self:
            settings.mtbg_edge_cache_live_values = table

    def set_values(self):
        was_on = self.env['mtbg.edge.cache']._mtbg_params()['on']
        super().set_values()
        on = self.env['mtbg.edge.cache']._mtbg_params()['on']
        self.env['mtbg.edge.cache']._mtbg_sync_jobs()
        if on != was_on:
            self.env['mtbg.edge.cache']._mtbg_purge(self.env._("Switched on") if on else self.env._("Switched off"))

    def action_mtbg_edge_cache_purge(self):
        """The "Purge cache now" button (0.5.1; was "Test purge"): the values typed saved first, then the purge."""
        self.ensure_one()
        self.execute()
        return self.env['mtbg.edge.cache.log'].action_mtbg_purge_now()

    def action_mtbg_edge_cache_log(self):
        """The Purge log button (an object button: it is called on the settings record)."""
        return self.env['ir.actions.act_window']._for_xml_id('mtbg_tours_edge_cache.action_edge_cache_log')
