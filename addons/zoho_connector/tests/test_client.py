from datetime import timedelta
from unittest.mock import MagicMock, patch

from odoo import fields
from odoo.tests import TransactionCase, tagged

from odoo.addons.zoho_connector.services import client as zoho_client
from odoo.addons.zoho_connector.services.client import Zoho, ZohoError, ZohoWriteBlocked


def answer(status=200, body=None, headers=None):
    res = MagicMock()
    res.status_code, res.headers = status, headers or {}
    res.content = b'{}'
    res.json.return_value = body if body is not None else {'code': 0}
    return res


class ZohoCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ICP = cls.env['ir.config_parameter']
        # a neutral connection: a copy of a site may hold real values
        ICP.search([('key', '=like', 'mtbg\\_tours.zoho\\_%')]).unlink()
        for key, value in {'zoho_client_id': 'cid', 'zoho_client_secret': 'secret', 'zoho_refresh_token': 'refresh',
                           'zoho_org_id': 'ORG_BOOKS', 'zoho_expense_org_id': 'ORG_EXP', 'zoho_shifts_org_id': 'ORG_SH',
                           }.items():
            ICP.set_param(f'mtbg_tours.{key}', value)
        cls.env['mtbg.zoho.token']._mtbg_set('TOKEN', 9999999999.0)
        zoho_client._calls.clear()

    def setUp(self):
        super().setUp()
        sleep = patch.object(zoho_client, '_sleep')
        self.sleep = sleep.start()
        self.addCleanup(sleep.stop)
        zoho_client._calls.clear()

    def switch(self, app, on=True, writes=False):
        ICP = self.env['ir.config_parameter']
        ICP.set_param(f'mtbg_tours.zoho_{app}_enabled', '1' if on else '0')
        ICP.set_param(f'mtbg_tours.zoho_{app}_writes', '1' if writes else '0')


