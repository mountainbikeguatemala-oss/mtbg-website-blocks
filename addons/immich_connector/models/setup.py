"""Set up the photo server (Settings › Immich › Set up the photo server), one step at a time:

1. What is needed: a NAS (or any always-on computer) with Docker, Immich on it, and a storage bucket for the photos
   shown online (an R2 bucket through the Cloudflare connector).
2. The office network: the photo server's address, Immich's port, the upload page's port, the wifi name, and the
   secure office address (``nas.<domain>``) (saved).
3. Secure address (owner, 2026-11-16): phones upload from the Staff App (an https page) only to an https address, so
   the photo server gets one that works only on the office network: a public DNS record ``nas.<domain>`` -> its
   office address (DNS only; made here through Cloudflare when a token allows it, else shown to add by hand) and a
   real certificate (Let's Encrypt, DNS-01 with a Cloudflare token the owner types here, written into the zip only).
4. The token: made here, shown once (a new one stops the old one).
5. The files: a zip with config.env (this site's address, the token, the bucket and the public address from the
   settings; every other secret blank, for the operator), docker-compose.yml, the sync service, the https front
   (tls/: its own compose project, Caddy with the Cloudflare DNS module; tls/.env and tls/tls.env with the
   certificate's token, filled in) and README.md.
6. Check: waiting for the photo server to call in (its last call, recorded by the API), and the https check from a
   phone on the office wifi (``https://nas.<domain>/ping``). Finish saves the office upload page as the https
   address (``_office_base()``).

The token and the certificate's Cloudflare token are on the wizard's row only while it runs (they go into the zip);
Finish blanks them. Neither is ever logged or saved anywhere else."""
import io
import ipaddress
import os
import re
import socket
import zipfile
from urllib.parse import urlparse

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

NAS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "nas")
STEPS = [("intro", "What you need"), ("network", "Office network"), ("secure", "Secure address"), ("token", "Token"),
         ("files", "Files"), ("check", "Check")]
