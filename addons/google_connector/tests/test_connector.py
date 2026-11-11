import base64
import json
from unittest.mock import patch

from odoo.tests import HttpCase, TransactionCase, tagged

from odoo.addons.google_connector.models import client as client_module
from odoo.addons.google_connector.models.catalog import APIS
from odoo.addons.google_connector.models.client import GoogleClient, GoogleError
from odoo.addons.google_connector.models.connector import GoogleConnector

READ = "https://www.googleapis.com/auth/calendar.readonly"
WRITE = "https://www.googleapis.com/auth/calendar.events"
SPECS = {"testcal": {"label": "Test Calendar", "module": False, "read_scopes": [READ], "write_scopes": [WRITE]},
         "maps": {"label": "Test Maps", "module": False, "needs_account": False, "uses_maps_key": True}}


class Response:
    def __init__(self, status=200, payload=None, headers=None, content=None):
        self.status_code = status
        self._payload = payload
        self.headers = headers or {}
        self.content = content if content is not None else (json.dumps(payload).encode() if payload is not None else b"")
        self.text = self.content.decode(errors="replace")

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def id_token(email):
    claims = base64.urlsafe_b64encode(json.dumps({"email": email}).encode()).decode().rstrip("=")
    return "h.%s.s" % claims


@tagged("post_install", "-at_install")
class TestGoogleConnector(TransactionCase):

    def setUp(self):
        super().setUp()
        patcher = patch.object(GoogleConnector, "_google_app_specs", lambda self: dict(SPECS))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.G = self.env["google.connector"]
        self.G._google_set_credentials(client_id="cid", client_secret="secret", maps_key="mkey")
        self.G._google_sync_apps()
        self.cal = self.G._google_app("testcal")
        self.account = self.env["google.connector.account"].create({
            "name": "ops@example.com", "email": "ops@example.com", "state": "connected", "refresh_token": "r",
            "access_token": "a", "token_expiry": 9999999999, "granted_scopes": "openid %s" % READ})

    def test_apps_switches_and_client_guards(self):
        self.assertFalse(self.G.app_on("testcal"))
        with self.assertRaises(GoogleError):
            self.G.client("testcal")
        self.cal.on = True
        self.assertIsInstance(self.G.client("testcal"), GoogleClient)
        with self.assertRaises(GoogleError, msg="writes not allowed"):
            self.G.client("testcal", write=True)
        self.cal.writes_allowed = True
        with self.assertRaises(GoogleError) as missing:
            self.G.client("testcal", write=True)
        self.assertEqual(missing.exception.missing_scopes, (WRITE,), "the account has not granted the write scope")
        self.assertEqual(self.G.missing_scopes("testcal"), [WRITE])
        self.assertEqual(self.cal.status, "missing")
        self.account.granted_scopes = "openid %s %s" % (READ, WRITE)
        self.assertIsInstance(self.G.client("testcal", write=True), GoogleClient)
        self.cal.invalidate_recordset(["status"])
        self.assertEqual(self.cal.status, "ready")

    def test_an_app_no_module_declares_any_more_goes(self):
        self.env["google.connector.app"].create({"code": "retired", "label": "Retired"})
        self.G._google_sync_apps()
        self.assertFalse(self.env["google.connector.app"].search([("code", "=", "retired")]))
        self.assertTrue(self.cal.exists(), "a declared app stays, with its switches")

    def test_maps_key_only_when_maps_is_on(self):
        self.assertEqual(self.G.maps_key(), "")
        self.G._google_app("maps").on = True
        self.assertEqual(self.G.maps_key(), "mkey")

    def test_maps_client_uses_the_key_alone(self):
        """Maps needs no Google account: the key as a parameter, no token, the same limits; never the key in an error."""
        self.account.unlink()
        with self.assertRaises(GoogleError):
            self.G.client("maps")
        self.G._google_app("maps").on = True
        seen = []

        def fake_request(method, url, **kwargs):
            seen.append(kwargs)
            return Response(200, content=b"PNG") if len(seen) == 1 else Response(403, {"error": {"message": "bad key=mkey"}})
        with patch.object(client_module.requests, "request", side_effect=fake_request):
            client = self.G.client("maps")
            self.assertEqual(client.get("https://maps.googleapis.com/maps/api/staticmap", params={"size": "1x1"},
                                        raw=True), b"PNG")
            with self.assertRaises(GoogleError) as refused:
                client.get("https://maps.googleapis.com/maps/api/staticmap")
        self.assertEqual(seen[0]["params"], {"size": "1x1", "key": "mkey"})
        self.assertNotIn("Authorization", seen[0]["headers"])
        self.assertNotIn("mkey", str(refused.exception))
        self.G._google_set_credentials(maps_key="")
        with self.assertRaises(GoogleError, msg="no key"):
            self.G.client("maps")

    def test_client_retries_refreshes_and_limits(self):
        self.cal.on = True
        self.account.write({"access_token": False, "token_expiry": 0})
        calls, sleeps = [], []
        answers = [Response(429, {"error": {"message": "slow down"}}, {"Retry-After": "2"}),
                   Response(401, {"error": "expired"}), Response(200, {"items": [1]})]

        def fake_request(method, url, **kwargs):
            calls.append((method, url, kwargs["headers"]["Authorization"]))
            return answers.pop(0)
        with patch.object(client_module.requests, "post", return_value=Response(200, {"access_token": "new", "expires_in": 3600})), \
                patch.object(client_module.requests, "request", side_effect=fake_request):
            client = self.G.client("testcal")
            client.sleep = sleeps.append
            self.assertEqual(client.get("https://g.example/x"), {"items": [1]})
        self.assertEqual(calls[0][2], "Bearer new", "a refreshed token")
        self.assertIn(2.0, sleeps, "Retry-After honoured")
        with patch.object(client_module.requests, "request", return_value=Response(403, {"error": {"message": "no"}})):
            with self.assertRaises(GoogleError) as refused:
                self.G.client("testcal").get("https://g.example/x")
        self.assertEqual(refused.exception.status, 403)
        self.cal._google_count_call(10 ** 6)
        self.cal.calls_today = 7
        self.assertFalse(self.cal._google_count_call(7), "the day's limit")

    def test_consent_and_sign_in(self):
        self.cal.on = True
        url = self.G.consent_url(self.account)
        self.assertIn("calendar.readonly", url)
        self.assertIn("include_granted_scopes=true", url)
        state = url.split("state=")[1].split("&")[0]
        self.assertEqual(self.G._account_from_state(state), self.account)
        self.assertFalse(self.G._account_from_state(state[:-1] + ("1" if state[-1] == "0" else "0")))
        fresh = self.env["google.connector.account"].create({})
        with patch.object(client_module.requests, "post", return_value=Response(200, {
                "access_token": "t", "refresh_token": "rt", "expires_in": 3600, "scope": "openid %s" % READ,
                "id_token": id_token("ops@example.com")})):
            kept = self.G._oauth_done(fresh, "code")
        self.assertEqual(kept, self.account, "the same Google address: one account")
        self.assertFalse(fresh.exists())
        self.assertEqual(self.account.refresh_token, "rt")

    def test_sync_log(self):
        with self.G.sync_log("testcal", "push") as log:
            log.add(created=2, note="two events")
        self.assertEqual((log.state, log.created), ("done", 2))
        try:  # (assertRaises would roll the failed log back)
            with self.G.sync_log("testcal", "push") as failing:
                raise ValueError("boom")
        except ValueError:
            pass
        self.assertEqual(failing.state, "failed")
        self.assertIn("boom", failing.note)

    def test_neutralize_clears_the_login(self):
        self.cal.write({"on": True, "writes_allowed": True})
        sql = open(__file__.replace("tests/test_connector.py", "data/neutralize.sql")).read()
        self.env.flush_all()
        self.env.cr.execute(sql)
        self.env.invalidate_all()
        self.assertFalse(self.account.refresh_token)
        self.assertFalse(self.cal.on)
        self.assertFalse(self.env["ir.config_parameter"].sudo().get_param("google_connector.client_secret"))

    def test_setup_wizard_steps(self):
        """Google Cloud's order, every link in the project; the client checked with Google; Maps' step only when on."""
        wizard = self.env["google.connector.setup"].create({"project_id": "elite-wonder-512610-m8"})
        self.assertEqual(wizard.step, "project")
        action = wizard.action_next()
        self.assertEqual(action["res_id"], wizard.id)
        self.assertEqual(self.env["ir.config_parameter"].sudo().get_param("google_connector.project_id"),
                         "elite-wonder-512610-m8")
        self.assertEqual(wizard.step, "apps")
        self.cal.on = True
        wizard.action_next()
        self.assertEqual(wizard.step, "apis")
        with patch.dict(APIS, {"testcal": [("calendar-json.googleapis.com", "Google Calendar API")]}):
            wizard.invalidate_recordset(["apis_html"])
            self.assertIn("apis/library/calendar-json.googleapis.com?project=elite-wonder-512610-m8", wizard.apis_html)
        wizard.action_next()
        self.assertEqual(wizard.step, "consent")
        self.assertIn("auth/scopes?project=elite-wonder-512610-m8", wizard.consent_html)
        self.assertIn("auth/audience?project=elite-wonder-512610-m8", wizard.consent_html)
        for scope in self.G._google_scopes_wanted():
            self.assertIn(scope, wizard.scope_strings.split(", "), "every scope to paste in Data access")
        wizard.action_next()
        self.assertEqual(wizard.step, "client")
        self.assertIn(self.G.redirect_uri(), wizard.redirect_uris.split("\n"))
        self.assertIn("<code>%s</code>" % self.G.redirect_uri(), wizard.client_html)
        self.assertIn("auth/clients/create?project=elite-wonder-512610-m8", wizard.client_html)
        wizard.write({"client_id": "cid2", "client_secret": "s2"})
        with patch.object(GoogleConnector, "_google_check_client", lambda self, c, s: None):
            wizard.action_next()
        self.assertEqual(self.env["ir.config_parameter"].sudo().get_param("google_connector.client_id"), "cid2")
        self.assertEqual(wizard.step, "accounts", "Maps off: its billing and key step is skipped")
        wizard.action_next()
        self.assertEqual(wizard.step, "check")
        self.G._google_app("maps").on = True
        wizard.action_back()
        self.assertEqual(wizard.step, "accounts")
        wizard.action_back()
        self.assertEqual(wizard.step, "maps")
        self.assertIn("billing/linkedaccount?project=elite-wonder-512610-m8", wizard.maps_html)
        # an app that shows nothing before its first read from Google: a last step says so and opens it
        wizard.action_next()
        wizard.action_next()
        self.assertEqual(wizard.step, "check", "no such app on: Check access is the last step")
        contacts = self.env["google.connector.app"].sudo().create({"code": "contacts", "label": "Google Contacts"}) \
            if not self.G._google_app("contacts") else self.G._google_app("contacts")
        contacts.on = True
        wizard.action_next()
        self.assertEqual(wizard.step, "first")
        self.assertIn(contacts, wizard.first_app_ids)
        self.assertIn("Check", contacts.first_sync_note)
        with patch.object(GoogleConnector, "_google_check_client", lambda self, c, s: "invalid_client"):
            bad = self.env["google.connector.setup"].create({"step": "client", "client_id": "x", "client_secret": "y"})
            with self.assertRaises(Exception):
                bad.action_next()


