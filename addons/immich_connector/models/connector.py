"""The photo server connection: its token, the office addresses, album links, the last call-in.

The token is made here (``_new_token``: shown once, its SHA-256 kept), and every call of the photo server is checked
with ``_check_bearer(request)``: the stored hash is read with a fresh query, never Odoo's parameter cache, so a new
token takes effect at once in every worker; the comparison is constant time. A good call records when the server last
called in (at most once a minute, without clearing any cache), which the setup wizard's last step shows.

The secure office address' health (19.0.1.2.0): the photo server checks its own ``https://NAS_HOSTNAME/ping`` every
15 minutes and sends the latest result on its calls, as the ``X-Office-Tls`` header (JSON: ``ping_ok``,
``ping_error``, ``cert_expires``, ``checked_at``; ``data/nas/app/office_tls.py``). It is kept here, shown in
Settings › Immich, and a problem (no answer twice in a row, the certificate ending within 20 days, no check for a
day) becomes one alert for staff: in the Alert Feed when it is installed (an alert source, soft), else a to-do for
the Settings administrators, once per problem (again at most daily once done), cleared when it works again."""
import hashlib
import hmac
import json
import logging
import secrets
from datetime import date, datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.misc import format_date, format_datetime

_logger = logging.getLogger(__name__)

