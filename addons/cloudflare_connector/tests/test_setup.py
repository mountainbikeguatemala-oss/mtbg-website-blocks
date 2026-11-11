import hashlib
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from ..models import setup as setup_mod

ACC = "acc0123456789"


class FakeCloudflare:
    """Answers the wizard's calls like the Cloudflare API does, and records them."""

    def __init__(self, bucket_exists=False, fail_on=None, accounts=None, buckets=(), r2_off=False, lock_rules=()):
        self.calls = []
        self.bucket_exists = bucket_exists
        self.fail_on = fail_on
        self.accounts = accounts or [{"id": ACC, "name": "Example account"}]
        self.buckets = list(buckets)
        self.r2_off = r2_off
        self.lock_rules = list(lock_rules)
        self.n = 0

    def __call__(self, method, path, token, **kw):
        self.calls.append((method, path, kw.get("json")))
        if self.fail_on and self.fail_on in path and method == "POST":
            return False, None, "boom (1000)", 400
        if path == "/accounts":
            return True, self.accounts, "", 200
        if path.endswith("/tokens/verify"):
            return True, {"id": "setup-id", "status": "active"}, "", 200
        if path.endswith("/permission_groups"):
            return True, [{"id": "pg-r2", "name": "Workers R2 Storage Bucket Item Write"},
                          {"id": "pg-purge", "name": "Cache Purge"}], "", 200
        if path == "/accounts/%s/r2/buckets" % ACC and method == "GET":
            if self.r2_off:
                return False, None, "Please enable R2 through the Cloudflare Dashboard. (10042)", 403
            return True, {"buckets": [{"name": b, "location": "ENAM", "creation_date": "2026-11-10T12:00:00Z"}
                                      for b in self.buckets]}, "", 200
        if path == "/accounts/%s/r2/buckets" % ACC and method == "POST":
            return (False, None, "exists (10004)", 409) if self.bucket_exists else (True, {"name": "x"}, "", 200)
        if path.endswith("/lock") and method == "GET":
            return True, {"rules": self.lock_rules}, "", 200
        if "/r2/buckets/" in path and method == "GET":
            return True, {"name": "x"}, "", 200
        if path.endswith("/lock"):
            return True, {}, "", 200
        if path == "/accounts/%s/tokens" % ACC and method == "POST":
            self.n += 1
            return True, {"id": "tok-%s" % self.n, "value": "secret-value-%s" % self.n}, "", 200
        if path == "/zones":
            return True, [{"id": "zone-1", "name": "example.com"}, {"id": "zone-2", "name": "other.org"}], "", 200
        if method == "DELETE":
            return True, {"id": path.rsplit("/", 1)[-1]}, "", 200
        return False, None, "unexpected %s %s" % (method, path), 404


