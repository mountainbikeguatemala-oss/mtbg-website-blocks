"""The connection to Meta: the operator's own Meta app, the Facebook login of a person who manages the Pages, and the
Pages found (with their Instagram accounts) and which of them this site uses. Its form is the setup (Settings ›
Meta): each step says exactly what to do in Meta and checks it at once.

1. app:   the Meta app's ID and secret (a free app, made once: the step lists the clicks);
2. login: "Connect with Facebook" (or a pasted token): a long-lived login, so the Pages' tokens never expire;
3. pages: tick the Pages and Instagram accounts this site uses (the apps then use them: messages, the feed...);
4. posting: only when an app posts (Marketing installed): the Meta app's use cases, the Instagram account linked
   to the Page, a new login with the posting permissions, then a check of each (green / red);
5. done.

Every day the login and the Pages' tokens are checked (each Page's ``state``); the apps hear of it
(``meta.connector._meta_pages_changed``).
"""
import logging
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from . import graph

_logger = logging.getLogger(__name__)

WEBHOOK_PATH = "/meta_connector/webhook"
OAUTH_PATH = "/meta_connector/oauth"
# a connection moved from Communication Flows keeps the addresses its Meta app already knows
LEGACY_WEBHOOK_PATH = "/cfd/meta/webhook"
LEGACY_OAUTH_PATH = "/cfd/meta/oauth"
STEPS = [("app", "Meta app"), ("login", "Facebook login"), ("pages", "Pages"), ("posting", "Posting"), ("done", "Done")]
PAGE_STATES = [("new", "Not checked"), ("connected", "Connected"), ("disconnected", "Disconnected")]


