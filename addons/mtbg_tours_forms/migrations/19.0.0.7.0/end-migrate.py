"""0.7.0 (owner, 2026-11-16: Odoo's CRM retired): /contactus redirects to /contact-us; the Lead Generation Bot is
archived (models/form.py ``_mtbg_retire_crm_extras``)."""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _logger.info("Forms 0.7.0: %s", env['mtbg.form']._mtbg_retire_crm_extras())
