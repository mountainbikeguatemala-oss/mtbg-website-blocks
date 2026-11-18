"""Zoho Books expenses (Import & Sync) and the vendors' Zoho Books link, on the connector alone (0.2.0): no other
extension is needed; Zoho is never called (every request is a mock)."""
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.zoho_connector.services import client as zoho_client

from .test_client import ZohoCase, answer


def books_answers(routes):
    """A requests.request mock answering by the path's end (``routes``: {path: body}); records every call."""
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url.split('/books/v3/')[-1]))
        path = url.split('/books/v3/')[-1]
        return answer(body=dict({'code': 0}, **routes.get(path, {})))
    return request, calls


@tagged('post_install', '-at_install', 'mtbg')
class TestBooksExpenses(ZohoCase):

    def setUp(self):
        super().setUp()
        self.Account = self.env['mtbg.zoho.books.account']
        self.Run = self.env['mtbg.zoho.books.import']
        # the copy of a site may hold categories and runs of its own
        self.Account.with_context(active_test=False).search([]).write({'sync': False})

    def test_categories_read_only_and_never_twice(self):
        with self.assertRaises(UserError):
            self.Account.mtbg_read_accounts()  # Zoho Books off
        self.switch('books')
        request, calls = books_answers({'chartofaccounts': {'chartofaccounts': [
            {'account_id': 'ZZ_A1', 'account_name': 'Fuel'}, {'account_id': 'ZZ_A2', 'account_name': 'Office'}]}})
        with patch.object(zoho_client.requests, 'request', side_effect=request):
            self.assertEqual(self.Account.mtbg_read_accounts(), 2)
            self.assertEqual(self.Account.mtbg_read_accounts(), 2)
        accounts = self.Account.search([('zoho_account_id', 'in', ('ZZ_A1', 'ZZ_A2'))])
        self.assertEqual(len(accounts), 2, "read again: never twice")
        self.assertEqual(set(accounts.mapped('destination')), {'skip'}, "nothing brought in until told where")
        self.assertEqual({m for m, _p in calls}, {'GET'}, "read only")
        keys = [k for k, _l in self.Account._mtbg_destination_selection()]
        self.assertTrue({'skip', 'internal'} <= set(keys))

    def test_a_run_brings_lines_to_their_destination_and_review(self):
        self.switch('books')
        account = self.Account.create({'zoho_account_id': 'ZZ_A1', 'name': 'Fuel'})
        partner = self.env['res.partner'].create({'name': 'ZZ sent'})
        # an expense Odoo sent itself is never brought back in
        self.env['mtbg.zoho.ref']._mtbg_set(partner, 'books', 'staff_expense', state='done', zoho_id='ZZ_E2')
        request, calls = books_answers({
            'expenses': {'expenses': [
                {'expense_id': 'ZZ_E1', 'account_id': 'ZZ_A1', 'account_name': 'Fuel', 'date': '2026-11-01'},
                {'expense_id': 'ZZ_E2', 'account_id': 'ZZ_A1', 'account_name': 'Fuel', 'date': '2026-11-01'},
                {'expense_id': 'ZZ_E3', 'account_id': 'ZZ_OTHER', 'account_name': 'Rent', 'date': '2026-11-01'}]},
            'expenses/ZZ_E1': {'expense': {'expense_id': 'ZZ_E1', 'date': '2026-11-01', 'currency_code': 'GTQ',
                                           'vendor_name': 'Gas station', 'line_items': [
                                               {'line_item_id': 'L1', 'account_id': 'ZZ_A1', 'amount': 150,
                                                'description': 'Diesel'}]}},
            'expenses/ZZ_E2': {'expense': {'expense_id': 'ZZ_E2', 'line_items': [
                {'line_item_id': 'L2', 'account_id': 'ZZ_A1', 'amount': 10}]}},
        })
        Account = type(account)
        with patch.object(zoho_client.requests, 'request', side_effect=request), \
                patch.object(Account, '_mtbg_import_line', autospec=True, return_value=('review', 'not sure')):
            run = self.Run.create({'account_ids': [(6, 0, account.ids)]})._mtbg_run_all()
        self.assertEqual(run.state, 'done', run.message)
        self.assertEqual((run.expense_total, run.expense_done, run.skipped_count), (2, 2, 1),
                         "the other category's expense never read; the one Odoo sent skipped")
        self.assertNotIn(('GET', 'expenses/ZZ_E3'), calls)
        self.assertEqual({m for m, _p in calls}, {'GET'}, "read only")
        self.assertEqual(run.review_ids.mapped('zoho_line_id'), ['ZZ_E1:L1'])
        self.assertEqual((run.review_ids.amount, run.review_ids.vendor), (150.0, 'Gas station'))
        self.assertTrue(account.sync, "kept in sync from now on")
        ICP = self.env['ir.config_parameter']
        self.assertTrue(ICP.get_param('mtbg_tours.zoho_books_expenses_first_sync'))
        run.review_ids.action_skip()
        run.invalidate_recordset(['review_ids'])
        self.assertFalse(run.review_ids)
        settings = self.env['res.config.settings'].create({})
        self.assertIn('Fuel', settings.mtbg_zoho_expenses_sync_info)

    def test_only_zoho_managers_import(self):
        account = self.Account.create({'zoho_account_id': 'ZZ_A9', 'name': 'Nine'})
        user = self.env['res.users'].create({'name': 'ZZ user', 'login': 'zz_books_user',
                                             'group_ids': [(6, 0, [self.env.ref('base.group_user').id])]})
        run = self.Run.create({'account_ids': [(6, 0, account.ids)]})
        with self.assertRaises(UserError):
            run.with_user(user).action_import()
        self.assertEqual(run.state, 'draft')

    def test_jobs_and_pages_are_the_connectors(self):
        for xmlid in ('cron_zoho_books_import', 'cron_zoho_books_expenses_sync', 'action_books_import',
                      'action_books_accounts', 'view_books_import_form', 'view_books_review_list'):
            self.assertTrue(self.env.ref(f'zoho_connector.{xmlid}', raise_if_not_found=False), xmlid)
        view = self.env.ref('zoho_connector.view_zoho_settings')
        self.assertIn('name="mtbg_zoho_books_expenses"', view.arch)
        action = self.env['res.config.settings'].create({}).action_mtbg_zoho_expense_categories()
        self.assertEqual(action['res_model'], 'mtbg.zoho.books.account')


