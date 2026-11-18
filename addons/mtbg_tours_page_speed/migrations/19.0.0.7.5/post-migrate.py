"""0.7.5: the speed log's time is the code's, never an update's: the job is marked never to be rewritten by an update,
and set to the coming 02:30 in the business's time zone (Settings › Operator Timezone)."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['ir.model.data'].search([('module', '=', 'mtbg_tours_page_speed'), ('name', '=', 'cron_speed_log')]).write(
        {'noupdate': True})
    env['mtbg.page.speed.log']._mtbg_schedule_night()
