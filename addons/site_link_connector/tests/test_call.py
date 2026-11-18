"""The call helper, with the HTTP mocked: what is sent, what comes back, the errors and the log of failed calls."""
from unittest.mock import MagicMock, patch

import requests

from odoo.tests import TransactionCase, tagged

from odoo.addons.site_link_connector.models import site_link as site_link_module
from odoo.addons.site_link_connector.models.site_link import SiteLinkError


def answer(status=200, body=None, headers=None, text=''):
    res = MagicMock()
    res.status_code, res.headers, res.text = status, headers or {}, text
    res.content = b'x' if body is not None else b''
    if isinstance(body, Exception):
        res.json.side_effect = body
    else:
        res.json.return_value = body
    return res


@tagged('post_install', '-at_install')
class TestSiteLinkCall(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Site = cls.env['site.link']
        cls.Site.with_context(active_test=False).search([]).unlink()
        cls.site = cls.Site.create({
            'name': 'Other', 'base_url': 'https://other.example.com/', 'db_name': 'other_db',
            'api_key': 'KEY123', 'role': 'inventory_source', 'timeout': 7,
        })

    def post(self, *answers):
        patcher = patch.object(site_link_module.requests, 'post', side_effect=list(answers))
        mock = patcher.start()
        self.addCleanup(patcher.stop)
        return mock

    def call_fails(self, *args, **kw):
        """The call's SiteLinkError. (Not assertRaises: it rolls back its savepoint, and the failed call's log with
        it, as the caller's own transaction would roll back; the log is kept apart from that.)"""
        try:
            self.Site._site_link_call(*args, **kw)
        except SiteLinkError as exc:
            return exc
        self.fail("SiteLinkError not raised")

    def logs(self):
        return self.env['site.link.log'].search([('site_id', '=', self.site.id)])

    def test_call_sends_json2(self):
        post = self.post(answer(200, {'found': False, 'barcode': 'B1'}))
        result = self.Site._site_link_call(self.site, 'site.link.api', 'part_lookup', barcode='B1')
        self.assertEqual(result, {'found': False, 'barcode': 'B1'})
        args, kw = post.call_args
        self.assertEqual(args[0], 'https://other.example.com/json/2/site.link.api/part_lookup')
        self.assertEqual(kw['json'], {'barcode': 'B1'})
        self.assertEqual(kw['headers']['Authorization'], 'bearer KEY123')
        self.assertEqual(kw['headers']['X-Odoo-Database'], 'other_db')
        self.assertEqual(kw['timeout'], 7)
        self.assertFalse(kw['allow_redirects'])
        self.assertFalse(self.logs(), "a call that worked is not logged")

    def test_call_by_role_and_ids(self):
        post = self.post(answer(200, [{'id': 3}]))
        self.Site._site_link_call('inventory_source', 'res.partner', 'read', [3, 4], fields=['name'])
        self.assertEqual(post.call_args[1]['json'], {'fields': ['name'], 'ids': [3, 4]})
        with self.assertRaises(SiteLinkError):
            self.Site._site_link_call('inventory_source', 'res.partner', 'read', 'not-an-id')
        with self.assertRaises(SiteLinkError):
            self.Site._site_link_call('no_such_role', 'res.partner', 'read')

    def test_errors_are_clear_and_logged(self):
        cases = [
            (answer(401, {'name': 'werkzeug.exceptions.Unauthorized', 'message': 'Invalid apikey'}), 'refused the API key'),
            (answer(404, {'name': 'werkzeug.exceptions.NotFound', 'message': 'nope'}), 'has no site.link.api.health'),
            (answer(403, {'name': 'odoo.exceptions.AccessError', 'message': 'no group'}), 'may not do this'),
            (answer(500, {'name': 'builtins.ValueError', 'message': 'boom'}), 'HTTP 500'),
            (answer(301, None, headers={'Location': 'https://www.other.example.com/json/2/x/y'}), 'redirect'),
            (answer(200, ValueError('no json')), 'not JSON'),
            (requests.Timeout('slow'), 'did not answer within 7 seconds'),
            (requests.ConnectionError('refused'), 'cannot be reached'),
        ]
        for res, expected in cases:
            with self.subTest(expected=expected):
                self.post(res)
                exc = self.call_fails(self.site, 'site.link.api', 'health')
                self.assertIn(expected, exc.args[0])
                log = self.logs()[:1]
                self.assertIn(expected, log.message)
                self.assertEqual((log.model, log.method), ('site.link.api', 'health'))
        self.assertEqual(len(self.logs()), len(cases))
        self.assertEqual(self.logs()[-1].status, 401)

    def test_no_key_no_call(self):
        self.site.api_key = False
        post = self.post()
        self.call_fails(self.site, 'site.link.api', 'health')
        post.assert_not_called()
        self.assertEqual(len(self.logs()), 1)

    def test_log_in_its_own_cursor(self):
        """A committed site's failed call is logged through a cursor of its own (in tests: the registry's test
        cursor), so the caller's rollback does not take it away."""
        self.post(answer(500, {'name': 'x', 'message': 'boom'}))
        with self.enter_registry_test_mode():
            self.call_fails(self.site, 'site.link.api', 'health')
        self.assertEqual(self.logs().mapped('status'), [500])

    def test_test_connection(self):
        health = {'protocol': 1, 'database': 'other_db', 'odoo_version': '19.0', 'module_version': '19.0.0.1.0',
                  'user': 'link', 'methods': ['health', 'part_lookup', 'part_consume']}
        self.post(answer(200, health))
        action = self.site.action_test_connection()
        self.assertEqual(action['params']['type'], 'success')
        self.assertTrue(self.site.last_check_ok)
        self.assertIn('part_lookup', self.site.last_check_message)
        # an inventory source without inventory methods, from another database: not OK
        self.post(answer(200, dict(health, database='else', methods=['health'])))
        action = self.site.action_test_connection()
        self.assertEqual(action['params']['type'], 'danger')
        self.assertFalse(self.site.last_check_ok)
        self.assertIn('not other_db', self.site.last_check_message)
        # an error: shown, not raised
        self.post(answer(401, {'name': 'x', 'message': 'Invalid apikey'}))
        action = self.site.action_test_connection()
        self.assertEqual(action['params']['type'], 'danger')
        self.assertIn('refused the API key', self.site.last_check_message)
