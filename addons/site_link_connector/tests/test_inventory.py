"""The protocol's inventory side (where Inventory is installed): lookup, consumption and its idempotency."""
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestSiteLinkInventory(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # the other site's technical user: the group only, no Inventory rights
        cls.link_user = new_test_user(cls.env, 'site_link_tech', groups='base.group_user,'
                                      'site_link_connector.group_site_link_remote')
        cls.plain_user = new_test_user(cls.env, 'site_link_plain', groups='base.group_user')
        cls.Api = cls.env['site.link.api'].with_user(cls.link_user)
        if 'stock.move' not in cls.env:
            return
        cls.vendor = cls.env['res.partner'].create({'name': 'Parts Vendor'})
        cls.product = cls.env['product.product'].create({
            'name': 'Brake pad', 'default_code': 'BP-1', 'barcode': 'SLC-0001', 'type': 'consu',
            'is_storable': True, 'standard_price': 12.5, 'list_price': 20.0,
            'seller_ids': [(0, 0, {'partner_id': cls.vendor.id, 'price': 10.0})],
        })
        cls.stock = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1).lot_stock_id
        cls.env['stock.quant']._update_available_quantity(cls.product, cls.stock, 10)

    def setUp(self):
        super().setUp()
        if 'stock.move' not in self.env:
            self.skipTest("Inventory is not installed on this database")

    def test_health_lists_inventory_methods(self):
        health = self.Api.health()
        self.assertEqual(health['protocol'], 1)
        self.assertEqual(health['database'], self.env.cr.dbname)
        self.assertEqual(health['methods'][:8], ['health', 'sso_ticket', 'user_sync', 'customer_search',
                                                 'customer_create', 'customer_bikes', 'part_lookup', 'part_consume'])
        self.assertEqual('repair_quote' in health['methods'], 'sale.order' in self.env)

    def test_caller_needs_the_group(self):
        Api = self.env['site.link.api'].with_user(self.plain_user)
        for call in (Api.health, lambda: Api.part_lookup('SLC-0001'),
                     lambda: Api.part_consume('SLC-0001', 1, 'REF-X')):
            with self.assertRaises(AccessError):
                call()

    def test_lookup(self):
        found = self.Api.part_lookup('SLC-0001')
        self.assertTrue(found['found'])
        self.assertEqual(found['id'], self.product.id)
        self.assertEqual(found['default_code'], 'BP-1')
        self.assertEqual(found['qty_available'], 10)
        self.assertEqual(found['unit_cost'], 12.5)
        self.assertEqual(found['sale_price'], 20.0)
        self.assertEqual(found['vendor'], 'Parts Vendor')
        self.assertIsNone(found['image_url'])
        self.assertEqual(self.Api.part_lookup(' NOPE '), {'found': False, 'barcode': 'NOPE'})
        with self.assertRaises(UserError):
            self.Api.part_lookup('')

    def test_consume_once_per_reference(self):
        first = self.Api.part_consume('SLC-0001', 2, 'BIKE-7/REPAIR-1', note='front brake')
        self.assertFalse(first['already_done'])
        self.assertEqual(first['qty'], 2)
        self.assertEqual(first['total_cost'], 25.0)
        self.assertEqual(first['unit_cost'], 12.5)
        move = self.env['stock.move'].browse(first['move_id'])
        self.assertEqual(move.state, 'done')
        self.assertEqual(move.origin, 'BIKE-7/REPAIR-1')
        self.assertEqual(move.location_id, self.stock)
        self.assertEqual(move.location_dest_id.usage, 'inventory')
        self.assertEqual(self.product.qty_available, 8)

        again = self.Api.part_consume(self.product.id, 2, 'BIKE-7/REPAIR-1')
        self.assertTrue(again['already_done'])
        self.assertEqual(again['move_id'], first['move_id'])
        self.assertEqual(again['total_cost'], 25.0)
        self.assertEqual(self.product.qty_available, 8, "the same reference never consumes twice")
        self.assertEqual(self.env['stock.move'].search_count([('origin', '=', 'BIKE-7/REPAIR-1')]), 1)

        other = self.Api.part_consume(self.product.id, 1, 'BIKE-7/REPAIR-2')
        self.assertFalse(other['already_done'])
        self.assertNotEqual(other['move_id'], first['move_id'])
        self.assertEqual(self.product.qty_available, 7)
        self.assertEqual(self.env['site.link.consumption'].search_count(
            [('reference', 'in', ['BIKE-7/REPAIR-1', 'BIKE-7/REPAIR-2'])]), 2)

    def test_consume_checks(self):
        for args in (('SLC-0001', 0, 'R-A'), ('SLC-0001', 1, ''), ('NOPE', 1, 'R-B'), (999999999, 1, 'R-C')):
            with self.subTest(args=args), self.assertRaises(UserError):
                self.Api.part_consume(*args)
        self.assertEqual(self.product.qty_available, 10)
        service = self.env['product.product'].create({'name': 'Labour', 'type': 'service', 'barcode': 'SLC-SRV'})
        with self.assertRaises(UserError):
            self.Api.part_consume(service.id, 1, 'R-D')
        self.assertFalse(self.env['site.link.consumption'].search([('reference', 'like', 'R-%')]))
