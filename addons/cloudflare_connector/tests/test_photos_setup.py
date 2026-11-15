import hashlib
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.cloudflare_connector.models import photos_setup as PS
from odoo.addons.cloudflare_connector.models.r2 import R2Client

ACCOUNT = "acc123"


@tagged("post_install", "-at_install")
class TestPhotosSetup(TransactionCase):
    """Set up photos storage (1.6.0): a bucket of its own (no lock), its public address, lifecycle, CORS, the site's
    key kept and the photo server's shown once. Cloudflare is never called: every request is answered here."""

    def setUp(self):
        super().setUp()
        self.ICP = self.env["ir.config_parameter"].sudo()
        self.ICP.set_param("web.base.url", "https://www.example.com")
        self.ICP.set_param("mtbg_tours.short_link_domain", "ex.co")
        for key in ("bucket", "access_key_id", "secret_access_key", "token_id", "domain", "account_id"):
            self.ICP.set_param(PS.PHOTOS + key, False)
        self.calls = []
        self.tokens = iter([{"id": "site-key-id", "value": "site-secret"}, {"id": "nas-key-id", "value": "nas-secret"}])

        def fake(method, path, token, **kwargs):
            self.calls.append((method, path, kwargs.get("json")))
            if path == "/accounts":
                return True, [{"id": ACCOUNT, "name": "Example"}], "", 200
            if path == "/zones":
                return True, [{"id": "zone-co", "name": "ex.co"}, {"id": "zone-com", "name": "example.com"}], "", 200
            if path.endswith("/tokens/verify"):
                return True, {"id": "setup-id"}, "", 200
            if path.endswith("/permission_groups"):
                return True, [{"id": "pg-write", "name": "Workers R2 Storage Bucket Item Write"}], "", 200
            if method == "POST" and path.endswith("/tokens"):
                return True, next(self.tokens), "", 200
            return True, {}, "", 200

        patcher = patch.object(PS, "_cf", fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        check = patch.object(R2Client, "check", lambda client: True)
        check.start()
        self.addCleanup(check.stop)

    def test_defaults(self):
        wizard = self.env["cloudflare.photos.setup.wizard"].create({})
        self.assertEqual(wizard.bucket_name, "example-photos", "the site name, www left out")
        self.assertEqual(wizard.domain, "photos.ex.co", "photos.<short domain>")
        self.assertEqual(wizard.origin, "https://www.example.com")

    def test_run(self):
        wizard = self.env["cloudflare.photos.setup.wizard"].create({"setup_token": "tok", "bucket_name": "site-photos"})
        wizard.action_connect()
        self.assertEqual((wizard.step, wizard.account_id, wizard.zone_id), ("review", ACCOUNT, "zone-co"))
        with self.assertLogs("odoo.addons.cloudflare_connector.models.photos_setup", level="INFO") as logs:
            wizard.action_run()
        self.assertTrue(wizard.done, wizard.log)
        paths = [(m, p) for m, p, _j in self.calls]
        base = "/accounts/%s/r2/buckets/site-photos" % ACCOUNT
        self.assertIn(("POST", "/accounts/%s/r2/buckets" % ACCOUNT), paths)
        self.assertNotIn(("PUT", base + "/lock"), paths, "no lock on the photos bucket")
        body = {(m, p): j for m, p, j in self.calls}
        self.assertEqual(body[("POST", base + "/domains/custom")]["domain"], "photos.ex.co")
        self.assertEqual(body[("POST", base + "/domains/custom")]["zoneId"], "zone-co")
        rules = body[("PUT", base + "/lifecycle")]["rules"]
        self.assertEqual([(r["conditions"]["prefix"], r["deleteObjectsTransition"]["condition"]["maxAge"])
                          for r in rules], [("tours/", 60 * 86400), ("inbox/", 14 * 86400), ("staging/", 120 * 86400)])
        cors = body[("PUT", base + "/cors")]["rules"][0]
        self.assertEqual(cors["allowed"]["origins"], ["https://www.example.com"])
        self.assertEqual(sorted(cors["allowed"]["methods"]), ["GET", "HEAD", "PUT"])
        self.assertIn("Content-Type", cors["allowed"]["headers"])
        # the site's key: kept apart from the backups key
        self.assertEqual(self.ICP.get_param(PS.PHOTOS + "bucket"), "site-photos")
        self.assertEqual(self.ICP.get_param(PS.PHOTOS + "access_key_id"), "site-key-id")
        self.assertEqual(self.ICP.get_param(PS.PHOTOS + "secret_access_key"),
                         hashlib.sha256(b"site-secret").hexdigest())
        self.assertEqual(self.ICP.get_param(PS.PHOTOS + "domain"), "photos.ex.co")
        # the photo server's key: shown once, never kept, never logged
        nas_secret = hashlib.sha256(b"nas-secret").hexdigest()
        self.assertEqual((wizard.nas_access_key_id, wizard.nas_secret_access_key), ("nas-key-id", nas_secret))
        kept = " ".join(self.ICP.search([]).mapped("value"))
        self.assertNotIn(nas_secret, kept)
        self.assertNotIn("nas-key-id", kept)
        self.assertNotIn(nas_secret, wizard.log + "\n".join(logs.output))
        self.assertIn(("DELETE", "/accounts/%s/tokens/setup-id" % ACCOUNT), paths, "the setup token goes")
        self.assertFalse(wizard.setup_token)
        wizard.action_finish()
        self.assertFalse(wizard.nas_access_key_id or wizard.nas_secret_access_key)
        # the photos client uses the photos bucket
        R2 = self.env["cloudflare.r2"].sudo()
        self.assertTrue(R2.photos_configured())
        client = R2.photos_client()
        self.assertEqual((client.bucket, client.access_key_id), ("site-photos", "site-key-id"))
        self.assertEqual(R2.photos_domain(), "https://photos.ex.co")
        self.assertEqual(R2.photos_bucket(), "site-photos")
        self.assertIn("/site-photos/inbox/a.jpg?", R2.presign_put("inbox/a.jpg", 60, "image/jpeg", photos=True))

    def test_domain_not_on_the_account(self):
        wizard = self.env["cloudflare.photos.setup.wizard"].create({"setup_token": "tok", "domain": "photos.other.org"})
        with self.assertRaises(Exception):
            wizard.action_connect()

    def test_fallback_to_the_main_bucket(self):
        for key, value in (("account_id", "acc"), ("r2_access_key_id", "K"), ("r2_secret_access_key", "S"),
                           ("r2_bucket", "backups")):
            self.ICP.set_param("cloudflare_connector." + key, value)
        R2 = self.env["cloudflare.r2"].sudo()
        self.assertFalse(R2.photos_configured())
        self.assertEqual(R2.photos_client().bucket, "backups")
