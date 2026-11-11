import hashlib
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from ..models import setup as setup_mod

ACC = "acc0123456789"


class FakeCloudflare:
    """Answers the wizard's calls like the Cloudflare API does, and records them."""

    def __init__(self, bucket_exists=False, fail_on=None):
        self.calls = []
        self.bucket_exists = bucket_exists
        self.fail_on = fail_on
        self.n = 0

    def __call__(self, method, path, token, **kw):
        self.calls.append((method, path, kw.get("json")))
        if self.fail_on and self.fail_on in path and method == "POST":
            return False, None, "boom (1000)", 400
        if path == "/accounts":
            return True, [{"id": ACC, "name": "MTB"}], "", 200
        if path.endswith("/tokens/verify"):
            return True, {"id": "setup-id", "status": "active"}, "", 200
        if path.endswith("/permission_groups"):
            return True, [{"id": "pg-r2", "name": "Workers R2 Storage Bucket Item Write"},
                          {"id": "pg-purge", "name": "Cache Purge"}], "", 200
        if path == "/accounts/%s/r2/buckets" % ACC and method == "POST":
            return (False, None, "exists (10004)", 409) if self.bucket_exists else (True, {"name": "x"}, "", 200)
        if "/r2/buckets/" in path and method == "GET":
            return True, {"name": "x"}, "", 200
        if path.endswith("/lock"):
            return True, {}, "", 200
        if path == "/accounts/%s/tokens" % ACC and method == "POST":
            self.n += 1
            return True, {"id": "tok-%s" % self.n, "value": "secret-value-%s" % self.n}, "", 200
        if path == "/zones":
            return True, [{"id": "zone-1", "name": "example.com"}], "", 200
        if method == "DELETE":
            return True, {"id": path.rsplit("/", 1)[-1]}, "", 200
        return False, None, "unexpected %s %s" % (method, path), 404


@tagged("post_install", "-at_install")
class TestSetupWizard(TransactionCase):

    def setUp(self):
        super().setUp()
        self.env["ir.config_parameter"].sudo().set_param("web.base.url", "https://www.example.com")
        self.check = patch.object(setup_mod.R2Client, "check", return_value=True).start()
        self.addCleanup(patch.stopall)

    def _run(self, fake, **vals):
        wiz = self.env["cloudflare.setup.wizard"].create(dict({"setup_token": "SETUP"}, **vals))
        with patch.object(setup_mod, "_cf", fake):
            wiz.action_run()
        return wiz

    def _p(self, k):
        return self.env["ir.config_parameter"].sudo().get_param("cloudflare_connector." + k)

    def test_defaults_from_site(self):
        wiz = self.env["cloudflare.setup.wizard"].new({})
        self.assertEqual(wiz.zone_name, "example.com")
        self.assertEqual(wiz.bucket_name, "example-backups")

    def test_full_run(self):
        fake = FakeCloudflare()
        wiz = self._run(fake, bucket_name="mtbg-backups-tours")
        self.assertTrue(wiz.done, wiz.log)
        self.assertFalse(wiz.setup_token)
        self.assertEqual(self._p("account_id"), ACC)
        self.assertEqual(self._p("r2_bucket"), "mtbg-backups-tours")
        self.assertEqual(self._p("r2_access_key_id"), "tok-1")
        self.assertEqual(self._p("r2_secret_access_key"), hashlib.sha256(b"secret-value-1").hexdigest())
        self.assertEqual(self._p("api_token"), "secret-value-2")
        self.assertEqual(self._p("zone_id"), "zone-1")
        r2_policy = [c for c in fake.calls if c[0] == "POST" and c[1].endswith("/tokens")][0][2]["policies"][0]
        self.assertEqual(r2_policy["resources"],
                         {"com.cloudflare.edge.r2.bucket.%s_default_mtbg-backups-tours" % ACC: "*"})
        self.assertEqual(r2_policy["permission_groups"], [{"id": "pg-r2"}])
        lock = [c for c in fake.calls if c[1].endswith("/lock")][0][2]
        self.assertEqual([r["prefix"] for r in lock["rules"]], ["snapshots/", "files/"])
        self.assertEqual(lock["rules"][0]["condition"], {"type": "Age", "maxAgeSeconds": 7 * 86400})
        self.assertIn(("DELETE", "/accounts/%s/tokens/setup-id" % ACC, None), fake.calls)
        self.assertIn("Setup token deleted", wiz.log)

    def test_local_address_has_no_zone(self):
        self.env["ir.config_parameter"].sudo().set_param("web.base.url", "http://127.0.0.1:8069")
        wiz = self.env["cloudflare.setup.wizard"].new({})
        self.assertEqual(wiz.zone_name, "")
        self.assertTrue(wiz.bucket_name.endswith("-backups"))

    def test_existing_bucket_is_kept(self):
        wiz = self._run(FakeCloudflare(bucket_exists=True), bucket_name="mtbg-backups-tours")
        self.assertTrue(wiz.done, wiz.log)
        self.assertIn("already exists", wiz.log)

    def test_stop_keeps_progress_and_blanks_token(self):
        fake = FakeCloudflare(fail_on="/tokens")  # the token creation fails after the bucket was made
        wiz = self._run(fake, bucket_name="mtbg-backups-tours")
        self.assertFalse(wiz.done)
        self.assertFalse(wiz.setup_token)
        self.assertIn("Stopped", wiz.log)
        self.assertIn("Bucket mtbg-backups-tours created", wiz.log)
        self.assertFalse(self._p("r2_access_key_id"))

    def test_rerun_revokes_previous_key(self):
        self._run(FakeCloudflare(), bucket_name="b1-backups", create_purge_token=False)
        fake = FakeCloudflare()
        fake.n = 10
        self._run(fake, bucket_name="b1-backups", create_purge_token=False)
        self.assertEqual(self._p("r2_access_key_id"), "tok-11")
        self.assertIn(("DELETE", "/accounts/%s/tokens/tok-1" % ACC, None), fake.calls)


@tagged("post_install", "-at_install")
class TestSetupTokenLink(TransactionCase):

    def test_template_url_prefills_the_four_permissions(self):
        import json
        from urllib.parse import parse_qs, urlparse
        url = setup_mod.setup_token_url()
        parsed = urlparse(url)
        self.assertEqual((parsed.netloc, parsed.path), ("dash.cloudflare.com", "/"))
        q = parse_qs(parsed.query)
        self.assertEqual(q["to"], ["/:account/api-tokens"], "an account-owned token: the wizard can delete it")
        self.assertEqual(json.loads(q["permissionGroupKeys"][0]), [
            {"key": "workers_r2", "type": "edit"}, {"key": "account_api_tokens", "type": "edit"},
            {"key": "zone", "type": "read"}, {"key": "cache", "type": "purge"}])

    def test_button_opens_without_a_token(self):
        wiz = self.env["cloudflare.setup.wizard"].create({})
        action = wiz.action_open_dashboard()
        self.assertEqual(action["type"], "ir.actions.act_url")
        self.assertIn("permissionGroupKeys=", action["url"])

    def test_set_up_still_needs_the_token(self):
        from odoo.exceptions import UserError
        with self.assertRaises(UserError):
            self.env["cloudflare.setup.wizard"].create({}).action_run()
