"""0.4.0 on a site without Tours: the contact types are new (every contact a lead): typed from what is on record
(ourselves, suppliers, those who paid), then the source channels from history. With Tours: nothing (its contacts
have their types already). Nothing is sent."""
import logging

from odoo import SUPERUSER_ID, api

from odoo.addons.mtbg_tours_crm_rules.hooks import tours_pipeline

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if tours_pipeline(cr):
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    counts = env['res.partner']._mtbg_classify_on_install()
    _logger.info("Contact Rules 0.4.0: contacts typed; source channels from history: %s", counts)
