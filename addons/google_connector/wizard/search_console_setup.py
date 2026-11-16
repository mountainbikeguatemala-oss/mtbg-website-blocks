"""Google Search Console's settings (the app card's Settings): the property to import, chosen from a dropdown of the
Google account's Search Console properties once the account is connected with Search Console access."""
from odoo import api, fields, models

from ..models.client import GoogleError
from ..models.search_console import APP


class SearchConsoleSetup(models.TransientModel):
    _name = "google.search.console.setup"
    _description = "Google Search Console settings"

    site_id = fields.Many2one("google.search.console.site", string="Property", domain=[("listed", "=", True)],
                              help="The Search Console property to import: a domain property (sc-domain:) counts "
                                   "every address of the domain (www, without www, http and https).")
    site_count = fields.Integer(readonly=True)
    status = fields.Char(readonly=True)
    problem = fields.Text(readonly=True)
    needs_reconnect = fields.Boolean(readonly=True)
    summary = fields.Text(readonly=True)
    progress = fields.Char(readonly=True)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        Connector = self.env["google.connector"]
        Connector._check_admin()
        Connector._google_sync_apps()
        Site = self.env["google.search.console.site"].sudo()
        app = Connector._google_app(APP)
        sites, problem = Site.search([("listed", "=", True)]), ""
        if app.status == "ready":
            try:
                sites = Site._sc_refresh_sites()
            except GoogleError as error:
                problem = Site._sc_error_text(error)
        site = Site._sc_preferred(sites)
        chosen = Site._sc_selected()
        problem = problem or (chosen._sc_problem() if chosen else Site._sc_blocker() if app.on else "")
        if app.status == "ready" and not sites and not problem:
            problem = self.env._("The connected Google account sees no property in Search Console: it must be an "
                                 "Owner or Full user of the website's property (Search Console › Settings › Users "
                                 "and permissions).")
        statuses = dict(app._fields["status"]._description_selection(self.env))
        values.update({
            "site_id": site.id or False, "site_count": len(sites), "status": statuses.get(app.status, ""),
            "problem": problem or False, "needs_reconnect": app.status in ("missing", "no_account"),
            "summary": chosen._sc_summary_text() if chosen else False,
            "progress": chosen._sc_progress() if chosen else False})
        return values

    def _reopen(self):
        return {"type": "ir.actions.act_window", "res_model": self._name, "view_mode": "form", "target": "new",
                "name": self.env._("Google Search Console")}

    def action_save(self):
        self.env["google.connector"]._check_admin()
        self.ensure_one()
        if self.site_id and not self.site_id.selected:
            self.site_id.sudo()._sc_select()
            cron = self.env.ref("google_connector.ir_cron_search_console", raise_if_not_found=False)
            if cron:
                cron.sudo()._trigger()
        return {"type": "ir.actions.act_window_close"}

    def action_refresh(self):
        return self._reopen()

    def action_import_now(self):
        """The last days and the next chunk of history now (an error shows here and in the sync log)."""
        self.env["google.connector"]._check_admin()
        self.action_save()
        site = self.env["google.search.console.site"].sudo()._sc_selected()
        if site and not site._sc_blocker():
            site._sc_refresh() and not site.backfill_done and site._sc_backfill_chunk()
        return self._reopen()

    def action_reconnect(self):
        """Google's consent page for the app's account, asking for Search Console's read access too."""
        app = self.env["google.connector"]._google_app(APP)
        account = app._google_account()
        if account:
            return account.action_connect()
        return self.env["ir.actions.actions"]._for_xml_id("google_connector.action_google_setup")

    def action_open_report(self):
        return self.env["ir.actions.actions"]._for_xml_id("google_connector.action_search_console_day")
