"""The photo server connection: its token, the office addresses, album links, the last call-in.

The token is made here (``_new_token``: shown once, its SHA-256 kept), and every call of the photo server is checked
with ``_check_bearer(request)``: the stored hash is read with a fresh query, never Odoo's parameter cache, so a new
token takes effect at once in every worker; the comparison is constant time. A good call records when the server last
called in (at most once a minute, without clearing any cache), which the setup wizard's last step shows."""
import hashlib
import hmac
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

P = "immich_connector."
TOKEN = P + "nas_token_hash"
LAST_SEEN = P + "last_seen"
SEEN_EVERY = timedelta(minutes=1)


def token_hash(token):
    return hashlib.sha256((token or "").encode()).hexdigest()


def _fresh(env, key):
    """A parameter read straight from the table (not the cached get_param; this transaction's own changes first)."""
    env["ir.config_parameter"].flush_model(["key", "value"])
    env.cr.execute("SELECT value FROM ir_config_parameter WHERE key = %s", [key])
    row = env.cr.fetchone()
    return (row[0] if row else "") or ""


class ImmichConnector(models.AbstractModel):
    _name = "immich.connector"
    _description = "Immich photo server connection"

    # ------------------------------------------------------------------ settings
    @api.model
    def _param(self, name):
        return (self.env["ir.config_parameter"].sudo().get_param(P + name) or "").strip()

    @api.model
    def _upload_url(self):
        """The office upload page (the photo server's, on the office network), no trailing slash; '' when unset."""
        return self._param("upload_url").rstrip("/")

    @api.model
    def _wifi_name(self):
        return self._param("wifi_name")

    @api.model
    def _immich_url(self):
        """Immich's address (office network, or the internet in public mode), no trailing slash."""
        return self._param("immich_url").rstrip("/")

    @api.model
    def _album_url(self, album_id):
        base = self._immich_url()
        return "%s/albums/%s" % (base, album_id) if base and album_id else ""

    @api.model
    def _public_mode(self):
        """Immich is reachable from the internet and an API key is set: albums can be made from here."""
        return self._param("public_mode") in ("1", "True", "true") and bool(self._immich_url()) \
            and bool(self._param("api_key"))

    @api.model
    def _client(self):
        """The Immich client (public mode only), else UserError."""
        from .client import ImmichClient
        if not self._public_mode():
            raise UserError(_("Immich is not reachable from the internet in the settings (Settings › Immich)."))
        return ImmichClient(self._immich_url(), self._param("api_key"))

    # ------------------------------------------------------------------ the token
    @api.model
    def _new_token(self):
        """A new photo server token (the old one stops working): returned once, only its hash kept."""
        if not self.env.su and not self.env.user.has_group("base.group_system"):
            raise AccessError(_("Only an administrator makes the photo server's token."))
        token = secrets.token_urlsafe(32)
        self.env["ir.config_parameter"].sudo().set_param(TOKEN, token_hash(token))
        return token

    @api.model
    def _has_token(self):
        return bool(_fresh(self.env, TOKEN))

    @api.model
    def _check_token(self, token):
        stored = _fresh(self.env, TOKEN)
        return bool(stored and token) and hmac.compare_digest(token_hash(token), stored)

    @api.model
    def _check_bearer(self, request):
        """The request's ``Authorization: Bearer <token>`` (an Odoo request, or a header string): True when it is the
        photo server's token (then its call-in is recorded)."""
        header = request if isinstance(request, str) else request.httprequest.headers.get("Authorization", "")
        if not header or not header.startswith("Bearer "):
            return False
        if not self._check_token(header[7:].strip()):
            return False
        self._mark_seen()
        return True

    @api.model
    def _mark_seen(self):
        """When the photo server last called in: kept with a direct write (no cache cleared), at most once a minute."""
        if getattr(self.env.cr, "readonly", False):
            return  # (a read-only request: the next call records it)
        now = fields.Datetime.now()
        last = self._last_seen()
        if last and now - last < SEEN_EVERY:
            return
        value = fields.Datetime.to_string(now)
        self.env.cr.execute("UPDATE ir_config_parameter SET value = %s WHERE key = %s", [value, LAST_SEEN])
        if not self.env.cr.rowcount:
            self.env.cr.execute(
                "INSERT INTO ir_config_parameter (key, value, create_uid, write_uid, create_date, write_date) "
                "VALUES (%s, %s, 1, 1, now() at time zone 'UTC', now() at time zone 'UTC') "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", [LAST_SEEN, value])

    @api.model
    def _last_seen(self):
        value = _fresh(self.env, LAST_SEEN)
        return fields.Datetime.to_datetime(value) if value else None


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    immich_upload_url = fields.Char("Office upload page URL", config_parameter=P + "upload_url",
                                    help="The photo server's upload page on the office network")
    immich_wifi_name = fields.Char("Office wifi name", config_parameter=P + "wifi_name",
                                   help="Staff are told to connect to this wifi before uploading at the office")
    immich_url = fields.Char("Immich URL", config_parameter=P + "immich_url",
                             help="Immich's address (on the office network), for album links: <this>/albums/<id>")
    immich_public_mode = fields.Boolean("Immich reachable from the internet", config_parameter=P + "public_mode",
                                        help="Odoo can reach Immich itself (an API key below): albums are made from "
                                             "here at once instead of waiting for the photo server")
    immich_api_key = fields.Char("Immich API key", config_parameter=P + "api_key", groups="base.group_system")
    immich_token_set = fields.Boolean("Photo server token set", compute="_compute_immich_status")
    immich_last_seen = fields.Datetime("Photo server last called in", compute="_compute_immich_status")

    def _compute_immich_status(self):
        Connector = self.env["immich.connector"].sudo()
        token, seen = Connector._has_token(), Connector._last_seen()
        for settings in self:
            settings.immich_token_set = token
            settings.immich_last_seen = seen

    def action_immich_new_token(self):
        """A new photo server token, shown once (a notification that stays)."""
        token = self.env["immich.connector"]._new_token()
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {
            "title": _("New photo server token (shown once: copy it now)"), "message": token, "sticky": True,
            "type": "warning"}}

    def action_immich_test(self):
        """Test connection (public mode): Immich answers with the key."""
        self.execute()  # the values typed in, saved first
        try:
            info = self.env["immich.connector"].sudo()._client().ping()
        except Exception as error:  # noqa: BLE001 - said to the administrator
            raise UserError(_("Immich did not answer: %s", error)) from error
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {
            "title": _("Immich"), "message": _("Connected (Immich %s).", info.get("version") or "?"),
            "type": "success"}}
