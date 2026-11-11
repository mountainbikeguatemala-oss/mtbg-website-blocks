"""The Google connector's API (frozen: Tours and CFD modules build on it).

* ``_google_app_specs()``: each app module extends it with its app: {code: {label, module, description,
  read_scopes, write_scopes, needs_account, uses_maps_key, uses_server_key, settings_action, sequence}}.
* ``app_on(code)``, ``writes_allowed(code)``.
* ``client(code, write=False, account=None)``: a GoogleClient (token refresh, rate limits, retries); GoogleError
  when the app is off, writes are not allowed, or no Google account is connected.
* ``maps_key()``: the Maps API key, "" when Maps is off.
* ``missing_scopes(code=None)``, ``consent_url(account=None)``.
* ``sync_log(code, operation)``: a context manager giving a google.connector.log row (``.add(...)``).

Credentials (the OAuth client, the Maps key) are entered only in the setup wizard; they live in system parameters
no one but administrators reads, and google_connector's neutralize clears them."""
import hashlib
import hmac
import time
from contextlib import contextmanager
from urllib.parse import urlencode

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .catalog import CATALOG
from .client import GoogleClient, GoogleError, email_from_id_token, token_request

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
OAUTH_PATH = "/google_connector/oauth"
BASE_SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email"]
PARAM = "google_connector."


