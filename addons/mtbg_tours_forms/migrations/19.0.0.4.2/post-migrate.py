from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """The messaging terms (owner, 2026-10-28): the owner's wording copied into the settings."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['mtbg.text.setting'].mtbg_seed()
