"""The Zoho access token (about an hour long), shared by every Zoho app of the suite and by Invoicing's Books sync.

It is kept here, not in system parameters: writing a system parameter empties Odoo's caches in every worker, the
website's page cache included, so renewing the token every hour made the next page of each worker slow (page speed,
2026-10-30). The self client (client id, secret, refresh token) stays in the parameters: only the setup writes it.
"""
from odoo import api, fields, models


class MtbgZohoToken(models.Model):
    _name = 'mtbg.zoho.token'
    _description = 'Zoho access token'

    access_token = fields.Char(copy=False)
    expires_at = fields.Float(copy=False, help="When the token ends (seconds since 1970)")

    @api.model
    def _mtbg_get(self):
        """(token, expires_at) as saved, ('', 0.0) without one."""
        row = self.sudo().search([], limit=1)
        return (row.access_token or '', row.expires_at or 0.0)

    @api.model
    def _mtbg_set(self, token, expires_at=0.0):
        """Save the token (``False``: forget it)."""
        row = self.sudo().search([], limit=1)
        values = {'access_token': token or False, 'expires_at': expires_at if token else 0.0}
        if row:
            row.write(values)
        elif token:
            self.sudo().create(values)
