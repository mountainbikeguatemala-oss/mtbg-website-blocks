"""The one Zoho setup wizard (the Zoho section's "Set up Zoho"; owner, 2026-10-25: "Invoices should not control the Zoho
link"). It writes the same parameters Invoices & Payments reads (``mtbg_tours.zoho_*``), so its Zoho Books sync keeps
working unchanged:

1. the data centre and the Self Client (id, secret);
2. the apps to include: their combined scopes for Generate Code, then the grant code, exchanged once for a refresh token;
3. each app's organization (Zoho Books and Zoho Expense listed; Zoho Shifts typed; Zoho Expense's filled in from Zoho
   Books', usually the same, owner 2026-10-26);
4. where an extension brings one, its own choices in Zoho Books (e.g. Invoices & Payments': deposit account, custom
   fields, invoice template; ``_mtbg_books_choices`` / ``_mtbg_books_finish``, overridden there);
5. Check access, per app.
"""
import json
import logging
import re
import time

from odoo import _, api, fields, models
from odoo.exceptions import AccessError
from odoo.tools.translate import LazyTranslate

from ..services.client import APPS, DATA_CENTRES, Zoho, ZohoError, data_centre, exchange_grant_code

_logger = logging.getLogger(__name__)
_lt = LazyTranslate(__name__)

# which apps' scopes the grant asks for: Books always (Invoices & Payments needs it), the others when chosen
ALWAYS = ('books',)
# each app's card: where its organization ID is found (``{domain}``: the data centre's), and what the card says
ORG_URLS = {
    'books': 'https://books.{domain}/app#/organizations',
    'expense': 'https://expense.{domain}/app#/settings/organization',
    'shifts': 'https://shifts.{domain}/web/organizations',
}
# an app whose organization ID is usually another's (owner, 2026-10-26): filled in from it, a different one can be typed
ORG_SAME_AS = {'expense': 'books'}
ORG_HINTS = {
    'books': _lt("Zoho Books › your organizations: the Organization ID (also in Settings › Organization Profile)."),
    'expense': _lt("Zoho Expense › Settings › Organization Profile: the Organization ID."),
    'shifts': _lt("Zoho Shifts › Organizations: your organization's ID."),
}
ORG_ID_PATTERN = r'^\d{5,20}$'


