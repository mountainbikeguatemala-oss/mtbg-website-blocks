import io
import zipfile
from datetime import timedelta
from unittest.mock import MagicMock

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
        wizard.write({"lan_address": "192.168.1.50", "immich_port": 2283, "upload_port": 8090, "wifi_name": "Office"})
        wizard.action_next()
        self.assertEqual(self.C._upload_url(), "http://192.168.1.50:8090")
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
        wizard.action_next()
        self.assertEqual(wizard.step, "check")
        self.assertFalse(wizard.last_seen and wizard.last_seen > fields.Datetime.now() + timedelta(minutes=1))
        wizard.action_finish()
        self.assertFalse(wizard.token, "the token leaves the wizard")

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
