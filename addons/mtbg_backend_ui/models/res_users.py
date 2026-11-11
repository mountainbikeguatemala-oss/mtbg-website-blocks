"""Who may change the admin's shared screens: boards, record cards, the settings pages and the translated texts."""
from odoo import models


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _mtbg_ui_manager(self):
        """Whether this user may change the boards, the cards' look, the settings pages and the translated texts.
        Administrators by default; a suite narrows or widens it (Tours Core: its managers)."""
        self.ensure_one()
        return self.has_group('base.group_system')
