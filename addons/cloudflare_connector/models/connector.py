"""The Cloudflare connection: one place for the Cloudflare account, its API token and R2 storage.

Other extensions call it through soft checks and never import it:

    if 'cloudflare.r2' in env:
        sha = env['cloudflare.r2'].upload_file('backups/x.dump', '/tmp/x.dump')

``cloudflare.r2`` hands out a client for the saved bucket (or another bucket of the same account);
``cloudflare.api`` calls the Cloudflare REST API with the saved token.
"""
import logging
import time

import requests

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .r2 import R2Client, R2Error

_logger = logging.getLogger(__name__)

P = "cloudflare_connector."
API = "https://api.cloudflare.com/client/v4"
PURGE_BATCH = 30      # URLs per purge request (Cloudflare: 100 on every plan, 500 on Enterprise; 30 keeps well inside)
# prefixes, hosts or tags per purge request (2.0.1; Cloudflare's documentation, 2026-11: 100 on every plan). Fewer calls
# matter: on the Free plan these purges share 5 requests a minute (a burst of 25)
PURGE_BATCH_OTHER = 100
PURGE_TIMEOUT = 10
PURGE_TRIES = 4       # on 429 (rate limited): wait Retry-After (capped), then try again


def _param(env, name):
    return (env["ir.config_parameter"].sudo().get_param(P + name) or "").strip()


class CloudflareR2(models.AbstractModel):
    _name = "cloudflare.r2"
    _description = "Cloudflare R2 storage"

    @api.model
    def is_configured(self):
        return all(_param(self.env, k) for k in ("account_id", "r2_access_key_id", "r2_secret_access_key",
                                                  "r2_bucket"))

    @api.model
    def client(self, bucket=None):
        """An R2Client for ``bucket`` (default: the bucket saved in Settings). Raises UserError when not set up."""
        if not self.env.su and not self.env.user.has_group("base.group_system"):
            raise AccessError(_("Only administrators can use the Cloudflare R2 connection."))
        try:
            return R2Client(_param(self.env, "account_id"), _param(self.env, "r2_access_key_id"),
                            _param(self.env, "r2_secret_access_key"), bucket or _param(self.env, "r2_bucket"),
                            endpoint=_param(self.env, "r2_endpoint") or None)
        except R2Error as e:
            raise UserError(_("Cloudflare R2 is not set up yet: Settings › Cloudflare. (%s)", e)) from e

    # The photos bucket (1.6.0, "Set up photos storage"): its own keys, apart from the backups bucket's; without one,
    # the main bucket
    @api.model
    def photos_configured(self):
        """The photos bucket is set up (its own bucket and key)."""
        return all(_param(self.env, "r2_photos_" + k) for k in ("bucket", "access_key_id", "secret_access_key"))

    @api.model
    def photos_client(self):
        """An R2Client for the photos bucket; the main bucket's when no photos bucket is set up."""
        if not self.photos_configured():
            return self.client()
        if not self.env.su and not self.env.user.has_group("base.group_system"):
            raise AccessError(_("Only administrators can use the Cloudflare R2 connection."))
        try:
            return R2Client(_param(self.env, "r2_photos_account_id") or _param(self.env, "account_id"),
                            _param(self.env, "r2_photos_access_key_id"),
                            _param(self.env, "r2_photos_secret_access_key"), _param(self.env, "r2_photos_bucket"),
                            endpoint=_param(self.env, "r2_endpoint") or None)
        except R2Error as e:
            raise UserError(_("Cloudflare R2 is not set up yet: Settings › Cloudflare. (%s)", e)) from e

    @api.model
    def photos_bucket(self):
        """The photos bucket's name, '' when none is set up."""
        return _param(self.env, "r2_photos_bucket")

    @api.model
    def photos_domain(self):
        """The photos bucket's public address (https://...), '' when none."""
        domain = _param(self.env, "r2_photos_domain")
        return "https://%s" % domain if domain else ""

    def _pick(self, bucket, photos):
        return self.photos_client() if photos else self.client(bucket)

    # Shortcuts for the common calls (each returns what the client returns; ``photos``: the photos bucket).
    @api.model
    def upload_file(self, key, path, bucket=None, content_type="application/octet-stream"):
        return self.client(bucket).put_file(key, path, content_type)

    @api.model
    def upload_bytes(self, key, data, bucket=None, content_type="application/octet-stream"):
        return self.client(bucket).put_bytes(key, data, content_type)

    @api.model
    def download_file(self, key, path, bucket=None):
        return self.client(bucket).get_file(key, path)

    @api.model
    def list_objects(self, prefix="", bucket=None, photos=False):
        return self._pick(bucket, photos).list(prefix)

    @api.model
    def stat(self, key, bucket=None):
        return self.client(bucket).head(key)

    @api.model
    def remove(self, key, bucket=None, photos=False):
        return self._pick(bucket, photos).delete(key)

    @api.model
    def download_url(self, key, expires=3600, filename=None, bucket=None, photos=False):
        """A private, short-lived download link (signed; the bucket stays private). Administrators only."""
        return self._pick(bucket, photos).presign_get(key, expires, filename)


    @api.model
    def presign_put(self, key, expires=3600, content_type="application/octet-stream", bucket=None, photos=False):
        """A private, short-lived upload link (1.5.1: a PUT with that Content-Type). Administrators only (the caller
        decides who may upload, and where)."""
        return self._pick(bucket, photos).presign_put(key, expires, content_type)


