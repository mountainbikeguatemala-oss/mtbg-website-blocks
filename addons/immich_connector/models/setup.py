"""Set up the photo server (Settings › Immich › Set up the photo server), one step at a time:

1. What is needed: a NAS (or any always-on computer) with Docker, Immich on it, and a storage bucket for the photos
   shown online (an R2 bucket through the Cloudflare connector).
2. The office network: the photo server's address, Immich's port, the upload page's port, the wifi name (saved).
3. The token: made here, shown once (a new one stops the old one).
4. The files: a zip with config.env (this site's address, the token, the bucket and the public address from the
   settings; every other secret blank, for the operator), docker-compose.yml, the sync service and README.md.
5. Check: waiting for the photo server to call in (its last call, recorded by the API).

The token is on the wizard's row only while it runs (it goes into the zip); Finish blanks it."""
import io
import os
import re
import zipfile

from odoo import _, api, fields, models
from odoo.exceptions import UserError

NAS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "nas")
STEPS = [("intro", "What you need"), ("network", "Office network"), ("token", "Token"), ("files", "Files"),
         ("check", "Check")]
ADDRESS_RE = re.compile(r"^[A-Za-z0-9.-]{1,253}$")
# left blank in config.env for the operator (owner, 2026-11-14): never filled from this site
SKIP_DIRS = ("__pycache__", "data", "work")
SECRETS = ("IMMICH_API_KEY", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "WATERMARK_PATH")


class ImmichSetupWizard(models.TransientModel):
    _name = "immich.setup.wizard"
    _description = "Set up the photo server"

    step = fields.Selection(STEPS, default="intro", required=True)
    lan_address = fields.Char("Photo server address", help="Its address on the office network, e.g. 192.168.1.20")
    immich_port = fields.Integer("Immich port", default=2283)
    upload_port = fields.Integer("Upload page port", default=8090)
    wifi_name = fields.Char("Office wifi name")
    token = fields.Char(readonly=True)
    last_seen = fields.Datetime("Last call-in", compute="_compute_last_seen")

    def _compute_last_seen(self):
        seen = self.env["immich.connector"].sudo()._last_seen()
        for wizard in self:
            wizard.last_seen = seen

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        Connector = self.env["immich.connector"].sudo()
        match = re.match(r"^https?://([^:/]+)(?::(\d+))?", Connector._immich_url() or "")
        if match:
            values.setdefault("lan_address", match.group(1))
            if match.group(2):
                values["immich_port"] = int(match.group(2))
        port = re.match(r"^https?://[^:/]+:(\d+)", Connector._upload_url() or "")
        if port:
            values["upload_port"] = int(port.group(1))
        values.setdefault("wifi_name", Connector._wifi_name())
        return values

    def _reopen(self):
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
                "target": "new", "name": _("Set up the photo server")}

    def _save_network(self):
        self.ensure_one()
        address = (self.lan_address or "").strip()
        if not ADDRESS_RE.match(address):
            raise UserError(_("Type the photo server's address on the office network, e.g. 192.168.1.20."))
        for port in (self.immich_port, self.upload_port):
            if not 0 < (port or 0) < 65536:
                raise UserError(_("A port is a number from 1 to 65535."))
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("immich_connector.immich_url", "http://%s:%d" % (address, self.immich_port))
        ICP.set_param("immich_connector.upload_url", "http://%s:%d" % (address, self.upload_port))
        ICP.set_param("immich_connector.wifi_name", (self.wifi_name or "").strip())

    def action_next(self):
        self.ensure_one()
        keys = [key for key, _label in STEPS]
        if self.step == "network":
            self._save_network()
        if self.step == "token" and not self.token:
            raise UserError(_("Make the token first."))
        self.step = keys[min(keys.index(self.step) + 1, len(keys) - 1)]
        return self._reopen()

    def action_back(self):
        self.ensure_one()
        keys = [key for key, _label in STEPS]
        self.step = keys[max(keys.index(self.step) - 1, 0)]
        return self._reopen()

    def action_token(self):
        self.ensure_one()
        self.token = self.env["immich.connector"]._new_token()
        return self._reopen()

    def action_download(self):
        self.ensure_one()
        return {"type": "ir.actions.act_url", "target": "self",
                "url": "/immich_connector/setup/%d/photo-server.zip" % self.id}

    def action_check(self):
        return self._reopen()

    def action_finish(self):
        self.write({"token": False})
        return {"type": "ir.actions.act_window_close"}

    # ------------------------------------------------------------------ the zip
    @api.model
    def _bundle_values(self):
        """config.env's values this site fills in ({NAME: value}): its address, the connector's settings, the photos'
        storage bucket (the Cloudflare connector's, when installed). Every secret but the token stays blank. Other
        modules add theirs (``super()`` then update), e.g. the photos' public address."""
        ICP = self.env["ir.config_parameter"].sudo()
        Connector = self.env["immich.connector"].sudo()
        port = re.match(r"^https?://[^:/]+:(\d+)", Connector._upload_url() or "")
        values = {
            "SITE_URL": (ICP.get_param("web.base.url") or "").rstrip("/"),
            "IMMICH_URL": Connector._immich_url(),
            "UPLOAD_PORT": port.group(1) if port else "",
            "R2_ACCOUNT_ID": ICP.get_param("cloudflare_connector.account_id") or "",
            "R2_BUCKET": ICP.get_param("cloudflare_connector.r2_bucket") or "",
            "PUBLIC_BASE_URL": "",
        }
        tz = ICP.get_param("immich_connector.timezone") or self.env.user.tz or ""
        if tz:
            values.update(TIMEZONE=tz, TZ=tz)
        return values

    def _config_env(self):
        """config.env from the service's config.env.example, its lines filled in (a value left empty keeps the
        example's), the token from this run; the secrets (keys, the watermark) stay as the example has them."""
        self.ensure_one()
        values = {k: v for k, v in self._bundle_values().items() if v}
        values["NAS_TOKEN"] = self.token or ""
        for secret in SECRETS:
            values.pop(secret, None)
        try:
            with open(os.path.join(NAS_DIR, "config.env.example"), encoding="utf-8") as example:
                lines = example.read().splitlines()
        except OSError:
            lines = []
        out, seen = [], set()
        for line in lines:
            name = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
            if name in SECRETS:
                out.append("%s=" % name)
            elif name in values:
                out.append("%s=%s" % (name, str(values[name]).replace("\n", " ")))
                seen.add(name)
            else:
                out.append(line)
        out += ["%s=%s" % (name, value) for name, value in values.items() if name not in seen]
        return "\n".join(out) + "\n"

    def _bundle(self):
        """The zip's bytes: config.env, then every file of data/nas (docker-compose.yml, the sync service,
        README.md)."""
        self.ensure_one()
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("photo-server/config.env", self._config_env())
            for root, dirs, files in os.walk(NAS_DIR):
                # as the service's .gitignore: never its local data, work files, caches or a config.env
                dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
                for name in sorted(files):
                    if name == "config.env" or name.endswith(".pyc"):
                        continue
                    path = os.path.join(root, name)
                    archive.write(path, "photo-server/" + os.path.relpath(path, NAS_DIR))
        return buffer.getvalue()
