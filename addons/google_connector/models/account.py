"""A Google account connected through the connector (one sign-in, used by the apps that pick it)."""
import time

from odoo import _, api, fields, models

from .client import GoogleError, token_request


class GoogleConnectorAccount(models.Model):
    _name = "google.connector.account"
    _description = "Google account (Google connector)"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    name = fields.Char(required=True, default=lambda self: _("Google account"))
    email = fields.Char(readonly=True, help="The Google account signed in (filled in at sign-in).")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)
    state = fields.Selection([("draft", "Not connected"), ("connected", "Connected"), ("error", "Needs attention")],
                             default="draft", required=True, readonly=True)
    state_reason = fields.Char(readonly=True)
    granted_scopes = fields.Char(readonly=True, copy=False, groups="base.group_system")
    refresh_token = fields.Char(copy=False, groups="base.group_system")
    access_token = fields.Char(copy=False, groups="base.group_system")
    token_expiry = fields.Float(copy=False, groups="base.group_system")
    app_ids = fields.One2many("google.connector.app", "account_id", string="Apps")

    def _google_token(self):
        """A valid access token (refreshed when old); GoogleError(auth=True) when the sign-in is gone."""
        account = self.sudo()
        if not account.refresh_token:
            raise GoogleError(_("%s is not connected to Google.", account.email or account.name), auth=True)
        if account.access_token and account.token_expiry > time.time():
            return account.access_token
        client_id, secret = self.env["google.connector"]._google_client()
        try:
            tokens = token_request({"client_id": client_id, "client_secret": secret,
                                    "grant_type": "refresh_token", "refresh_token": account.refresh_token})
        except GoogleError as error:
            account.write({"state": "error", "state_reason": str(error)[:250]})
            raise
        values = {"access_token": tokens["access_token"],
                  "token_expiry": time.time() + tokens.get("expires_in", 3600) - 60}
        if tokens.get("scope"):
            values["granted_scopes"] = tokens["scope"]
        account.write(values)
        return tokens["access_token"]

    def _google_forget_access_token(self):
        self.sudo().write({"access_token": False, "token_expiry": 0})

    def _google_has_scopes(self, scopes):
        granted = set((self.sudo().granted_scopes or "").split())
        return [scope for scope in scopes if scope not in granted]

    def action_connect(self):
        """Sign in (again) to Google with the access the apps that are on need."""
        self.env["google.connector"]._check_admin()
        self.ensure_one()
        return {"type": "ir.actions.act_url", "target": "self", "url": self.env["google.connector"].consent_url(self)}

    def action_disconnect(self):
        self.env["google.connector"]._check_admin()
        self.sudo().write({"refresh_token": False, "access_token": False, "token_expiry": 0, "state": "draft",
                           "state_reason": False, "granted_scopes": False})
        self.env["google.connector"]._google_changed()

    @api.model
    def _google_for_email(self, email):
        """The connector's account of a Google address (created, not connected, when missing)."""
        email = (email or "").strip().lower()
        account = self.sudo().with_context(active_test=False).search([("email", "=ilike", email)], limit=1) if email \
            else self.sudo()
        return account or self.sudo().create({"name": email or _("Google account"), "email": email or False})