@tagged('post_install', '-at_install', 'mtbg')
class TestZohoClient(ZohoCase):

    def test_switches_and_writes(self):
        books = Zoho(self.env, 'books')
        self.assertFalse(books.enabled, "every app starts off")
        with patch.object(zoho_client.requests, 'request') as req:
            with self.assertRaisesRegex(ZohoError, 'off or not connected'):
                books.request('GET', 'projects')
            self.switch('books')
            with self.assertRaises(ZohoWriteBlocked):
                books.request('POST', 'projects', json={})
            self.assertFalse(req.called, "nothing reaches Zoho while off or with writes off")
            req.return_value = answer(body={'code': 0, 'projects': []})
            books.request('GET', 'projects')
            self.assertEqual(req.call_count, 1)

    def test_organization_and_base_per_app(self):
        for app in ('books', 'expense', 'shifts'):
            self.switch(app)
        with patch.object(zoho_client.requests, 'request', return_value=answer()) as req:
            Zoho(self.env, 'books').request('GET', 'projects')
            Zoho(self.env, 'expense').request('GET', 'expensereports')
            Zoho(self.env, 'shifts').request('GET', 'settings/jobsites')
        (books, expense, shifts) = req.call_args_list
        self.assertEqual(books.args[1], 'https://www.zohoapis.com/books/v3/projects')
        self.assertEqual(books.kwargs['params']['organization_id'], 'ORG_BOOKS')
        self.assertEqual(expense.args[1], 'https://www.zohoapis.com/expense/v1/expensereports')
        self.assertEqual(expense.kwargs['headers']['X-com-zoho-expense-organizationid'], 'ORG_EXP')
        self.assertEqual(shifts.args[1], 'https://shifts.zoho.com/api/v1/ORG_SH/settings/jobsites')
        self.assertEqual(books.kwargs['headers']['Authorization'], 'Zoho-oauthtoken TOKEN',
                         "the access token Invoices & Payments cached is shared")

    def test_probe_sends_no_paging_to_shifts(self):
        """Check access: Zoho Shifts refuses any parameter it does not know ("Extra parameter found in URL")."""
        with patch.object(zoho_client.requests, 'request', return_value=answer()) as req:
            for app in ('books', 'shifts'):
                self.assertTrue(Zoho(self.env, app).probe()['ok'], app)
        (books, shifts) = req.call_args_list
        self.assertEqual(books.kwargs['params'].get('per_page'), 1)
        self.assertFalse(shifts.kwargs.get('params'), "nothing in the Shifts address but its path")

    def test_file_upload(self):
        """A receipt goes up as a multipart form, never as JSON (Payroll's Record payment)."""
        self.switch('books', writes=True)
        receipt = {'receipt': ('voucher.pdf', b'%PDF-1.4', 'application/pdf')}
        with patch.object(zoho_client.requests, 'request', return_value=answer()) as req:
            Zoho(self.env, 'books').request('POST', 'expenses/1/receipt', files=receipt)
        self.assertEqual(req.call_args.kwargs['files'], receipt)
        self.assertIsNone(req.call_args.kwargs['json'])

    def test_retries_and_no_double_write(self):
        self.switch('books', writes=True)
        books = Zoho(self.env, 'books')
        busy, ok = answer(429, {'code': 44, 'message': 'Too many requests'}, {'Retry-After': '2'}), answer()
        with patch.object(zoho_client.requests, 'request', side_effect=[busy, ok]) as req:
            books.request('POST', 'projects', json={'project_name': 'x'})
        self.assertEqual(req.call_count, 2, "too many requests: the same call again")
        self.sleep.assert_any_call(2.0)
        with patch.object(zoho_client.requests, 'request', side_effect=[answer(500, {'code': 1}), ok]) as req:
            books.request('GET', 'projects')
        self.assertEqual(req.call_count, 2, "a read is tried again after a Zoho failure")
        with patch.object(zoho_client.requests, 'request', side_effect=[answer(500, {'code': 1, 'message': 'boom'})]) as req, \
                self.assertRaisesRegex(ZohoError, 'boom'):
            books.request('POST', 'projects', json={})
        self.assertEqual(req.call_count, 1, "a write is never sent twice")

    def test_pacing(self):
        self.env['ir.config_parameter'].set_param('mtbg_tours.zoho_rate_limit', '2')
        books = Zoho(self.env, 'books')
        clock = [100.0]
        self.sleep.side_effect = lambda seconds: clock.__setitem__(0, clock[0] + seconds)
        with patch.object(zoho_client.time, 'monotonic', side_effect=lambda: clock[0]):
            books._pace()
            books._pace()
            self.assertFalse(self.sleep.called)
            books._pace()
        self.assertTrue(self.sleep.called, "the third call of the minute waits for the minute to pass")
        self.assertGreaterEqual(clock[0], 160)

    def test_log_keeps_writes_and_failures(self):
        self.switch('books', writes=True)
        Log = self.env['mtbg.zoho.log']
        Log.search([]).unlink()
        books = Zoho(self.env, 'books')
        with patch.object(zoho_client.requests, 'request', return_value=answer()):
            books.request('GET', 'projects')
            self.assertFalse(Log.search([]), "a read that worked is not logged")
            books.request('POST', 'projects', json={})
        with patch.object(zoho_client.requests, 'request', return_value=answer(400, {'code': 1001, 'message': 'Bad'})):
            try:  # not assertRaises: it rolls back to a savepoint (as a failed sync does; the log has its own cursor)
                books.request('GET', 'projects')
            except ZohoError:
                pass
            else:
                self.fail("a refusal raises")
        logs = Log.search([], order='id')
        self.assertEqual([(l.method, l.ok) for l in logs], [('POST', True), ('GET', False)])
        self.assertIn('1001 Bad', logs[1].message)

    def test_scope_check(self):
        with patch.object(zoho_client.requests, 'request', side_effect=[
                answer(), answer(401, {'code': 'OAUTH_SCOPE_MISMATCH', 'message': 'scope'}), answer(), answer()]):
            settings = self.env['res.config.settings'].create({})
            settings.action_mtbg_zoho_check_access()
        settings = self.env['res.config.settings'].create({})
        self.assertIn('Zoho Books: ok (off)', settings.mtbg_zoho_access_info, "checked while the app is still off")
        self.assertIn('Zoho Expense: scope missing', settings.mtbg_zoho_access_info)
        self.assertIn('ZohoExpense.project.READ', settings.mtbg_zoho_scopes_needed)
        self.assertFalse(Zoho(self.env, 'books').enabled, "a check does not switch anything on")


@tagged('post_install', '-at_install', 'mtbg')
class TestZohoToken(ZohoCase):
    """The access token is renewed without a system parameter: Odoo's caches (the website's pages) stay warm."""

    def _renewed(self, service):
        self.env['mtbg.zoho.token']._mtbg_set('OLD', 1.0)  # ended
        answer = MagicMock(status_code=200)
        answer.json.return_value = {'access_token': 'NEW', 'expires_in': 3600, 'scope': 'ZohoBooks.fullaccess.all'}
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('mtbg_tours.zoho_granted_scopes', 'ZohoBooks.fullaccess.all')  # (as saved: no change)
        self.env.flush_all()
        self.env.registry.cache_invalidated.clear()
        with patch('requests.post', return_value=answer) as post:
            self.assertEqual(service._access_token(), 'NEW')
            self.assertEqual(service._access_token(), 'NEW', "kept: no second refresh")
        self.assertEqual(post.call_count, 1)
        self.env.flush_all()
        self.assertFalse(self.env.registry.cache_invalidated, "no cache emptied by the renewal")
        token, expires = self.env['mtbg.zoho.token']._mtbg_get()
        self.assertEqual(token, 'NEW')
        self.assertGreater(expires, 1000)
        self.assertFalse(ICP.search([('key', 'in', ('mtbg_tours.zoho_access_token',
                                                    'mtbg_tours.zoho_access_token_expires'))]))

    def test_connector_renewal_keeps_the_caches(self):
        self._renewed(Zoho(self.env, 'books'))


