"""The Zoho sync log: every write sent to a Zoho app and every failed call (reads that worked are not logged)."""
from datetime import timedelta

from odoo import api, fields, models

KEEP_DAYS = 90


class MtbgZohoLog(models.Model):
    _name = 'mtbg.zoho.log'
    _description = 'Zoho sync log'
    _order = 'id desc'

    app = fields.Selection([('books', 'Zoho Books'), ('expense', 'Zoho Expense'), ('shifts', 'Zoho Shifts'),
                            ('crm', 'Zoho CRM')], string='Zoho App', index=True, readonly=True)
    method = fields.Char(readonly=True)
    path = fields.Char(readonly=True)
    status = fields.Integer(string='HTTP Status', readonly=True)
    ok = fields.Boolean(string='OK', readonly=True, index=True)
    message = fields.Char(readonly=True)
    duration_ms = fields.Integer(string='Duration (ms)', readonly=True)
    res_model = fields.Char(string='Odoo Model', readonly=True)
    res_id = fields.Many2oneReference(string='Odoo Record ID', model_field='res_model', readonly=True)

    @api.model
    def _mtbg_cleanup(self):
        """Cron: the log keeps its last KEEP_DAYS days."""
        self.sudo().search([('create_date', '<', fields.Datetime.now() - timedelta(days=KEEP_DAYS))]).unlink()
