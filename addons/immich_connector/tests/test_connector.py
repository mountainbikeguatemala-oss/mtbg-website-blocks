import io
import os
import socket
import subprocess
import sys
import zipfile
from datetime import timedelta
from unittest.mock import MagicMock, patch

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.immich_connector.models.client import ImmichClient, ImmichError


@tagged("post_install", "-at_install")
class TestImmichConnector(TransactionCase):

    def setUp(self):
        super().setUp()
        self.C = self.env["immich.connector"]
        self.ICP = self.env["ir.config_parameter"].sudo()

    def test_token(self):
        token = self.C._new_token()
        self.assertGreaterEqual(len(token), 43)
        stored = self.ICP.get_param("immich_connector.nas_token_hash")
        self.assertNotIn(token, stored, "only its hash is kept")
        self.assertTrue(self.C._check_bearer("Bearer " + token))
        self.assertFalse(self.C._check_bearer("Bearer " + token + "x"))
        self.assertFalse(self.C._check_bearer(token), "the Bearer scheme is needed")
        self.assertFalse(self.C._check_bearer(""))
        newer = self.C._new_token()
        self.assertFalse(self.C._check_bearer("Bearer " + token), "a new token stops the old one at once")
        self.assertTrue(self.C._check_bearer("Bearer " + newer))
        user = self.env["res.users"].create({"name": "Not Admin", "login": "not.admin.immich",
                                             "group_ids": [(6, 0, [self.env.ref("base.group_user").id])]})
        with self.assertRaises(AccessError):
            self.C.with_user(user)._new_token()

    def test_last_seen(self):
        self.ICP.search([("key", "=", "immich_connector.last_seen")]).unlink()
        self.assertFalse(self.C._last_seen())
        token = self.C._new_token()
        self.C._check_bearer("Bearer " + token)
        seen = self.C._last_seen()
        self.assertTrue(seen)
        self.assertLess(abs((fields.Datetime.now() - seen).total_seconds()), 5)
        self.C._check_bearer("Bearer wrong")
        self.assertEqual(self.C._last_seen(), seen, "a wrong token is not a call-in")

    def test_settings(self):
        settings = self.env["res.config.settings"].create({
            "immich_upload_url": "http://192.168.1.50:8090/", "immich_wifi_name": "Office",
            "immich_url": "http://192.168.1.50:2283/"})
        settings.execute()
        self.assertEqual(self.C._upload_url(), "http://192.168.1.50:8090")
        self.assertEqual(self.C._wifi_name(), "Office")
        self.ICP.set_param("immich_connector.wifi_name", "Office 2G, Office 5G ,")
        self.assertEqual(self.C._wifi_names(), ["Office 2G", "Office 5G"], "several networks, separated by commas")
        self.assertEqual(self.C._album_url("abc"), "http://192.168.1.50:2283/albums/abc")
        self.assertFalse(self.C._public_mode(), "no API key: not public")
        with self.assertRaises(UserError):
            self.C._client()
        self.ICP.set_param("immich_connector.public_mode", True)
        self.ICP.set_param("immich_connector.api_key", "k")
        self.assertTrue(self.C._public_mode())

    def test_client(self):
        session = MagicMock()
        session.request.return_value = MagicMock(status_code=201, content=b"{}",
                                                 json=lambda: {"id": "a1", "albumName": "2026-11-14 · Ride"})
        client = ImmichClient("https://immich.example.com/", "key", session=session)
        self.assertEqual(client.album_create("2026-11-14 · Ride"), {"id": "a1", "name": "2026-11-14 · Ride"})
        method, url = session.request.call_args[0]
        self.assertEqual((method, url), ("POST", "https://immich.example.com/api/albums"))
        self.assertEqual(session.request.call_args[1]["headers"]["x-api-key"], "key")
        session.request.return_value = MagicMock(status_code=401, text="bad key", content=b"x")
        with self.assertRaises(ImmichError):
            client.album_rename("a1", "x")

    def test_wizard_zip(self):
        self.ICP.set_param("cloudflare_connector.account_id", "acc123")
        self.ICP.set_param("cloudflare_connector.r2_bucket", "tour-photos")
        self.ICP.set_param("cloudflare_connector.r2_secret_access_key", "SECRET-NEVER")
        wizard = self.env["immich.setup.wizard"].create({})
        wizard.action_next()
        self.assertEqual(wizard.step, "network")
        wizard.write({"lan_address": "192.168.1.50", "immich_port": 2283, "upload_port": 8090, "wifi_name": "Office",
                      "nas_domain": ""})
        wizard.action_next()
        self.assertEqual(wizard.step, "token", "no secure address: its step is skipped")
        self.assertEqual(self.C._upload_url(), "http://192.168.1.50:8090")
        self.assertFalse(self.C._office_base(), "plain http only: no secure office address")
        self.assertEqual(self.C._immich_url(), "http://192.168.1.50:2283")
        with self.assertRaises(UserError):
            wizard.action_next()  # the token first
        wizard.action_token()
        token = wizard.token
        self.assertTrue(self.C._check_bearer("Bearer " + token))
        wizard.action_next()
        archive = zipfile.ZipFile(io.BytesIO(wizard._bundle()))
        names = archive.namelist()
        self.assertIn("photo-server/config.env", names)
        self.assertIn("photo-server/docker-compose.yml", names)
        self.assertIn("photo-server/README.md", names)
        self.assertTrue(any(n.startswith("photo-server/app/") for n in names))
        for name in names:
            self.assertNotIn("__pycache__", name)
            self.assertFalse(name.endswith(".pyc"))
            self.assertNotIn("/data/", name)
            self.assertNotIn("/work/", name)
        self.assertEqual(names.count("photo-server/config.env"), 1)
        env = archive.read("photo-server/config.env").decode()
        lines = dict(line.split("=", 1) for line in env.splitlines() if "=" in line and not line.startswith("#"))
        self.assertEqual(lines["NAS_TOKEN"], token)
        self.assertEqual(lines["IMMICH_URL"], "http://192.168.1.50:2283")
        self.assertEqual(lines["UPLOAD_PORT"], "8090")
        self.assertEqual(lines["R2_ACCOUNT_ID"], "acc123")
        self.assertEqual(lines["R2_BUCKET"], "tour-photos")
        for secret in ("IMMICH_API_KEY", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "WATERMARK_PATH"):
            self.assertEqual(lines[secret], "", "%s stays blank" % secret)
        self.assertNotIn("SECRET-NEVER", env)
        self.assertNotIn("photo-server/tls/.env", names, "no secure address: no https front settings")
        self.assertNotIn("photo-server/tls/tls.env", names)
        wizard.action_next()
        self.assertEqual(wizard.step, "check")
        self.assertFalse(wizard.last_seen and wizard.last_seen > fields.Datetime.now() + timedelta(minutes=1))
        wizard.action_finish()
        self.assertFalse(wizard.token, "the token leaves the wizard")
        self.assertEqual(self.C._upload_url(), "http://192.168.1.50:8090", "no secure address: http stays")

    def test_at_office(self):
        from unittest.mock import MagicMock
        token = self.C._new_token()
        request = MagicMock()
        request.httprequest.headers = {"Authorization": "Bearer " + token}
        request.httprequest.remote_addr = "203.0.113.7"
        self.assertTrue(self.C._check_bearer(request))
        self.assertTrue(self.C._at_office("203.0.113.7"), "the same address, the photo server just called")
        self.assertFalse(self.C._at_office("198.51.100.9"), "another address")
        self.assertFalse(self.C._at_office(""))
        request.httprequest.remote_addr = "203.0.113.99"  # the office's 4G router got a new address
        self.assertTrue(self.C._check_bearer(request))
        self.assertTrue(self.C._at_office("203.0.113.99"))
        self.C._set_fresh("immich_connector.last_seen",
                          fields.Datetime.to_string(fields.Datetime.now() - timedelta(minutes=16)))
        self.assertFalse(self.C._at_office("203.0.113.99"), "the photo server has not called for 16 minutes")