class CloudflareApi(models.AbstractModel):
    _name = "cloudflare.api"
    _description = "Cloudflare API"

    @api.model
    def call(self, method, path, **kwargs):
        """Call ``API + path`` with the saved token; returns the JSON ``result``. Raises UserError on failure."""
        if not self.env.su and not self.env.user.has_group("base.group_system"):
            raise AccessError(_("Only administrators can use the Cloudflare connection."))
        token = _param(self.env, "api_token")
        if not token:
            raise UserError(_("No Cloudflare API token yet: Settings › Cloudflare."))
        try:
            r = requests.request(method, API + path, headers={"Authorization": "Bearer %s" % token},
                                 timeout=(10, 60), **kwargs)
            data = r.json()
        except (requests.RequestException, ValueError) as e:
            raise UserError(_("Cloudflare did not answer: %s", e)) from e
        if not data.get("success"):
            errors = "; ".join(str(x.get("message")) for x in data.get("errors") or []) or str(r.status_code)
            raise UserError(_("Cloudflare refused the call: %s", errors))
        return data.get("result")

    @api.model
    def zone(self):
        """The site's zone saved by Set up Cloudflare: {'id': ..., 'name': ...} (empty strings when not set)."""
        return {"id": _param(self.env, "zone_id"), "name": _param(self.env, "zone_name")}

    @api.model
    def purge(self, everything=False, urls=None, prefixes=None, hosts=None, zone_id=None, tags=None):
        """Empty Cloudflare's cache for the site's zone: everything, or the given URLs / URL prefixes / hosts /
        cache tags (2.0.1).

        URLs are sent 30 a request, prefixes, hosts and tags 100 a request; a rate-limited request (429) waits and is
        tried again. A prefix is a host and a path without a scheme or query string (``www.example.com/blog``: that
        address and everything under it, whatever its query string or cache key). It never raises (a purge must not
        break the save that asked for it): returns {'ok': bool, 'requests': int, 'error': str}.
        """
        if not self.env.su and not self.env.user.has_group("base.group_system"):
            return {"ok": False, "requests": 0, "error": _("Only administrators (or the system) can purge the cache.")}
        zone, token = zone_id or _param(self.env, "zone_id"), _param(self.env, "api_token")
        if not (zone and token):
            return {"ok": False, "requests": 0,
                    "error": _("No Cloudflare zone or cache-purge token yet: Settings › Cloudflare › Set up Cloudflare.")}
        if everything:
            bodies = [{"purge_everything": True}]
        else:
            bodies = []
            for key, items in (("files", urls), ("prefixes", prefixes), ("hosts", hosts), ("tags", tags)):
                items = [x for x in (items or []) if x]
                size = PURGE_BATCH if key == "files" else PURGE_BATCH_OTHER
                bodies += [{key: items[i:i + size]} for i in range(0, len(items), size)]
        sent = 0
        for body in bodies:
            for attempt in range(PURGE_TRIES):
                try:
                    res = requests.post(API + "/zones/%s/purge_cache" % zone, json=body, timeout=PURGE_TIMEOUT,
                                        headers={"Authorization": "Bearer %s" % token})
                    data = res.json()
                except (requests.RequestException, ValueError) as e:
                    return {"ok": False, "requests": sent, "error": _("Cloudflare could not be reached: %s", e)}
                sent += 1
                if res.status_code == 429 and attempt < PURGE_TRIES - 1:
                    try:
                        wait = float(res.headers.get("Retry-After") or 2 ** attempt)
                    except (TypeError, ValueError):
                        wait = 2 ** attempt
                    time.sleep(min(max(wait, 1), 10))
                    continue
                break
            if not data.get("success"):
                errors = "; ".join(str(e.get("message") or e) for e in data.get("errors") or []) \
                    or str(res.status_code)
                return {"ok": False, "requests": sent, "error": _("Cloudflare refused: %s", errors)}
        return {"ok": True, "requests": sent, "error": ""}

    @api.model
    def verify_token(self):
        """Account tokens verify under the account, user tokens under /user: try both."""
        account = _param(self.env, "account_id")
        try:
            return self.call("GET", "/accounts/%s/tokens/verify" % account) if account else self.call(
                "GET", "/user/tokens/verify")
        except UserError:
            return self.call("GET", "/user/tokens/verify")


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    cloudflare_account_id = fields.Char("Cloudflare account ID", config_parameter=P + "account_id")
    cloudflare_api_token = fields.Char("API token", config_parameter=P + "api_token", groups="base.group_system")
    cloudflare_r2_access_key_id = fields.Char("R2 access key ID", config_parameter=P + "r2_access_key_id",
                                              groups="base.group_system")
    cloudflare_r2_secret_access_key = fields.Char("R2 secret access key", config_parameter=P + "r2_secret_access_key",
                                                  groups="base.group_system")
    cloudflare_r2_bucket = fields.Char("R2 bucket", config_parameter=P + "r2_bucket")
    cloudflare_r2_endpoint = fields.Char(
        "R2 endpoint", config_parameter=P + "r2_endpoint",
        help="Leave empty for the account's endpoint (https://<account ID>.r2.cloudflarestorage.com). "
             "Only needed for a jurisdiction endpoint such as .eu.")
    cloudflare_zone_id = fields.Char("Zone ID", config_parameter=P + "zone_id")
    cloudflare_zone_name = fields.Char("Zone", config_parameter=P + "zone_name")
    cloudflare_status = fields.Char("Connection status", compute="_compute_cloudflare_status")
    # the photos bucket (1.6.0): made by Set up photos storage; shown, never typed
    cloudflare_photos_bucket = fields.Char("Photos bucket", compute="_compute_cloudflare_photos")
    cloudflare_photos_domain = fields.Char("Photos public address", compute="_compute_cloudflare_photos")

    def _compute_cloudflare_photos(self):
        bucket, domain = _param(self.env, "r2_photos_bucket"), _param(self.env, "r2_photos_domain")
        for rec in self:
            rec.cloudflare_photos_bucket = bucket
            rec.cloudflare_photos_domain = domain

    def action_cloudflare_check_photos(self):
        """Test photos storage: a write, a read and a delete in the photos bucket."""
        self.ensure_one()
        if not self.env["cloudflare.r2"].photos_configured():
            raise UserError(_("No photos bucket yet: press Set up photos storage."))
        try:
            self.env["cloudflare.r2"].photos_client().check()
        except (R2Error, UserError) as e:
            raise UserError(_("Photos storage check failed: %s", e)) from e
        return self._cloudflare_notify(_("Photos storage works: bucket %s accepted a write, a read and a delete.",
                                         _param(self.env, "r2_photos_bucket")))

    def _compute_cloudflare_status(self):
        status = self.env["ir.config_parameter"].sudo().get_param(P + "last_check") or _("Not checked yet")
        for rec in self:
            rec.cloudflare_status = status

    def _cloudflare_note(self, text):
        self.env["ir.config_parameter"].sudo().set_param(P + "last_check", "%s · %s" % (
            fields.Datetime.to_string(fields.Datetime.now()), text))

    def action_cloudflare_check_r2(self):
        self.ensure_one()
        self.execute()  # save what was typed first
        try:
            self.env["cloudflare.r2"].client().check()
        except (R2Error, UserError) as e:
            self._cloudflare_note(_("R2 failed: %s", e))
            raise UserError(_("R2 check failed: %s", e)) from e
        bucket = _param(self.env, "r2_bucket")
        self._cloudflare_note(_("R2 OK (bucket %s: write, read and delete)", bucket))
        return self._cloudflare_notify(_("R2 works: bucket %s accepted a write, a read and a delete.", bucket))

    def action_cloudflare_check_token(self):
        self.ensure_one()
        self.execute()
        try:
            result = self.env["cloudflare.api"].verify_token() or {}
        except UserError as e:
            self._cloudflare_note(_("API token failed: %s", e))
            raise
        state = result.get("status") or "active"
        self._cloudflare_note(_("API token %s", state))
        return self._cloudflare_notify(_("The Cloudflare API token is %s.", state))

    def _cloudflare_notify(self, message):
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"title": _("Cloudflare"), "message": message, "type": "success", "sticky": False,
                           "next": {"type": "ir.actions.client", "tag": "reload"}}}