@tagged("post_install", "-at_install")
class TestGoogleConnectorUi(HttpCase):

    def test_oauth_return_needs_a_signed_state(self):
        self.authenticate("admin", "admin")
        self.assertEqual(self.url_open("/google_connector/oauth?state=1-forged&code=x").status_code, 404)

    def test_settings_show_the_google_section(self):
        self.browser_js("/odoo", """
            const wait = (ms) => new Promise((r) => setTimeout(r, ms));
            (async () => {
                await odoo.__WOWL_DEBUG__.root.env.services.action.doAction("base_setup.action_general_configuration",
                                                                             {additionalContext: {module: "google_connector"}});
                let tab;
                for (let i = 0; i < 100 && !tab; i++) { tab = document.querySelector('.settings_tab [data-key="google_connector"]'); await wait(100); }
                tab && tab.click();
                for (let i = 0; i < 100 && !document.querySelector('.o_google_cards'); i++) { await wait(100); }
                if (!document.querySelector('.o_google_cards')) {
                    console.error('no Google cards: ' + document.title + ' / ' + [...document.querySelectorAll('.settings_tab .tab, .settings_tab [data-key]')].map((t) => t.dataset.key || t.textContent).join(',')); return;
                }
                if (![...document.querySelectorAll('button')].some((b) => b.textContent.includes('Set up Google'))) {
                    console.error('no Set up Google button'); return;
                }
                console.log('test successful');
            })();
        """, ready="odoo.isReady", login="admin", timeout=120)

    def test_setup_wizard_shows_its_buttons(self):
        """The wizard opens as a page (from Settings, and where Google's sign-in comes back): Next and Back show."""
        self.browser_js("/odoo/action-google_connector.action_google_setup_accounts", """
            const wait = (ms) => new Promise((r) => setTimeout(r, ms));
            const visible = (label) => [...document.querySelectorAll('.o_form_view button')]
                .some((b) => b.textContent.trim() === label && b.offsetParent !== null);
            (async () => {
                for (let i = 0; i < 100 && !visible('Next'); i++) { await wait(100); }
                if (!visible('Next') || !visible('Back')) {
                    console.error('no Next / Back on the sign-in return: ' + document.body.innerText.slice(0, 300)); return;
                }
                await odoo.__WOWL_DEBUG__.root.env.services.action.doAction("google_connector.action_google_setup");
                for (let i = 0; i < 100 && visible('Back'); i++) { await wait(100); }
                for (let i = 0; i < 100 && !visible('Next'); i++) { await wait(100); }
                if (!visible('Next')) { console.error('no Next on the first step'); return; }
                console.log('test successful');
            })();
        """, ready="odoo.isReady", login="admin", timeout=120)
