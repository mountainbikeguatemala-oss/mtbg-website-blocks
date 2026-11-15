"""Set up photos storage (owner, 2026-11-14: "I don't see photo R2 settings in the cloudflare connector"): a second
bucket for photos shown online, made from the same kind of setup token as Set up Cloudflare.

The backups bucket has a lock (nothing deleted before N days), so photos, which expire and are deleted, get their own
bucket, ``<site>-photos``, with NO lock. The run:

1. finds the account the setup token belongs to;
2. creates the bucket (or keeps it when it exists);
3. connects its public custom domain (e.g. ``photos.<short domain or zone>``): R2's custom domain on a zone of the
   account (a domain that can't be connected is said, the rest goes on);
4. sets its lifecycle rules (``tours/`` deleted after 60 days, ``inbox/`` after 14) and its CORS rule (PUT with
   Content-Type, GET and HEAD from the site's address: the Staff App's uploads, the gallery's browser zips);
5. makes the site's own key for that bucket (object read and write), kept in the photos parameters (``r2_photos_*``),
   apart from the backups key;
6. makes a second key for the photo server (the NAS), object read and write on that bucket only: shown ONCE in the
   wizard to copy, never saved by Odoo and never written to the log;
7. tests the site's key (write, read back, delete) and deletes the setup token in Cloudflare.

The setup token and the photo server's key are blanked from the wizard's row when it closes."""
import hashlib
import logging
import re
import time
from urllib.parse import urlparse

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .connector import P
from .r2 import R2Client, R2Error
from .setup import BUCKET_RE, PG_BUCKET_ITEM_WRITE, R2_OFF_CODES, _bucket_slug, _cf, _need, setup_token_url

_logger = logging.getLogger(__name__)

PHOTOS = P + "r2_photos_"  # the photos bucket's parameters: bucket, access_key_id, secret_access_key, token_id, domain
LIFECYCLE = [("tours/", 60), ("inbox/", 14), ("staging/", 120)]  # staging: the previews (Tour photos 0.1.3)
STEPS = [("connect", "Connect"), ("review", "Review"), ("done", "Done")]
DOMAIN_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def lifecycle_rules():
    """R2's lifecycle rules: each folder deleted after its days."""
    return [{"id": "delete-%s-%sd" % (prefix.strip("/"), days), "enabled": True, "conditions": {"prefix": prefix},
             "deleteObjectsTransition": {"condition": {"type": "Age", "maxAge": days * 86400}}}
            for prefix, days in LIFECYCLE]


def cors_rules(origin):
    """R2's CORS rule: the site's pages PUT (with Content-Type), GET and HEAD the photos."""
    return [{"allowed": {"origins": [origin], "methods": ["PUT", "GET", "HEAD"], "headers": ["Content-Type"]},
             "exposeHeaders": ["ETag", "Content-Length"], "maxAgeSeconds": 3600}]


