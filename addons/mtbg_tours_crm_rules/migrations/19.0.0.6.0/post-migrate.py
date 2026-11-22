"""0.6.0: the Alert Feed (when installed) gets the rules "Leads waiting on us" and "Follow-ups due". The reply status
itself is computed by the Communication Flow Designer (3.47.0, its own migration from the message history). Nothing
is sent."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    from odoo.addons.mtbg_tours_crm_rules.models.reply_status import sync_alert_sources
    sync_alert_sources(api.Environment(cr, SUPERUSER_ID, {}))
