"""0.9.0: the rows logged before get their page title: the title their page had on another night or its website
page's name, here (nothing fetched during the update); the other pages' own <title> by the speed log's job, a few a
run, starting a minute after the update."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['mtbg.page.speed.log']._mtbg_fill_titles(limit=100000, fetch=False)
    cron = env.ref('mtbg_tours_page_speed.cron_speed_log', raise_if_not_found=False)
    if cron and cron.active:
        cron._trigger()