class MetaConnectorApp(models.Model):
    _name = "meta.connector.app"
    _description = "Meta Connection"

    name = fields.Char(required=True, default=lambda self: _("Facebook & Instagram"))
    active = fields.Boolean(default=True)
    step = fields.Selection(STEPS, default="app", required=True)
    app_id = fields.Char(string="App ID", copy=False)
    app_secret = fields.Char(string="App Secret", groups="base.group_system", copy=False)
    app_name = fields.Char(string="App Name (Meta)", readonly=True, copy=False)
    config_id = fields.Char(string="Login Configuration ID", copy=False,
                            help="Only for apps that ask for one (Facebook Login for Business > Configurations): "
                                 "leave empty otherwise.")
    verify_token = fields.Char(readonly=True, copy=False, groups="base.group_system",
                               default=lambda self: secrets.token_urlsafe(24))
    oauth_state = fields.Char(copy=False, groups="base.group_system")
    user_token = fields.Char(groups="base.group_system", copy=False)
    manual_token = fields.Char(string="Or paste a user token", groups="base.group_system", copy=False,
                               help="From Meta's Graph API Explorer (the app selected, the permissions of the "
                                    "list): for an Odoo that is not on https yet.")
    user_name = fields.Char(string="Connected as", readonly=True, copy=False)
    user_token_expires = fields.Datetime(string="Login Expires", readonly=True, copy=False,
                                         help="Empty: never (the Pages' tokens never expire either).")
    granted_scopes = fields.Char(string="Permissions Granted", readonly=True, copy=False,
                                 help="What the login may do (Meta's answer, checked at each login and every day).")
    granted_targets = fields.Json(readonly=True, copy=False,
                                  help="For each permission limited to some assets, their IDs (e.g. the WhatsApp "
                                       "business accounts the login reaches).")
    human_agent = fields.Boolean(
        string="Human Agent permission",
        help="Meta granted the app the Human Agent permission (App Review): staff may answer up to 7 days after "
             "the customer's last message instead of 24 hours.")
    legacy_urls = fields.Boolean(readonly=True, copy=False,
                                 help="Moved from Communication Flows: keeps the addresses its Meta app knows.")
    webhook_url = fields.Char(compute="_compute_urls", string="Webhook Callback URL")
    redirect_url = fields.Char(compute="_compute_urls", string="OAuth Redirect URL")
    https = fields.Boolean(compute="_compute_urls")
    webhook_state = fields.Selection([("none", "Not set"), ("ok", "Registered"), ("manual", "Polling only")],
                                     default="none", readonly=True, copy=False)
    page_ids = fields.One2many("meta.connector.page", "app_id", string="Pages")
    scopes = fields.Char(compute="_compute_scopes", string="Permissions")
    posting_wanted = fields.Boolean(compute="_compute_posting")
    posting_checks = fields.Html(compute="_compute_posting", sanitize=False, string="Posting checks")
    message = fields.Text(readonly=True)
    message_kind = fields.Selection([("info", "Info"), ("success", "Success"), ("danger", "Problem")], default="info")

    def _compute_urls(self):
        for app in self:
            base = app.get_base_url()
            app.webhook_url = base + (LEGACY_WEBHOOK_PATH if app.legacy_urls else WEBHOOK_PATH)
            app.redirect_url = base + (LEGACY_OAUTH_PATH if app.legacy_urls else OAUTH_PATH)
            app.https = base.startswith("https://") or base.startswith(("http://localhost", "http://127.0.0.1"))

    def _compute_scopes(self):
        scopes = ", ".join(self.env["meta.connector"]._meta_scopes())
        for app in self:
            app.scopes = scopes

    @api.depends("granted_scopes", "page_ids.use_page", "page_ids.use_instagram", "page_ids.ig_id")
    def _compute_posting(self):
        from markupsafe import Markup
        wanted = self.env["meta.connector"]._meta_posting_wanted()
        for app in self:
            app.posting_wanted = wanted
            rows = app._posting_checks() if wanted else []
            app.posting_checks = Markup('<ul class="list-unstyled mb-0">%s</ul>') % Markup("").join(
                Markup('<li class="%s"><i class="fa %s me-2"/>%s</li>') % (
                    "text-success" if ok else "text-danger", "fa-check-circle" if ok else "fa-times-circle", label)
                for label, ok in rows) if rows else False

    def _posting_checks(self):
        """[(label, ok)]: each permission posting needs, granted to the login; the Page and the Instagram account
        ticked (with their IDs)."""
        self.ensure_one()
        granted = set((self.granted_scopes or "").split(","))
        rows = [(_("Permission %s", scope), scope in granted) for scope in graph.POSTING_SCOPES]
        page = self.page_ids.filtered("use_page")[:1]
        rows.append((_("Facebook Page: %s", "%s (%s)" % (page.name, page.page_id)) if page
                     else _("Facebook Page: none ticked"), bool(page)))
        ig = self.page_ids.filtered(lambda p: p.use_instagram and p.ig_id)[:1]
        rows.append((_("Instagram account: %s", "@%s (%s)" % (ig.ig_username or "", ig.ig_id)) if ig
                     else _("Instagram account: none linked to the Page and ticked"), bool(ig)))
        return rows

    def action_check_posting(self):
        """Posting step: Meta asked again what the login may do, then each check shows green or red."""
        self.ensure_one()
        self._check_admin()
        sudo = self.sudo()
        if sudo.user_token:
            try:
                self._store_grants(graph.debug_token(sudo.app_id, sudo.app_secret, sudo.user_token))
            except graph.GraphError as error:
                return self._say(_("Meta did not answer: %s", error), "danger")
        missing = [label for label, ok in self._posting_checks() if not ok]
        if missing:
            return self._say(_("Not ready yet: %s. Follow the steps above, then log in with Facebook again.",
                               "; ".join(missing)), "danger")
        return self._say(_("Posting is ready: every permission granted, the Page and the Instagram account ticked."),
                         "success")

    def action_finish_posting(self):
        self.ensure_one()
        self._check_admin()
        return self._say("", "info", "done")

    def action_back(self):
        order = [code for code, _label in STEPS]
        index = order.index(self.step)
        back = order[max(0, index - 1)]
        if back == "posting" and not self.env["meta.connector"]._meta_posting_wanted():
            back = "pages"
        return self._say("", "info", back)

    def _check_admin(self):
        if not self.env.user.has_group("base.group_system"):
            raise UserError(_("Only administrators can connect Facebook and Instagram (it stores Meta keys)."))

    def _say(self, message, kind="info", step=None):
        values = {"message": message, "message_kind": kind}
        if step:
            values["step"] = step
        self.write(values)
        return True

    @api.model
    def action_start(self):
        """Settings › Meta: the setup (the existing connection when there is one)."""
        self._check_admin()
        app = self.search([], limit=1) or self.create({})
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": app.id, "view_mode": "form",
                "views": [(False, "form")], "target": "current", "name": _("Set up Meta")}

    # ------------------------------------------------------------------ 1. the app
    def action_check_app(self):
        self.ensure_one()
        self._check_admin()
        app_id, secret = (self.app_id or "").strip(), (self.sudo().app_secret or "").strip()
        if not app_id or not secret:
            return self._say(_("Paste the App ID and the App Secret (App settings › Basic)."), "danger")
        try:
            info = graph.app_info(app_id, secret)
        except graph.GraphError as error:
            return self._say(_("Meta does not know this App ID and secret: %s", error), "danger")
        self.sudo().write({"app_id": app_id, "app_secret": secret, "app_name": info.get("name")})
        return self._say(_("App “%s” found. Now the Facebook login.", info.get("name")), "success", "login")

    # ------------------------------------------------------------------ 2. the login
    def action_login(self):
        """Open Facebook's login (it comes back to the OAuth address, then to this form)."""
        self.ensure_one()
        self._check_admin()
        state = secrets.token_urlsafe(24)
        self.sudo().oauth_state = state
        scopes = self.env["meta.connector"]._meta_scopes()
        return {"type": "ir.actions.act_url", "target": "self",
                "url": graph.login_url(self.app_id, self.redirect_url, state, self.config_id or None, scopes)}

    @api.model
    def _oauth_done(self, state, code=None, error=None):
        """Facebook's answer to the login. Returns the connection (or an empty recordset when ``state`` is unknown)."""
        app = self.sudo().search([("oauth_state", "=", state)], limit=1) if state else self.sudo()
        if not app:
            return app
        app.oauth_state = False
        if error or not code:
            app._say(_("Facebook login cancelled or refused: %s", error or _("no answer")), "danger", "login")
            return app
        try:
            token = graph.exchange_code(app.app_id, app.app_secret, app.redirect_url, code)
        except graph.GraphError as err:
            app._say(_("Facebook did not accept the login: %s", err), "danger", "login")
            return app
        app._use_user_token(token)
        return app

    def action_use_token(self):
        """The login without the redirect (e.g. no https yet): a user token pasted from Meta's Graph API Explorer."""
        self.ensure_one()
        self._check_admin()
        token = (self.sudo().manual_token or "").strip()
        if not token:
            return self._say(_("Paste the token first."), "danger")
        self.sudo().manual_token = False
        self._use_user_token(token)
        return True

    def _use_user_token(self, token):
        sudo = self.sudo()
        try:
            token, expires_in = graph.long_lived(sudo.app_id, sudo.app_secret, token)
            who = graph.me(token)
            found = graph.pages(token)
        except graph.GraphError as error:
            return self._say(str(error), "danger", "login")
        sudo.write({"user_token": token, "user_name": who.get("name"),
                    "user_token_expires": fields.Datetime.now() + timedelta(seconds=expires_in) if expires_in else False})
        try:
            self._store_grants(graph.debug_token(sudo.app_id, sudo.app_secret, token))
        except graph.GraphError as error:
            _logger.warning("Meta: the login's permissions not read: %s", error)
        self._load_pages(found)
        if not found:
            return self._say(_("Connected as %s, but Facebook gave no Page: log in again and tick every Page (and "
                               "Instagram account) when Facebook asks which ones the app may use.", who.get("name")),
                             "danger", "login")
        return self._say(_("Connected as %(who)s: %(count)s Page(s) found. Tick what this site uses.",
                           who=who.get("name"), count=len(found)), "success", "pages")

    def _store_grants(self, info):
        """The permissions Meta says the login has (debug_token), and the assets of those limited to some."""
        targets = {item["scope"]: [str(target) for target in item.get("target_ids") or []]
                   for item in info.get("granular_scopes") or [] if item.get("scope") and item.get("target_ids")}
        self.sudo().write({"granted_scopes": ",".join(info.get("scopes") or []) or False,
                           "granted_targets": targets or False})

    def _load_pages(self, found):
        """The Pages of the login, updated in place (apps point to them): new ones are ticked when none is used yet;
        one the login no longer gives is disconnected."""
        Page = self.env["meta.connector.page"].sudo()
        existing = {page.page_id: page for page in self.with_context(active_test=False).page_ids.sudo()}
        first = not any(page.use_page or page.use_instagram for page in existing.values())
        seen = set()
        for item in found:
            instagram = item.get("instagram_business_account") or {}
            values = {
                "app_id": self.id, "page_id": item["id"], "name": item.get("name"),
                "page_token": item.get("access_token"),
                "picture_url": ((item.get("picture") or {}).get("data") or {}).get("url"),
                "can_message": "MESSAGING" in (item.get("tasks") or ["MESSAGING"]),
                "ig_id": instagram.get("id") or False, "ig_username": instagram.get("username") or False,
                "ig_picture_url": instagram.get("profile_picture_url") or False,
                "state": "connected", "state_reason": False,
            }
            page = existing.get(item["id"])
            if page:
                if not values["ig_id"]:
                    values["use_instagram"] = False
                page.write(values)
            else:
                values.update(use_page=first, use_instagram=first and bool(values["ig_id"]))
                page = Page.create(values)
            seen.add(item["id"])
        for page_id, page in existing.items():
            if page_id not in seen:
                page.write({"state": "disconnected",
                            "state_reason": _("The last Facebook login did not give this Page.")})

    # ------------------------------------------------------------------ 3. the Pages
    def action_save_pages(self):
        self.ensure_one()
        self._check_admin()
        used = self.page_ids.filtered(lambda p: p.use_page or p.use_instagram)
        if not used:
            return self._say(_("Tick at least one Page or Instagram account."), "danger")
        webhook = self._register_webhooks()
        self.env["meta.connector"].with_context(meta_connector_setup=True)._meta_pages_changed(self.page_ids.sudo())
        self.env.ref("meta_connector.ir_cron_meta_instagram_feed")._trigger()
        notes = [_("This site uses: %s.", ", ".join(used.mapped("display_name")))]
        if webhook == "manual":
            notes.append(_("Without the webhook, new messages arrive every 10 minutes (see the Webhook box)."))
        if self.env["meta.connector"]._meta_posting_wanted():
            notes.append(_("Now Posting (Marketing): the Meta app's use cases, then a new Facebook login."))
            return self._say("\n".join(notes), "success", "posting")
        return self._say("\n".join(notes), "success", "done")

    def _register_webhooks(self):
        """The app's webhooks the apps need (Meta only calls public https addresses)."""
        sudo = self.sudo()
        wanted = self.env["meta.connector"]._meta_webhook_fields()
        if not self.page_ids.filtered("use_instagram"):
            wanted.pop("instagram", None)
        wanted = {obj: fields_ for obj, fields_ in wanted.items() if fields_}
        if not wanted:
            sudo.webhook_state = "none"
            return "none"
        if not self.get_base_url().startswith("https://"):
            sudo.webhook_state = "manual"
            return "manual"
        try:
            for obj, fields_ in wanted.items():
                graph.set_app_webhook(sudo.app_id, sudo.app_secret, obj, self.webhook_url, sudo.verify_token, fields_)
        except graph.GraphError as error:
            _logger.warning("Meta: webhook not registered: %s", error)
            sudo.webhook_state = "manual"
            return "manual"
        sudo.webhook_state = "ok"
        return "ok"

    def action_register_webhooks(self):
        self.ensure_one()
        self._check_admin()
        state = self._register_webhooks()
        if state == "ok":
            return self._say(_("Webhook registered: messages arrive at once."), "success")
        if state == "none":
            return self._say(_("No app on this site needs Meta's webhook."), "info")
        return self._say(_("Meta only calls public https addresses: open Odoo on its https address (System "
                           "parameter web.base.url), then try again. Until then, messages arrive every 10 minutes."),
                         "danger")

    def action_reconnect(self):
        """A new Facebook login (password changed, permission removed...): the Pages' tokens are renewed."""
        self.ensure_one()
        self._check_admin()
        return self._say(_("Log in with Facebook again: the Pages keep everything they had."), "info", "login")

    def action_change_pages(self):
        self.ensure_one()
        self._check_admin()
        return self._say("", "info", "pages")

    # ------------------------------------------------------------------ keeping the link
    @api.model
    def _cron_health(self):
        """Every day: are the login and the Pages' tokens still good? Each Page's state says so; the apps hear it."""
        for app in self.sudo().search([("user_token", "!=", False)]):
            used = app.page_ids.filtered(lambda p: p.use_page or p.use_instagram)
            try:
                info = graph.debug_token(app.app_id, app.app_secret, app.user_token)
            except graph.GraphError as error:
                _logger.warning("Meta: token check failed: %s", error)
                continue
            if not info.get("is_valid"):
                reason = (info.get("error") or {}).get("message") or _("Facebook ended the login.")
                used.write({"state": "disconnected", "state_reason": reason})
            else:
                app._store_grants(info)
                used._check()
            self.env["meta.connector"]._meta_pages_changed(app.page_ids)