class GoogleConnector(models.AbstractModel):
    _name = "google.connector"
    _description = "Google connector"

    # ------------------------------------------------------------------
    # Apps
    # ------------------------------------------------------------------
    @api.model
    def _google_app_specs(self):
        """{code: spec} of the installed apps: each app module adds its own (see the module docstring)."""
        return {}

    @api.model
    def _google_sync_apps(self):
        """One google.connector.app row per declared app, and per app of the catalog whose module exists here
        (a card with Install); their switches stay as they are. An app several modules use (e.g. Gmail: the Gmail
        and Google Voice channels) lists them (``uses``); a row no module declares any more is removed."""
        App = self.env["google.connector.app"].sudo()
        rows = {app.code: app for app in App.search([])}
        specs = dict(self._google_app_specs())
        known = set(self.env["ir.module.module"].sudo().search([("name", "in", [c["module"] for c in CATALOG.values()])])
                    .mapped("name"))
        for code, entry in CATALOG.items():
            if code not in specs and entry["module"] in known:
                specs[code] = entry
        for code in set(rows) - set(specs) - set(CATALOG):
            rows.pop(code).unlink()
        for code, spec in specs.items():
            description = spec.get("description") or ""
            if spec.get("uses"):
                description = "%s\n%s" % (description, self.env._("Used by: %s", ", ".join(spec["uses"]))) \
                    if description else self.env._("Used by: %s", ", ".join(spec["uses"]))
            values = {"label": spec.get("label") or code, "description": description or False,
                      "module": spec.get("module") or False, "sequence": spec.get("sequence", 10),
                      "read_scopes": " ".join(spec.get("read_scopes") or []) or False,
                      "write_scopes": " ".join(spec.get("write_scopes") or []) or False,
                      "needs_account": spec.get("needs_account", True), "uses_maps_key": bool(spec.get("uses_maps_key")),
                      "uses_server_key": bool(spec.get("uses_server_key")),
                      "settings_action": spec.get("settings_action") or False}
            if code in rows:
                changed = {k: v for k, v in values.items() if rows[code][k] != v}
                if changed:
                    rows[code].write(changed)  # what the module declares; the switches stay
            else:
                App.create(dict(values, code=code))
        return App.search([])

    @api.model
    def _google_app(self, code):
        app = self.env["google.connector.app"].sudo().search([("code", "=", code)], limit=1)
        if not app and code in self._google_app_specs():
            app = self._google_sync_apps().filtered(lambda a: a.code == code)
        return app

    @api.model
    def app_on(self, code):
        app = self._google_app(code)
        return bool(app and app.on and app.installed)

    @api.model
    def writes_allowed(self, code):
        app = self._google_app(code)
        return bool(app and app.on and app.writes_allowed)

    @api.model
    def client(self, code, write=False, account=None):
        """The client an app calls Google with (its account's token, the connector's limits)."""
        app = self._google_app(code)
        if not app or not app.on:
            raise GoogleError(_("The Google app %s is off (Settings › Google).", app.label if app else code))
        if write and not app.writes_allowed:
            raise GoogleError(_("%s may not change anything in Google: allow writes in Settings › Google.", app.label))
        get = self.env["ir.config_parameter"].sudo().get_param
        limits = {"per_second": int(get(PARAM + "per_second", 5) or 5), "per_day": int(get(PARAM + "per_day", 2500) or 2500)}
        if not app.needs_account:  # e.g. Maps, PageSpeed: an API key, no Google account
            if app.uses_server_key:
                key = self.server_key()
                if not key:
                    raise GoogleError(_("No server API key yet for %s: Set up Google › API keys.", app.label))
            else:
                key = self.maps_key(check_on=False) if app.uses_maps_key else ""
                if not key:
                    raise GoogleError(_("No Maps key yet for %s: Set up Google › API keys.", app.label))
            return GoogleClient(self.env["google.connector.account"], app.sudo(), key=key, **limits)
        account = (account or app._google_account()).sudo()
        if not account or account.state != "connected":
            raise GoogleError(_("No Google account is connected for %s: Set up Google.", app.label), auth=True)
        # reading needs the read access only; a write also its write access
        needed = (app.read_scopes or "").split() + ((app.write_scopes or "").split() if write else [])
        missing = account._google_has_scopes(needed)
        if missing:
            raise GoogleError(_("%(account)s has not granted %(app)s the access it needs: Reconnect in Set up Google.",
                                account=account.email or account.name, app=app.label), auth=True,
                              missing_scopes=missing)
        return GoogleClient(account, app, **limits)

    @api.model
    def maps_key(self, check_on=True):
        """The Maps API key (for Places in the browser, Static Maps links); "" when Maps is off or unset."""
        if check_on and not self.app_on("maps"):
            return ""
        return self.env["ir.config_parameter"].sudo().get_param(PARAM + "maps_key") or ""

    @api.model
    def server_key(self):
        """The server API key (calls from this site's server, no Google account: PageSpeed Insights); never shown."""
        return self.env["ir.config_parameter"].sudo().get_param(PARAM + "server_key") or ""

    @api.model
    def missing_scopes(self, code=None):
        """The access still to grant: of one app (``code``), else of every app that is on."""
        apps = self.env["google.connector.app"].sudo().search([("on", "=", True)] + ([("code", "=", code)] if code else []))
        missing = []
        for app in apps.filtered("needs_account"):
            account = app._google_account()
            needed = app._google_scopes()
            missing += needed if not account else account._google_has_scopes(needed)
        return sorted(set(missing))

    @api.model
    def _google_scopes_wanted(self):
        """What a sign-in asks for: the apps that are on (reads, and writes where allowed)."""
        scopes = list(BASE_SCOPES)
        for app in self.env["google.connector.app"].sudo().search([("on", "=", True), ("needs_account", "=", True)]):
            scopes += app._google_scopes()
        return sorted(set(scopes))

    @contextmanager
    def sync_log(self, code, operation, account=None):
        """A google.connector.log row for one sync of ``code``; failed (with the error) if the block raises."""
        log = self.env["google.connector.log"].sudo().create({
            "app_code": code, "operation": operation, "account_id": account.id if account else False})
        try:
            yield log
        except Exception as error:
            log.write({"state": "failed", "finished_at": fields.Datetime.now(),
                       "note": "\n".join(filter(None, [log.note, str(error)]))})
            raise
        log.write({"state": "done", "finished_at": fields.Datetime.now()})

    # ------------------------------------------------------------------
    # The Google login (the setup wizard enters it; nothing else does)
    # ------------------------------------------------------------------
    @api.model
    def _check_admin(self):
        if not self.env.user.has_group("base.group_system"):
            raise AccessError(_("Only administrators can change the Google connection."))

    @api.model
    def _google_client(self):
        get = self.env["ir.config_parameter"].sudo().get_param
        client_id, secret = get(PARAM + "client_id"), get(PARAM + "client_secret")
        if not client_id or not secret:
            raise GoogleError(_("No Google OAuth client yet: Set up Google."), auth=True)
        return client_id, secret

    @api.model
    def _google_set_credentials(self, client_id=None, client_secret=None, maps_key=None, server_key=None):
        self._check_admin()
        ICP = self.env["ir.config_parameter"].sudo()
        for key, value in (("client_id", client_id), ("client_secret", client_secret), ("maps_key", maps_key),
                           ("server_key", server_key)):
            if value is not None:
                ICP.set_param(PARAM + key, (value or "").strip() or False)

    @api.model
    def redirect_uri(self):
        return self.env["ir.config_parameter"].sudo().get_param("web.base.url", "").rstrip("/") + OAUTH_PATH

    @api.model
    def _oauth_state(self, account):
        secret = self.env["ir.config_parameter"].sudo().get_param("database.secret")
        signature = hmac.new(secret.encode(), b"google-%d" % account.id, hashlib.sha256).hexdigest()[:32]
        return "%d-%s" % (account.id, signature)

    @api.model
    def _account_from_state(self, state):
        account_id, _sep, _signature = (state or "").partition("-")
        Account = self.env["google.connector.account"].sudo()
        account = Account.browse(int(account_id)).exists() if account_id.isdigit() else Account
        if not account or not hmac.compare_digest(self._oauth_state(account), state or ""):
            return Account
        return account

    @api.model
    def consent_url(self, account=None):
        """Google's consent page for ``account`` (a new account when None), asking for what the apps that are on
        need; access granted earlier stays (include_granted_scopes)."""
        client_id, _secret = self._google_client()
        account = account or self.env["google.connector.account"].sudo().create({})
        params = {"client_id": client_id, "redirect_uri": self.redirect_uri(), "response_type": "code",
                  "scope": " ".join(self._google_scopes_wanted()), "access_type": "offline", "prompt": "consent",
                  "include_granted_scopes": "true", "state": self._oauth_state(account)}
        if account.email:
            params["login_hint"] = account.email
        return "%s?%s" % (AUTH_URL, urlencode(params))

    @api.model
    def _oauth_done(self, account, code):
        """Google sent the administrator back with ``code`` for ``account``: keep the tokens and the address."""
        client_id, secret = self._google_client()
        tokens = token_request({"client_id": client_id, "client_secret": secret, "redirect_uri": self.redirect_uri(),
                                "grant_type": "authorization_code", "code": code})
        account = account.sudo()
        values = {"access_token": tokens["access_token"], "token_expiry": time.time() + tokens.get("expires_in", 3600) - 60,
                  "granted_scopes": tokens.get("scope") or False, "state": "connected", "state_reason": False}
        if tokens.get("refresh_token"):
            values["refresh_token"] = tokens["refresh_token"]
        account.write(values)
        email = email_from_id_token(tokens.get("id_token"))
        if email:
            same = account.search([("email", "=ilike", email), ("id", "!=", account.id)], limit=1)
            if same:  # signed in again with an account already here: keep the first, with the new tokens
                same.write(dict(values, refresh_token=values.get("refresh_token") or same.refresh_token))
                account.app_ids.write({"account_id": same.id})
                account.unlink()
                self._google_changed()
                return same
            account.write({"email": email, "name": email})
        self._google_changed()
        return account

    @api.model
    def _google_changed(self):
        """A Google account signed in or out, an app switched: the apps using Google take it at once (not at their
        next cron, which may be paused). Apps extend it (e.g. a Gmail mailbox picks the account of its address)."""

    @api.model
    def _google_check_client(self, client_id, client_secret):
        """None when Google knows this OAuth client (a made-up code is refused as invalid_grant), else its error."""
        try:
            token_request({"client_id": client_id, "client_secret": client_secret, "redirect_uri": self.redirect_uri(),
                           "grant_type": "authorization_code", "code": "google-connector-check"})
        except GoogleError as error:
            return None if error.code == "invalid_grant" else str(error)
        return None

