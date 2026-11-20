"""One Zoho login for both sites (owner, 2026-11-20: "link via the site api the two sites zoho permission"): the
site with the login answers ``zoho_request`` for a link that may use it; the other site's Zoho Connector sends its
calls there. Needs Zoho Connector (skipped without it); Zoho and the link's HTTP are mocks."""
import base64
from unittest.mock import MagicMock, patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged


def zoho_answer(body):
    res = MagicMock()
    res.status_code, res.headers, res.content = 200, {}, b'{}'
    res.json.return_value = dict({'code': 0}, **body)
    return res


@tagged('post_install', '-at_install')
class TestZohoShare(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if 'mtbg.zoho.ref' not in cls.env:
            return
        from odoo.addons.zoho_connector.services import client
        cls.client = client
        ICP = cls.env['ir.config_parameter']
        ICP.search([('key', '=like', 'mtbg\\_tours.zoho\\_%')]).unlink()
        cls.Site = cls.env['site.link']
        cls.Site.with_context(active_test=False).search([]).unlink()
        cls.Api = cls.env['site.link.api']

    def setUp(self):
        super().setUp()
        if 'mtbg.zoho.ref' not in self.env:
            self.skipTest("Zoho Connector is not installed")
        sleep = patch.object(self.client, '_sleep')
        sleep.start()
        self.addCleanup(sleep.stop)
        self.client._calls.clear()

    def login_here(self, writes=True):
        ICP = self.env['ir.config_parameter']
        for key, value in {'zoho_client_id': 'cid', 'zoho_client_secret': 's', 'zoho_refresh_token': 'r',
                           'zoho_org_id': 'ORG', 'zoho_books_enabled': '1',
                           'zoho_books_writes': '1' if writes else '0'}.items():
            ICP.set_param(f'mtbg_tours.{key}', value)
        self.env['mtbg.zoho.token']._mtbg_set('TOKEN', 9999999999.0)

    def test_answering_side(self):
        self.login_here()
        link = self.Site.create({'name': 'Shop', 'base_url': 'https://shop.example.com', 'api_key': 'K',
                                 'role': 'other'})
        self.assertNotIn('zoho_request', self.Api._site_link_methods(), "not shared until ticked")
        with self.assertRaises(UserError):
            self.Api.zoho_request('books', 'GET', 'expenses')
        link.share_zoho = True
        self.assertIn('zoho_request', self.Api._site_link_methods())
        sent = []

        def request(method, url, **kwargs):
            sent.append((method, url.split('/books/v3/')[-1], kwargs.get('params'), kwargs.get('files')))
            return zoho_answer({'expense': {'expense_id': 'E1'}, 'expenses': []})

        caller = new_test_user(self.env, 'slc_zoho_caller', groups='base.group_user,'
                               'site_link_connector.group_site_link_remote')
        with patch.object(self.client.requests, 'request', side_effect=request):
            # the other site's technical user (no Zoho rights of its own)
            answer = self.Api.with_user(caller).zoho_request('books', 'POST', 'expenses', json={'amount': 5})
            self.assertEqual(answer['body']['expense']['expense_id'], 'E1')
            self.Api.zoho_request('books', 'POST', 'expenses/460000000012345/receipt',
                                  files={'receipt': ['r.jpg', base64.b64encode(b'JPG').decode(), 'image/jpeg']})
            self.Api.zoho_request('books', 'GET', 'chartofaccounts')
        self.assertEqual(sent[0][2].get('organization_id'), 'ORG', "this site's organization")
        self.assertEqual(sent[1][3]['receipt'], ('r.jpg', b'JPG', 'image/jpeg'))
        for method, path in (('POST', 'invoices'), ('DELETE', 'contacts/9'), ('PUT', 'chartofaccounts/1')):
            with self.assertRaises(UserError):
                self.Api.zoho_request('books', method, path)
        with self.assertRaises(UserError):
            self.Api.zoho_request('crm', 'GET', 'Leads')
        self.login_here(writes=False)
        with patch.object(self.client.requests, 'request', side_effect=request):
            self.assertIn('blocked', self.Api.zoho_request('books', 'POST', 'expenses', json={}))

    def test_using_side(self):
        """No Zoho login here: the link that may use the other site's; every call goes there."""
        ICP = self.env['ir.config_parameter']
        ICP.set_param('mtbg_tours.zoho_books_enabled', '1')
        books = self.client.Zoho(self.env, 'books')
        self.assertFalse(books.enabled, "no login, no link")
        link = self.Site.create({'name': 'Tours site', 'base_url': 'https://tours.example.com', 'api_key': 'K',
                                 'role': 'staff_source', 'use_zoho': True})
        books = self.client.Zoho(self.env, 'books')
        self.assertEqual(books.via, link)
        self.assertTrue(books.enabled and books.connected)
        self.assertFalse(books.writes)
        with self.assertRaises(self.client.ZohoWriteBlocked):
            books.request('POST', 'expenses', json={})  # Writes allowed off here: never sent
        ICP.set_param('mtbg_tours.zoho_books_writes', '1')
        calls = []

        def post(url, json=None, headers=None, **kwargs):
            """The other site's /json/2 (the real _site_link_call runs; only the network is faked)."""
            calls.append((url, json, headers))
            if json['path'] == 'expenses' and json['verb'] == 'POST':
                answer = {'body': {'code': 0, 'expense': {'expense_id': 'E7'}}}
            elif json['path'] == 'contacts':
                answer = {'error': 'Zoho Books GET contacts: 401 57 not authorised'}
            else:
                answer = {'blocked': 'writes are off there'}
            res = MagicMock()
            res.status_code, res.content = 200, b'x'
            res.json.return_value = answer
            return res

        books = self.client.Zoho(self.env, 'books')
        from odoo.addons.site_link_connector.models import site_link as site_link_module
        with patch.object(site_link_module.requests, 'post', side_effect=post):
            body = books.request('POST', 'expenses', json={'amount': 3},
                                 files={'receipt': ('r.jpg', b'JPG', 'image/jpeg')})
            self.assertEqual(body['expense']['expense_id'], 'E7')
            with self.assertRaises(self.client.ZohoError):
                books.request('GET', 'contacts')
            with self.assertRaises(self.client.ZohoWriteBlocked):
                books.request('PUT', 'expenses/7', json={})
        url, kwargs, headers = calls[0]
        self.assertEqual(url, 'https://tours.example.com/json/2/site.link.api/zoho_request')
        self.assertEqual((kwargs['app'], kwargs['verb'], kwargs['path']), ('books', 'POST', 'expenses'))
        self.assertEqual(headers['Authorization'], 'bearer K')
        self.assertEqual(kwargs['files']['receipt'], ['r.jpg', base64.b64encode(b'JPG').decode(), 'image/jpeg'])
        # what the other site receives is exactly what zoho_request takes
        import inspect
        self.assertLessEqual(set(kwargs), set(inspect.signature(type(self.Api).zoho_request).parameters) - {'self'})
        self.assertNotIn('organization_id', kwargs.get('params') or {}, "the other site adds its own")