class MetaConnectorPage(models.Model):
    _name = "meta.connector.page"
    _description = "Facebook Page (and its Instagram account)"
    _order = "name, id"

    app_id = fields.Many2one("meta.connector.app", required=True, ondelete="cascade", index=True)
    page_id = fields.Char(string="Facebook Page ID", required=True, index=True)
    name = fields.Char(string="Facebook Page")
    page_token = fields.Char(groups="base.group_system", copy=False)
    picture_url = fields.Char()
    can_message = fields.Boolean(default=True)
    ig_id = fields.Char(string="Instagram Account ID", index=True)
    ig_username = fields.Char(string="Instagram Account")
    ig_picture_url = fields.Char()
    ig_name = fields.Char(string="Instagram Name", readonly=True)
    ig_followers = fields.Integer(string="Instagram Followers", readonly=True)
    ig_posts = fields.Integer(string="Instagram Posts", readonly=True)
    ig_avatar_id = fields.Many2one("ir.attachment", string="Instagram Photo", readonly=True, ondelete="set null",
                                   help="The account's profile photo, kept here (WebP) for the feed's header.")
    use_page = fields.Boolean(string="Use the Page", help="This site uses the Facebook Page (e.g. Messenger).")
    use_instagram = fields.Boolean(string="Use Instagram",
                                   help="This site uses the Page's Instagram account (messages, the feed).")
    state = fields.Selection(PAGE_STATES, default="new", required=True, readonly=True)
    state_reason = fields.Char(readonly=True)

    _page_unique = models.Constraint("UNIQUE(app_id, page_id)", "This Page is already in the connection.")

    @api.depends("name", "ig_username", "use_page", "use_instagram")
    def _compute_display_name(self):
        for page in self:
            parts = [page.name or page.page_id]
            if page.ig_username:
                parts.append("@%s" % page.ig_username)
            page.display_name = " · ".join(parts)

    def _token(self):
        """The Page's token (Messenger and its Instagram account both use it)."""
        return self.sudo().page_token

    def _check(self):
        """Is each Page's token still good? Sets ``state`` (and the reason)."""
        for page in self.sudo():
            try:
                graph.page_info(page.page_id, page.page_token)
            except graph.GraphError as error:
                if error.auth:
                    page.write({"state": "disconnected", "state_reason": str(error)})
                continue
            page.write({"state": "connected", "state_reason": False})
        return True