SETUP = "odoo.addons.immich_connector.models.setup"
APP = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "nas", "app")


@tagged("post_install", "-at_install")
class TestSecureAddress(TransactionCase):
    """The secure office address (owner, 2026-11-16): nas.<domain> -> the photo server, https with a real
    certificate (DNS-01, the Cloudflare token typed in the wizard), CORS for the website, /ping."""

    def setUp(self):
        super().setUp()
        self.C = self.env["immich.connector"]
        self.ICP = self.env["ir.config_parameter"].sudo()
        self.ICP.set_param("web.base.url", "https://www.example.com")
        self.ICP.set_param("mtbg_tours.short_link_domain", "https://ex.co/")
        self.ICP.set_param("immich_connector.upload_url", "")
        self.ICP.set_param("immich_connector.office_base", "")
        self.ICP.set_param("immich_connector.nas_hostname", "")

    def _wizard(self, **values):
        wizard = self.env["immich.setup.wizard"].create({})
        wizard.action_next()
        wizard.write(dict({"lan_address": "192.168.1.50", "immich_port": 2283, "upload_port": 8090,
                           "wifi_name": "Office"}, **values))
        wizard.action_next()
        return wizard

    def test_default_domain(self):
        wizard = self.env["immich.setup.wizard"].create({})
        self.assertEqual(wizard.nas_domain, "ex.co", "the short-link domain first")
        self.assertEqual(wizard.nas_hostname, "nas.ex.co")
        self.ICP.set_param("mtbg_tours.short_link_domain", "")
        self.ICP.set_param("mtbg_tours.invoice_short_domain", "")
        self.ICP.set_param("cloudflare_connector.zone_name", "")
        self.assertEqual(self.env["immich.setup.wizard"].create({}).nas_domain, "example.com", "else the website's")
        self.assertEqual(self.env["immich.setup.wizard"]._site_origins(),
                         ["https://www.example.com", "https://example.com"])

    def test_network_checks(self):
        wizard = self.env["immich.setup.wizard"].create({"step": "network", "lan_address": "nas.local",
                                                         "nas_domain": "ex.co"})
        with self.assertRaises(UserError):
            wizard.action_next()  # a DNS record needs an IP address
        wizard.write({"lan_address": "192.168.1.50", "nas_domain": "not a domain"})
        with self.assertRaises(UserError):
            wizard.action_next()

    def test_steps_record_and_zip(self):
        wizard = self._wizard(https_port=8443)
        self.assertEqual(wizard.step, "secure")
        self.assertEqual(wizard.nas_hostname, "nas.ex.co")
        self.assertEqual(wizard.ping_url, "https://nas.ex.co:8443/ping")
        self.assertEqual(self.C._upload_url(), "http://192.168.1.50:8090", "http until Finish")
        with self.assertRaises(UserError):
            wizard.action_next()  # the certificate's token first

        # (a) the DNS record, through the Cloudflare connector (mocked) when it is installed with a token
        if "cloudflare.api" in self.env:
            self.ICP.set_param("cloudflare_connector.api_token", "saved-token")
            wizard.invalidate_recordset(["can_create_dns"])
            self.assertTrue(wizard.can_create_dns)
            calls = []

            def call(_self, method, path, **kwargs):
                calls.append((method, path, kwargs))
                if path == "/zones":
                    return [{"id": "z1"}] if kwargs["params"]["name"] == "ex.co" else []
                if method == "GET":
                    return []
                return {"id": "r1"}
            with patch.object(type(self.env["cloudflare.api"]), "call", call):
                wizard.action_dns_create()
            self.assertIn("Record created", wizard.dns_result)
            method, path, kwargs = calls[-1]
            self.assertEqual((method, path), ("POST", "/zones/z1/dns_records"))
            self.assertEqual({k: kwargs["json"][k] for k in ("type", "name", "content", "proxied")},
                             {"type": "A", "name": "nas.ex.co", "content": "192.168.1.50", "proxied": False})

        # ... or with the token typed here (Cloudflare's API mocked): an existing record is corrected
        wizard.dns_token = "CF-SECRET-TOKEN"
        answers = iter([{"success": True, "result": [{"id": "z1"}]},
                        {"success": True, "result": [{"id": "r1", "content": "10.0.0.9", "proxied": True}]},
                        {"success": True, "result": {"id": "r1"}}])
        with patch(SETUP + ".requests.request", side_effect=lambda *a, **k: MagicMock(
                status_code=200, json=lambda: next(answers))) as request:
            wizard.action_dns_create()
        self.assertIn("corrected", wizard.dns_result)
        self.assertEqual(request.call_args[0][0], "PATCH")
        self.assertEqual(request.call_args[1]["json"]["content"], "192.168.1.50")
        self.assertEqual(request.call_args[1]["headers"]["Authorization"], "Bearer CF-SECRET-TOKEN")
        with patch(SETUP + ".requests.request", return_value=MagicMock(
                status_code=403, json=lambda: {"success": False, "errors": [{"message": "no access"}]})):
            wizard.action_dns_create()
        self.assertIn("by hand", wizard.dns_result, "a refusal: the record to add by hand")

        # (c) the name, resolved from here
        with patch(SETUP + ".socket.getaddrinfo", return_value=[(2, 1, 6, "", ("192.168.1.50", 0))]):
            wizard.action_resolve()
        self.assertTrue(wizard.resolve_result.startswith("✓"))
        with patch(SETUP + ".socket.getaddrinfo", return_value=[(2, 1, 6, "", ("203.0.113.5", 0))]):
            wizard.action_resolve()
        self.assertIn("not the photo server", wizard.resolve_result)
        with patch(SETUP + ".socket.getaddrinfo", side_effect=socket.gaierror):
            wizard.action_resolve()
        self.assertIn("not found yet", wizard.resolve_result)

        wizard.action_next()
        self.assertEqual(wizard.step, "token")
        wizard.action_token()
        wizard.action_next()
        self.assertEqual(wizard.step, "files")
        archive = zipfile.ZipFile(io.BytesIO(wizard._bundle()))
        names = archive.namelist()
        for name in ("tls/.env", "tls/tls.env", "tls/Caddyfile", "tls/docker-compose.yml", "tls/Dockerfile",
                     "tls/tls.env.example", "docker-compose.yml", "config.env"):
            self.assertIn("photo-server/" + name, names)
        tls = archive.read("photo-server/tls/.env").decode()
        self.assertIn("NAS_HOSTNAME=nas.ex.co\n", tls)
        self.assertIn("NAS_HTTPS_PORT=8443\n", tls)
        self.assertIn("SITE_ORIGINS=https://www.example.com https://example.com\n", tls)
        self.assertIn("CLOUDFLARE_API_TOKEN=CF-SECRET-TOKEN\n", archive.read("photo-server/tls/tls.env").decode())
        holders = [n for n in names if b"CF-SECRET-TOKEN" in archive.read(n)]
        self.assertEqual(holders, ["photo-server/tls/tls.env"], "the token is only in tls/tls.env")
        caddy = archive.read("photo-server/tls/Caddyfile").decode()
        for text in ("{$NAS_HOSTNAME}:{$NAS_HTTPS_PORT}", "dns cloudflare {env.CLOUDFLARE_API_TOKEN}",
                     "handle /ping", '{"ok":true}', "Access-Control-Allow-Private-Network true", "Vary Origin",
                     '"GET, POST, PUT, OPTIONS"', '"Content-Type, X-File-Name, X-Last-Modified, X-File-Type"',
                     "Access-Control-Max-Age 600", "respond 204", "reverse_proxy tour-photos-upload:8090"):
            self.assertIn(text, caddy)
        compose = archive.read("photo-server/tls/docker-compose.yml").decode()
        for text in ("tour-photos-tls:2.10.2-cf", "./Caddyfile:/etc/caddy/Caddyfile:ro",
                     "${NAS_HTTPS_PORT:-443}:${NAS_HTTPS_PORT:-443}", "env_file: tls.env", "immich_default"):
            self.assertIn(text, compose)
        self.assertIn("caddy:2.10.2-builder", archive.read("photo-server/tls/Dockerfile").decode())
        self.assertIn("aliases: [tour-photos-upload]", archive.read("photo-server/docker-compose.yml").decode())
        self.assertNotIn("CF-SECRET-TOKEN", str(self.ICP.search([]).mapped("value")), "never saved in Odoo")

        wizard.action_next()
        self.assertEqual(wizard.step, "check")
        for _i in range(3):
            wizard.action_back()
        self.assertEqual(wizard.step, "secure", "check › files › token › secure")
        wizard.write({"step": "check"})
        wizard.action_finish()
        self.assertFalse(wizard.token)
        self.assertFalse(wizard.dns_token, "the certificate's token leaves the wizard")
        self.assertEqual(self.C._upload_url(), "https://nas.ex.co:8443")
        self.assertEqual(self.C._office_base(), "https://nas.ex.co:8443")
        again = self.env["immich.setup.wizard"].create({})
        self.assertEqual((again.nas_domain, again.https_port, again.upload_port), ("ex.co", 8443, 8090))

    def test_office_base(self):
        self.assertFalse(self.C._office_base())
        self.ICP.set_param("immich_connector.upload_url", "http://192.168.1.50:8090")
        self.assertFalse(self.C._office_base(), "plain http: none")
        self.ICP.set_param("immich_connector.upload_url", "https://nas.ex.co/upload")
        self.assertEqual(self.C._office_base(), "https://nas.ex.co", "a trailing /upload is dropped")
        self.ICP.set_param("immich_connector.office_base", "https://nas.ex.co:8443/")
        self.assertEqual(self.C._office_base(), "https://nas.ex.co:8443")
        settings = self.env["res.config.settings"].create({})
        self.assertEqual(settings.immich_office_base, "https://nas.ex.co:8443/")

    def test_upload_ping(self):
        """The upload page answers GET /ping (and /health) with {"ok":true}."""
        code = (
            "import sys, threading, urllib.request\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "import upload\n"
            "srv = upload.ThreadingHTTPServer(('127.0.0.1', 0), upload.Handler)\n"
            "threading.Thread(target=srv.serve_forever, daemon=True).start()\n"
            "for p in ('/ping', '/health'):\n"
            "    r = urllib.request.urlopen('http://127.0.0.1:%d%s' % (srv.server_port, p), timeout=5)\n"
            "    print(r.status, r.read().decode())\n")
        env = dict(os.environ, SITE_URL="https://www.example.com", NAS_TOKEN="x", IMMICH_API_KEY="x",
                   STATE_FILE="/nonexistent/state.json", UPLOAD_TMP="/nonexistent")
        try:
            out = subprocess.run([sys.executable, "-c", code, APP], capture_output=True, text=True, timeout=60,
                                 env=env, cwd="/")
        except subprocess.TimeoutExpired:
            self.fail("the upload page did not answer")
        if "ModuleNotFoundError" in out.stderr:
            self.skipTest("the photo service's libraries are not installed here: %s" % out.stderr.splitlines()[-1])
        self.assertEqual(out.stdout.split("\n")[:2], ['200 {"ok":true}', '200 {"ok":true}'], out.stderr[-500:])