P = "immich_connector."
TOKEN = P + "nas_token_hash"
LAST_SEEN = P + "last_seen"
OFFICE_IP = P + "office_ip"  # the office's public address, from the photo server's calls (never shown to anyone)
AT_OFFICE_FOR = timedelta(minutes=15)  # the photo server called in this recently: its address still counts
SEEN_EVERY = timedelta(minutes=1)
TLS = P + "office_tls"                   # the latest check of the secure office address (JSON, see below)
TLS_WATCH = P + "office_tls_watch"       # since when a check is expected (https set, the photo server calling in)
TLS_INCIDENT = P + "office_tls_incident"  # the problem being alerted (JSON: code, since, alerted_at, activity_ids)
TLS_HEADER = "X-Office-Tls"
TLS_FAILS = 2                            # failed checks in a row before an alert ...
TLS_FAIL_SPAN = timedelta(minutes=14)    # ... the first at least this long before the last (one check per 15 min)
TLS_CERT_DAYS = 20                       # the certificate ends within this many days: alert
TLS_MISSING = timedelta(hours=24)        # no check for this long while the photo server calls in: alert
TLS_CALLING = timedelta(hours=1)         # "still calls in": its last call-in this recent
TLS_REALERT = timedelta(hours=24)        # a to-do done while the problem goes on: again at most daily


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
    def _office_base(self):
        """The photo server's secure office address (https, office network only), e.g. https://nas.example.com, no
        trailing slash: the Staff App probes ``<base>/ping`` and uploads to ``<base>/upload/file`` straight from the
        app. False when only a plain http address is set (a secure page cannot send to it)."""
        for value in (self._param("office_base"), self._upload_url()):
            value = value.rstrip("/")
            if value.endswith("/upload"):
                value = value[:-len("/upload")]
            if value.startswith("https://"):
                return value
        return False

    @api.model
    def _wifi_name(self):
        return self._param("wifi_name")

    @api.model
    def _wifi_names(self):
        """The office wifi networks (several, separated by commas: e.g. a 2.4 GHz and a 5 GHz network behind the same
        router), in order."""
        return [name.strip() for name in self._wifi_name().split(",") if name.strip()]

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
        if isinstance(request, str):
            self._mark_seen()
            return True
        seen = self._mark_seen(request.httprequest.remote_addr)
        tls = request.httprequest.headers.get(TLS_HEADER)
        new = False
        if tls and not getattr(self.env.cr, "readonly", False):
            try:
                new = self._office_tls_report(json.loads(tls))
            except ValueError:
                _logger.info("Photo server: unreadable %s header", TLS_HEADER)
        if seen or new:
            self._office_tls_check()
        return True

    @api.model
    def _mark_seen(self, ip=None):
        """When the photo server last called in, and from which public address (the office's: the request's real
        client address, as the site reads every visitor's, behind its proxy): kept with direct writes (no cache
        cleared), at most once a minute; the address as soon as it changes (the office's 4G router)."""
        if getattr(self.env.cr, "readonly", False):
            return False  # (a read-only request: the next call records it)
        now = fields.Datetime.now()
        last = self._last_seen()
        if ip and ip != _fresh(self.env, OFFICE_IP):
            self._set_fresh(OFFICE_IP, ip)
        elif last and now - last < SEEN_EVERY:
            return False
        self._set_fresh(LAST_SEEN, fields.Datetime.to_string(now))
        return True

    @api.model
    def _set_fresh(self, key, value):
        self.env.cr.execute("UPDATE ir_config_parameter SET value = %s WHERE key = %s", [value, key])
        if not self.env.cr.rowcount:
            self.env.cr.execute(
                "INSERT INTO ir_config_parameter (key, value, create_uid, write_uid, create_date, write_date) "
                "VALUES (%s, %s, 1, 1, now() at time zone 'UTC', now() at time zone 'UTC') "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", [key, value])

    @api.model
    def _at_office(self, ip):
        """Deprecated (19.0.1.2.0): the Staff App's upload no longer asks (it probes ``<office base>/ping`` itself);
        kept, with the same answer, for older Staff App versions and the office banner / album links that still ask.

        Whether ``ip`` (a staff member's request) is the office's: the photo server called in within the last 15
        minutes from that same public address. Only yes or no ever leaves here."""
        last, office = self._last_seen(), _fresh(self.env, OFFICE_IP)
        return bool(ip and office and last and fields.Datetime.now() - last <= AT_OFFICE_FOR and ip == office)

    @api.model
    def _last_seen(self):
        value = _fresh(self.env, LAST_SEEN)
        return fields.Datetime.to_datetime(value) if value else None

    # ------------------------------------------------------------------ the secure office address' health
    @api.model
    def _office_tls(self):
        """The latest check kept: {ping_ok, ping_error, cert_expires, checked_at (the photo server's), received_at,
        fails (in a row), failing_since (when the first of them came)}; {} before the first."""
        try:
            value = json.loads(_fresh(self.env, TLS) or "{}")
        except ValueError:
            return {}
        return value if isinstance(value, dict) else {}

    @api.model
    def _office_tls_report(self, report):
        """A check from the photo server (the ``X-Office-Tls`` header): kept when it is a new one (its
        ``checked_at``: the photo server sends its latest on every call). True when kept."""
        if not isinstance(report, dict) or not isinstance(report.get("ping_ok"), bool) \
                or not isinstance(report.get("checked_at"), str):
            return False
        old = self._office_tls()
        checked = report["checked_at"][:40]
        if checked == old.get("checked_at"):
            return False
        now = fields.Datetime.to_string(fields.Datetime.now())
        cert = report.get("cert_expires")
        cert = cert[:10] if isinstance(cert, str) and _iso_date(cert[:10]) else old.get("cert_expires") or ""
        ok = report["ping_ok"]
        fails = 0 if ok else int(old.get("fails") or 0) + 1
        value = {"ping_ok": ok, "ping_error": "" if ok else str(report.get("ping_error") or "")[:500],
                 "cert_expires": cert, "checked_at": checked, "received_at": now, "fails": fails,
                 "failing_since": "" if ok else (old.get("failing_since") if fails > 1 else now) or now}
        self._set_fresh(TLS, json.dumps(value))
        return True

    @api.model
    def _office_tls_problem(self, now=None):
        """What is wrong with the secure office address now: {code, title, detail} or None (working, not checked
        yet, or no https office address: nothing to watch). ``code``: ``ping`` (no answer on 2 checks in a row),
        ``cert`` (the certificate ends within 20 days), ``missing`` (no check for 24 h while the photo server calls
        in)."""
        if not self._office_base():
            return None
        now = now or fields.Datetime.now()
        report = self._office_tls()
        received = _dt(report.get("received_at"))
        seen = self._last_seen()
        calling = bool(seen and now - seen <= TLS_CALLING)
        since = received or _dt(_fresh(self.env, TLS_WATCH))
        if calling and since and now - since >= TLS_MISSING:
            return {"code": "missing", "title": _("Secure office address: no check from the photo server"),
                    "detail": _("The photo server calls in but has sent no check of the secure office address since "
                                "%(since)s, so nobody would notice if phones at the office upload over mobile data. "
                                "Update the photo server's files (Settings › Immich › Set up the photo server, the "
                                "new zip: NAS_HOSTNAME and NAS_HTTPS_PORT in config.env), then restart photos-sync.",
                                since=self._office_tls_when(since))}
        if not report or not received or now - received >= TLS_MISSING:
            return None
        failing = _dt(report.get("failing_since"))
        if not report.get("ping_ok") and int(report.get("fails") or 0) >= TLS_FAILS and failing \
                and received - failing >= TLS_FAIL_SPAN:
            return {"code": "ping", "title": _("Secure office address not answering"),
                    "detail": _("Since %(since)s phones at the office upload over mobile data (slow): %(error)s. "
                                "Check, in this order: the photo server is on and its https front runs (restart "
                                "tour-photos-tls: in its tls folder, docker compose up -d); the router still lets "
                                "the name resolve to the photo server (after a router reset: allow the domain in its "
                                "DNS rebind protection again); the photo server kept its reserved office address; "
                                "the Cloudflare token in tls/tls.env still exists.",
                                since=self._office_tls_when(failing), error=report.get("ping_error") or "?")}
        cert = _iso_date(report.get("cert_expires"))
        if cert and (cert - now.date()).days < TLS_CERT_DAYS:
            return {"code": "cert", "title": _("Secure office address: the certificate ends %s",
                                               self._office_tls_day(cert)),
                    "detail": _("The certificate renews by itself through Cloudflare, and has not. Check that the "
                                "Cloudflare token in tls/tls.env still exists (Cloudflare › My Profile › API Tokens, "
                                "Edit zone DNS: never delete it), make a new one there if needed and put it in "
                                "tls/tls.env, then restart tour-photos-tls (docker compose up -d --force-recreate in "
                                "its tls folder).")}
        return None

    @api.model
    def _office_tls_status(self):
        """Settings › Immich's line: '' without an https office address."""
        if not self._office_base():
            return ""
        report = self._office_tls()
        if not report:
            return _("Secure office address: no check from the photo server yet (its files need NAS_HOSTNAME: "
                     "Set up the photo server's new zip).")
        if report.get("ping_ok"):
            cert = _iso_date(report.get("cert_expires"))
            if cert:
                return _("Secure office address: ✓ working · certificate until %(date)s (checked %(when)s)",
                         date=self._office_tls_day(cert), when=self._office_tls_when(_dt(report.get("received_at"))))
            return _("Secure office address: ✓ working (checked %s)",
                     self._office_tls_when(_dt(report.get("received_at"))))
        return _("Secure office address: ✗ not answering since %(since)s: %(error)s",
                 since=self._office_tls_when(_dt(report.get("failing_since")) or _dt(report.get("received_at"))),
                 error=report.get("ping_error") or "?")

    @api.model
    def _office_tls_day(self, day):
        return format_date(self.env, day, date_format="d MMM y")

    @api.model
    def _office_tls_when(self, moment):
        if not moment:
            return "?"
        return format_datetime(self.env, moment, tz=self.env.user.tz or "UTC", dt_format="d MMM y HH:mm")

    @api.model
    def _office_tls_alert_feed(self):
        """The Alert Feed is installed: it shows the problem itself (an alert source, below)."""
        return "mtbg.alert.feed" in self.env and "mtbg.alert.rule" in self.env

    @api.model
    def _office_tls_check(self):
        """After a call-in or a new check (a writable request): what is expected, and the alert raised or cleared.
        Never fails the photo server's call."""
        try:
            with self.env.cr.savepoint():
                self._office_tls_check_now()
        except Exception:  # noqa: BLE001 - logged; the photo server's call goes on
            _logger.exception("Photo server: the secure office address check failed")

    @api.model
    def _office_tls_check_now(self, now=None):
        now = now or fields.Datetime.now()
        if not self._office_base():
            self._set_fresh(TLS_WATCH, "")
        elif not self._office_tls() and not _fresh(self.env, TLS_WATCH):
            self._set_fresh(TLS_WATCH, fields.Datetime.to_string(now))
        problem = self._office_tls_problem(now)
        try:
            incident = json.loads(_fresh(self.env, TLS_INCIDENT) or "{}")
        except ValueError:
            incident = {}
        if not problem:
            if incident:
                _logger.info("Photo server: the secure office address works again (%s)", incident.get("code"))
                self._office_tls_clear(incident)
                self._set_fresh(TLS_INCIDENT, "")
            return None
        if incident.get("code") != problem["code"]:
            if incident:
                self._office_tls_clear(incident)
            _logger.warning("Photo server: %s: %s", problem["title"], problem["detail"])
            incident = {"code": problem["code"], "since": fields.Datetime.to_string(now), "alerted_at": "",
                        "activity_ids": []}
        if not self._office_tls_alert_feed():  # (the Alert Feed: its own alert, shown while the problem lasts)
            open_ids = self._office_tls_open_activities(incident)
            alerted = _dt(incident.get("alerted_at"))
            if not open_ids and (not alerted or now - alerted >= TLS_REALERT):
                incident["activity_ids"] = self._office_tls_notify(problem)
                incident["alerted_at"] = fields.Datetime.to_string(now)
        self._set_fresh(TLS_INCIDENT, json.dumps(incident))
        return problem

    @api.model
    def _office_tls_open_activities(self, incident):
        if "mail.activity" not in self.env or not incident.get("activity_ids"):
            return []
        return self.env["mail.activity"].sudo().browse(incident["activity_ids"]).exists().ids

    @api.model
    def _office_tls_notify(self, problem):
        """No Alert Feed: a to-do for each Settings administrator (on the company's contact), [ids]; nothing
        without Discuss (mail)."""
        if "mail.activity" not in self.env:
            return []
        admins = self.env.ref("base.group_system").sudo().all_user_ids.filtered(
            lambda user: user.active and not user.share and user.id != 1)  # (not OdooBot)
        todo = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        partner = self.env.company.partner_id
        model = self.env["ir.model"]._get_id("res.partner")
        Activity = self.env["mail.activity"].sudo().with_context(mail_activity_quick_update=True)
        ids = []
        for user in admins:
            lang = user.lang or "en_US"
            text = self.with_context(lang=lang).with_user(user)._office_tls_problem() or problem
            ids.append(Activity.create({
                "res_model_id": model, "res_id": partner.id, "user_id": user.id,
                "activity_type_id": todo.id if todo else False, "summary": text["title"][:250],
                "note": text["detail"], "date_deadline": fields.Date.context_today(self),
            }).id)
        return ids

    @api.model
    def _office_tls_clear(self, incident):
        """The problem is over (or another took its place): its to-dos go."""
        ids = self._office_tls_open_activities(incident)
        if ids:
            self.env["mail.activity"].sudo().browse(ids).unlink()

    # the Alert Feed's alert source (``mtbg_tours_alerts/models/alert_source.py``, soft: never imported)
    def _mtbg_alert_sources(self):
        sources = getattr(super(), "_mtbg_alert_sources", None)
        return (sources() if sources else []) + [{
            "code": "immich_office_tls", "name": _("Secure office address (photo server)"), "section": "logistics",
            "level": "warning", "sequence": 95, "icon": "fa-lock",
            "description": _("The photo server's secure office address (https, for uploads straight from the Staff "
                             "App at the office) stopped answering, its certificate ends within 20 days, or the photo "
                             "server sent no check for a day."),
            "alerts": "_mtbg_alerts_office_tls",
        }]

    @api.model
    def _mtbg_alerts_office_tls(self, rule, today):
        problem = self._office_tls_problem()
        if not problem:
            return []
        return [{"key": problem["code"], "title": problem["title"], "detail": problem["detail"], "date": today}]


def _dt(value):
    try:
        return fields.Datetime.to_datetime(value) if value else None
    except ValueError:
        return None


def _iso_date(value):
    try:
        return date.fromisoformat(value) if isinstance(value, str) and value else None
    except ValueError:
        return None


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    immich_upload_url = fields.Char("Office upload page URL", config_parameter=P + "upload_url",
                                    help="The photo server's upload page on the office network")
    immich_office_base = fields.Char("Office secure address", config_parameter=P + "office_base",
                                     help="The photo server's https address on the office network (e.g. "
                                          "https://nas.example.com): the Staff App uploads to it straight from the "
                                          "app. Set by Set up the photo server")
    immich_wifi_name = fields.Char("Office wifi name", config_parameter=P + "wifi_name",
                                   help="The office wifi network staff are told to connect to before uploading. "
                                        "Several (e.g. one 2.4 GHz and one 5 GHz, behind the same router): separate "
                                        "them with commas")
    immich_url = fields.Char("Immich URL", config_parameter=P + "immich_url",
                             help="Immich's address (on the office network), for album links: <this>/albums/<id>")
    immich_public_mode = fields.Boolean("Immich reachable from the internet", config_parameter=P + "public_mode",
                                        help="Odoo can reach Immich itself (an API key below): albums are made from "
                                             "here at once instead of waiting for the photo server")
    immich_api_key = fields.Char("Immich API key", config_parameter=P + "api_key", groups="base.group_system")
    immich_token_set = fields.Boolean("Photo server token set", compute="_compute_immich_status")
    immich_last_seen = fields.Datetime("Photo server last called in", compute="_compute_immich_status")
    immich_office_tls_status = fields.Char("Secure office address status", compute="_compute_immich_status")
    immich_office_tls_ok = fields.Boolean("Secure office address working", compute="_compute_immich_status")
    immich_office_tls_cert = fields.Date("Certificate until", compute="_compute_immich_status")
    immich_office_tls_checked = fields.Datetime("Secure office address last checked", compute="_compute_immich_status")

    def _compute_immich_status(self):
        Connector = self.env["immich.connector"].sudo()
        token, seen = Connector._has_token(), Connector._last_seen()
        report = Connector._office_tls()
        status = Connector._office_tls_status()
        for settings in self:
            settings.immich_token_set = token
            settings.immich_last_seen = seen
            settings.immich_office_tls_status = status
            settings.immich_office_tls_ok = bool(report.get("ping_ok"))
            settings.immich_office_tls_cert = _iso_date(report.get("cert_expires"))
            settings.immich_office_tls_checked = _dt(report.get("received_at"))

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