@tagged('post_install', '-at_install', 'mtbg')
class TestVendors(ZohoCase):

    def test_vendor_found_or_made_by_name(self):
        self.switch('books', writes=True)
        partner = self.env['res.partner'].create({'name': 'ZZ Ferretería Central', 'is_company': True})
        request, calls = books_answers({'contacts': {'contacts': [], 'contact': {'contact_id': 'ZZ_V1'}}})
        with patch.object(zoho_client.requests, 'request', side_effect=request):
            vendor_id = partner._mtbg_zoho_vendor_ensure(zoho_client.Zoho(self.env, 'books'))
        self.assertEqual(vendor_id, 'ZZ_V1')
        self.assertEqual(partner.mtbg_zoho_vendor_id, 'ZZ_V1', "linked on the contact")
        self.assertEqual([m for m, _p in calls], ['GET', 'POST'], "looked up by name first, then made")
        with patch.object(zoho_client.requests, 'request') as req:
            self.assertEqual(partner._mtbg_zoho_vendor_ensure(zoho_client.Zoho(self.env, 'books')), 'ZZ_V1')
            self.assertFalse(req.called, "known: no call")

    def test_waiting_vendors_wait_for_writes(self):
        self.switch('books', writes=False)
        partner = self.env['res.partner'].create({'name': 'ZZ Waiting Vendor', 'is_company': True})
        Ref = self.env['mtbg.zoho.ref']
        Ref._mtbg_set(partner, 'books', 'vendor_out', state='waiting')
        request, _calls = books_answers({'contacts': {'contacts': []}})
        with patch.object(zoho_client.requests, 'request', side_effect=request):
            self.env['res.partner']._mtbg_zoho_push_vendors(zoho_client.Zoho(self.env, 'books'))
        ref = Ref._mtbg_find(partner, 'books', 'vendor_out')
        self.assertEqual(ref.state, 'waiting', "writes off: it waits")
        self.assertFalse(partner.mtbg_zoho_vendor_id)

    def test_no_vendor_tick_nothing_queued(self):
        if 'mtbg_is_vendor' in self.env['res.partner']._fields:
            self.skipTest("an extension gives contacts a vendor tick")
        partner = self.env['res.partner'].create({'name': 'ZZ Plain', 'is_company': True})
        self.assertFalse(self.env['mtbg.zoho.ref']._mtbg_find(partner, 'books', 'vendor_out'))