class CloudflarePhotosSetupWizard(models.TransientModel):
    _name = "cloudflare.photos.setup.wizard"
    _description = "Set up photos storage on Cloudflare"

    step = fields.Selection(STEPS, default="connect", required=True)
    setup_token = fields.Char("Setup token", help="Made with the Create the token on Cloudflare button; used for "
                                                  "this setup only and deleted in Cloudflare at the end.")
    account_id = fields.Char("Account ID")
    account_name = fields.Char(readonly=True)
    bucket_name = fields.Char("Photos bucket", default=lambda self: self._default_bucket(),
                              help="A bucket of its own, with no lock: photos expire and are deleted")
    location_hint = fields.Selection([("enam", "Eastern North America"), ("wnam", "Western North America"),
                                      ("weur", "Western Europe"), ("eeur", "Eastern Europe"), ("apac", "Asia-Pacific"),
                                      ("oc", "Oceania")], string="Location", default="enam")
    domain = fields.Char("Public address", default=lambda self: self._default_domain(),
                         help="The photos' public address (a name on one of the account's websites): the gallery and "
                              "the emails show pictures from https://<this>/<key>")
    zone_id = fields.Char(readonly=True)
    origin = fields.Char("Site address (CORS)", default=lambda self: self._default_origin(),
                         help="The site's address its pages upload and download from")
    nas_access_key_id = fields.Char("Photo server access key ID", readonly=True)
    nas_secret_access_key = fields.Char("Photo server secret access key", readonly=True)
    nas_endpoint = fields.Char("R2 endpoint", readonly=True)
    log = fields.Text(readonly=True)
    done = fields.Boolean(readonly=True)

    # ------------------------------------------------------------------ defaults
    @api.model
    def _site_url(self):
        return (self.env["ir.config_parameter"].sudo().get_param("web.base.url") or "").rstrip("/")

    @api.model
    def _default_bucket(self):
        host = urlparse(self._site_url()).hostname or self.env.cr.dbname
        host = re.sub(r"^www\.", "", host or "")
        return _bucket_slug("%s-photos" % host.split(".")[0])

    @api.model
    def _default_domain(self):
        ICP = self.env["ir.config_parameter"].sudo()
        short = (ICP.get_param("mtbg_tours.short_link_domain") or ICP.get_param("mtbg_tours.invoice_short_domain")
                 or "").strip()
        short = re.sub(r"^https?://", "", short).strip("/").lower()
        zone = (ICP.get_param(P + "zone_name") or "").strip().lower()
        base = short or zone or re.sub(r"^www\.", "", urlparse(self._site_url()).hostname or "")
        return "photos.%s" % base if base else ""

    @api.model
    def _default_origin(self):
        url = urlparse(self._site_url())
        return "%s://%s" % ("https" if url.scheme in ("https", "") else url.scheme, url.netloc) if url.netloc else ""

    def _reopen(self):
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
                "target": "new", "name": _("Set up photos storage")}

    def _check_admin(self):
        if not self.env.user.has_group("base.group_system"):
            raise UserError(_("Only an administrator sets up Cloudflare."))

    def action_open_dashboard(self):
        return {"type": "ir.actions.act_url", "url": setup_token_url("Odoo photos setup (deleted after use)"),
                "target": "new"}

    # ------------------------------------------------------------------ steps
    def action_connect(self):
        self.ensure_one()
        self._check_admin()
        token = (self.setup_token or "").strip()
        if not token:
            raise UserError(_("Paste the setup token first."))
        accounts = _need(_cf("GET", "/accounts", token, params={"per_page": 50}), _("Checking the token")) or []
        if len(accounts) != 1 and not self.account_id:
            raise UserError(_("The token sees %s accounts: make it again for one account only.", len(accounts)))
        account = self.account_id or accounts[0]["id"]
        name = next((a.get("name") for a in accounts if a.get("id") == account), account)
        bucket = (self.bucket_name or "").strip().lower()
        if not BUCKET_RE.match(bucket) or "--" in bucket:
            raise UserError(_("A bucket name has 3 to 63 characters: lowercase letters, digits and single hyphens."))
        domain = (self.domain or "").strip().lower()
        if domain and not DOMAIN_RE.match(domain):
            raise UserError(_("The public address is a name such as photos.example.com."))
        if not (self.origin or "").startswith(("https://", "http://")):
            raise UserError(_("The site address starts with https://"))
        zone_id = False
        if domain:
            zones = _need(_cf("GET", "/zones", token, params={"account.id": account, "per_page": 50}),
                          _("Reading the websites")) or []
            match = [z for z in zones if domain == z["name"] or domain.endswith("." + z["name"])]
            if not match:
                raise UserError(_("%s is not on a website of this Cloudflare account: pick a name on one of them (%s).",
                                  domain, ", ".join(z["name"] for z in zones) or "-"))
            zone_id = sorted(match, key=lambda z: -len(z["name"]))[0]["id"]
        self.write({"account_id": account, "account_name": name, "bucket_name": bucket, "domain": domain,
                    "zone_id": zone_id, "step": "review"})
        return self._reopen()

    def action_back(self):
        self.ensure_one()
        self.step = "connect"
        return self._reopen()

    def action_run(self):
        self.ensure_one()
        self._check_admin()
        token = (self.setup_token or "").strip()
        if not token:
            raise UserError(_("Paste the setup token first."))
        lines = []

        def note(text):
            lines.append(text)
            _logger.info("Cloudflare photos setup: %s", text)  # (never a key: the notes name things only)

        ok = False
        try:
            self._run(token, note)
            ok = True
        except UserError as e:
            note(_("Stopped: %s", e.args[0] if e.args else e))
        finally:
            self.write({"setup_token": False, "log": "\n".join(lines), "done": ok, "step": "done"})
        return self._reopen()

    def action_finish(self):
        """The photo server's key leaves the wizard (it was shown once)."""
        self.write({"nas_access_key_id": False, "nas_secret_access_key": False, "setup_token": False})
        return {"type": "ir.actions.act_window_close"}

    # ------------------------------------------------------------------ the run
    def _token_for_bucket(self, token, account, bucket, group_id, label):
        host = urlparse(self._site_url()).hostname or self.env.cr.dbname
        return _need(_cf("POST", "/accounts/%s/tokens" % account, token, json={
            "name": ("%s · R2 %s (%s)" % (host, bucket, label))[:120],
            "policies": [{"effect": "allow", "permission_groups": [{"id": group_id}],
                          "resources": {"com.cloudflare.edge.r2.bucket.%s_default_%s" % (account, bucket): "*"}}],
        }), _("Creating the %s key", label))

    def _run(self, token, note):
        ICP = self.env["ir.config_parameter"].sudo()
        account, bucket, domain = self.account_id, self.bucket_name, self.domain
        note(_("✓ Account %s", self.account_name or account))
        ok, result, _err, _st = _cf("GET", "/accounts/%s/tokens/verify" % account, token)
        setup_token_id, setup_is_account = (result or {}).get("id"), True
        if not ok:
            ok, result, _err, _st = _cf("GET", "/user/tokens/verify", token)
            setup_token_id, setup_is_account = (result or {}).get("id"), False
        if not setup_token_id:
            raise UserError(_("The setup token is not valid (Cloudflare could not verify it)."))

        # 1. the bucket, no lock
        ok, _res, errors, status = _cf("POST", "/accounts/%s/r2/buckets" % account, token,
                                       json={"name": bucket, "locationHint": self.location_hint or "enam",
                                             "storageClass": "Standard"})
        if ok:
            note(_("✓ Bucket %s created (no lock)", bucket))
        elif _cf("GET", "/accounts/%s/r2/buckets/%s" % (account, bucket), token)[0]:
            note(_("✓ Bucket %s already exists: kept", bucket))
        elif any(code in (errors or "") for code in R2_OFF_CODES):
            raise UserError(_("R2 is not turned on for this account: turn it on on the Cloudflare dashboard, then run "
                              "the setup again."))
        else:
            raise UserError(_("Creating bucket %(b)s failed: %(e)s", b=bucket, e=errors or status))
        base = "/accounts/%s/r2/buckets/%s" % (account, bucket)

        # 2. the public custom domain (said when it can't be connected; the rest goes on)
        if domain and self.zone_id:
            ok, _res, errors, _st = _cf("POST", base + "/domains/custom", token, json={
                "domain": domain, "zoneId": self.zone_id, "enabled": True, "minTLS": "1.2"})
            if ok:
                note(_("✓ Public address %s connected", domain))
            elif "already" in (errors or "").lower():
                note(_("✓ Public address %s already connected", domain))
            else:
                note(_("! Public address %(d)s not connected (%(e)s): connect it on the bucket's Settings in the "
                       "Cloudflare dashboard (Custom Domains)", d=domain, e=errors))

        # 3. lifecycle and CORS
        _need(_cf("PUT", base + "/lifecycle", token, json={"rules": lifecycle_rules()}), _("Setting the lifecycle rules"))
        note(_("✓ Lifecycle: %s", ", ".join("%s deleted after %s days" % (p, d) for p, d in LIFECYCLE)))
        _need(_cf("PUT", base + "/cors", token, json={"rules": cors_rules(self.origin)}), _("Setting CORS"))
        note(_("✓ CORS: PUT (Content-Type), GET and HEAD from %s", self.origin))

        # 4. the keys: the site's (kept), the photo server's (shown once)
        groups = _need(_cf("GET", "/accounts/%s/tokens/permission_groups" % account, token,
                           params={"per_page": 1000}), _("Reading the permission groups")) or []
        group_id = next((g.get("id") for g in groups if g.get("name") in PG_BUCKET_ITEM_WRITE), None)
        if not group_id:
            raise UserError(_("Cloudflare has no permission group named %s on this account.", PG_BUCKET_ITEM_WRITE[0]))
        site = self._token_for_bucket(token, account, bucket, group_id, "Odoo photos")
        old_site_id = ICP.get_param(PHOTOS + "token_id")
        ICP.set_param(P + "account_id", ICP.get_param(P + "account_id") or account)
        ICP.set_param(PHOTOS + "account_id", account)
        ICP.set_param(PHOTOS + "bucket", bucket)
        ICP.set_param(PHOTOS + "access_key_id", site["id"])
        ICP.set_param(PHOTOS + "secret_access_key", hashlib.sha256(site["value"].encode()).hexdigest())
        ICP.set_param(PHOTOS + "token_id", site["id"])
        ICP.set_param(PHOTOS + "domain", domain or "")
        note(_("✓ Site key created, limited to bucket %s", bucket))
        nas = self._token_for_bucket(token, account, bucket, group_id, "photo server")
        self.write({"nas_access_key_id": nas["id"],
                    "nas_secret_access_key": hashlib.sha256(nas["value"].encode()).hexdigest(),
                    "nas_endpoint": "https://%s.r2.cloudflarestorage.com" % account})
        note(_("✓ Photo server key created, limited to bucket %s (shown below once)", bucket))

        # 5. test the site's key
        client = R2Client(account, site["id"], ICP.get_param(PHOTOS + "secret_access_key"), bucket)
        last = None
        for _attempt in range(10):
            try:
                client.check()
                last = None
                break
            except R2Error as e:
                last = e
                time.sleep(3)
        if last:
            raise UserError(_("The new photos key did not work yet: %s. Run the setup again in a minute.", last))
        note(_("✓ Photos storage test passed: write, read back, delete"))
        if old_site_id and old_site_id != site["id"]:
            if _cf("DELETE", "/accounts/%s/tokens/%s" % (account, old_site_id), token)[0]:
                note(_("✓ The previous photos key was revoked"))

        # 6. the setup token goes
        path = ("/accounts/%s/tokens/%s" % (account, setup_token_id)) if setup_is_account \
            else "/user/tokens/%s" % setup_token_id
        ok, _res, errors, _st = _cf("DELETE", path, token)
        note(_("✓ Setup token deleted in Cloudflare") if ok else
             _("Could not delete the setup token (%s): delete it on the Cloudflare dashboard.", errors))
