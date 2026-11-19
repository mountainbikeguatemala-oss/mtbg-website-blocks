"""Single sign-on: the ticket (who may have one, hashed, once, 60 seconds) and the sign-in link over real HTTP."""
from datetime import timedelta
from urllib.parse import urlparse

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.http import root
from odoo.tests import HttpCase, new_test_user, tagged

from odoo.addons.site_link_connector.models.site_link_sso import sso_hash

SSO = 'site_link_connector.group_site_link_sso'


@tagged('post_install', '-at_install')
class TestSiteLinkSso(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.link_user = new_test_user(cls.env, 'slc_sso_link', groups='base.group_user,'
                                      'site_link_connector.group_site_link_remote')
        cls.mechanic = new_test_user(cls.env, 'slc.mechanic@example.com', groups=f'base.group_user,{SSO}')
        cls.no_group = new_test_user(cls.env, 'slc.nogroup@example.com', groups='base.group_user')
        cls.portal = new_test_user(cls.env, 'slc.portal@example.com', groups=f'base.group_portal,{SSO}')
        cls.admin = cls.env.ref('base.user_admin')
        cls.root_user = cls.env.ref('base.user_root')
        (cls.admin | cls.root_user).write({'group_ids': [(4, cls.env.ref(SSO).id)]})
        cls.Api = cls.env['site.link.api'].with_user(cls.link_user)
        cls.Ticket = cls.env['site.link.sso.ticket'].sudo()

    def ticket_fails(self, login):
        """The refusal (not assertRaises: its savepoint would take the refusal's log row away)."""
        try:
            self.Api.sso_ticket(login)
        except UserError as exc:
            return exc
        self.fail("UserError not raised")

    def open_link(self, url):
        res = self.url_open(url, allow_redirects=False)
        self.assertIn(res.status_code, (302, 303))
        return urlparse(res.headers['Location']).path

    def session_uid(self):
        sid = self.opener.cookies.get('session_id')
        return root.session_store.get(sid).uid if sid else None

    def sso_logs(self, user):
        return self.env['site.link.log'].search([('kind', '=', 'sso'), ('user_id', '=', user.id)])

    def test_ticket_signs_in_once(self):
        answer = self.Api.sso_ticket(' SLC.Mechanic@Example.com ')
        self.assertEqual(answer['expires_in'], 60)
        self.assertTrue(answer['url'].startswith('/site_link/sso/'))
        token = answer['url'].rsplit('/', 1)[1]
        self.assertGreaterEqual(len(token), 40)
        ticket = self.Ticket.search([('user_id', '=', self.mechanic.id)])
        self.assertEqual(len(ticket), 1)
        self.assertEqual(ticket.token_hash, sso_hash(token), "only the token's hash is kept")
        self.assertNotIn(token, ticket.token_hash)
        self.assertFalse(ticket.used_at)

        self.assertEqual(self.open_link(answer['url']), '/odoo')
        self.assertEqual(self.session_uid(), self.mechanic.id)
        self.assertTrue(ticket.used_at)

        # the same link again: refused, the login page
        self.opener.cookies.clear()
        self.assertEqual(self.open_link(answer['url']), '/web/login')
        self.assertFalse(self.session_uid())
        logs = self.sso_logs(self.mechanic)
        self.assertEqual(sorted(logs.mapped('method')), ['sso_login', 'sso_login', 'sso_ticket'])
        self.assertEqual(sorted(logs.mapped('status')), [200, 200, 410])

    def test_unknown_link(self):
        self.assertEqual(self.open_link('/site_link/sso/not-a-token'), '/web/login')
        self.assertFalse(self.session_uid())

    def test_ticket_expires(self):
        answer = self.Api.sso_ticket(self.mechanic.login)
        ticket = self.Ticket.search([('user_id', '=', self.mechanic.id)])
        self.assertAlmostEqual(ticket.expires_at, fields.Datetime.now() + timedelta(seconds=60),
                               delta=timedelta(seconds=5))
        ticket.expires_at = fields.Datetime.now() - timedelta(seconds=1)
        self.assertEqual(self.open_link(answer['url']), '/web/login')
        self.assertFalse(self.session_uid())
        self.assertIn(410, self.sso_logs(self.mechanic).mapped('status'))

    def test_who_may_not(self):
        for user in (self.root_user, self.admin, self.no_group, self.portal):
            with self.subTest(user=user.login):
                exc = self.ticket_fails(user.login)
                self.assertIn('No single sign-on', exc.args[0])
                self.assertEqual(self.sso_logs(user).mapped('status'), [403])
        self.assertIn('no such user', self.ticket_fails('nobody@example.com').args[0])
        self.assertIn('superuser or admin', self.ticket_fails(self.admin.login).args[0])
        self.mechanic.active = False
        self.assertIn('archived', self.ticket_fails(self.mechanic.login).args[0])
        self.assertFalse(self.Ticket.search([]), "no ticket was given")

    def test_blocked_at_sign_in_too(self):
        """A ticket made some other way for a blocked user, or a user taken out of the group after the ticket was
        given: the sign-in refuses it."""
        for user in (self.admin, self.root_user):
            token = self.Ticket._site_link_issue(user)
            self.assertEqual(self.open_link(f'/site_link/sso/{token}'), '/web/login')
            self.assertFalse(self.session_uid())
        answer = self.Api.sso_ticket(self.mechanic.login)
        self.mechanic.write({'group_ids': [(3, self.env.ref(SSO).id)]})
        self.assertEqual(self.open_link(answer['url']), '/web/login')
        self.assertFalse(self.session_uid())
        self.assertEqual(self.sso_logs(self.mechanic).filtered(lambda l: l.method == 'sso_login').status, 403)

    def test_caller_needs_the_group(self):
        with self.assertRaises(AccessError):
            self.env['site.link.api'].with_user(self.no_group).sso_ticket(self.mechanic.login)

    def test_caller_helper(self):
        """site.link._site_link_sso_url: the other site's address and the ticket's path (call mocked)."""
        from unittest.mock import patch
        site = self.env['site.link'].create({'name': 'Shop', 'base_url': 'https://shop.example.com/',
                                             'api_key': 'K', 'role': 'inventory_source'})
        with patch.object(type(self.env['site.link']), '_site_link_call',
                          return_value={'url': '/site_link/sso/abc', 'expires_in': 60}) as call:
            url = self.env['site.link']._site_link_sso_url('slc.mechanic@example.com')
        self.assertEqual(url, 'https://shop.example.com/site_link/sso/abc')
        self.assertEqual(call.call_args.args, (site, 'site.link.api', 'sso_ticket'))
        self.assertEqual(call.call_args.kwargs, {'login': 'slc.mechanic@example.com'})

    # ------------------------------------------------------------------ return address, start, login page button

    def test_sign_in_redirect_is_local(self):
        for redirect, expected in (('/odoo/action-base.action_res_users', '/odoo/action-base.action_res_users'),
                                   ('https://evil.example.com/x', '/odoo'), ('//evil.example.com/x', '/odoo'),
                                   ('/\\evil.example.com', '/odoo')):
            with self.subTest(redirect=redirect):
                self.opener.cookies.clear()
                url = self.Api.sso_ticket(self.mechanic.login)['url']
                res = self.url_open(url, params={'redirect': redirect}, allow_redirects=False)
                location = urlparse(res.headers['Location'])
                self.assertEqual(location.path, expected.split('?')[0])
                self.assertIn(location.netloc, ('', urlparse(self.base_url()).netloc))

    def start(self, target):
        return self.url_open('/site_link/sso/start', params={'return': target}, allow_redirects=False)

    def test_start(self):
        from unittest.mock import patch
        shop = self.env['site.link'].create({'name': 'Shop', 'base_url': 'https://shop.example.com',
                                             'api_key': 'K', 'role': 'inventory_source'})
        Site = type(self.env['site.link'])
        good = 'https://shop.example.com/odoo/inventory'
        # not signed in here: the login page first, then back to the start
        res = self.start(good)
        self.assertEqual(urlparse(res.headers['Location']).path, '/web/login')
        self.assertIn('site_link%2Fsso%2Fstart', res.headers['Location'])
        self.authenticate(self.mechanic.login, self.mechanic.login)
        with patch.object(Site, '_site_link_call', return_value={'url': '/site_link/sso/TOKEN', 'expires_in': 60}) \
                as call:
            for evil in ('https://evil.example.com/odoo', 'https://shop.example.com.evil.example.com/',
                         'https://shop.example.com@evil.example.com/', '//shop.example.com/odoo',
                         'http://shop.example.com/odoo', 'https://shop.example.com:8443/', 'javascript:alert(1)', '',
                         'https://shop.example.com:443.evil.example.com/'):
                with self.subTest(evil=evil):
                    self.assertEqual(self.start(evil).status_code, 403)
            call.assert_not_called()
            res = self.start(good)
        self.assertEqual(res.headers['Location'], 'https://shop.example.com/site_link/sso/TOKEN'
                                                  '?return=%2Fodoo%2Finventory&redirect=%2Fodoo%2Finventory')
        self.assertEqual(call.call_args.args, (shop, 'site.link.api', 'sso_ticket'))
        self.assertEqual(call.call_args.kwargs, {'login': self.mechanic.login})

    def test_login_page_button(self):
        res = self.url_open('/web/login')
        self.assertNotIn('o_site_link_staff_login', res.text)
        self.env['site.link'].create({'name': 'Staff', 'base_url': 'https://staff.example.com', 'api_key': 'K',
                                      'role': 'staff_source'})
        res = self.url_open('/web/login')
        self.assertIn('Log in with your staff account', res.text)
        self.assertIn('https://staff.example.com/site_link/sso/start?return=', res.text)

    def test_administrators_never(self):
        """Settings or Access Rights rights: no ticket, and no sign-in with a ticket given before the rights came."""
        settings = new_test_user(self.env, 'slc.owner@example.com', groups=f'base.group_system,{SSO}')
        rights = new_test_user(self.env, 'slc.rights@example.com', groups=f'base.group_erp_manager,{SSO}')
        for user in (settings, rights):
            with self.subTest(user=user.login):
                self.assertIn('administrator', self.ticket_fails(user.login).args[0])
        self.assertFalse(self.Ticket.search([('user_id', 'in', (settings | rights).ids)]))
        answer = self.Api.sso_ticket(self.mechanic.login)
        self.mechanic.write({'group_ids': [(4, self.env.ref('base.group_system').id)]})
        self.assertEqual(self.open_link(answer['url']), '/web/login')
        self.assertFalse(self.session_uid())
        self.assertIn('administrator', self.sso_logs(self.mechanic).filtered(
            lambda l: l.method == 'sso_login').message)

    # ------------------------------------------------------------------ both ways (19.0.0.2.4)

    def test_sign_in_return(self):
        """``return`` (and ``redirect``, its older name): a path here or a full address on this site's own host;
        anything else opens /odoo and is logged."""
        own = self.base_url().rstrip('/')
        for params, expected in (({'return': '/odoo/action-base.action_res_users?x=1'},
                                  '/odoo/action-base.action_res_users?x=1'),
                                 ({'return': own + '/odoo/settings?a=b'}, '/odoo/settings?a=b'),
                                 ({'return': '/odoo/a', 'redirect': '/odoo/b'}, '/odoo/a'),
                                 ({'redirect': '/odoo/b'}, '/odoo/b'),
                                 ({'return': 'https://evil.example.com/odoo'}, '/odoo'),
                                 ({'return': own.replace('http://', 'https://') + '/odoo/x'}, '/odoo'),
                                 ({'return': own + '.evil.example.com/odoo'}, '/odoo'),
                                 ({'return': '//evil.example.com/odoo'}, '/odoo')):
            with self.subTest(params=params):
                self.opener.cookies.clear()
                url = self.Api.sso_ticket(self.mechanic.login)['url']
                res = self.url_open(url, params=params, allow_redirects=False)
                location = urlparse(res.headers['Location'])
                self.assertIn(location.netloc, ('', urlparse(self.base_url()).netloc))
                self.assertEqual(location.path + ('?' + location.query if location.query else ''), expected)
                self.assertEqual(self.session_uid(), self.mechanic.id)
        refused = self.sso_logs(self.mechanic).filtered(lambda l: l.status == 400)
        self.assertEqual(len(refused), 4)
        self.assertIn('evil.example.com', refused.sorted('id')[0].message)

    def test_start_fallback(self):
        """``fallback=1``: no ticket there for this login, the address opens as it is (logged); without it the error
        page."""
        from unittest.mock import patch
        from odoo.addons.site_link_connector.models.site_link import SiteLinkError
        self.env['site.link'].create({'name': 'Tours', 'base_url': 'https://staff.example.com', 'api_key': 'K',
                                      'role': 'staff_source'})
        Site = type(self.env['site.link'])
        target = 'https://staff.example.com/odoo/action-x?staff_mode=tour'
        # not signed in: the login page keeps the fallback for the way back
        res = self.url_open('/site_link/sso/start', params={'return': target, 'fallback': '1'},
                            allow_redirects=False)
        self.assertIn('fallback%3D1', res.headers['Location'])
        self.authenticate(self.mechanic.login, self.mechanic.login)
        refusal = SiteLinkError("Tours: No single sign-on for x: administrator.", 422)
        with patch.object(Site, '_site_link_call', side_effect=refusal):
            res = self.url_open('/site_link/sso/start', params={'return': target, 'fallback': '1'},
                                allow_redirects=False)
            self.assertEqual(res.headers['Location'], target)
            res = self.url_open('/site_link/sso/start', params={'return': target}, allow_redirects=False)
            self.assertEqual(res.status_code, 502)
        log = self.sso_logs(self.mechanic).filtered(lambda l: l.method == 'sso_start')
        self.assertEqual(log.status, 422)
        self.assertIn('opened https://staff.example.com/odoo/action-x', log.message)
        with patch.object(Site, '_site_link_call', return_value={'url': '/site_link/sso/T', 'expires_in': 60}):
            res = self.url_open('/site_link/sso/start', params={'return': target, 'fallback': '1'},
                                allow_redirects=False)
        self.assertEqual(res.headers['Location'], 'https://staff.example.com/site_link/sso/T?return='
                         '%2Fodoo%2Faction-x%3Fstaff_mode%3Dtour&redirect=%2Fodoo%2Faction-x%3Fstaff_mode%3Dtour')
