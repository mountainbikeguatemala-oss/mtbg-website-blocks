"""19.0.1.6.0: posting on several Pages. On each connection, the Page and the Instagram account posts went on until
now (the first ticked, in the Pages' order) become the defaults."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Page = env["meta.connector.page"].with_context(active_test=False)
    for app in env["meta.connector.app"].with_context(active_test=False).search([]):
        pages = Page.search([("app_id", "=", app.id)])
        if not pages.filtered("post_default_page"):
            first = pages.filtered("use_page")[:1]
            if first:
                first.post_default_page = True
        if not pages.filtered("post_default_instagram"):
            first = pages.filtered(lambda p: p.use_instagram and p.ig_id)[:1]
            if first:
                first.post_default_instagram = True
