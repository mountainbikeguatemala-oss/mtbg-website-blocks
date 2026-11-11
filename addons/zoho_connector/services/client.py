"""The one Zoho client of the suite: every Zoho app (Books, Expense, Shifts) through one OAuth self client (Zoho CRM removed 2026-11-08).

One connection for the whole site (Settings › Zoho › Set up Zoho), in these parameters (their names kept from
before the connector was an extension of its own, so a site keeps its login):

    mtbg_tours.zoho_client_id / _client_secret / _refresh_token   the self client (secrets)
    mtbg_tours.zoho_accounts_url / _api_url                       the data centre (empty: US)
    the access token: model mtbg.zoho.token, shared by every app and extension; not a system parameter, so its hourly
    renewal does not empty Odoo's caches

Per app (``APPS``): its organization (``org_param``), and two switches, both off until the owner says so:
``mtbg_tours.zoho_<app>_enabled`` (the app syncs at all) and ``mtbg_tours.zoho_<app>_writes`` (anything but a GET is
allowed; refused with ``ZohoWriteBlocked`` otherwise). Every write and every failure goes to the sync log
(``mtbg.zoho.log``), written on a cursor of its own so a rolled-back sync keeps its log.

Calls are paced (``mtbg_tours.zoho_rate_limit`` per minute and app, default 90: Zoho Books allows 100) and retried
with a growing wait when Zoho says "too many requests" (any call) or fails on its side (GET only: a write is never
sent twice).
"""
import collections
import hashlib
import json
import re
import logging
import threading
import time

import requests

import odoo
from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

TIMEOUT = 30
RETRIES = 3
RATE_LIMIT = 90
_sleep = time.sleep  # tests replace it
_calls = collections.defaultdict(collections.deque)  # (db, app) -> times of the last minute's calls
_lock = threading.Lock()


def _domain(accounts_url):
    """'https://accounts.zoho.eu' -> 'zoho.eu'"""
    host = (accounts_url or 'https://accounts.zoho.com').split('//')[-1].strip('/')
    return host.removeprefix('accounts.') or 'zoho.com'


# key: label, the API's base address (api server, data centre domain, organization), where the organization goes
# (query parameter, header or path), the scopes it needs, a cheap GET to check them
APPS = {
    'books': {'label': 'Zoho Books', 'org_param': 'zoho_org_id', 'org_in': ('query', 'organization_id'),
              'base': lambda api_url, domain, org: f"{api_url}/books/v3",
              'scopes': 'ZohoBooks.fullaccess.all', 'probe': 'projects', 'probe_params': {'per_page': 1}},
    'expense': {'label': 'Zoho Expense', 'org_param': 'zoho_expense_org_id',
                'org_in': ('header', 'X-com-zoho-expense-organizationid'),
                'base': lambda api_url, domain, org: f"{api_url}/expense/v1",
                # read only (Zoho 0.3.12: the reports are no longer made; the history import reads them)
                # orgsettings.READ: its organizations listed (the wizard's check of the ID typed; owner, 2026-10-26)
                'scopes': 'ZohoExpense.expensereport.READ,ZohoExpense.project.READ,ZohoExpense.orgsettings.READ',
                'probe': 'expensereports', 'probe_params': {'per_page': 1}},
    'shifts': {'label': 'Zoho Shifts', 'org_param': 'zoho_shifts_org_id', 'org_in': ('path', None),
               'base': lambda api_url, domain, org: f"https://shifts.{domain}/api/v1/{org}",
               # the Shifts link's own list (two-way, least privilege)
               'scopes': 'ZohoShifts.settings.READ,ZohoShifts.employees.READ,ZohoShifts.schedules.READ,'
                         'ZohoShifts.timeoff.READ,ZohoShifts.timesheets.READ,'
                         'ZohoShifts.settings.CREATE,ZohoShifts.settings.UPDATE,ZohoShifts.employees.UPDATE,'
                         'ZohoShifts.schedules.CREATE,ZohoShifts.schedules.UPDATE,ZohoShifts.schedules.DELETE,'
                         'ZohoShifts.timeoff.CREATE,ZohoShifts.timeoff.UPDATE,'
                         'ZohoShifts.timesheets.CREATE,ZohoShifts.timesheets.UPDATE,ZohoShifts.timesheets.DELETE',
               # no paging parameters: Zoho Shifts refuses any it does not know ("Extra parameter found in URL")
               'probe': 'settings/jobsites', 'probe_params': None},
}


class ZohoError(Exception):
    pass