@tagged('post_install', '-at_install', 'mtbg')
class TestTakeover(ZohoCase):

    def test_books_names_and_tables_move(self):
        from odoo.addons.zoho_connector import hooks
        cr = self.env.cr
        exact, patterns = hooks.moved_names(cr)
        for name in ('model_mtbg_zoho_books_account', 'model_mtbg_zoho_books_import', 'model_mtbg_zoho_books_review',
                     'cron_zoho_books_import', 'cron_zoho_books_import_ir_actions_server', 'action_books_import',
                     'field_res_partner__mtbg_zoho_vendor_id', 'field_res_users__mtbg_zoho_vendor_id',
                     'field_res_config_settings__mtbg_zoho_expenses_sync_info'):
            self.assertIn(name, exact)
        cr.execute("""INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
                      VALUES ('mgu_old_zoho', 'field_mtbg_zoho_books_account__name', 'ir.model.fields', 1, false),
                             ('mgu_old_zoho', 'view_books_import_form', 'ir.ui.view', 1, false),
                             ('mgu_old_zoho', 'field_res_partner__mtbg_zoho_vendor_id', 'ir.model.fields', 1, false),
                             ('mgu_old_zoho', 'constraint_mtbg_zoho_books_account_account_uniq', 'ir.model.constraint', 1,
                              false),
                             ('mgu_old_zoho', 'view_departure_unrelated', 'ir.ui.view', 1, false)""")
        self.assertEqual(hooks.move_into(cr, 'mgu_old_zoho', 'mgu_new_zoho', exact, patterns), 4)
        cr.execute("SELECT name FROM ir_model_data WHERE module = 'mgu_old_zoho'")
        self.assertEqual(cr.fetchall(), [('view_departure_unrelated',)])
        # the table constraints and many2many tables
        for name in ('mgu_old_zoho', 'mgu_new_zoho'):
            cr.execute("INSERT INTO ir_module_module (name, state) VALUES (%s, 'uninstalled')", [name])
        cr.execute("""INSERT INTO ir_model_constraint (name, model, module, type)
                      SELECT 'mgu_zz_con', m.id, o.id, 'u' FROM ir_model m, ir_module_module o
                       WHERE m.model = 'mtbg.zoho.books.account' AND o.name = 'mgu_old_zoho'""")
        cr.execute("""INSERT INTO ir_model_relation (name, model, module)
                      SELECT 'mgu_zz_rel', m.id, o.id FROM ir_model m, ir_module_module o
                       WHERE m.model = 'mtbg.zoho.books.import' AND o.name = 'mgu_old_zoho'""")
        self.assertEqual(hooks.move_tables(cr, 'mgu_old_zoho', 'mgu_new_zoho', hooks.TABLE_MODELS), 2)
        cr.execute("""SELECT count(*) FROM ir_model_constraint c JOIN ir_module_module m ON m.id = c.module
                       WHERE m.name = 'mgu_new_zoho'""")
        self.assertEqual(cr.fetchone()[0], 1)
