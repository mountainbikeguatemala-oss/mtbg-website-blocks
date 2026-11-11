"""Set up Google: the one place Google credentials are entered, step by step, in Google Cloud's own order (owner,
2026-10-27: "clearer and have links to each step in the cloud platform with clear steps in order").

① the Google Cloud project (its ID makes every link below open in it), ② the apps to use, ③ the APIs those apps
need (one link each), ④ the consent screen: branding, the exact access to add (Data access), In production
(Audience), ⑤ the OAuth client: the redirect address of every site address, its ID and secret (checked with
Google), ⑥ the Maps key and billing (when Maps is on), ⑦ sign in the Google account(s), ⑧ Check access: each app
ready, or which access is missing."""
from markupsafe import Markup, escape
from urllib.parse import quote, urlparse

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.catalog import APIS
from ..models.connector import OAUTH_PATH

STEPS = [("project", "1. Project"), ("apps", "2. Apps"), ("apis", "3. APIs"), ("consent", "4. Consent screen"),
         ("client", "5. OAuth client"), ("maps", "6. API keys"), ("accounts", "7. Sign in"),
         ("check", "8. Check access"), ("first", "9. First sync")]
CONSOLE = "https://console.cloud.google.com/"
# what a scope lets the apps do, in plain words (others: their own name)
SCOPE_WORDS = {
    "https://www.googleapis.com/auth/gmail.readonly": "Read Gmail",
    "https://www.googleapis.com/auth/gmail.send": "Send email from Gmail",
    "https://www.googleapis.com/auth/gmail.modify": "Change Gmail (labels, read marks)",
    "https://www.googleapis.com/auth/calendar": "Google Calendar (read and change)",
    "https://www.googleapis.com/auth/calendar.readonly": "Read Google Calendar",
    "https://www.googleapis.com/auth/calendar.events": "Google Calendar events (read and change)",
    "https://www.googleapis.com/auth/calendar.events.readonly": "Read Google Calendar events",
    "https://www.googleapis.com/auth/contacts.readonly": "Read Google Contacts",
    "https://www.googleapis.com/auth/contacts.other.readonly": "Read Google's other contacts (people emailed)",
    "https://www.googleapis.com/auth/business.manage": "Google Business Profile (the reviews; Google offers no "
                                                       "read-only access, the reviews app only reads)",
    "openid": "Sign in",
    "https://www.googleapis.com/auth/userinfo.email": "Your Google address",
}


def console(path, project):
    """A Google Cloud console page, opened in ``project`` when it is known."""
    url = CONSOLE + path
    return url + ("&" if "?" in url else "?") + "project=" + quote(project) if project else url


def link(url, label):
    return Markup('<a href="%s" target="_blank" rel="noopener">%s <i class="fa fa-external-link small"/></a>') % (
        url, label)


