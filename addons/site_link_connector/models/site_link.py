"""A linked Odoo site: its address, database and the API key of a technical user there, and the one helper that calls
it (Odoo's own external API, POST /json/2/<model>/<method>, the key as a bearer token, the database in
X-Odoo-Database)."""
import logging
import time

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

PROTOCOL_MODEL = 'site.link.api'
ROLES = [
    ('inventory_source', 'Inventory source'),
    ('other', 'Other'),
]


class SiteLinkError(UserError):
    """A call to a linked site failed. ``status`` is the HTTP status (0: no answer), ``remote`` the other site's error
    name when it gave one."""

    def __init__(self, message, status=0, remote=None):
        super().__init__(message)
        self.status = status
        self.remote = remote


class SiteLink(models.Model):
    _name = 'site.link'
    _description = 'Linked site'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    base_url = fields.Char(string='Address', required=True,
                           help="The other site's address, e.g. https://shop.example.com (no path).")
    db_name = fields.Char(string='Database',
                          help="The other site's database name (sent as X-Odoo-Database; needed when it serves several).")
    api_key = fields.Char(string='API Key', groups='base.group_system', copy=False,
                          help="An API key of the technical user on the other site (that user's Preferences › "
                               "Account Security › New API Key, no expiry or a long one). The user needs the group "
                               "\"Site Link: calls from a linked site\" there.")
    role = fields.Selection(ROLES, string="Other Site's Role", required=True, default='other',
                            help="What the other site is to this one. Inventory source: the site that owns the "
                                 "products and stock; part lookups and consumptions go there.")
    timeout = fields.Integer(string='Time Limit (s)', default=15, help="Seconds to wait for the other site's answer.")
    last_check_at = fields.Datetime(string='Last Test', readonly=True, copy=False)
    last_check_ok = fields.Boolean(string='Last Test OK', readonly=True, copy=False)
    last_check_message = fields.Text(string='Last Test Result', readonly=True, copy=False)
    log_count = fields.Integer(compute='_compute_log_count', string='Failed Calls')

    def _compute_log_count(self):
        counts = dict(self.env['site.link.log']._read_group([('site_id', 'in', self.ids)], ['site_id'], ['__count']))
        for site in self:
            site.log_count = counts.get(site, 0)

    # ------------------------------------------------------------------ the call helper

    @api.model
    def _site_link_resolve(self, site):
        """A site.link record, its id, or a role ('inventory_source'): the first active site with that role."""
        if isinstance(site, models.BaseModel):
            site = site.sudo()
        elif isinstance(site, int):
            site = self.sudo().browse(site).exists()
        elif isinstance(site, str):
            site = self.sudo().search([('role', '=', site)], limit=1)
        else:
            site = self.sudo().browse()
        if len(site) != 1:
            raise SiteLinkError(self.env._("No linked site found (Settings › Site Link)."))
        return site

    @api.model
    def _site_link_call(self, site, model, method, *ids, **kwargs):
        """Call ``model.method(**kwargs)`` on the linked site ``site`` (a record, an id or a role) and return its
        answer (JSON: dicts, lists, numbers, strings). Odoo's /json/2 takes named arguments only; positional ones are
        record ids (``ids``). ``context`` is passed as the call's context. Raises SiteLinkError with a clear message;
        every failed call is logged (Settings › Site Link › Failed calls)."""
        site = self._site_link_resolve(site)
        if len(ids) == 1 and isinstance(ids[0], (list, tuple)):
            ids = tuple(ids[0])
        if any(not isinstance(i, int) or isinstance(i, bool) for i in ids):
            raise SiteLinkError(self.env._("Odoo's /json/2 API takes named arguments only; positional arguments "
                                           "are record ids (integers)."))
        payload = dict(kwargs)
        if ids:
            payload['ids'] = list(ids)
        base = (site.base_url or '').strip().rstrip('/')
        url = f"{base}/json/2/{model}/{method}"
        headers = {'Content-Type': 'application/json', 'User-Agent': 'Odoo site_link_connector'}
        if site.api_key:
            headers['Authorization'] = f"bearer {site.api_key.strip()}"
        if site.db_name:
            headers['X-Odoo-Database'] = site.db_name.strip()
        started = time.monotonic()
        status = 0
        try:
            if not base.startswith(('http://', 'https://')):
                raise SiteLinkError(self.env._("%(site)s: the address must start with https:// (or http://).",
                                               site=site.name))
            if not site.api_key:
                raise SiteLinkError(self.env._("%(site)s: no API key saved.", site=site.name))
            try:
                res = requests.post(url, json=payload, headers=headers, allow_redirects=False,
                                    timeout=max(site.timeout or 15, 1))
            except requests.Timeout as exc:
                raise SiteLinkError(self.env._("%(site)s did not answer within %(s)s seconds.",
                                               site=site.name, s=site.timeout)) from exc
            except requests.RequestException as exc:
                raise SiteLinkError(self.env._("%(site)s cannot be reached (%(url)s): %(error)s",
                                               site=site.name, url=base, error=exc)) from exc
            status = res.status_code
            if 200 <= status < 300:
                try:
                    return res.json() if res.content else None
                except ValueError as exc:
                    raise SiteLinkError(self.env._("%(site)s answered something that is not JSON (HTTP %(status)s): "
                                                   "is the address an Odoo site?", site=site.name, status=status),
                                        status) from exc
            raise self._site_link_http_error(site, model, method, res)
        except SiteLinkError as exc:
            self._site_link_log_failure(site, model, method, exc.status or status, exc.args[0],
                                        int((time.monotonic() - started) * 1000))
            raise

    @api.model
    def _site_link_http_error(self, site, model, method, res):
        """The SiteLinkError for a non-2xx answer: Odoo's /json/2 error body is {name, message, ...}."""
        _ = self.env._
        status = res.status_code
        try:
            body = res.json()
        except ValueError:
            body = None
        remote = body.get('name') if isinstance(body, dict) else None
        detail = (body.get('message') if isinstance(body, dict) else None) or (res.text or '')[:300].strip()
        if 300 <= status < 400:
            msg = _("%(site)s answered a redirect to %(to)s: save that address instead.",
                    site=site.name, to=res.headers.get('Location') or '?')
        elif status == 401:
            msg = _("%(site)s refused the API key (wrong, revoked or expired key, or wrong database): %(detail)s",
                    site=site.name, detail=detail)
        elif status == 403:
            msg = _("%(site)s: the API key's user may not do this: %(detail)s", site=site.name, detail=detail)
        elif status == 404:
            msg = _("%(site)s has no %(model)s.%(method)s (is Site Link Connector installed and up to date there?): "
                    "%(detail)s", site=site.name, model=model, method=method, detail=detail)
        else:
            msg = _("%(site)s answered HTTP %(status)s to %(model)s.%(method)s: %(detail)s",
                    site=site.name, status=status, model=model, method=method, detail=detail)
        return SiteLinkError(msg, status, remote)

    @api.model
    def _site_link_log_failure(self, site, model, method, status, message, duration_ms):
        """The failed call, logged in its own transaction (kept even when the caller's transaction rolls back)."""
        _logger.warning("site link call failed: %s %s.%s (%s): %s", site.name, model, method, status, message)
        vals = {'site_id': site.id, 'model': model, 'method': method, 'status': status,
                'message': (message or '')[:2000], 'duration_ms': duration_ms}
        try:
            with self.env.registry.cursor() as cr:
                env = api.Environment(cr, self.env.uid, self.env.context)
                if env['site.link'].sudo().browse(site.id).exists():
                    env['site.link.log'].sudo().create(vals)
                    return
            # the site is not committed yet (made in this transaction): logged with the caller's transaction
            with self.env.cr.savepoint():
                self.env['site.link.log'].sudo().create(vals)
        except Exception:  # noqa: BLE001 - the log must never hide the call's own error
            _logger.exception("site link: the failed call could not be logged")

    # ------------------------------------------------------------------ health / Test connection

    def _site_link_health(self):
        """The other site's health (site.link.api.health): checked to be an answer of this protocol."""
        self.ensure_one()
        result = self._site_link_call(self, PROTOCOL_MODEL, 'health')
        if not isinstance(result, dict) or 'protocol' not in result:
            raise SiteLinkError(self.env._("%(site)s answered, but not with a site link health check.", site=self.name))
        return result

    def action_test_connection(self):
        self.ensure_one()
        _ = self.env._
        try:
            health = self._site_link_health()
        except SiteLinkError as exc:
            ok, message = False, exc.args[0]
        else:
            ok = True
            message = _("Connected: database %(db)s, Odoo %(odoo)s, Site Link Connector %(version)s, user %(user)s.\n"
                        "Methods offered: %(methods)s",
                        db=health.get('database'), odoo=health.get('odoo_version'),
                        version=health.get('module_version'), user=health.get('user'),
                        methods=', '.join(health.get('methods') or []) or '-')
            if self.db_name and health.get('database') and health['database'] != self.db_name.strip():
                ok = False
                message += "\n" + _("The other site answered from database %(db)s, not %(saved)s.",
                                    db=health['database'], saved=self.db_name)
            if self.role == 'inventory_source' and 'part_lookup' not in (health.get('methods') or []):
                ok = False
                message += "\n" + _("This site is set as the inventory source, but it offers no inventory methods "
                                    "(is Inventory installed there?).")
        self.write({'last_check_at': fields.Datetime.now(), 'last_check_ok': ok, 'last_check_message': message})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Test connection: %s", self.name),
                'message': message,
                'type': 'success' if ok else 'danger',
                'sticky': not ok,
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def action_open_log(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('site_link_connector.action_site_link_log')
        action['domain'] = [('site_id', '=', self.id)]
        return action
