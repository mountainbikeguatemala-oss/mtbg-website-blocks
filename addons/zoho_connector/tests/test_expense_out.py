"""Expenses recorded in Odoo (0.3.0): the categories and payment methods read from Zoho Books. The sending itself is
tested where a model has the expense mixin (the shop's used purchases); Zoho is never called (mocks)."""
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.zoho_connector.services import client as zoho_client

from .test_books import books_answers
from .test_client import ZohoCase


@tagged('post_install', '-at_install', 'mtbg')
class TestExpenseLists(ZohoCase):

    def test_sync_categories_and_methods(self):
        Category = self.env['mtbg.expense.category']
        Method = self.env['mtbg.expense.method']
        with self.assertRaises(UserError):
            Category.action_mtbg_zoho_sync()  # Zoho Books off
        self.switch('books')
        own = Category.create({'name': 'ZZ Used parts', 'zoho_account_id': 'ZZ_A1'})
        request, calls = books_answers({
            'chartofaccounts': {'chartofaccounts': [
                {'account_id': 'ZZ_A1', 'account_name': 'Parts', 'account_type': 'expense'},
                {'account_id': 'ZZ_A2', 'account_name': 'Consumables', 'account_type': 'cost_of_goods_sold'},
                {'account_id': 'ZZ_A3', 'account_name': 'Sales', 'account_type': 'income'}]},
            'bankaccounts': {'bankaccounts': [
                {'account_id': 'ZZ_B1', 'account_name': 'Shop cash', 'account_type': 'cash', 'currency_code': 'USD'},
                {'account_id': 'ZZ_B2', 'account_name': 'Loan', 'account_type': 'other_current_liability'}]},
        })
        with patch.object(zoho_client.requests, 'request', side_effect=request):
            Category.action_mtbg_zoho_sync()
            Category.action_mtbg_zoho_sync()
            Method.action_mtbg_zoho_sync()
        self.assertEqual(own.name, 'ZZ Used parts', "a known one keeps its name here")
        self.assertEqual(own.zoho_account_name, 'Parts')
        new = Category.search([('zoho_account_id', '=', 'ZZ_A2')])
        self.assertEqual(len(new), 1, "read again: never twice")
        self.assertFalse(new.in_app, "a category read from Zoho is not offered until ticked")
        self.assertFalse(Category.search([('zoho_account_id', '=', 'ZZ_A3')]), "only expense accounts")
        cash = Method.search([('zoho_paid_through_id', '=', 'ZZ_B1')])
        self.assertEqual((cash.name, cash.currency_id.name, cash.in_app), ('Shop cash', 'USD', False))
        self.assertFalse(Method.search([('zoho_paid_through_id', '=', 'ZZ_B2')]))
        self.assertEqual({m for m, _p in calls}, {'GET'}, "read only")