class GoogleConnectorSetup(models.TransientModel):
    _name = "google.connector.setup"
    _description = "Set up Google"

    step = fields.Selection(STEPS, default="project", required=True)
    project_id = fields.Char(string="Google Cloud Project ID",
                             help="The project's ID (not its name), e.g. elite-wonder-512610-m8: Google Cloud's "
                                  "project picker shows it. Every link of this setup then opens in that project.")
    client_id = fields.Char(string="OAuth Client ID")
    client_secret = fields.Char(string="OAuth Client Secret", help="Left empty: the one saved stays.")
    has_secret = fields.Boolean(compute="_compute_saved")
    redirect_uri = fields.Char(compute="_compute_saved", string="Authorized Redirect URI")
    redirect_uris = fields.Text(compute="_compute_saved", string="Authorized Redirect URIs")
    app_ids = fields.Many2many("google.connector.app", string="Apps")
    scopes_text = fields.Text(compute="_compute_scopes", string="Access Google will ask for")
    scope_strings = fields.Text(compute="_compute_scopes", string="Scopes to add")
    account_ids = fields.Many2many("google.connector.account", string="Google Accounts",
                                   compute="_compute_accounts")
    maps_key = fields.Char(string="Maps API Key", help="Left empty: the one saved stays.")
    has_maps_key = fields.Boolean(compute="_compute_saved")
    server_key = fields.Char(string="Server API Key", help="Left empty: the one saved stays.")
    has_server_key = fields.Boolean(compute="_compute_saved")
    server_key_on = fields.Boolean(compute="_compute_scopes")
    maps_on = fields.Boolean(compute="_compute_scopes")
    project_html = fields.Html(compute="_compute_links", sanitize=False)
    apis_html = fields.Html(compute="_compute_links", sanitize=False)
    consent_html = fields.Html(compute="_compute_links", sanitize=False)
    client_html = fields.Html(compute="_compute_links", sanitize=False)
    maps_html = fields.Html(compute="_compute_links", sanitize=False)
    check_html = fields.Html(compute="_compute_check", sanitize=False)
    first_app_ids = fields.Many2many("google.connector.app", compute="_compute_first_apps",
                                     string="Apps to read once")

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        self.env["google.connector"]._check_admin()
        apps = self.env["google.connector"]._google_sync_apps()
        get = self.env["ir.config_parameter"].sudo().get_param
        values.setdefault("app_ids", [(6, 0, apps.ids)])
        values.setdefault("client_id", get("google_connector.client_id") or False)
        values.setdefault("project_id", get("google_connector.project_id") or False)
        return values

    def _compute_display_name(self):
        for wizard in self:
            wizard.display_name = self.env._("Set up Google")

    @api.model
    def _site_addresses(self):
        """Every address this site answers on: its base URL and each website's domain (e.g. new. now, www. at
        go-live): Google needs the redirect address of each one people sign in from."""
        bases = [self.env["ir.config_parameter"].sudo().get_param("web.base.url", "")]
        if "website" in self.env:
            bases += self.env["website"].sudo().search([]).mapped("domain")
        seen = []
        for base in bases:
            base = (base or "").strip().rstrip("/")
            if not base:
                continue
            if "://" not in base:
                base = "https://" + base
            parsed = urlparse(base)
            base = "%s://%s" % (parsed.scheme, parsed.netloc)
            if base not in seen:
                seen.append(base)
        return seen

    def _compute_saved(self):
        get = self.env["ir.config_parameter"].sudo().get_param
        addresses = self._site_addresses()
        for wizard in self:
            wizard.has_secret = bool(get("google_connector.client_secret"))
            wizard.has_maps_key = bool(get("google_connector.maps_key"))
            wizard.has_server_key = bool(get("google_connector.server_key"))
            wizard.redirect_uri = self.env["google.connector"].redirect_uri()
            wizard.redirect_uris = "\n".join(base + OAUTH_PATH for base in addresses)

    @api.depends("app_ids.on", "app_ids.writes_allowed")
    def _compute_scopes(self):
        for wizard in self:
            scopes = self.env["google.connector"]._google_scopes_wanted()
            words = [self.env._(SCOPE_WORDS[s]) if s in SCOPE_WORDS else s.rsplit("/", 1)[-1] for s in scopes]
            wizard.scopes_text = "\n".join("• %s" % word for word in words)
            wizard.scope_strings = ", ".join(scopes)  # Google's "Manually add scopes" takes them comma-separated
            wizard.maps_on = any(app.on and app.uses_maps_key for app in wizard.app_ids)
            wizard.server_key_on = any(app.on and app.uses_server_key for app in wizard.app_ids)

    @api.depends("project_id", "app_ids.on", "redirect_uris")
    def _compute_links(self):
        def steps(*items):
            return Markup("<ol>%s</ol>") % Markup("").join(Markup("<li>%s</li>") % item for item in items)

        for wizard in self:
            project = (wizard.project_id or "").strip()
            wizard.project_html = steps(
                Markup(_("Open %(pick)s and choose the project all the Google apps will use, or %(create)s one. One "
                         "project for everything: Gmail, Contacts, Calendar, Maps.")) % {
                    "pick": link(console("projectselector2/home/dashboard", ""), _("Google Cloud's project picker")),
                    "create": link(console("projectcreate", ""), _("create"))},
                _("A Google account can only make a few projects (Google's limit): reuse the existing one rather "
                  "than making a new one each time."),
                _("Maps needs billing switched on in the project (a card on file; Google's free monthly credit "
                  "usually covers a tour operator). Without Maps, no billing is needed."),
                _("Copy the project's ID (the picker's ID column, e.g. elite-wonder-512610-m8) into the field below: "
                  "every link of the next steps then opens in that project."))
            rows = []
            for app in wizard.app_ids.filtered("on"):
                for api_id, label in APIS.get(app.code, []):
                    rows.append(Markup("<li>%s <span class='text-muted'>(%s)</span></li>") % (
                        link(console("apis/library/%s" % api_id, project), label), app.label))
            wizard.apis_html = (Markup("<p>%s</p><ol>%s</ol>") % (
                _("Open each API below and press Enable (an API already on shows Manage: nothing to do). An app "
                  "whose API is off gets an error from Google."), Markup("").join(rows))) if rows else \
                Markup("<p class='text-muted'>%s</p>") % _("No app is switched on yet (step 2).")
            wizard.consent_html = steps(
                Markup(_("%(branding)s: the app name your team sees when signing in (e.g. Odoo), a support email, "
                         "and this site's domain under Authorized domains.")) % {
                    "branding": link(console("auth/branding", project), _("Branding"))},
                Markup(_("%(scopes)s: Add or remove scopes › Manually add scopes: paste the WHOLE box below "
                         "(every scope, comma-separated), Add to table, Update, Save. A scope missing here makes "
                         "Google refuse the sign-in.")) % {
                    "scopes": link(console("auth/scopes", project), _("Data access"))},
                Markup(_("%(audience)s: User type External, then Publish app so the status reads In production. "
                         "Stay in production: in Testing, Google ends the sign-in every 7 days. Google then shows "
                         "\"Google hasn't verified this app\" once at sign-in: Advanced › Go to the app; that is "
                         "expected for your own app.")) % {
                    "audience": link(console("auth/audience", project), _("Audience"))})
            wizard.client_html = steps(
                Markup(_("%(client)s: Application type Web application, any name (e.g. Odoo).")) % {
                    "client": link(console("auth/clients/create", project), _("Create an OAuth client"))},
                Markup("%s<ul>%s</ul>") % (
                    _("Under Authorized redirect URIs, press Add URI for EACH address below (one per address this "
                      "site is opened on: the current one, and e.g. www. when it goes live), then Create. A sign-in "
                      "from an address missing here fails with redirect_uri_mismatch."),
                    Markup("").join(Markup("<li><code>%s</code></li>") % uri
                                    for uri in (wizard.redirect_uris or "").split("\n") if uri)),
                Markup(_("Copy its Client ID and Client secret here (an existing client: %(clients)s, open it). "
                         "Odoo checks them with Google.")) % {
                    "clients": link(console("auth/clients", project), _("Clients"))},
                _("Only this path is used (/google_connector/oauth): an older one in the client, e.g. "
                  "/cfd/gvoice/oauth, is not used any more and can stay or go."))
            wizard.maps_html = steps(
                Markup(_("%(billing)s: link a billing account to the project (Maps does not work without it).")) % {
                    "billing": link(console("billing/linkedaccount", project), _("Billing"))},
                Markup(_("%(credentials)s: Create credentials › API key. Restrict it: API restrictions to the Maps "
                         "APIs of step 3; Application restrictions to Websites, this site's domain(s) only. Browsers "
                         "see the key (address search): the restriction is what protects it.")) % {
                    "credentials": link(console("apis/credentials", project), _("Credentials"))},
                _("Paste the key below."))

    def _compute_first_apps(self):
        for wizard in self:
            wizard.first_app_ids = self.env["google.connector.app"].sudo().search([("on", "=", True)]).filtered(
                "first_sync_note")

    def _compute_accounts(self):
        for wizard in self:
            wizard.account_ids = self.env["google.connector.account"].sudo().search([])

    def _compute_check(self):
        Account = self.env["google.connector.account"].sudo()
        for wizard in self:
            rows = []
            for card in self.env["google.connector.app"].google_card_data():
                if not card["installed"]:
                    continue
                ok = card["status"] in ("ready", "off")
                missing = ""
                if card["status"] == "missing":
                    app = self.env["google.connector.app"].sudo().browse(card["id"])
                    lacking = app._google_account()._google_has_scopes(app._google_scopes()) if app._google_account() \
                        else []
                    missing = ", ".join(self.env._(SCOPE_WORDS[s]) if s in SCOPE_WORDS else s for s in lacking)
                rows.append(Markup("<tr><td>%s</td><td class='%s'>%s</td><td>%s</td><td>%s</td></tr>") % (
                    card["label"], "text-success" if card["status"] == "ready" else ("text-muted" if ok else "text-danger"),
                    card["status_label"], card["account"] or "", missing))
            wizard.check_html = Markup(
                "<table class='table table-sm'><thead><tr><th>%s</th><th>%s</th><th>%s</th><th>%s</th></tr></thead>"
                "<tbody>%s</tbody></table>") % (_("App"), _("Status"), _("Google account"), _("Missing access"),
                                                Markup("").join(rows))

    # steps
    def _open(self, step):
        self.step = step
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
                "views": [(False, "form")], "target": "current", "name": _("Set up Google")}

    def _save_step(self):
        Connector = self.env["google.connector"]
        if self.step == "project":
            self.env["ir.config_parameter"].sudo().set_param("google_connector.project_id",
                                                              (self.project_id or "").strip() or False)
        elif self.step == "client":
            if not self.client_id:
                raise UserError(_("Paste the OAuth client ID first."))
            secret = self.client_secret or self.env["ir.config_parameter"].sudo().get_param(
                "google_connector.client_secret")
            if not secret:
                raise UserError(_("Paste the OAuth client secret."))
            problem = Connector._google_check_client(self.client_id.strip(), secret.strip())
            if problem:
                raise UserError(_("Google does not accept this client: %s", problem))
            Connector._google_set_credentials(client_id=self.client_id, client_secret=self.client_secret or None)
            self.client_secret = False
        elif self.step == "maps" and (self.maps_key or self.server_key):
            Connector._google_set_credentials(maps_key=self.maps_key or None, server_key=self.server_key or None)
            self.maps_key = self.server_key = False

    def _maps_needed(self):
        """An app with an API key is on (Maps, PageSpeed): the API keys step is shown."""
        return bool(self.env["google.connector.app"].sudo().search_count(
            [("on", "=", True), "|", ("uses_maps_key", "=", True), ("uses_server_key", "=", True)]))

    def _steps(self):
        order = [code for code, _label in STEPS]
        if not self._maps_needed():
            order.remove("maps")
        if not self.env["google.connector.app"].sudo().search([("on", "=", True)]).filtered("first_sync_note"):
            order.remove("first")
        return order

    def action_next(self):
        self._save_step()
        order = self._steps()
        following = order[order.index(self.step) + 1:] if self.step in order else []
        return self._open(following[0] if following else order[-1])

    def action_back(self):
        order = self._steps()
        previous = order[:order.index(self.step)] if self.step in order else []
        return self._open(previous[-1] if previous else "project")

    def action_connect(self):
        """Sign in a Google account (Google comes back to the Sign in step)."""
        return {"type": "ir.actions.act_url", "target": "self", "url": self.env["google.connector"].consent_url()}

    def action_finish(self):
        return {"type": "ir.actions.act_url", "target": "self", "url": "/odoo/settings#google_connector"}
