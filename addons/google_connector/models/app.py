"""One Google app of the connector (Gmail, Voice, Calendar, Maps...): declared by its module
(google.connector._google_app_specs), switched on here, with or without writes, on one Google account."""
from odoo import _, api, fields, models


class GoogleConnectorApp(models.Model):
    _name = "google.connector.app"
    _description = "Google app (Google connector)"
    _order = "sequence, id"

    code = fields.Char(required=True, readonly=True, index=True)
    label = fields.Char(required=True, readonly=True)
    description = fields.Char(readonly=True)
    module = fields.Char(readonly=True, help="The module that brings the app.")
    sequence = fields.Integer(default=10)
    on = fields.Boolean(string="On", help="The app may call Google.")
    writes_allowed = fields.Boolean(string="Writes Allowed",
                                    help="The app may also create, change or send in Google (else it only reads).")
    account_id = fields.Many2one("google.connector.account", string="Google Account", ondelete="set null",
                                 help="The Google account the app uses (the first connected one when empty).")
    read_scopes = fields.Text(readonly=True)
    write_scopes = fields.Text(readonly=True)
    needs_account = fields.Boolean(readonly=True, default=True)
    uses_maps_key = fields.Boolean(readonly=True)
    uses_server_key = fields.Boolean(readonly=True, help="Calls Google from the server with the connector's server API "
                                                          "key (e.g. PageSpeed Insights), no Google account.")
    settings_action = fields.Char(readonly=True)
    installed = fields.Boolean(compute="_compute_module")
    version = fields.Char(compute="_compute_module")
    status = fields.Selection([("not_installed", "Not installed"), ("off", "Off"), ("ready", "On"),
                               ("missing", "Missing access"), ("no_account", "No Google account"),
                               ("no_key", "No API key")], compute="_compute_status")
    first_sync_note = fields.Char(compute="_compute_first_sync_note",
                                  help="What the app shows only after its first read from Google.")
    calls_day = fields.Date(readonly=True, copy=False)
    calls_today = fields.Integer(readonly=True, copy=False)

    _code_unique = models.Constraint("UNIQUE(code)", "One row per Google app.")

    def _compute_first_sync_note(self):
        from .catalog import FIRST_SYNC
        for app in self:
            app.first_sync_note = self.env._(FIRST_SYNC[app.code]) if app.code in FIRST_SYNC else False

    def _compute_module(self):
        modules = {m.name: m for m in self.env["ir.module.module"].sudo().search([("name", "in", self.mapped("module"))])}
        for app in self:
            module = modules.get(app.module)
            app.installed = bool(module and module.state == "installed") or not app.module
            app.version = module.installed_version if module else False

    @api.depends("on", "writes_allowed", "account_id.state", "account_id.granted_scopes", "installed")
    @api.depends_context("uid")
    def _compute_status(self):
        Connector = self.env["google.connector"]
        for app in self:
            if not app.installed:
                app.status = "not_installed"
            elif not app.on:
                app.status = "off"
            elif app.uses_maps_key and not Connector.maps_key(check_on=False):
                app.status = "no_key"
            elif app.uses_server_key and not Connector.server_key():
                app.status = "no_key"
            elif app.needs_account and not app._google_account():
                app.status = "no_account"
            elif app.needs_account and app._google_account()._google_has_scopes(app._google_scopes()):
                app.status = "missing"
            else:
                app.status = "ready"

    def _google_scopes(self):
        """The access the app needs as it is switched (reads, and writes when allowed)."""
        self.ensure_one()
        scopes = (self.read_scopes or "").split()
        if self.writes_allowed:
            scopes += (self.write_scopes or "").split()
        return scopes

    def _google_account(self):
        self.ensure_one()
        if self.account_id and self.account_id.state == "connected":
            return self.account_id
        return self.account_id or self.env["google.connector.account"].sudo().search(
            [("state", "=", "connected")], limit=1)

    def _google_count_call(self, per_day):
        """One more call today: False when the day's limit is reached."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        app = self.sudo()
        count = app.calls_today + 1 if app.calls_day == today else 1
        if count > per_day:
            return False
        self.env.cr.execute("UPDATE google_connector_app SET calls_day = %s, calls_today = %s WHERE id = %s",
                            (today, count, app.id))
        app.invalidate_recordset(["calls_day", "calls_today"])
        return True

    def action_open_settings(self):
        self.ensure_one()
        if not self.settings_action:
            return False
        return self.env["ir.actions.actions"]._for_xml_id(self.settings_action)

    def write(self, vals):
        switched = {"on", "writes_allowed", "account_id"} & set(vals)
        if switched:
            self.env["google.connector"]._check_admin()
        result = super().write(vals)
        if switched:
            self.env["google.connector"]._google_changed()
        return result

    @api.model
    def google_card_data(self):
        """The settings' cards: one per declared app."""
        self.env["google.connector"]._google_sync_apps()
        statuses = dict(self._fields["status"]._description_selection(self.env))
        return [{"id": app.id, "code": app.code, "label": app.label, "description": app.description or "",
                 "module": app.module or "", "version": app.version or "", "installed": app.installed,
                 "on": app.on, "writes_allowed": app.writes_allowed, "status": app.status,
                 "status_label": statuses.get(app.status, ""), "account": app._google_account().email or "",
                 "has_writes": bool(app.write_scopes), "settings": bool(app.settings_action)}
                for app in self.sudo().search([])]