@tagged("post_install", "-at_install")
class TestSetupWizard(TransactionCase):

    def setUp(self):
        super().setUp()
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("web.base.url", "https://www.example.com")
        for key in ("r2_bucket", "r2_token_id", "r2_access_key_id", "api_token", "zone_id"):
            ICP.set_param("cloudflare_connector." + key, False)  # a site's own setup never leaks into the defaults
        self.check = patch.object(setup_mod.R2Client, "check", return_value=True).start()
        self.addCleanup(patch.stopall)

    def _walk(self, fake, connect_vals=None, **vals):
        """Connect, then the bucket and cache steps, then Set up: what the user clicks through."""
        wiz = self.env["cloudflare.setup.wizard"].create(dict({"setup_token": "SETUP"}, **(connect_vals or {})))
        with patch.object(setup_mod, "_cf", fake):
            wiz.action_connect()
            self.assertEqual(wiz.step, "bucket")
            wiz.write(vals)
            wiz.action_bucket_next()
            wiz.action_cache_next()
            self.assertEqual(wiz.step, "review")
            wiz.action_run()
        return wiz

    def _p(self, k):
        return self.env["ir.config_parameter"].sudo().get_param("cloudflare_connector." + k)

    def test_defaults_from_site(self):
        wiz = self.env["cloudflare.setup.wizard"].new({})
        self.assertEqual(wiz.zone_name, "example.com")
        self.assertEqual(wiz.bucket_name, "example-backups")
        self.assertEqual(wiz.step, "connect")

    def test_local_address_has_no_zone(self):
        self.env["ir.config_parameter"].sudo().set_param("web.base.url", "http://127.0.0.1:8069")
        wiz = self.env["cloudflare.setup.wizard"].new({})
        self.assertEqual(wiz.zone_name, "")
        self.assertTrue(wiz.bucket_name.endswith("-backups"))

    def test_connect_reads_buckets_and_zones(self):
        wiz = self.env["cloudflare.setup.wizard"].create({"setup_token": "SETUP"})
        with patch.object(setup_mod, "_cf", FakeCloudflare(buckets=["old-backups"])):
            wiz.action_connect()
        self.assertEqual((wiz.step, wiz.account_id, wiz.account_name), ("bucket", ACC, "Example account"))
        self.assertTrue(wiz.r2_enabled)
        self.assertEqual(wiz.bucket_count, 1)
        self.assertIn("made 2026-11-10", wiz.choice_ids.filtered(lambda c: c.kind == "bucket").display_name)
        self.assertEqual(wiz.zone_choice_id.name, "example.com", "the site's own zone is picked")
        self.assertEqual(wiz.bucket_mode, "new")

    def test_connect_with_several_accounts_asks_which(self):
        fake = FakeCloudflare(accounts=[{"id": ACC, "name": "Shop"}, {"id": "acc-2", "name": "Tours"}])
        wiz = self.env["cloudflare.setup.wizard"].create({"setup_token": "SETUP"})
        with patch.object(setup_mod, "_cf", fake):
            wiz.action_connect()
            self.assertEqual((wiz.step, wiz.account_count), ("connect", 2))
            wiz.account_choice_id = wiz.choice_ids.filtered(lambda c: c.key == ACC)
            wiz.action_connect()
        self.assertEqual((wiz.step, wiz.account_name), ("bucket", "Shop"))

    def test_r2_turned_off_is_explained(self):
        wiz = self.env["cloudflare.setup.wizard"].create({"setup_token": "SETUP"})
        with patch.object(setup_mod, "_cf", FakeCloudflare(r2_off=True)):
            wiz.action_connect()
        self.assertEqual(wiz.step, "connect", "it waits until R2 is on")
        self.assertFalse(wiz.r2_enabled)
        self.assertEqual(wiz.action_open_r2()["url"], "https://dash.cloudflare.com/%s/r2/overview" % ACC)
        with patch.object(setup_mod, "_cf", FakeCloudflare()):
            wiz.action_connect()  # turned on: Next again goes on
        self.assertEqual(wiz.step, "bucket")

    def test_bucket_name_rules(self):
        from odoo.exceptions import UserError
        wiz = self.env["cloudflare.setup.wizard"].create({"setup_token": "SETUP"})
        with patch.object(setup_mod, "_cf", FakeCloudflare(buckets=["taken-backups"])):
            wiz.action_connect()
        for bad in ("ab", "Bad Name", "-x-backups", "a--b"):
            wiz.bucket_name = bad
            with self.assertRaises(UserError):
                wiz.action_bucket_next()
        wiz.bucket_name = "taken-backups"
        self.assertTrue(wiz.bucket_name_taken)
        with self.assertRaises(UserError):
            wiz.action_bucket_next()
        wiz.bucket_name = "shop-backups"
        wiz.action_bucket_next()
        self.assertEqual(wiz.step, "cache")
        wiz.action_back()
        self.assertEqual(wiz.step, "bucket")

    def test_saved_bucket_is_offered_as_existing(self):
        self.env["ir.config_parameter"].sudo().set_param("cloudflare_connector.r2_bucket", "example-backups")
        wiz = self.env["cloudflare.setup.wizard"].create({"setup_token": "SETUP"})
        with patch.object(setup_mod, "_cf", FakeCloudflare(buckets=["example-backups"])):
            wiz.action_connect()
        self.assertEqual((wiz.bucket_mode, wiz.bucket_choice_id.name), ("existing", "example-backups"))

    def test_full_run(self):
        fake = FakeCloudflare()
        wiz = self._walk(fake, bucket_name="shop-backups")
        self.assertTrue(wiz.done, wiz.log)
        self.assertEqual(wiz.step, "done")
        self.assertFalse(wiz.setup_token)
        self.assertEqual(self._p("account_id"), ACC)
        self.assertEqual(self._p("r2_bucket"), "shop-backups")
        self.assertEqual(self._p("r2_access_key_id"), "tok-1")
        self.assertEqual(self._p("r2_secret_access_key"), hashlib.sha256(b"secret-value-1").hexdigest())
        self.assertEqual(self._p("api_token"), "secret-value-2")
        self.assertEqual(self._p("zone_id"), "zone-1")
        r2_policy = [c for c in fake.calls if c[0] == "POST" and c[1].endswith("/tokens")][0][2]["policies"][0]
        self.assertEqual(r2_policy["resources"], {"com.cloudflare.edge.r2.bucket.%s_default_shop-backups" % ACC: "*"})
        self.assertEqual(r2_policy["permission_groups"], [{"id": "pg-r2"}])
        lock = [c for c in fake.calls if c[1].endswith("/lock") and c[0] == "PUT"][0][2]
        self.assertEqual([r["prefix"] for r in lock["rules"]], ["snapshots/", "files/"])
        self.assertEqual(lock["rules"][0]["condition"], {"type": "Age", "maxAgeSeconds": 7 * 86400})
        self.assertIn(("DELETE", "/accounts/%s/tokens/setup-id" % ACC, None), fake.calls)
        self.assertIn("✓ Setup token deleted", wiz.log)
        self.assertIn("Create the bucket shop-backups", wiz.summary)

    def test_other_zone_and_no_cache_key(self):
        fake = FakeCloudflare()
        wiz = self.env["cloudflare.setup.wizard"].create({"setup_token": "SETUP"})
        with patch.object(setup_mod, "_cf", fake):
            wiz.action_connect()
            wiz.action_bucket_next()
            wiz.zone_choice_id = wiz.choice_ids.filtered(lambda c: c.name == "other.org")
            wiz.action_cache_next()
            wiz.action_run()
        self.assertEqual(self._p("zone_id"), "zone-2")
        fake2 = FakeCloudflare()
        self._walk(fake2, bucket_name="b2-backups", create_purge_token=False)
        self.assertEqual(len([c for c in fake2.calls if c[0] == "POST" and c[1].endswith("/tokens")]), 1)

    def test_existing_bucket_lock_rules(self):
        rules = [{"id": "keep-30d", "prefix": "", "condition": {"type": "Age", "maxAgeSeconds": 30 * 86400}}]
        for lock_rules, puts in ((rules, 0), ((), 1)):
            fake = FakeCloudflare(buckets=["shared-backups"], lock_rules=lock_rules)
            wiz = self.env["cloudflare.setup.wizard"].create({"setup_token": "SETUP"})
            with patch.object(setup_mod, "_cf", fake):
                wiz.action_connect()
                wiz.write({"bucket_mode": "existing",
                           "bucket_choice_id": wiz.choice_ids.filtered(lambda c: c.kind == "bucket").id})
                wiz.action_bucket_next()
                wiz.action_cache_next()
                wiz.action_run()
            self.assertTrue(wiz.done, wiz.log)
            self.assertEqual(self._p("r2_bucket"), "shared-backups")
            self.assertFalse([c for c in fake.calls if c[0] == "POST" and c[1].endswith("/r2/buckets")])
            self.assertEqual(len([c for c in fake.calls if c[0] == "PUT" and c[1].endswith("/lock")]), puts)

    def test_stop_keeps_progress_and_blanks_token(self):
        fake = FakeCloudflare(fail_on="/tokens")  # the token creation fails after the bucket was made
        wiz = self._walk(fake, bucket_name="shop-backups")
        self.assertFalse(wiz.done)
        self.assertFalse(wiz.setup_token)
        self.assertIn("Stopped", wiz.log)
        self.assertIn("✓ Bucket shop-backups created", wiz.log)
        self.assertFalse(self._p("r2_access_key_id"))

    def test_rerun_revokes_previous_key(self):
        self._walk(FakeCloudflare(), bucket_name="b1-backups", create_purge_token=False)
        fake = FakeCloudflare(buckets=["b1-backups"])
        fake.n = 10
        wiz = self.env["cloudflare.setup.wizard"].create({"setup_token": "SETUP"})
        with patch.object(setup_mod, "_cf", fake):
            wiz.action_connect()
            self.assertEqual(wiz.bucket_mode, "existing", "the saved bucket is offered again")
            wiz.create_purge_token = False
            wiz.action_bucket_next()
            wiz.action_cache_next()
            wiz.action_run()
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