class MtbgZohoSetup(models.AbstractModel):
    _name = 'mtbg.zoho.setup'
    _description = 'Zoho setup wizard'

    def _check(self):
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_("Only administrators can set up Zoho."))

    def _icp(self):
        return self.env['ir.config_parameter'].sudo()

    @api.model
    def _mtbg_scopes(self, apps):
        apps = [app for app in APPS if app in ALWAYS or app in (apps or [])]
        return ','.join(APPS[app]['scopes'] for app in apps)

    @api.model
    def _mtbg_granted(self, app):
        """Whether the login's grant has every permission of ``app`` (None: Zoho did not say which it has)."""
        granted = self._icp().get_param('mtbg_tours.zoho_granted_scopes') or ''
        if not granted.strip():
            return None
        have = {scope.lower() for scope in re.split(r'[\s,]+', granted) if scope}
        return all(scope.lower() in have for scope in APPS[app]['scopes'].split(','))

    @api.model
    def mtbg_setup_start(self):
        """What the wizard shows first: data centres, what is set, the apps (their cards' status)."""
        self._check()
        ICP = self._icp()
        accounts = (ICP.get_param('mtbg_tours.zoho_accounts_url') or 'https://accounts.zoho.com').rstrip('/')
        current = next((key for key, *_rest in DATA_CENTRES if data_centre(key)['accounts_url'] == accounts), 'us')
        books = Zoho(self.env, 'books')
        # a login saved; Zoho is not asked when the wizard opens (owner, 2026-10-26): Keep this login and Check
        # access try it
        connected, error = books.connected, ''
        used = set(json.loads(ICP.get_param('mtbg_tours.zoho_setup_apps') or '[]') or [])
        cards = {c['app'] for c in self.env['mtbg.zoho.subextension']._mtbg_cards() if c['status'] in ('built_in', 'installed')}
        dc = data_centre(current)
        apps = [{'code': app, 'label': APPS[app]['label'], 'always': app in ALWAYS,
                 'checked': app in ALWAYS or app in used or (not used and app in cards),
                 'needs_org': bool(APPS[app]['org_param']),
                 'org_url': ORG_URLS[app].format(domain=dc['domain']) if app in ORG_URLS else '',
                 'org_hint': self.env._(ORG_HINTS[app]) if app in ORG_HINTS else '',
                 'same_as': ORG_SAME_AS.get(app, ''), 'granted': connected and self._mtbg_granted(app) is not False}
                for app in APPS]
        return {
            'books_step': self._mtbg_books_step(),
            'data_centres': [data_centre(key) for key, *_rest in DATA_CENTRES], 'data_centre': current,
            'client_id': ICP.get_param('mtbg_tours.zoho_client_id') or '',
            'has_secret': bool(ICP.get_param('mtbg_tours.zoho_client_secret')),
            'connected': connected, 'connection_error': error, 'apps': apps, 'org_id_pattern': ORG_ID_PATTERN,
            'granted_scopes': ICP.get_param('mtbg_tours.zoho_granted_scopes') or '',
            'orgs': {app: Zoho(self.env, app).org_id for app in APPS if APPS[app]['org_param']},
        }

    @api.model
    def mtbg_setup_scopes(self, apps):
        """The scope string to paste into the Self Client's Generate Code."""
        self._check()
        return self._mtbg_scopes(apps)

    @api.model
    def mtbg_setup_connect(self, data_centre_key, client_id, client_secret, code, apps):
        """The grant code for a refresh token (the login every app and Invoices & Payments use), then each app's
        organizations."""
        self._check()
        ICP = self._icp()
        dc = data_centre(data_centre_key)
        client_id = (client_id or '').strip()
        client_secret = (client_secret or '').strip() or ICP.get_param('mtbg_tours.zoho_client_secret') or ''
        code = (code or '').strip()
        if not (client_id and client_secret and code):
            return {'ok': False, 'message': _("Paste the Client ID, the Client Secret and the code.")}
        try:
            token = exchange_grant_code(dc['accounts_url'], client_id, client_secret, code)
        except ZohoError as e:
            return {'ok': False, 'message': str(e)}
        expires = time.time() + max(300, int(token.get('expires_in', 3600)) - 120) if token.get('access_token') else 0
        for key, value in {
            'zoho_client_id': client_id, 'zoho_client_secret': client_secret, 'zoho_refresh_token': token['refresh_token'],
            'zoho_accounts_url': dc['accounts_url'], 'zoho_api_url': (token.get('api_domain') or dc['api_url']).rstrip('/'),
            'zoho_granted_scopes': token.get('scope') or self._mtbg_scopes(apps),
            'zoho_setup_apps': json.dumps(sorted(set(apps or []) | set(ALWAYS))),
        }.items():
            ICP.set_param(f'mtbg_tours.{key}', value)
        self.env['mtbg.zoho.token']._mtbg_set(token.get('access_token') or False, expires)
        return self.mtbg_setup_orgs()

    @api.model
    def mtbg_setup_orgs(self):
        """Each app's organizations the login reaches, and the one saved."""
        self._check()
        try:
            Zoho(self.env, 'books')._access_token()
        except ZohoError as e:
            _logger.info("Zoho setup: the saved login was refused: %s", e)
            return {'ok': False, 'message': _("Zoho refused the saved login: make a new grant code below.")}
        result = {'ok': True, 'orgs': {}, 'notes': []}
        for app, spec in APPS.items():
            if not spec['org_param']:
                continue
            zoho = Zoho(self.env, app)
            listed = []
            if self._mtbg_granted(app) is False:
                # not in this login's grant yet: Zoho is not asked (it would only refuse); the ID typed is kept
                result['notes'].append(_("%(app)s: this login does not have its permissions yet, so its organizations "
                                         "are not checked. The ID typed is kept; add the app with a new grant code to "
                                         "have it checked.", app=spec['label']))
            else:
                try:
                    listed = zoho.organizations()
                except ZohoError as e:
                    _logger.info("Zoho setup: %s organizations not listed: %s", app, e)
                    result['notes'].append(_("%(app)s: Zoho did not list its organizations, so the ID typed is kept "
                                             "unchecked. Check access, at the end, tries it.", app=spec['label']))
            result['orgs'][app] = {'label': spec['label'], 'listed': listed, 'value': zoho.org_id}
        return result

    @api.model
    def mtbg_setup_save_orgs(self, orgs):
        """Save each app's organization; then Invoices & Payments' Zoho Books choices (its own method)."""
        self._check()
        ICP = self._icp()
        for app, value in (orgs or {}).items():
            if app in APPS and APPS[app]['org_param']:
                ICP.set_param(f"mtbg_tours.{APPS[app]['org_param']}", (str(value or '')).strip() or False)
        books_org = (orgs or {}).get('books') or Zoho(self.env, 'books').org_id
        if not books_org:
            return {'ok': False, 'message': _("Choose the Zoho Books organization.")}
        return dict(self._mtbg_books_choices(books_org), ok=True)

    @api.model
    def mtbg_setup_finish(self, values, langs=None, contact_language_field=None, templates=None):
        """Invoices & Payments' choices (its own method, which checks its connection), then Check access per app."""
        self._check()
        books = self._mtbg_books_finish(values, langs, contact_language_field, templates)
        checks = {app: dict(Zoho(self.env, app).probe(), at=fields.Datetime.to_string(fields.Datetime.now())) for app in APPS}
        self._icp().set_param('mtbg_tours.zoho_access_check', json.dumps(checks))
        return {'books': books, 'access': [{'app': APPS[app]['label'], **check} for app, check in checks.items()]}

    # ------------------------------------------------------------------ an extension's own Zoho Books step
    @api.model
    def _mtbg_books_step(self):
        """Whether an extension brings its own Zoho Books choices to the wizard (its card before Check access)."""
        return False

    @api.model
    def _mtbg_books_choices(self, books_org):
        """That step's choices (an extension's override), {} without one."""
        return {}

    @api.model
    def _mtbg_books_finish(self, values, langs=None, contact_language_field=None, templates=None):
        """That step saved (an extension's override), None without one."""
        return None
