"""Set up Cloudflare from Odoo: one setup token in, narrow keys out, one step at a time.

The administrator creates ONE setup token on the Cloudflare dashboard (a pre-filled link) and pastes it. The wizard
then walks through the choices (owner, 2026-11-11: "it should guide creation of bucket for R2"):

* Connect: the token is checked; the account, its R2 buckets and its zones are read (R2 turned off on the account:
  the wizard says so, with the link that turns it on).
* Bucket: a new bucket (name, location, lock, each explained, with the price) or one of the account's buckets.
* Website cache: the zone whose cache Odoo may purge (or none).
* Review, then Set up, which:

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


BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
R2_OFF_CODES = ("10042",)  # "Please enable R2 through the Cloudflare Dashboard"
LOCATIONS = [("enam", "Eastern North America (closest to a server in Miami or New York)"),
             ("wnam", "Western North America"), ("weur", "Western Europe"), ("eeur", "Eastern Europe"),
             ("apac", "Asia-Pacific"), ("oc", "Oceania")]
STEPS = [("connect", "Connect"), ("bucket", "Bucket"), ("cache", "Website cache"), ("review", "Review"),
         ("done", "Done")]


def r2_dashboard_url(account):
    return "https://dash.cloudflare.com/%s/r2/overview" % account


def _bucket_slug(text):
    slug = re.sub(r"[^a-z0-9-]+", "-", (text or "").lower()).strip("-")
    return re.sub(r"-{2,}", "-", slug)[:63] or "odoo"


class CloudflareSetupChoice(models.TransientModel):
    """One account, bucket or zone the setup token sees (what the wizard offers to pick from)."""
    _name = "cloudflare.setup.choice"
    _description = "Cloudflare setup: account, bucket or zone"
    _order = "sequence, name"

    wizard_id = fields.Many2one("cloudflare.setup.wizard", required=True, ondelete="cascade")
    kind = fields.Selection([("account", "Account"), ("bucket", "Bucket"), ("zone", "Zone")], required=True)
    key = fields.Char(required=True)
    name = fields.Char(required=True)
    info = fields.Char()
    sequence = fields.Integer(default=10)

    @api.depends("name", "info")
    def _compute_display_name(self):
        for choice in self:
            choice.display_name = "%s (%s)" % (choice.name, choice.info) if choice.info else choice.name


class CloudflareSetupWizard(models.TransientModel):
    _name = "cloudflare.setup.wizard"
    _description = "Set up Cloudflare from Odoo"

    step = fields.Selection(STEPS, default="connect", required=True)
    setup_token = fields.Char(
        "Setup token",
        help="Made with the Create the token on Cloudflare button (the permissions come filled in). It is used "
             "for this setup only and deleted in Cloudflare at the end.")
    choice_ids = fields.One2many("cloudflare.setup.choice", "wizard_id")
    account_choice_id = fields.Many2one("cloudflare.setup.choice", "Account",
                                        domain="[('wizard_id', '=', id), ('kind', '=', 'account')]")
    account_count = fields.Integer(compute="_compute_counts")
    account_id = fields.Char("Account ID", help="Filled in when the token is checked.")
    account_name = fields.Char(readonly=True)
    r2_enabled = fields.Boolean(readonly=True)
    r2_url = fields.Char(compute="_compute_r2_url")

    bucket_mode = fields.Selection([("new", "Create a new bucket"), ("existing", "Use a bucket that already exists")],
                                   "Bucket", default="new", required=True)
    bucket_name = fields.Char("New bucket name", default=lambda self: self._default_bucket())
    bucket_choice_id = fields.Many2one("cloudflare.setup.choice", "Existing bucket",
                                       domain="[('wizard_id', '=', id), ('kind', '=', 'bucket')]")
    bucket_count = fields.Integer(compute="_compute_counts")
    bucket_name_taken = fields.Boolean(compute="_compute_bucket_name_taken")
    lock_days = fields.Integer("Keep every file at least (days)", default=7,
                               help="Bucket lock: nothing under the locked folders can be deleted or overwritten "
                                    "before this age, not even with the bucket's key. 0 = no lock.")
    lock_prefixes = fields.Char("Locked folders", default="snapshots/ files/",
                                help="Folders of the bucket the lock covers, separated by spaces (the connection test "
                                     "writes and deletes a file outside them).")
    location_hint = fields.Selection(LOCATIONS, string="Location", default="enam",
                                     help="Where Cloudflare keeps the bucket. Pick the one closest to the server: "
                                          "backups go up and come back faster. It cannot be changed later.")

    create_purge_token = fields.Boolean("Let Odoo clear this site's cache on Cloudflare", default=True,
                                        help="A key that can only purge the cache of the chosen zone (Edge Cache "
                                             "uses it when a page changes).")
    zone_choice_id = fields.Many2one("cloudflare.setup.choice", "Website (zone)",
                                     domain="[('wizard_id', '=', id), ('kind', '=', 'zone')]")
    zone_count = fields.Integer(compute="_compute_counts")
    zone_name = fields.Char("Zone", default=lambda self: self._default_zone())
    delete_setup_token = fields.Boolean("Delete the setup token in Cloudflare when done", default=True)
    summary = fields.Text(compute="_compute_summary")
    log = fields.Text(readonly=True)
    done = fields.Boolean(readonly=True)

    # ------------------------------------------------------------------ defaults and computes
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

    @api.depends("choice_ids")
    def _compute_counts(self):
        for wiz in self:
            kinds = wiz.choice_ids.mapped("kind")
            wiz.account_count, wiz.bucket_count, wiz.zone_count = (kinds.count(k) for k in ("account", "bucket", "zone"))

    @api.depends("account_id")
    def _compute_r2_url(self):
        for wiz in self:
            wiz.r2_url = r2_dashboard_url(wiz.account_id) if wiz.account_id else "https://dash.cloudflare.com/"

    @api.depends("bucket_name", "choice_ids")
    def _compute_bucket_name_taken(self):
        for wiz in self:
            name = _bucket_slug(wiz.bucket_name)
            wiz.bucket_name_taken = bool(wiz.choice_ids.filtered(lambda c: c.kind == "bucket" and c.key == name))

    @api.depends("bucket_mode", "bucket_name", "bucket_choice_id", "lock_days", "lock_prefixes", "location_hint",
                 "create_purge_token", "zone_choice_id", "account_name", "delete_setup_token")
    def _compute_summary(self):
        locations = dict(LOCATIONS)
        for wiz in self:
            lines = [_("Account: %s", wiz.account_name or wiz.account_id or "-")]
            if wiz.bucket_mode == "existing":
                lines.append(_("Use the bucket %s", wiz.bucket_choice_id.name or "-"))
            else:
                lines.append(_("Create the bucket %(name)s in %(where)s", name=_bucket_slug(wiz.bucket_name),
                               where=locations.get(wiz.location_hint, wiz.location_hint)))
            if wiz.lock_days > 0 and (wiz.lock_prefixes or "").split():
                lines.append(_("Lock: files in %(folders)s cannot be deleted for %(days)s days",
                               folders=wiz.lock_prefixes, days=wiz.lock_days))
            else:
                lines.append(_("No lock"))
            lines.append(_("Make this site's own R2 key, limited to that bucket, and test it"))
            if wiz.create_purge_token and wiz.zone_choice_id:
                lines.append(_("Make a key that can only clear the cache of %s", wiz.zone_choice_id.name))
            else:
                lines.append(_("No cache key"))
            if wiz.delete_setup_token:
                lines.append(_("Delete the setup token in Cloudflare"))
            wiz.summary = "\n".join("• " + line for line in lines)

    def _reopen(self):
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
                "target": "new", "name": _("Set up Cloudflare")}

    def _check_admin(self):
        if not self.env.user.has_group("base.group_system"):
            raise UserError(_("Only administrators can set up Cloudflare."))

    def action_open_dashboard(self):
        return {"type": "ir.actions.act_url", "url": setup_token_url(), "target": "new"}

    def action_open_r2(self):
        self.ensure_one()
        return {"type": "ir.actions.act_url", "url": self.r2_url, "target": "new"}

    # ------------------------------------------------------------------ step 1: connect
    def action_connect(self):
        """Check the token and read what it sees: its accounts, then (one account) the buckets and zones."""
        self.ensure_one()
        self._check_admin()
        token = (self.setup_token or "").strip()
        if not token:
            raise UserError(_("Paste the setup token first."))
        if self.account_choice_id:
            account, name = self.account_choice_id.key, self.account_choice_id.name
        else:
            accounts = _need(_cf("GET", "/accounts", token, params={"per_page": 50}),
                             _("Checking the token")) or []
            if not accounts:
                raise UserError(_("The token sees no Cloudflare account: create it again with the button above."))
            self.choice_ids.unlink()
            Choice = self.env["cloudflare.setup.choice"]
            for a in accounts:
                Choice.create({"wizard_id": self.id, "kind": "account", "key": a["id"], "name": a.get("name") or a["id"]})
            if len(accounts) > 1:
                return self._reopen()  # the user picks the account, then Next again
            account, name = accounts[0]["id"], accounts[0].get("name") or accounts[0]["id"]
        self.choice_ids.filtered(lambda c: c.kind != "account").unlink()
        self.write({"account_id": account, "account_name": name})
        self._read_buckets(token)
        self._read_zones(token)
        if not self.r2_enabled:
            return self._reopen()  # the page says how to turn R2 on; Next again checks again
        self.step = "bucket"
        return self._reopen()

    def _read_buckets(self, token):
        ok, result, errors, status = _cf("GET", "/accounts/%s/r2/buckets" % self.account_id, token,
                                         params={"per_page": 1000})
        if not ok:
            if any(code in (errors or "") for code in R2_OFF_CODES):
                self.r2_enabled = False
                return
            raise UserError(_("Reading the R2 buckets failed: %s", errors or status))
        self.r2_enabled = True
        buckets = (result or {}).get("buckets", []) if isinstance(result, dict) else (result or [])
        Choice = self.env["cloudflare.setup.choice"]
        locations = {k: v.split(" (")[0] for k, v in LOCATIONS}
        for b in buckets:
            where = locations.get((b.get("location") or "").lower(), b.get("location") or "")
            made = (b.get("creation_date") or "")[:10]
            Choice.create({"wizard_id": self.id, "kind": "bucket", "key": b["name"], "name": b["name"],
                           "info": ", ".join(x for x in (where, made and _("made %s", made)) if x)})
        if self.bucket_name and self.bucket_name_taken and self.bucket_mode == "new":
            # the default name exists already (a second run): offer it as the existing bucket
            self.bucket_mode = "existing"
            self.bucket_choice_id = self.choice_ids.filtered(
                lambda c: c.kind == "bucket" and c.key == _bucket_slug(self.bucket_name))[:1]

    def _read_zones(self, token):
        ok, result, _errors, _status = _cf("GET", "/zones", token, params={"account.id": self.account_id,
                                                                            "per_page": 50})
        Choice = self.env["cloudflare.setup.choice"]
        wanted = (self.zone_name or "").strip().lower()
        for z in (result or []) if ok else []:
            Choice.create({"wizard_id": self.id, "kind": "zone", "key": z["id"], "name": z["name"],
                           "sequence": 1 if z["name"].lower() == wanted else 10})
        zones = self.choice_ids.filtered(lambda c: c.kind == "zone")
        self.zone_choice_id = zones.filtered(lambda c: c.name.lower() == wanted)[:1] or (zones[:1] if len(zones) == 1
                                                                                          else False)
        if not zones:
            self.create_purge_token = False

    # ------------------------------------------------------------------ steps 2-4
    def action_bucket_next(self):
        self.ensure_one()
        if self.bucket_mode == "existing":
            if not self.bucket_choice_id:
                raise UserError(_("Pick the bucket to use."))
        else:
            name = (self.bucket_name or "").strip().lower()
            if not BUCKET_RE.match(name) or "--" in name:
                raise UserError(_("A bucket name has 3 to 63 characters: lowercase letters, digits and single hyphens, "
                                  "starting and ending with a letter or digit."))
            if self.bucket_name_taken:
                raise UserError(_("The account has a bucket named %s already: pick it under \"Use a bucket that "
                                  "already exists\", or choose another name.", name))
            self.bucket_name = name
        if self.lock_days < 0:
            raise UserError(_("The lock cannot be negative (0 = no lock)."))
        self.step = "cache"
        return self._reopen()

    def action_cache_next(self):
        self.ensure_one()
        if self.create_purge_token and not self.zone_choice_id:
            raise UserError(_("Pick the website, or untick the cache key."))
        self.step = "review"
        return self._reopen()

    def action_back(self):
        self.ensure_one()
        order = [s for s, _label in STEPS]
        self.step = order[max(0, order.index(self.step) - 1)]
        return self._reopen()

    # ------------------------------------------------------------------ the run
    def action_run(self):
        self.ensure_one()
        self._check_admin()
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
            self.write({"setup_token": False, "log": "\n".join(lines), "done": ok, "step": "done"})
        return self._reopen()

    def _run(self, token, note):
        ICP = self.env["ir.config_parameter"].sudo()
        existing = self.bucket_mode == "existing" and self.bucket_choice_id
        bucket = self.bucket_choice_id.key if existing else _bucket_slug(self.bucket_name)

        # 1. the account
        account = (self.account_id or "").strip()
        if not account:
            accounts = _need(_cf("GET", "/accounts", token, params={"per_page": 50}), _("Finding the account")) or []
            if len(accounts) != 1:
                raise UserError(_("The token sees %(n)s accounts (%(names)s): pick the account.",
                                  n=len(accounts), names=", ".join(a.get("name", "?") for a in accounts) or "-"))
            account = accounts[0]["id"]
        note(_("✓ Account %s", self.account_name or account))

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
        keep_lock = False
        if existing:
            note(_("✓ Bucket %s (already there)", bucket))
            ok, current, _err, _st = _cf("GET", "/accounts/%s/r2/buckets/%s/lock" % (account, bucket), token)
            rules = (current or {}).get("rules") if ok and isinstance(current, dict) else None
            if rules:
                keep_lock = True  # its own lock rules stay as they are (another tool may rely on them)
                note(_("✓ Bucket lock kept as it is (%s rules)", len(rules)))
        else:
            ok, _res, errors, status = _cf("POST", "/accounts/%s/r2/buckets" % account, token,
                                           json={"name": bucket, "locationHint": self.location_hint or "enam",
                                                 "storageClass": "Standard"})
            if ok:
                note(_("✓ Bucket %s created", bucket))
            else:
                exists = _cf("GET", "/accounts/%s/r2/buckets/%s" % (account, bucket), token)
                if not exists[0]:
                    if any(code in (errors or "") for code in R2_OFF_CODES):
                        raise UserError(_("R2 is not turned on for this account: open R2 on the Cloudflare dashboard "
                                          "(%s), turn it on, then run the setup again.", r2_dashboard_url(account)))
                    raise UserError(_("Creating bucket %(b)s failed: %(e)s", b=bucket, e=errors or status))
                note(_("✓ Bucket %s already exists: kept", bucket))
        prefixes = (self.lock_prefixes or "").split()
        if not keep_lock and self.lock_days > 0 and prefixes:
            _need(_cf("PUT", "/accounts/%s/r2/buckets/%s/lock" % (account, bucket), token, json={"rules": [{
                "id": ("keep-%sd-%s" % (self.lock_days, _bucket_slug(prefix)))[:60], "enabled": True,
                "prefix": prefix, "condition": {"type": "Age", "maxAgeSeconds": int(self.lock_days) * 86400},
            } for prefix in prefixes]}), _("Setting the bucket lock"))
            note(_("✓ Bucket lock: %(folders)s kept at least %(days)s days", folders=" ".join(prefixes),
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
        note(_("✓ R2 key created, limited to bucket %s (object read and write)", bucket))

        # 5. cache-purge token for the chosen zone
        zone_id = self.zone_choice_id.key if self.zone_choice_id else False
        zone_name = self.zone_choice_id.name if self.zone_choice_id else (self.zone_name or "").strip()
        if self.create_purge_token and not zone_id and zone_name:
            zones = _need(_cf("GET", "/zones", token, params={"name": zone_name, "account.id": account}),
                          _("Finding zone %s", zone_name)) or []
            if not zones:
                raise UserError(_("Zone %s is not in this Cloudflare account.", zone_name))
            zone_id, zone_name = zones[0]["id"], zones[0]["name"]
        if self.create_purge_token and zone_id:
            purge = _need(_cf("POST", "/accounts/%s/tokens" % account, token, json={
                "name": ("%s · cache purge (Odoo)" % zone_name)[:120],
                "policies": [{"effect": "allow", "permission_groups": [{"id": group(PG_CACHE_PURGE)}],
                              "resources": {"com.cloudflare.api.account.zone.%s" % zone_id: "*"}}],
            }), _("Creating the cache-purge token"))
            ICP.set_param(P + "zone_id", zone_id)
            ICP.set_param(P + "zone_name", zone_name)
            ICP.set_param(P + "api_token", purge["value"])
            ICP.set_param(P + "api_token_id", purge["id"])
            note(_("✓ Cache key created for %s", zone_name))

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
        note(_("✓ R2 test passed: write, read back, delete"))
        ICP.set_param(P + "last_check", "%s · %s" % (fields.Datetime.to_string(fields.Datetime.now()),
                                                     _("Set up from Odoo; R2 OK (bucket %s)", bucket)))

        # an earlier R2 key made by this wizard is replaced: revoke it
        if old_r2_id and old_r2_id != r2_token["id"]:
            if _cf("DELETE", "/accounts/%s/tokens/%s" % (account, old_r2_id), token)[0]:
                note(_("✓ The previous R2 key was revoked"))

        # 7. the setup token goes
        if self.delete_setup_token:
            path = ("/accounts/%s/tokens/%s" % (account, setup_token_id)) if setup_is_account \
                else "/user/tokens/%s" % setup_token_id
            ok, _res, errors, _st = _cf("DELETE", path, token)
            note(_("✓ Setup token deleted in Cloudflare") if ok else
                 _("Could not delete the setup token (%s): delete it on the Cloudflare dashboard.", errors))
