"""A linked Odoo site: its address, database and the API key of a technical user there, and the one helper that calls
it (Odoo's own external API, POST /json/2/<model>/<method>, the key as a bearer token, the database in
X-Odoo-Database)."""
import logging
import time

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from .site_link_sso import SSO_ADMIN_GROUPS

_logger = logging.getLogger(__name__)

PROTOCOL_MODEL = 'site.link.api'
ROLES = [
    ('inventory_source', 'Inventory source'),
    ('staff_source', 'Staff accounts'),
    ('other', 'Other'),
]
# what the employee list sync sends and watches on res.users
USER_SYNC_FIELDS = {'login', 'name', 'email', 'active', 'group_ids', 'share'}


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
    sync_users = fields.Boolean(string='Send Employees', copy=False,
                                help="This site's employee list is the one list: its internal users (login, name, "
                                     "email, active) are sent to the other site, which makes, updates and archives its "
                                     "users to match (no password: they sign in with their account here). Sent on "
                                     "every change of a user, by a daily safety net, and with Sync employees now. "
                                     "Set it on one side only.")
    shop_group_ids = fields.Many2many('res.groups', 'site_link_shop_group_rel', 'site_id', 'group_id',
                                      string='Shop Access Groups',
                                      help="On the site that receives an employee list: the groups (of this site) an "
                                           "employee sent with shop access gets, besides \"Site link: single sign-on "
                                           "allowed\"; sent without shop access, they are taken away.")
    last_sync_at = fields.Datetime(string='Last Employee Sync', readonly=True, copy=False)
    last_sync_message = fields.Text(string='Last Employee Sync Result', readonly=True, copy=False)
    last_check_at = fields.Datetime(string='Last Test', readonly=True, copy=False)
    last_check_ok = fields.Boolean(string='Last Test OK', readonly=True, copy=False)
    last_check_message = fields.Text(string='Last Test Result', readonly=True, copy=False)
    log_count = fields.Integer(compute='_compute_log_count', string='Failed Calls')

    @api.constrains('shop_group_ids')
    def _check_shop_group_ids(self):
        """No Shop Access Group gives administrator rights: shop access comes with single sign-on."""
        admin = self.env['res.groups'].sudo()
        for xmlid in SSO_ADMIN_GROUPS:
            admin |= self.env.ref(xmlid, raise_if_not_found=False) or admin.browse()
        for site in self:
            bad = site.shop_group_ids.sudo().filtered(lambda g: g in admin or g.all_implied_ids & admin)
            if bad:
                raise ValidationError(self.env._(
                    "Shop Access Groups may not give administrator rights (Settings or Access Rights): %s",
                    ', '.join(bad.mapped('display_name'))))

    def _compute_log_count(self):
        counts = dict(self.env['site.link.log']._read_group([('site_id', 'in', self.ids), ('kind', '=', 'failed')],
                                                             ['site_id'], ['__count']))
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

    # ------------------------------------------------------------------ the protocol, one line each (caller side)

    @api.model
    def _site_link_api(self, method, site='inventory_source', **kwargs):
        """``site.link.api.<method>(**kwargs)`` on the linked site ``site`` (a record, an id or a role)."""
        return self._site_link_call(site, PROTOCOL_MODEL, method, **kwargs)

    @api.model
    def _site_link_offers(self, method, site='inventory_source'):
        """Soft check: True when a site is linked (``site``: a record, an id or a role) and its health lists
        ``method``; False otherwise (no site, unreachable, older connector there). Costs one call."""
        try:
            health = self._site_link_resolve(site)._site_link_health()
        except SiteLinkError:
            return False
        return method in (health.get('methods') or [])

    @api.model
    def _site_link_sso_url(self, login, site='inventory_source'):
        """The full one-time sign-in address on the linked site for its user ``login`` (valid 60 seconds)."""
        site = self._site_link_resolve(site)
        answer = self._site_link_api('sso_ticket', site, login=login)
        return (site.base_url or '').strip().rstrip('/') + answer['url']

    @api.model
    def _site_link_customer_search(self, query, limit=10, site='inventory_source'):
        return self._site_link_api('customer_search', site, query=query, limit=limit)

    @api.model
    def _site_link_customer_create(self, name, phone=None, email=None, site='inventory_source'):
        return self._site_link_api('customer_create', site, name=name, phone=phone, email=email)

    @api.model
    def _site_link_customer_bikes(self, partner_id, site='inventory_source'):
        return self._site_link_api('customer_bikes', site, partner_id=partner_id)

    @api.model
    def _site_link_repair_quote(self, reference, partner_id, lines, note=None, bike=None, site='inventory_source'):
        return self._site_link_api('repair_quote', site, reference=reference, partner_id=partner_id, lines=lines,
                                   note=note, bike=bike)

    @api.model
    def _site_link_repair_status(self, reference, site='inventory_source'):
        return self._site_link_api('repair_status', site, reference=reference)

    @api.model
    def _site_link_repair_invoice(self, reference, site='inventory_source'):
        return self._site_link_api('repair_invoice', site, reference=reference)

    # ------------------------------------------------------------------ one employee list (caller side)

    def _site_link_sync_users_list(self):
        """The employees sent to the linked site ``self``: [{login, name, email, active, shop_access}].
        When another extension defines ``res.users._site_link_employees()`` (same answer; no dependency on this
        connector needed), its list is used (as superuser); otherwise this site's internal users, archived ones
        included (they are archived there too), with ``shop_access`` None (the other site leaves its shop groups
        alone). Either way user ids 1 and 2 and the template and public users are never sent."""
        self.ensure_one()
        skip = {1, 2} | {u.id for u in (self.env.ref('base.default_user', raise_if_not_found=False),
                                         self.env.ref('base.public_user', raise_if_not_found=False)) if u}
        Users = self.env['res.users'].sudo().with_context(active_test=False)
        if hasattr(Users, '_site_link_employees'):
            skip_logins = {login.lower() for login in Users.browse(list(skip)).exists().mapped('login') if login}
            return [dict(e) for e in (Users._site_link_employees() or [])
                    if isinstance(e, dict) and isinstance(e.get('login'), str)
                    and e['login'].strip().lower() not in skip_logins]
        users = Users.search([('share', '=', False), ('id', 'not in', list(skip))], order='id')
        return [{'login': u.login, 'name': u.name, 'email': u.email or None, 'active': u.active,
                 'shop_access': None} for u in users]

    def _site_link_sync_users(self):
        """Send the employee list to ``self`` (soft: skipped when the other site offers no user_sync). Keeps the
        result on the site; raises SiteLinkError when the call fails (logged as every failed call)."""
        self.ensure_one()
        _ = self.env._
        if not self._site_link_offers('user_sync', self):
            message = _("Skipped: %s offers no employee sync (user_sync); is Site Link Connector up to date there?",
                        self.name)
            self.sudo().write({'last_sync_at': fields.Datetime.now(), 'last_sync_message': message})
            return None
        users = self._site_link_sync_users_list()
        answer = self._site_link_api('user_sync', self, users=users) or []
        created = sum(1 for a in answer if a.get('created'))
        updated = sum(1 for a in answer if a.get('updated'))
        message = _("%(sent)s employees sent: %(created)s made, %(updated)s updated there.",
                    sent=len(users), created=created, updated=updated)
        self.sudo().write({'last_sync_at': fields.Datetime.now(), 'last_sync_message': message})
        return answer

    def action_sync_users(self):
        """Button: Sync employees now."""
        self.ensure_one()
        try:
            answer = self._site_link_sync_users()
            ok = answer is not None
        except SiteLinkError as exc:
            ok = False
            self.sudo().write({'last_sync_at': fields.Datetime.now(), 'last_sync_message': exc.args[0]})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._("Sync employees: %s", self.name),
                'message': self.last_sync_message,
                'type': 'success' if ok else 'warning',
                'sticky': not ok,
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    @api.model
    def _site_link_sync_users_cron(self):
        """Cron (daily safety net, and run soon after a user changes): every site that gets the employee list."""
        for site in self.sudo().search([('sync_users', '=', True)]):
            try:
                site._site_link_sync_users()
            except SiteLinkError:
                _logger.warning("site link: employee sync to %s failed (see Failed Calls)", site.name)

    @api.model
    def _site_link_sync_users_soon(self):
        """Run the employee sync soon (in the cron worker, after this transaction): nothing when no site gets it."""
        if self.sudo().search_count([('sync_users', '=', True)], limit=1):
            cron = self.env.ref('site_link_connector.cron_site_link_user_sync', raise_if_not_found=False)
            if cron:
                cron.sudo()._trigger()

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
        action['domain'] = [('site_id', '=', self.id), ('kind', '=', 'failed')]
        return action
