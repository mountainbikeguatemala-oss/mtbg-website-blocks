"""Set up Cloudflare from Odoo: one setup token in, narrow keys out.

The administrator creates ONE setup token on the Cloudflare dashboard and pastes it here. With it, the wizard:

1. finds the account the token belongs to,
2. creates this site's R2 bucket (or keeps it if it exists) and its bucket lock (objects kept N days),
3. creates an account-owned token limited to that bucket (object read and write) and saves it as the R2 key
   (access key ID = the token's id, secret = SHA-256 of its value: how Cloudflare derives S3 credentials),
4. optionally creates a token limited to purging this site's zone cache and saves it as the API token,
5. tests R2, and
6. deletes the setup token in Cloudflare, so the powerful key stops working although it passed through the site.

The setup token itself is never saved in the settings; the wizard row holding it is blanked when the run ends.
"""
import hashlib
import json
import logging
import re
import time
from urllib.parse import quote, urlencode, urlparse

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .connector import API, P
from .r2 import R2Client, R2Error

_logger = logging.getLogger(__name__)

# Permission group names (looked up by name through the live permission-groups endpoint).
PG_BUCKET_ITEM_WRITE = ("Workers R2 Storage Bucket Item Write",)
PG_CACHE_PURGE = ("Cache Purge",)

DASHBOARD_TOKENS = "https://dash.cloudflare.com/profile/api-tokens"
ACCOUNT_TOKENS = "https://dash.cloudflare.com/?to=/:account/api-tokens"
# Cloudflare "template URL": the Create Token page opens with these permissions already ticked
# (developers.cloudflare.com/fundamentals/api/how-to/account-owned-token-template/).
SETUP_TOKEN_PERMISSIONS = [{"key": "workers_r2", "type": "edit"}, {"key": "account_api_tokens", "type": "edit"},
                           {"key": "zone", "type": "read"}, {"key": "cache", "type": "purge"}]


def setup_token_url(name="Odoo setup (deleted after use)"):
    """The pre-filled Create Token link: the user only presses Review token › Create Token.

    An ACCOUNT-owned token (owner, 2026-11-10: a token made under My Profile could not delete itself, Cloudflare
    9109): its Account API Tokens Edit lets the wizard delete it at the end. Checked on the live dashboard: the
    account policy (R2, API tokens) and the zone policy (Zone Read, Cache Purge on all domains) come pre-filled; the
    dashboard asks which account when the login has several."""
    return ACCOUNT_TOKENS + "&" + urlencode({
        "permissionGroupKeys": json.dumps(SETUP_TOKEN_PERMISSIONS, separators=(",", ":")), "name": name},
        quote_via=quote)


def _cf(method, path, token, **kwargs):
    """One Cloudflare REST call with ``token``; returns (ok, result, errors, status)."""
    try:
        r = requests.request(method, API + path, headers={"Authorization": "Bearer %s" % token},
                             timeout=(10, 60), **kwargs)
        data = r.json()
    except (requests.RequestException, ValueError) as e:
        raise UserError(_("Cloudflare did not answer: %s", e)) from e
    errors = "; ".join("%s (%s)" % (e.get("message"), e.get("code")) for e in data.get("errors") or [])
    return bool(data.get("success")), data.get("result"), errors, r.status_code


def _need(ok_result_errors, what):
    ok, result, errors, status = ok_result_errors
    if not ok:
        raise UserError(_("%(what)s failed: %(errors)s", what=what, errors=errors or status))
    return result


def _bucket_slug(text):
    slug = re.sub(r"[^a-z0-9-]+", "-", (text or "").lower()).strip("-")
    return re.sub(r"-{2,}", "-", slug)[:63] or "odoo"