# Zoho data centres: (key, label, domain of accounts / API console, API server). The connector's own login (its setup
# wizard); the same table as Invoicing's until its Zoho Books code moves here.
DATA_CENTRES = [
    ('us', 'United States (zoho.com)', 'zoho.com', 'https://www.zohoapis.com'),
    ('eu', 'Europe (zoho.eu)', 'zoho.eu', 'https://www.zohoapis.eu'),
    ('uk', 'United Kingdom (zoho.uk)', 'zoho.uk', 'https://www.zohoapis.uk'),
    ('in', 'India (zoho.in)', 'zoho.in', 'https://www.zohoapis.in'),
    ('au', 'Australia (zoho.com.au)', 'zoho.com.au', 'https://www.zohoapis.com.au'),
    ('jp', 'Japan (zoho.jp)', 'zoho.jp', 'https://www.zohoapis.jp'),
    ('ca', 'Canada (zohocloud.ca)', 'zohocloud.ca', 'https://www.zohoapis.ca'),
    ('sa', 'Saudi Arabia (zoho.sa)', 'zoho.sa', 'https://www.zohoapis.sa'),
    ('cn', 'China (zoho.com.cn)', 'zoho.com.cn', 'https://www.zohoapis.com.cn'),
]


def data_centre(key):
    dc = next((d for d in DATA_CENTRES if d[0] == key), DATA_CENTRES[0])
    return {'key': dc[0], 'label': dc[1], 'accounts_url': f"https://accounts.{dc[2]}",
            'console_url': f"https://api-console.{dc[2]}/", 'api_url': dc[3], 'domain': dc[2]}


def exchange_grant_code(accounts_url, client_id, client_secret, code):
    """A Self Client's grant code (Generate Code) for a refresh token, once; returns the token response."""
    try:
        res = requests.post(f"{accounts_url.rstrip('/')}/oauth/v2/token", data={
            'grant_type': 'authorization_code', 'client_id': client_id, 'client_secret': client_secret,
            'code': code}, timeout=TIMEOUT)
        data = res.json()
    except (requests.RequestException, ValueError) as e:
        raise ZohoError(f"Zoho could not be reached: {e}") from e
    if data.get('error') or not data.get('refresh_token'):
        error = data.get('error') or 'no refresh token returned'
        hints = {'invalid_code': "The code is wrong, already used or more than its minutes old: generate a new one.",
                 'invalid_client': "The Client ID or Client Secret is wrong, or the client is in another data centre.",
                 'invalid_client_secret': "The Client Secret is wrong."}
        raise ZohoError(hints.get(error, f"Zoho refused the code: {error}"))
    return data


class ZohoWriteBlocked(ZohoError):
    """A write refused: the app's "Writes allowed" is off."""


class ZohoScopeError(ZohoError):
    """The token lacks this app's scope (the grant code must be made again with it)."""


def fingerprint(payload):
    """A short, stable hash of what was sent (to send again only what changed)."""
    return hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]


def truthy(value):
    return str(value or '').strip() in ('1', 'True', 'true')


