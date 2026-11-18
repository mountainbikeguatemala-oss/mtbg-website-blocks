"""Customer repairs: the quotation (made once per reference, changed while it is a quotation), its status and its
invoice (made once, never sent), with Repair and without it (soft), and without Sales (soft)."""
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.site_link_connector.models.site_link_api import SiteLinkApi

PIXEL = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='


@tagged('post_install', '-at_install')
class TestSiteLinkRepair(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.link_user = new_test_user(cls.env, 'slc_repair_link', groups='base.group_user,'
                                      'site_link_connector.group_site_link_remote')
        cls.Api = cls.env['site.link.api'].with_user(cls.link_user)
        if 'sale.order' not in cls.env:
            return
        cls.customer = cls.env['res.partner'].create({'name': 'Repair Customer', 'email': 'rc.slc@example.com'})
        cls.pad = cls.env['product.product'].create({
            'name': 'Brake pad SLC', 'barcode': 'SLC-R-0001', 'type': 'consu', 'is_storable': True,
            'list_price': 20.0, 'standard_price': 8.0, 'invoice_policy': 'delivery',
        })
        cls.chain = cls.env['product.product'].create({
            'name': 'Chain SLC', 'barcode': 'SLC-R-0002', 'type': 'consu', 'is_storable': True,
            'list_price': 35.0, 'invoice_policy': 'delivery',
        })
        cls.wash = cls.env['product.product'].create({'name': 'Bike wash SLC', 'barcode': 'SLC-R-0003',
                                                      'type': 'service', 'list_price': 10.0})
        cls.stock = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1).lot_stock_id
        cls.env['stock.quant']._update_available_quantity(cls.pad, cls.stock, 10)
        cls.env['stock.quant']._update_available_quantity(cls.chain, cls.stock, 5)
        cls.lines = [{'product': 'SLC-R-0001', 'qty': 2}, {'service': 'Brake bleed', 'price': 50.0, 'hours': 1.5}]

    def setUp(self):
        super().setUp()
        if 'sale.order' not in self.env:
            self.skipTest("Sales is not installed on this database")

    def orders(self, reference):
        return self.env['sale.order'].search([('client_order_ref', '=', reference)])

    def product_lines(self, order):
        return {(line.product_id.name, line.name, line.product_uom_qty, line.price_unit)
                for line in order.order_line if not line.display_type}

    def notes(self, order):
        return '\n'.join(order.order_line.filtered('display_type').mapped('name'))

    def accept(self, order):
        """The customer accepts the quotation (as on the portal: signed, then confirmed)."""
        order.write({'signature': PIXEL, 'signed_by': 'Repair Customer', 'signed_on': fields.Datetime.now()})
        order.action_confirm()

    def assert_nothing_sent(self, *records):
        mails = self.env['mail.mail'].search([('recipient_ids', 'in', self.customer.id)])
        self.assertFalse(mails, "no email to the customer")
        for record in records:
            self.assertNotIn(self.customer, record.message_partner_ids, "the customer follows nothing")
            self.assertFalse(record.message_ids.filtered(lambda m: self.customer in m.partner_ids))

    def test_health_lists_repair_methods(self):
        methods = self.Api.health()['methods']
        for method in ('repair_quote', 'repair_status', 'repair_invoice', 'sso_ticket', 'customer_search'):
            self.assertIn(method, methods)

    def test_quote_once_per_reference(self):
        first = self.Api.repair_quote('WO-1', self.customer.id, self.lines, note='Front brake squeals')
        order = self.env['sale.order'].browse(first['order_id'])
        self.assertEqual(first['state'], 'draft')
        self.assertEqual(first['name'], order.name)
        self.assertEqual(first['currency'], order.currency_id.name)
        self.assertEqual(first['amount_total'], order.amount_total)
        self.assertIn(f"/my/orders/{order.id}", first['portal_url'])
        self.assertIn('access_token=', first['portal_url'])
        self.assertEqual(order.partner_id, self.customer)
        self.assertEqual(self.product_lines(order), {
            ('Brake pad SLC', 'Brake pad SLC', 2.0, 20.0),
            ('Repair labour', 'Brake bleed (1.5 h)', 1.0, 50.0),
        })
        self.assertIn('Front brake squeals', self.notes(order))
        if 'repair.order' in self.env:
            repair = order.repair_order_ids
            self.assertEqual(len(repair), 1)
            self.assertEqual(repair.partner_id, self.customer)
            self.assertEqual(repair.move_ids.product_id, self.pad)

        # the same call again: the same quotation, nothing changed
        written = order.write_date
        self.assertEqual(self.Api.repair_quote('WO-1', self.customer.id, self.lines, note='Front brake squeals'),
                         first)
        self.assertEqual(order.write_date, written)
        self.assertEqual(self.orders('WO-1'), order)

        # other lines, same reference: the same quotation, its lines changed
        changed = self.Api.repair_quote('WO-1', self.customer.id, [
            {'product': self.pad.id, 'qty': 1}, {'product': 'SLC-R-0002', 'qty': 1}, {'product': 'SLC-R-0003', 'qty': 1},
            {'product': 'SLC-R-0001', 'qty': 2},
        ], bike='Red hardtail, size M')
        self.assertEqual(changed['order_id'], order.id)
        self.assertEqual(self.orders('WO-1'), order)
        self.assertEqual(self.product_lines(order), {
            ('Brake pad SLC', 'Brake pad SLC', 3.0, 20.0),
            ('Chain SLC', 'Chain SLC', 1.0, 35.0),
            ('Bike wash SLC', 'Bike wash SLC', 1.0, 10.0),
        })
        self.assertEqual(changed['amount_total'], order.amount_total)
        self.assertIn('Bike: Red hardtail, size M', self.notes(order))
        if 'repair.order' in self.env:
            self.assertEqual(len(order.repair_order_ids), 1)
            self.assertEqual(sorted(order.repair_order_ids.move_ids.mapped('product_uom_qty')), [1.0, 3.0])
        self.assertEqual(self.env['site.link.repair'].search_count([('reference', '=', 'WO-1')]), 1)
        self.assertEqual(self.pad.qty_available, 10, "a quotation takes nothing out of stock")
        self.assert_nothing_sent(order)

    def test_status_and_invoice(self):
        quote = self.Api.repair_quote('WO-2', self.customer.id, self.lines)
        order = self.env['sale.order'].browse(quote['order_id'])
        status = self.Api.repair_status('WO-2')
        self.assertEqual(status, {'name': order.name, 'state': 'draft', 'approved': False, 'invoiced': False,
                                  'paid': False, 'amount_total': order.amount_total,
                                  'portal_url': quote['portal_url']})
        with self.assertRaisesRegex(UserError, 'not accepted yet'):
            self.Api.repair_invoice('WO-2')
        with self.assertRaisesRegex(UserError, 'No repair quote'):
            self.Api.repair_status('WO-NOPE')

        self.accept(order)
        self.assertTrue(self.Api.repair_status('WO-2')['approved'])
        # accepted: the same lines answer as before, other lines are refused
        self.assertEqual(self.Api.repair_quote('WO-2', self.customer.id, self.lines)['order_id'], order.id)
        with self.assertRaisesRegex(UserError, 'can no longer change'):
            self.Api.repair_quote('WO-2', self.customer.id, [{'product': 'SLC-R-0002', 'qty': 1}])

        invoice_answer = self.Api.repair_invoice('WO-2')
        invoice = self.env['account.move'].browse(invoice_answer['invoice_id'])
        self.assertEqual(invoice_answer['state'], 'draft', "made, never posted or sent")
        self.assertEqual(invoice.state, 'draft')
        self.assertEqual(invoice.move_type, 'out_invoice')
        self.assertEqual(invoice_answer['amount_total'], order.amount_total)
        self.assertEqual(set(invoice.invoice_line_ids.filtered(lambda l: l.display_type == 'product').mapped('quantity')),
                         {2.0, 1.0})
        self.assertIn(self.pad, invoice.invoice_line_ids.product_id, "the parts are invoiced")
        if 'repair.order' in self.env:
            self.assertEqual(order.repair_order_ids.state, 'done')
            self.assertEqual(self.pad.qty_available, 8, "the finished repair took its parts out of stock")
        # again: the same invoice, no second one
        self.assertEqual(self.Api.repair_invoice('WO-2'), invoice_answer)
        self.assertEqual(len(order.invoice_ids), 1)
        status = self.Api.repair_status('WO-2')
        self.assertTrue(status['invoiced'])
        self.assertFalse(status['paid'])
        self.assert_nothing_sent(order, invoice)
        self.assertFalse(self.env['mail.mail'].search([('model', 'in', ['sale.order', 'account.move']),
                                                       ('res_id', 'in', [order.id, invoice.id])]))

    def test_without_repair(self):
        """Repair not installed (soft): the quotation alone, its lines straight on it."""
        self.pad.invoice_policy = 'order'
        with patch.object(SiteLinkApi, '_site_link_has_repair', return_value=False):
            quote = self.Api.repair_quote('WO-3', self.customer.id, self.lines, note='No repair module')
            order = self.env['sale.order'].browse(quote['order_id'])
            if 'repair.order' in self.env:
                self.assertFalse(order.repair_order_ids)
            self.assertEqual(self.product_lines(order), {
                ('Brake pad SLC', 'Brake pad SLC', 2.0, 20.0),
                ('Repair labour', 'Brake bleed (1.5 h)', 1.0, 50.0),
            })
            self.Api.repair_quote('WO-3', self.customer.id, [{'service': 'Tune-up', 'price': 30}])
            self.assertEqual(self.product_lines(order), {('Repair labour', 'Tune-up', 1.0, 30.0)})
            self.accept(order)
            first = self.Api.repair_invoice('WO-3')
            self.assertEqual(first['amount_total'], order.amount_total)
            self.assertEqual(self.Api.repair_invoice('WO-3')['invoice_id'], first['invoice_id'])
            self.assertEqual(len(order.invoice_ids), 1)

    def test_without_sales(self):
        with patch.object(SiteLinkApi, '_site_link_has_sales', return_value=False):
            self.assertNotIn('repair_quote', self.Api.health()['methods'])
            for call in (lambda: self.Api.repair_quote('WO-4', self.customer.id, self.lines),
                         lambda: self.Api.repair_status('WO-4'), lambda: self.Api.repair_invoice('WO-4')):
                with self.assertRaisesRegex(UserError, 'has no Sales'):
                    call()
        self.assertFalse(self.env['site.link.repair'].search([('reference', '=', 'WO-4')]))

    def test_checks(self):
        bad = [
            ('', self.customer.id, self.lines, {}),
            ('WO-5', 999999999, self.lines, {}),
            ('WO-5', self.customer.id, [], {}),
            ('WO-5', self.customer.id, [{'product': 'NO-SUCH', 'qty': 1}], {}),
            ('WO-5', self.customer.id, [{'product': 'SLC-R-0001', 'qty': 0}], {}),
            ('WO-5', self.customer.id, [{'service': '', 'price': 1}], {}),
            ('WO-5', self.customer.id, [{'service': 'x', 'price': -1}], {}),
            ('WO-5', self.customer.id, [{'qty': 1}], {}),
        ]
        if 'repair.bike' not in self.env:
            bad.append(('WO-5', self.customer.id, self.lines, {'bike': 12}))
        for reference, partner, lines, kw in bad:
            with self.subTest(lines=lines, kw=kw), self.assertRaises(UserError):
                self.Api.repair_quote(reference, partner, lines, **kw)
        self.assertFalse(self.orders('WO-5'))
        # a quote of reference A belongs to its customer
        self.Api.repair_quote('WO-6', self.customer.id, self.lines)
        other = self.env['res.partner'].create({'name': 'Someone else'})
        with self.assertRaisesRegex(UserError, "Repair Customer's quotation"):
            self.Api.repair_quote('WO-6', other.id, self.lines)

    def test_caller_helpers(self):
        """site.link's one-line helpers call the protocol method with its named arguments (call mocked)."""
        site = self.env['site.link'].create({'name': 'Shop', 'base_url': 'https://shop.example.com',
                                             'api_key': 'K', 'role': 'inventory_source'})
        Site = self.env['site.link']
        with patch.object(type(Site), '_site_link_call', return_value={'ok': 1}) as call:
            Site._site_link_repair_quote('WO-7', 5, self.lines, note='n')
            self.assertEqual(call.call_args.args, ('inventory_source', 'site.link.api', 'repair_quote'))
            self.assertEqual(call.call_args.kwargs, {'reference': 'WO-7', 'partner_id': 5, 'lines': self.lines,
                                                     'note': 'n', 'bike': None})
            Site._site_link_repair_status('WO-7', site=site)
            self.assertEqual(call.call_args.args, (site, 'site.link.api', 'repair_status'))
            Site._site_link_repair_invoice('WO-7')
            Site._site_link_customer_search('ana', limit=3)
            self.assertEqual(call.call_args.kwargs, {'query': 'ana', 'limit': 3})
            Site._site_link_customer_create('Ana', phone='1')
            Site._site_link_customer_bikes(5)
            self.assertEqual(call.call_args.kwargs, {'partner_id': 5})
        health = {'protocol': 1, 'methods': ['health', 'repair_quote']}
        with patch.object(type(Site), '_site_link_call', return_value=health):
            self.assertTrue(Site._site_link_offers('repair_quote'))
            self.assertFalse(Site._site_link_offers('sso_ticket'))
        self.assertFalse(Site._site_link_offers('repair_quote', site='no_such_role'))

    def test_customer_bike(self):
        """Where a customer bike model is installed (another extension): the contact's bikes, and the quote's bike
        on its repair order."""
        if 'repair.bike' not in self.env or 'bike_id' not in self.env['repair.order']._fields:
            self.skipTest("No customer bike model on this database")
        bike = self.env['repair.bike'].create({'partner_id': self.customer.id, 'frame_serial': 'FR-SLC-1'})
        self.assertEqual(self.Api.customer_bikes(self.customer.id),
                         [{'id': bike.id, 'name': bike.display_name, 'serial': 'FR-SLC-1'}])
        quote = self.Api.repair_quote('WO-8', self.customer.id, self.lines, bike=bike.id)
        self.assertEqual(self.env['sale.order'].browse(quote['order_id']).repair_order_ids.bike_id, bike)
        other = self.env['res.partner'].create({'name': 'Other owner'})
        other_bike = self.env['repair.bike'].create({'partner_id': other.id})
        with self.assertRaisesRegex(UserError, 'is not'):
            self.Api.repair_quote('WO-9', self.customer.id, self.lines, bike=other_bike.id)
