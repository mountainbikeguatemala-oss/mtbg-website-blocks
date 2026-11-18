"""End to end, no mocks of Odoo: the site linked to itself through the test server, Odoo's real /json/2 and a real
API key. (The test server only answers requests carrying its test cookie: the helper's requests go through the
test's own HTTP session, unchanged otherwise.)"""
from datetime import datetime, timedelta
from unittest.mock import patch

from odoo.tests import HttpCase, new_test_user, tagged

from odoo.addons.site_link_connector.models import site_link as site_link_module
from odoo.addons.site_link_connector.models.site_link import SiteLinkError


@tagged('post_install', '-at_install')
class TestSiteLinkHttp(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        user = new_test_user(cls.env, 'site_link_http', groups='base.group_user,'
                             'site_link_connector.group_site_link_remote')
        key = cls.env['res.users.apikeys'].with_user(user)._generate(
            scope='rpc', name='site link test', expiration_date=datetime.now() + timedelta(days=1))
        cls.site = cls.env['site.link'].create({
            'name': 'Myself', 'base_url': cls.base_url(), 'db_name': cls.env.cr.dbname, 'api_key': key,
            'role': 'other',
        })

    def setUp(self):
        super().setUp()
        patcher = patch.object(site_link_module.requests, 'post', side_effect=self.opener.post)
        patcher.start()
        self.addCleanup(patcher.stop)

    def call(self, method, **kw):
        return self.env['site.link']._site_link_call(self.site, 'site.link.api', method, **kw)

    def call_fails(self, method, **kw):
        try:
            self.call(method, **kw)
        except SiteLinkError as exc:
            return exc
        self.fail("SiteLinkError not raised")

    def test_health_over_http(self):
        health = self.call('health')
        self.assertEqual(health['database'], self.env.cr.dbname)
        self.assertEqual(health['user'], 'site_link_http')
        self.assertIn('health', health['methods'])
        self.assertEqual(health['methods'] == ['health'], 'stock.move' not in self.env)
        self.site.action_test_connection()
        self.assertTrue(self.site.last_check_ok, self.site.last_check_message)

    def test_errors_over_http(self):
        self.assertEqual(self.call_fails('no_such_method').status, 404)
        if 'stock.move' in self.env:
            exc = self.call_fails('part_consume', product='NO-SUCH-BARCODE', qty=1, reference='HTTP-1')
            self.assertIn('No product NO-SUCH-BARCODE', exc.args[0])
        else:
            exc = self.call_fails('part_lookup', barcode='X')
            self.assertIn('has no Inventory', exc.args[0])
        self.site.api_key = 'wrong'
        self.assertEqual(self.call_fails('health').status, 401)
        statuses = self.env['site.link.log'].search([('site_id', '=', self.site.id)]).mapped('status')
        self.assertEqual(len(statuses), 3)
        self.assertIn(401, statuses)
        self.assertIn(404, statuses)