class CloudflareSetupWizard(models.TransientModel):
    _name = "cloudflare.setup.wizard"
    _description = "Set up Cloudflare from Odoo"

    setup_token = fields.Char(
        "Setup token",
        help="Made with the Create the token on Cloudflare button (the permissions come filled in). It is used "
             "once and deleted in Cloudflare at the end.")
    account_id = fields.Char("Account ID", help="Only needed when the token sees more than one account.")
    bucket_name = fields.Char("Bucket", default=lambda self: self._default_bucket(), required=True)
    lock_days = fields.Integer("Keep every file at least (days)", default=7,
                               help="Bucket lock: nothing under the locked folders can be deleted or overwritten "
                                    "before this age. 0 = no lock.")
    lock_prefixes = fields.Char("Locked folders", default="snapshots/ files/",
                                help="Folders of the bucket the lock covers, separated by spaces (the connection test "
                                     "writes and deletes a file outside them).")
    location_hint = fields.Selection([("enam", "Eastern North America"), ("wnam", "Western North America"),
                                      ("weur", "Western Europe"), ("eeur", "Eastern Europe"),
                                      ("apac", "Asia-Pacific"), ("oc", "Oceania")],
                                     string="Location", default="enam")
    create_purge_token = fields.Boolean("Also create a cache-purge token for this site's zone", default=True)
    zone_name = fields.Char("Zone", default=lambda self: self._default_zone())
    delete_setup_token = fields.Boolean("Delete the setup token in Cloudflare when done", default=True)
    log = fields.Text(readonly=True)
    done = fields.Boolean(readonly=True)

    @api.model
    def _site_host(self):
        url = self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
        return (urlparse(url).hostname or "").lower()

    @api.model
    def _default_zone(self):
        host = self._site_host()
        if not host or host == "localhost" or host.endswith(".localhost") or re.fullmatch(r"[\d.:\[\]]+", host):
            return ""  # a local or IP address has no Cloudflare zone
        parts = host.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else host

    @api.model
    def _default_bucket(self):
        saved = (self.env["ir.config_parameter"].sudo().get_param(P + "r2_bucket") or "").strip()
        if saved:
            return saved
        zone = self._default_zone().split(".")[0] or self.env.cr.dbname
        return _bucket_slug("%s-backups" % zone)

    def action_open_dashboard(self):
        return {"type": "ir.actions.act_url", "url": setup_token_url(), "target": "new"}

    # ------------------------------------------------------------------ the run
    def action_run(self):
        self.ensure_one()
        if not self.env.user.has_group("base.group_system"):
            raise UserError(_("Only administrators can set up Cloudflare."))
        token = (self.setup_token or "").strip()
        if not token:
            raise UserError(_("Paste the setup token first."))
        lines = []

        def note(text):
            lines.append(text)
            _logger.info("Cloudflare setup: %s", text)

        ok = False
        try:
            self._run(token, note)
            ok = True
        except UserError as e:
            # no raise: what was already created (bucket, saved keys) stays, and the log says where it stopped
            note(_("Stopped: %s", e.args[0] if e.args else e))
        finally:
            # the setup token never stays in the database, whatever happened
            self.write({"setup_token": False, "log": "\n".join(lines), "done": ok})
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
                "target": "new"}

    def _run(self, token, note):
        ICP = self.env["ir.config_parameter"].sudo()
        bucket = _bucket_slug(self.bucket_name)

        # 1. the account
        account = (self.account_id or "").strip()
        if not account:
            accounts = _need(_cf("GET", "/accounts", token, params={"per_page": 50}), _("Finding the account")) or []
            if len(accounts) != 1:
                raise UserError(_("The token sees %(n)s accounts (%(names)s): enter the Account ID.",
                                  n=len(accounts), names=", ".join(a.get("name", "?") for a in accounts) or "-"))
            account = accounts[0]["id"]
        note(_("Account %s", account))

        # the setup token's own id (to delete it at the end)
        ok, result, _err, _st = _cf("GET", "/accounts/%s/tokens/verify" % account, token)
        setup_token_id, setup_is_account = (result or {}).get("id"), True
        if not ok:
            ok, result, _err, _st = _cf("GET", "/user/tokens/verify", token)
            setup_token_id, setup_is_account = (result or {}).get("id"), False
        if not setup_token_id:
            raise UserError(_("The setup token is not valid (Cloudflare could not verify it)."))

        # 2. permission groups (looked up by name)
        groups = _need(_cf("GET", "/accounts/%s/tokens/permission_groups" % account, token,
                           params={"per_page": 1000}), _("Reading the permission groups")) or []
        by_name = {g.get("name"): g.get("id") for g in groups}

        def group(names):
            for n in names:
                if by_name.get(n):
                    return by_name[n]
            raise UserError(_("Cloudflare has no permission group named %s on this account.", " / ".join(names)))

        # 3. bucket + lock
        ok, _res, errors, status = _cf("POST", "/accounts/%s/r2/buckets" % account, token,
                                       json={"name": bucket, "locationHint": self.location_hint or "enam",
                                             "storageClass": "Standard"})
        if ok:
            note(_("Bucket %s created", bucket))
        else:
            exists = _cf("GET", "/accounts/%s/r2/buckets/%s" % (account, bucket), token)
            if not exists[0]:
                raise UserError(_("Creating bucket %(b)s failed: %(e)s", b=bucket, e=errors or status))
            note(_("Bucket %s already exists: kept", bucket))
        prefixes = (self.lock_prefixes or "").split()
        if self.lock_days > 0 and prefixes:
            _need(_cf("PUT", "/accounts/%s/r2/buckets/%s/lock" % (account, bucket), token, json={"rules": [{
                "id": ("keep-%sd-%s" % (self.lock_days, _bucket_slug(prefix)))[:60], "enabled": True,
                "prefix": prefix, "condition": {"type": "Age", "maxAgeSeconds": int(self.lock_days) * 86400},
            } for prefix in prefixes]}), _("Setting the bucket lock"))
            note(_("Bucket lock: %(folders)s kept at least %(days)s days", folders=" ".join(prefixes),
                   days=self.lock_days))

        # 4. the site's own R2 key, limited to its bucket
        host = self._site_host() or self.env.cr.dbname
        r2_token = _need(_cf("POST", "/accounts/%s/tokens" % account, token, json={
            "name": ("%s · R2 %s (Odoo)" % (host, bucket))[:120],
            "policies": [{"effect": "allow", "permission_groups": [{"id": group(PG_BUCKET_ITEM_WRITE)}],
                          "resources": {"com.cloudflare.edge.r2.bucket.%s_default_%s" % (account, bucket): "*"}}],
        }), _("Creating the R2 key"))
        old_r2_id = ICP.get_param(P + "r2_token_id")
        ICP.set_param(P + "account_id", account)
        ICP.set_param(P + "r2_bucket", bucket)
        ICP.set_param(P + "r2_access_key_id", r2_token["id"])
        ICP.set_param(P + "r2_secret_access_key", hashlib.sha256(r2_token["value"].encode()).hexdigest())
        ICP.set_param(P + "r2_token_id", r2_token["id"])
        note(_("R2 key created, limited to bucket %s (object read and write)", bucket))

        # 5. cache-purge token for the site's zone
        if self.create_purge_token and (self.zone_name or "").strip():
            zones = _need(_cf("GET", "/zones", token, params={"name": self.zone_name.strip(), "account.id": account}),
                          _("Finding zone %s", self.zone_name)) or []
            if not zones:
                raise UserError(_("Zone %s is not in this Cloudflare account.", self.zone_name))
            zone_id = zones[0]["id"]
            purge = _need(_cf("POST", "/accounts/%s/tokens" % account, token, json={
                "name": ("%s · cache purge (Odoo)" % zones[0]["name"])[:120],
                "policies": [{"effect": "allow", "permission_groups": [{"id": group(PG_CACHE_PURGE)}],
                              "resources": {"com.cloudflare.api.account.zone.%s" % zone_id: "*"}}],
            }), _("Creating the cache-purge token"))
            ICP.set_param(P + "zone_id", zone_id)
            ICP.set_param(P + "zone_name", zones[0]["name"])
            ICP.set_param(P + "api_token", purge["value"])
            ICP.set_param(P + "api_token_id", purge["id"])
            note(_("Cache-purge token created for zone %s", zones[0]["name"]))

        # 6. test R2 (a new token can take a few seconds to reach every Cloudflare location)
        client = R2Client(account, ICP.get_param(P + "r2_access_key_id"), ICP.get_param(P + "r2_secret_access_key"),
                          bucket)
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
            raise UserError(_("The new R2 key did not work yet: %s. Run the setup again in a minute.", last))
        note(_("R2 test passed: write, read back, delete"))
        ICP.set_param(P + "last_check", "%s · %s" % (fields.Datetime.to_string(fields.Datetime.now()),
                                                     _("Set up from Odoo; R2 OK (bucket %s)", bucket)))

        # an earlier R2 key made by this wizard is replaced: revoke it
        if old_r2_id and old_r2_id != r2_token["id"]:
            if _cf("DELETE", "/accounts/%s/tokens/%s" % (account, old_r2_id), token)[0]:
                note(_("The previous R2 key was revoked"))

        # 7. the setup token goes
        if self.delete_setup_token:
            path = ("/accounts/%s/tokens/%s" % (account, setup_token_id)) if setup_is_account \
                else "/user/tokens/%s" % setup_token_id
            ok, _res, errors, _st = _cf("DELETE", path, token)
            note(_("Setup token deleted in Cloudflare") if ok else
                 _("Could not delete the setup token (%s): delete it on the Cloudflare dashboard.", errors))
