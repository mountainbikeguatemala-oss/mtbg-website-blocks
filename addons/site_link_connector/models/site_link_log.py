"""Failed calls to linked sites (calls that worked are not logged), kept 90 days. Admins only."""
from datetime import timedelta

from odoo import api, fields, models

KEEP_DAYS = 90


class SiteLinkLog(models.Model):
    _name = 'site.link.log'
    _description = 'Linked site: failed call'
    _order = 'id desc'

    site_id = fields.Many2one('site.link', string='Site', index=True, ondelete='cascade', readonly=True)
    model = fields.Char(readonly=True)
    method = fields.Char(readonly=True)
    status = fields.Integer(string='HTTP Status', readonly=True, help="0: no answer (unreachable, time limit, setup).")
    message = fields.Text(readonly=True)
    duration_ms = fields.Integer(string='Duration (ms)', readonly=True)

    @api.model
    def _site_link_cleanup(self):
        """Cron: the log keeps its last KEEP_DAYS days."""
        self.sudo().search([('create_date', '<', fields.Datetime.now() - timedelta(days=KEEP_DAYS))]).unlink()