@tagged('post_install', '-at_install', 'mtbg')
class TestConnectorAlone(ZohoCase):
    """The connector on a site with no other Zoho extension: the wizard has no Zoho Books step, the references
    retry nothing on their own, the cards come only from extensions."""

    def test_wizard_without_a_books_step(self):
        start = self.env['mtbg.zoho.setup'].mtbg_setup_start()
        if 'mtbg.invoice.settings.page' in self.env:
            self.skipTest("an extension brings its Zoho Books step here")
        self.assertFalse(start['books_step'])
        self.assertEqual(self.env['mtbg.zoho.setup']._mtbg_books_choices('ORG'), {})
        self.assertIsNone(self.env['mtbg.zoho.setup']._mtbg_books_finish({}))

    def test_references(self):
        Ref = self.env['mtbg.zoho.ref']
        partner = self.env['res.partner'].create({'name': 'Zoho ref test'})
        ref = Ref._mtbg_set(partner, 'books', 'contact', state='error', zoho_id='C1', error='Refused')
        self.assertEqual(Ref._mtbg_set(partner, 'books', 'contact', state='done'), ref, "one per record, app and kind")
        self.assertEqual(Ref._mtbg_records('books', 'contact', 'res.partner', 'C1'), partner)
        self.assertEqual(Ref.browse(ref.id)._mtbg_retry(), ref, "nobody here retries a contact: returned")
        self.assertTrue(Ref._mtbg_zoho_manager(), "administrators")

    def test_takeover_hook(self):
        from odoo.addons.zoho_connector import hooks
        cr = self.env.cr
        cr.execute("""INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
                      VALUES ('mgu_old_zoho', 'model_mtbg_zoho_ref', 'ir.model', 1, false),
                             ('mgu_old_zoho', 'field_mtbg_zoho_ref__zoho_id', 'ir.model.fields', 1, false),
                             ('mgu_old_zoho', 'view_unrelated', 'ir.ui.view', 1, false)""")
        exact, patterns = hooks.moved_names(cr)
        cr.execute("DELETE FROM ir_model_data WHERE module = 'mgu_new_zoho'")
        moved = hooks.move_into(cr, 'mgu_old_zoho', 'mgu_new_zoho', exact, patterns)
        self.assertEqual(moved, 2)
        cr.execute("SELECT module, name FROM ir_model_data WHERE module LIKE 'mgu\\_%zoho' ORDER BY name")
        self.assertEqual(cr.fetchall(), [('mgu_new_zoho', 'field_mtbg_zoho_ref__zoho_id'),
                                         ('mgu_new_zoho', 'model_mtbg_zoho_ref'), ('mgu_old_zoho', 'view_unrelated')])

    def test_settings_section(self):
        view = self.env.ref('zoho_connector.view_zoho_settings')
        self.assertIn('name="zoho_connector"', view.arch, "an app of the main Settings")
        self.assertIn("'module': 'zoho_connector'", self.env.ref('zoho_connector.action_zoho_settings').context)


from odoo.tests import HttpCase  # noqa: E402


@tagged('post_install', '-at_install', 'mtbg')
class TestZohoSettingsPage(HttpCase):
    """Settings › Zoho on a site with the connector alone: the wizard opens, its cards slide, no Zoho Books step of
    another extension's."""

    def test_wizard_opens(self):
        if 'mtbg.invoice.settings.page' in self.env:
            self.skipTest("an extension brings its Zoho Books step here")
        code = """
            const deadline = Date.now() + 20000;
            let clicked = false;
            (function check() {
                const button = [...document.querySelectorAll('button')].find((b) => b.textContent.includes('Set up Zoho'));
                if (button && !clicked) { button.click(); clicked = true; }
                const steps = [...document.querySelectorAll('.mtbg_zs_step')];
                const permissions = steps.find((s) => s.textContent.includes('Permissions'));
                const invoices = steps.find((s) => s.textContent.includes('Invoices'));
                if (steps.length >= 6 && permissions && permissions.disabled && !invoices) {
                    console.log('test successful');
                } else if (Date.now() > deadline) {
                    console.error('test failed: steps ' + steps.length + ' invoices step: ' + !!invoices);
                } else { setTimeout(check, 300); }
            })();
        """
        self.browser_js('/odoo/action-zoho_connector.action_zoho_settings', code,
                        ready="document.readyState === 'complete'", login='admin', timeout=90)