ADDRESS_RE = re.compile(r"^[A-Za-z0-9.-]{1,253}$")
DOMAIN_RE = re.compile(r"^(?=.{3,240}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
HOST_LABEL = "nas"
CF_API = "https://api.cloudflare.com/client/v4"
# left blank in config.env for the operator (owner, 2026-11-14): never filled from this site
SKIP_DIRS = ("__pycache__", "data", "work", "config")
SECRETS = ("IMMICH_API_KEY", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "WATERMARK_PATH")


def _upload_is_https(ICP):
    """The office upload page is already an https address (a finished secure setup)."""
    return (ICP.get_param("immich_connector.upload_url") or "").startswith("https://")


class ImmichSetupWizard(models.TransientModel):
    _name = "immich.setup.wizard"
    _description = "Set up the photo server"

    step = fields.Selection(STEPS, default="intro", required=True)
    lan_address = fields.Char("Photo server address", help="Its address on the office network, e.g. 192.168.1.20")
    immich_port = fields.Integer("Immich port", default=2283)
    upload_port = fields.Integer("Upload page port", default=8090)
    wifi_name = fields.Char("Office wifi name", help="Several networks (e.g. 2.4 GHz and 5 GHz behind the same router): "
                                                     "separate them with commas")
    nas_domain = fields.Char("Domain", help="A domain of yours on Cloudflare (e.g. your short-link domain). The secure "
                                            "office address is nas.<this domain>")
    nas_hostname = fields.Char("Secure office address", compute="_compute_nas_hostname")
    https_port = fields.Integer("HTTPS port", default=443,
                                help="The port the photo server answers https on. Keep 443 unless the NAS already uses "
                                     "it (then e.g. 8443: the address becomes https://nas.<domain>:8443)")
    dns_token = fields.Char("Cloudflare token for the certificate", copy=False,
                            help="A Cloudflare API token with Zone › DNS › Edit on this domain only. It goes into the "
                                 "zip's tls/tls.env and leaves this wizard on Finish")
    can_create_dns = fields.Boolean(compute="_compute_can_create_dns")
    dns_result = fields.Text(readonly=True)
    resolve_result = fields.Text(readonly=True)
    ping_url = fields.Char("Check address", compute="_compute_nas_hostname")
    token = fields.Char(readonly=True)
    last_seen = fields.Datetime("Last call-in", compute="_compute_last_seen")

    def _compute_last_seen(self):
        seen = self.env["immich.connector"].sudo()._last_seen()
        for wizard in self:
            wizard.last_seen = seen

    @api.depends("nas_domain", "https_port")
    def _compute_nas_hostname(self):
        for wizard in self:
            domain = self._clean_domain(wizard.nas_domain)
            wizard.nas_hostname = "%s.%s" % (HOST_LABEL, domain) if domain else False
            base = wizard._secure_base()
            wizard.ping_url = base + "/ping" if base else False

    @api.depends("dns_token")
    def _compute_can_create_dns(self):
        saved = "cloudflare.api" in self.env and bool(
            (self.env["ir.config_parameter"].sudo().get_param("cloudflare_connector.api_token") or "").strip())
        for wizard in self:
            wizard.can_create_dns = saved or bool((wizard.dns_token or "").strip())

    @api.model
    def _clean_domain(self, text):
        domain = re.sub(r"^https?://", "", (text or "").strip().lower()).split("/")[0].split(":")[0].strip(".")
        return re.sub(r"^%s\." % HOST_LABEL, "", domain)

    def _secure_base(self):
        """https://nas.<domain>[:port] for this run, '' without a domain."""
        self.ensure_one()
        domain = self._clean_domain(self.nas_domain)
        if not domain:
            return ""
        port = self.https_port or 443
        return "https://%s.%s%s" % (HOST_LABEL, domain, "" if port == 443 else ":%d" % port)

    @api.model
    def _default_domain(self):
        """The short-link domain when the suite has one, else the Cloudflare zone, else the website's domain."""
        ICP = self.env["ir.config_parameter"].sudo()
        for key in ("mtbg_tours.short_link_domain", "mtbg_tours.invoice_short_domain", "cloudflare_connector.zone_name"):
            domain = self._clean_domain(ICP.get_param(key))
            if domain and DOMAIN_RE.match(domain):
                return domain
        host = self._clean_domain(re.sub(r"^www\.", "", urlparse(ICP.get_param("web.base.url") or "").hostname or ""))
        return host if DOMAIN_RE.match(host or "") else ""

    @api.model
    def _site_origins(self):
        """The website's origins the Staff App runs on: https://www.<domain> and https://<domain> (or the address
        itself for a local or IP address)."""
        url = urlparse((self.env["ir.config_parameter"].sudo().get_param("web.base.url") or "").strip())
        host = (url.hostname or "").lower()
        if not host:
            return []
        bare = re.sub(r"^www\.", "", host)
        if not DOMAIN_RE.match(bare):
            return ["%s://%s" % (url.scheme or "http", url.netloc)]
        return ["https://www.%s" % bare, "https://%s" % bare]

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        Connector = self.env["immich.connector"].sudo()
        match = re.match(r"^https?://([^:/]+)(?::(\d+))?", Connector._immich_url() or "")
        if match:
            values.setdefault("lan_address", match.group(1))
            if match.group(2):
                values["immich_port"] = int(match.group(2))
        port = Connector._param("upload_port") or (re.match(r"^http://[^:/]+:(\d+)", Connector._upload_url() or "")
                                                     or [None, ""])[1]
        if port and port.isdigit():
            values["upload_port"] = int(port)
        values.setdefault("wifi_name", Connector._wifi_name())
        saved = Connector._param("nas_hostname")
        values.setdefault("nas_domain", self._clean_domain(saved) if saved else self._default_domain())
        if Connector._param("https_port").isdigit():
            values["https_port"] = int(Connector._param("https_port"))
        return values

    def _reopen(self):
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form",
                "target": "new", "name": _("Set up the photo server")}

    def _save_network(self):
        self.ensure_one()
        address = (self.lan_address or "").strip()
        if not ADDRESS_RE.match(address):
            raise UserError(_("Type the photo server's address on the office network, e.g. 192.168.1.20."))
        for port in (self.immich_port, self.upload_port, self.https_port):
            if not 0 < (port or 0) < 65536:
                raise UserError(_("A port is a number from 1 to 65535."))
        domain = self._clean_domain(self.nas_domain)
        if domain and not DOMAIN_RE.match(domain):
            raise UserError(_("Type a domain of yours for the secure office address, e.g. example.com."))
        if domain and not self._lan_ip(address):
            raise UserError(_("The secure office address needs the photo server's IP address on the office network "
                              "(e.g. 192.168.1.20), not a name."))
        self.nas_domain = domain
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("immich_connector.immich_url", "http://%s:%d" % (address, self.immich_port))
        ICP.set_param("immich_connector.upload_port", str(self.upload_port))
        ICP.set_param("immich_connector.nas_hostname", "%s.%s" % (HOST_LABEL, domain) if domain else "")
        ICP.set_param("immich_connector.https_port", str(self.https_port or 443))
        if not domain or not _upload_is_https(ICP):
            # http until Finish switches the upload page to the https address (a working https one stays as it is)
            ICP.set_param("immich_connector.upload_url", "http://%s:%d" % (address, self.upload_port))
        if not domain:
            ICP.set_param("immich_connector.office_base", "")
        ICP.set_param("immich_connector.wifi_name", ", ".join(
            n.strip() for n in (self.wifi_name or "").split(",") if n.strip()))

    @api.model
    def _lan_ip(self, address):
        """``address`` when it is an IPv4 address, else ''."""
        try:
            return str(ipaddress.IPv4Address((address or "").strip()))
        except ValueError:
            return ""

    def action_next(self):
        self.ensure_one()
        keys = [key for key, _label in STEPS]
        if self.step == "network":
            self._save_network()
        if self.step == "token" and not self.token:
            raise UserError(_("Make the token first."))
        if self.step == "secure" and not (self.dns_token or "").strip():
            raise UserError(_("Type the Cloudflare token for the certificate first (Zone › DNS › Edit on %s).",
                              self._clean_domain(self.nas_domain)))
        step = keys[min(keys.index(self.step) + 1, len(keys) - 1)]
        if step == "secure" and not self._clean_domain(self.nas_domain):
            step = "token"  # no secure address: uploads from the app keep going over the internet
        self.step = step
        return self._reopen()

    def action_back(self):
        self.ensure_one()
        keys = [key for key, _label in STEPS]
        step = keys[max(keys.index(self.step) - 1, 0)]
        if step == "secure" and not self._clean_domain(self.nas_domain):
            step = "network"
        self.step = step
        return self._reopen()

    # ------------------------------------------------------------------ the secure address
    def _cf(self, method, path, **kwargs):
        """A Cloudflare API call: with the token typed here when there is one, else through the Cloudflare
        connector (its saved token), when installed. Returns the call's ``result``; UserError on a refusal."""
        token = (self.dns_token or "").strip()
        if not token:
            if "cloudflare.api" not in self.env:
                raise UserError(_("Type the Cloudflare token below first, or add the record by hand."))
            return self.env["cloudflare.api"].sudo().call(method, path, **kwargs)
        try:
            r = requests.request(method, CF_API + path, headers={"Authorization": "Bearer %s" % token},
                                 timeout=(10, 30), **kwargs)
            data = r.json()
        except (requests.RequestException, ValueError) as error:
            raise UserError(_("Cloudflare did not answer: %s", error)) from error
        if not data.get("success"):
            errors = "; ".join(str(x.get("message")) for x in data.get("errors") or []) or str(r.status_code)
            raise UserError(_("Cloudflare refused the call: %s", errors))
        return data.get("result")

    def _zone_id(self, domain):
        """The Cloudflare zone holding ``domain`` (the domain itself or a parent)."""
        parts = domain.split(".")
        for i in range(len(parts) - 1):
            zones = self._cf("GET", "/zones", params={"name": ".".join(parts[i:])}) or []
            if zones:
                return zones[0]["id"]
        raise UserError(_("%s is not a domain of this Cloudflare account (or the token cannot see it).", domain))

    def _dns_record(self):
        """(name, ip) of the record this run needs."""
        self.ensure_one()
        ip = self._lan_ip(self.lan_address)
        if not (self.nas_hostname and ip):
            raise UserError(_("Go back to Office network: the photo server's IP address and a domain are needed."))
        return self.nas_hostname, ip

    def action_dns_create(self):
        """The DNS record nas.<domain> -> the photo server's office address (A, DNS only): made, corrected or left
        as it is."""
        self.ensure_one()
        name, ip = self._dns_record()
        try:
            zone = self._zone_id(self._clean_domain(self.nas_domain))
            body = {"type": "A", "name": name, "content": ip, "ttl": 1, "proxied": False,
                    "comment": "Photo server, office network only"}
            found = self._cf("GET", "/zones/%s/dns_records" % zone, params={"type": "A", "name": name}) or []
            if found and found[0].get("content") == ip and not found[0].get("proxied"):
                result = _("✓ The record is already there: %(name)s → %(ip)s (DNS only).", name=name, ip=ip)
            elif found:
                self._cf("PATCH", "/zones/%s/dns_records/%s" % (zone, found[0]["id"]), json=body)
                result = _("✓ Record corrected: %(name)s → %(ip)s (DNS only).", name=name, ip=ip)
            else:
                self._cf("POST", "/zones/%s/dns_records" % zone, json=body)
                result = _("✓ Record created: %(name)s → %(ip)s (DNS only).", name=name, ip=ip)
        except UserError as error:
            result = _("✗ %(error)s Add the record by hand (below).", error=error.args[0] if error.args else error)
        self.dns_result = result
        return self._reopen()

    def action_resolve(self):
        """From here (Odoo): the name must resolve to the photo server's office address. (The https check happens
        on a phone at the office, on the last step.)"""
        self.ensure_one()
        name, ip = self._dns_record()
        try:
            found = sorted({info[4][0] for info in socket.getaddrinfo(name, None, socket.AF_INET)})
        except (socket.gaierror, OSError, UnicodeError):
            found = []
        if not found:
            self.resolve_result = _("✗ %s is not found yet. A new record can take a few minutes; try again.", name)
        elif found == [ip]:
            self.resolve_result = _("✓ %(name)s → %(ip)s, the photo server.", name=name, ip=ip)
        else:
            self.resolve_result = _("✗ %(name)s → %(found)s, not the photo server (%(ip)s). Correct the record.",
                                    name=name, found=", ".join(found), ip=ip)
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
        """The secrets leave the wizard; with a secure address, the office upload page becomes its https address."""
        ICP = self.env["ir.config_parameter"].sudo()
        for wizard in self:
            base = wizard._secure_base()
            if base:
                ICP.set_param("immich_connector.office_base", base)
                ICP.set_param("immich_connector.upload_url", base)
        self.write({"token": False, "dns_token": False})
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
        upload_port = Connector._param("upload_port")
        if upload_port.isdigit():
            values["UPLOAD_PORT"] = upload_port
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

    @api.model
    def _tls_values(self):
        """tls/.env (the https front's own compose project): the secure office address, its port, the website
        origins allowed to call it (space-separated)."""
        Connector = self.env["immich.connector"].sudo()
        return {"NAS_HOSTNAME": Connector._param("nas_hostname"),
                "NAS_HTTPS_PORT": Connector._param("https_port") or "443",
                "SITE_ORIGINS": " ".join(self._site_origins())}

    def _tls_env(self):
        lines = ["# The https front (tls/): written by Set up the photo server. Start it from this folder with",
                 "#   docker compose up -d --build"]
        lines += ["%s=%s" % item for item in self._tls_values().items()]
        return "\n".join(lines) + "\n"

    def _tls_secret_env(self):
        """tls/tls.env: the Cloudflare token for the certificate (DNS-01), from this run only."""
        self.ensure_one()
        return ("# Cloudflare API token, Zone › DNS › Edit on the secure address's domain only (the certificate).\n"
                "# Keep this file private.\nCLOUDFLARE_API_TOKEN=%s\n" % (self.dns_token or "").strip().replace("\n", ""))

    def _bundle(self):
        """The zip's bytes: config.env, then every file of data/nas (docker-compose.yml, the sync service, the https
        front in tls/ with its .env and tls.env, README.md)."""
        self.ensure_one()
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("photo-server/config.env", self._config_env())
            if self.env["immich.connector"].sudo()._param("nas_hostname"):
                archive.writestr("photo-server/tls/.env", self._tls_env())
                archive.writestr("photo-server/tls/tls.env", self._tls_secret_env())
            for root, dirs, files in os.walk(NAS_DIR):
                # as the service's .gitignore: never its local data, work files, caches or a config.env
                dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
                for name in sorted(files):
                    if name in ("config.env", "tls.env", ".env") or name.endswith(".pyc"):
                        continue
                    path = os.path.join(root, name)
                    archive.write(path, "photo-server/" + os.path.relpath(path, NAS_DIR))
        return buffer.getvalue()
