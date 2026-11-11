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
PURGE_BATCH = 30      # URLs (or prefixes, hosts) per purge request: the smallest limit across Cloudflare plans
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

    # Shortcuts for the common calls (each returns what the client returns).
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
    def list_objects(self, prefix="", bucket=None):
        return self.client(bucket).list(prefix)

    @api.model
    def stat(self, key, bucket=None):
        return self.client(bucket).head(key)

    @api.model
    def remove(self, key, bucket=None):
        return self.client(bucket).delete(key)

    @api.model
    def download_url(self, key, expires=3600, filename=None, bucket=None):
        """A private, short-lived download link (signed; the bucket stays private). Administrators only."""
        return self.client(bucket).presign_get(key, expires, filename)


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
    def purge(self, everything=False, urls=None, prefixes=None, hosts=None, zone_id=None):
        """Empty Cloudflare's cache for the site's zone: everything, or the given URLs / URL prefixes / hosts.

        Lists are sent in batches of 30; a rate-limited request (429) waits and is tried again. It never raises (a
        purge must not break the save that asked for it): returns {'ok': bool, 'requests': int, 'error': str}.
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
            for key, items in (("files", urls), ("prefixes", prefixes), ("hosts", hosts)):
                items = [x for x in (items or []) if x]
                bodies += [{key: items[i:i + PURGE_BATCH]} for i in range(0, len(items), PURGE_BATCH)]
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