class Zoho:
    """``Zoho(env, 'books').request('GET', 'projects')``"""

    def __init__(self, env, app):
        if app not in APPS:
            raise ZohoError(f"Unknown Zoho app: {app}")
        self.env = env
        self.app = app
        self.spec = APPS[app]
        self.icp = env['ir.config_parameter'].sudo()

    def _param(self, key, default=''):
        return (self.icp.get_param(f'mtbg_tours.{key}') or default).strip()

    # ------------------------------------------------------------------ state
    @property
    def connected(self):
        return all(self._param(k) for k in ('zoho_client_id', 'zoho_client_secret', 'zoho_refresh_token'))

    @property
    def org_id(self):
        return self._param(self.spec['org_param']) if self.spec['org_param'] else ''

    @property
    def _forced(self):
        """A one-booking run (``mtbg_zoho_force`` in the context: {'apps': [...], 'writes': bool}): the app on for that
        call only, its switches untouched (owner, 2026-10-27: Jennifer's booking first, nothing else swept)."""
        force = self.env.context.get('mtbg_zoho_force') or {}
        return force if self.app in (force.get('apps') or ()) else None

    @property
    def enabled(self):
        """The app is switched on, the connection made and its organization set."""
        switched = self._forced is not None or truthy(self._param(f'zoho_{self.app}_enabled'))
        return switched and self.connected and (bool(self.org_id) or not self.spec['org_param'])

    @property
    def writes(self):
        forced = self._forced
        if forced is not None:
            return self.enabled and bool(forced.get('writes'))
        return self.enabled and truthy(self._param(f'zoho_{self.app}_writes'))

    # ------------------------------------------------------------------ transport
    def _access_token(self):
        cached, expires = self.env['mtbg.zoho.token']._mtbg_get()
        if cached and expires > time.time() + 60:
            return cached  # one token for every app (and Invoicing): Zoho blocks a burst of refreshes
        accounts = self._param('zoho_accounts_url', 'https://accounts.zoho.com').rstrip('/')
        try:
            res = requests.post(f"{accounts}/oauth/v2/token", data={
                'grant_type': 'refresh_token', 'refresh_token': self._param('zoho_refresh_token'),
                'client_id': self._param('zoho_client_id'), 'client_secret': self._param('zoho_client_secret'),
            }, timeout=TIMEOUT)
            data = res.json()
        except (requests.RequestException, ValueError) as e:
            raise ZohoError(f"Zoho OAuth request failed: {e}") from e
        token = data.get('access_token')
        if not token:
            raise ZohoError(f"Zoho OAuth refused: {data.get('error') or res.status_code}")
        self.env['mtbg.zoho.token']._mtbg_set(token, time.time() + max(300, int(data.get('expires_in', 3600)) - 120))
        if data.get('scope'):
            self.icp.set_param('mtbg_tours.zoho_granted_scopes', data['scope'])
        return token

    def _pace(self):
        limit = int(self._param('zoho_rate_limit', str(RATE_LIMIT)) or RATE_LIMIT)
        key = (self.env.cr.dbname, self.app)
        while True:
            with _lock:
                calls, now = _calls[key], time.monotonic()
                while calls and now - calls[0] > 60:
                    calls.popleft()
                if len(calls) < limit:
                    calls.append(now)
                    return
                wait = 60 - (now - calls[0]) + 0.05
            _sleep(wait)

    def _url(self, path):
        api_url = self._param('zoho_api_url', 'https://www.zohoapis.com').rstrip('/')
        base = self.spec['base'](api_url, _domain(self._param('zoho_accounts_url')), self.org_id)
        return f"{base}/{path.lstrip('/')}"

    def request(self, method, path, params=None, json=None, record=None, _check=True, files=None):
        """One call to the app. ``record`` (optional) is noted in the log; ``files`` (optional): a multipart upload
        ({field: (name, bytes, mimetype)}, e.g. an expense's receipt) instead of a JSON body. Returns the JSON answer."""
        method = method.upper()
        if _check and not self.enabled:
            raise ZohoError(f"{self.spec['label']} is off or not connected")
        dry = self.env.context.get('mtbg_zoho_dry')
        if dry is not None and method != 'GET':
            # a dry run: the write is noted, not sent; a stand-in answer lets the next steps be checked too
            dry.append({'app': self.app, 'method': method, 'path': path, 'json': json,
                        'files': sorted(files) if files else None})
            return {'project': {'project_id': 'DRY-PROJECT', 'project_name': (json or {}).get('project_name'),
                                'customer_id': (json or {}).get('customer_id')},
                    'expense_report': {'report_id': 'DRY-REPORT', 'project_id': (json or {}).get('project_id')},
                    'invoice': {}}
        if method != 'GET' and not self.writes:
            raise ZohoWriteBlocked(f"{self.spec['label']}: writes are off ({method} {path} not sent)")
        params, headers = dict(params or {}), {}
        where, name = self.spec['org_in']
        if where == 'query':
            params[name] = self.org_id
        elif where == 'header':
            headers[name] = self.org_id
        started, attempt, body, status = time.monotonic(), 0, {}, 0
        while True:
            attempt += 1
            self._pace()
            headers['Authorization'] = f"Zoho-oauthtoken {self._access_token()}"
            try:
                res = requests.request(method, self._url(path), params=params, json=None if files else json,
                                       files=files or None, headers=headers, timeout=TIMEOUT)
                status = res.status_code
                body = res.json() if res.content else {}
            except (requests.RequestException, ValueError) as e:
                if method == 'GET' and attempt < RETRIES:
                    _sleep(2 ** attempt)
                    continue
                self._log(method, path, 0, False, f"{e}", started, record)
                raise ZohoError(f"{self.spec['label']} {method} {path} failed: {e}") from e
            retry = status == 429 or (status >= 500 and method == 'GET')
            if retry and attempt < RETRIES:
                try:
                    wait = float(res.headers.get('Retry-After') or 0)
                except ValueError:
                    wait = 0
                _sleep(wait or 2 ** attempt)
                continue
            break
        body = body if isinstance(body, dict) else {'data': body}
        code = body.get('code', 0)
        ok = status < 300 and code in (0, '0', None, 'SUCCESS')
        message = body.get('message') or body.get('error') or ''
        if method != 'GET' or not ok:
            self._log(method, path, status, ok, '' if ok else f"{code} {message}".strip(), started, record)
        if not ok:
            text = f"{self.spec['label']} {method} {path}: {status} {code} {message}".strip()
            if (status == 401 and 'SCOPE' in f"{code} {message}".upper()) or str(code) == '57':
                raise ZohoScopeError(text)
            raise ZohoError(text)
        return body

    def download(self, path, params=None):
        """A file (an expense's receipt), read only: (bytes, mimetype, filename). Raises ZohoError when Zoho answers
        with an error (JSON) instead of the file."""
        if not self.enabled:
            raise ZohoError(f"{self.spec['label']} is off or not connected")
        params, headers = dict(params or {}), {}
        where, name = self.spec['org_in']
        if where == 'query':
            params[name] = self.org_id
        elif where == 'header':
            headers[name] = self.org_id
        started = time.monotonic()
        for attempt in range(1, RETRIES + 1):
            self._pace()
            headers['Authorization'] = f"Zoho-oauthtoken {self._access_token()}"
            try:
                res = requests.get(self._url(path), params=params, headers=headers, timeout=TIMEOUT)
            except requests.RequestException as e:
                if attempt < RETRIES:
                    _sleep(2 ** attempt)
                    continue
                self._log('GET', path, 0, False, f"{e}", started, None)
                raise ZohoError(f"{self.spec['label']} GET {path} failed: {e}") from e
            if (res.status_code == 429 or res.status_code >= 500) and attempt < RETRIES:
                _sleep(2 ** attempt)
                continue
            break
        mimetype = (res.headers.get('Content-Type') or '').split(';')[0].strip()
        if res.status_code >= 300 or mimetype == 'application/json':
            try:
                body = res.json()
            except ValueError:
                body = {}
            message = f"{body.get('code', '')} {body.get('message') or ''}".strip() or str(res.status_code)
            self._log('GET', path, res.status_code, False, message, started, None)
            raise ZohoError(f"{self.spec['label']} GET {path}: {res.status_code} {message}")
        disposition = res.headers.get('Content-Disposition') or ''
        found = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', disposition)
        return res.content, mimetype or 'application/octet-stream', (found.group(1) if found else '')

    def _log(self, method, path, status, ok, message, started, record):
        """The sync log, on its own cursor: it stays even when the sync's transaction is rolled back."""
        vals = {'app': self.app, 'method': method, 'path': path[:250], 'status': status, 'ok': ok,
                'message': (message or '')[:1000], 'duration_ms': int((time.monotonic() - started) * 1000),
                'res_model': record._name if record else False, 'res_id': record.id if record else False}
        try:
            if odoo.modules.module.current_test:  # a test's own transaction (a second cursor would commit)
                self.env['mtbg.zoho.log'].sudo().create(vals)
                return
            with self.env.registry.cursor() as cr:
                api.Environment(cr, SUPERUSER_ID, {})['mtbg.zoho.log'].create(vals)
        except Exception as e:  # never let the log break a sync
            _logger.warning("Zoho sync log not written (%s): %s", e, vals)

    # ------------------------------------------------------------------ checks
    def probe(self):
        """A cheap read: {'ok', 'message'} (the token's scope for this app, the organization)."""
        if not self.connected:
            return {'ok': False, 'message': 'not connected'}
        if self.spec['org_param'] and not self.org_id:
            return {'ok': False, 'message': 'organization id missing'}
        try:  # also before the app is switched on (a read only)
            self.request('GET', self.spec['probe'], params=self.spec.get('probe_params'), _check=False)
            return {'ok': True, 'message': 'access ok'}
        except ZohoScopeError as e:
            return {'ok': False, 'message': f'scope missing ({e})'}
        except ZohoError as e:
            return {'ok': False, 'message': str(e)}

    def organizations(self):
        """[{id, name}] of the app's organizations the login reaches (Books, Expense; none for the others)."""
        paths = {'books': ('books/v3/organizations', 'organizations'), 'expense': ('expense/v1/organizations', 'organizations')}
        if self.app not in paths or not self.connected:
            return []
        path, key = paths[self.app]
        api_url = self._param('zoho_api_url', 'https://www.zohoapis.com').rstrip('/')
        try:
            res = requests.get(f"{api_url}/{path}", timeout=TIMEOUT,
                               headers={'Authorization': f"Zoho-oauthtoken {self._access_token()}"})
            body = res.json()
        except (requests.RequestException, ValueError) as e:
            raise ZohoError(f"{self.spec['label']} organizations failed: {e}") from e
        if res.status_code >= 300 or body.get('code', 0) not in (0, '0'):
            raise ZohoError(f"{self.spec['label']} organizations: {body.get('code')} {body.get('message') or res.status_code}")
        return [{'id': str(o.get('organization_id')), 'name': o.get('name') or o.get('organization_name') or ''}
                for o in body.get(key) or [] if o.get('organization_id')]

