"""Employee list sync (caller side): a change to an internal user runs the sync to the linked sites soon."""
from odoo import api, models

from .site_link import USER_SYNC_FIELDS


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        if users.filtered(lambda u: not u.share):
            self.env['site.link']._site_link_sync_users_soon()
        return users

    def write(self, vals):
        res = super().write(vals)
        if USER_SYNC_FIELDS.intersection(vals):
            self.env['site.link']._site_link_sync_users_soon()
        return res
