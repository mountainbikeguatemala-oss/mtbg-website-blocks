"""The protocol's customer side: search, create (or find), the customer's bikes (soft: [] with no bike model)."""
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestSiteLinkCustomers(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.link_user = new_test_user(cls.env, 'slc_cust_link', groups='base.group_user,'
                                      'site_link_connector.group_site_link_remote')
        cls.plain_user = new_test_user(cls.env, 'slc_cust_plain', groups='base.group_user')
        cls.Api = cls.env['site.link.api'].with_user(cls.link_user)
        cls.ana = cls.env['res.partner'].create({'name': 'Ana Slcustomer', 'email': 'ana.slc@example.com',
                                                 'phone': '+502 5555-1234'})

    def test_search(self):
        for query in ('slcustomer', 'ANA.SLC@example', '5555-1234', '(502) 55551234'):
            with self.subTest(query=query):
                found = self.Api.customer_search(query)
                self.assertIn({'id': self.ana.id, 'name': 'Ana Slcustomer', 'phone': '+502 5555-1234',
                               'email': 'ana.slc@example.com'}, found)
        self.assertFalse(self.Api.customer_search('zz-nobody-zz'))
        self.assertLessEqual(len(self.Api.customer_search('an', limit=500)), 50)
        with self.assertRaises(UserError):
            self.Api.customer_search(' ')
        self.assertTrue(self.env['site.link.log'].search([('kind', '=', 'served'), ('method', '=', 'customer_search')]))

    def test_create_or_find(self):
        self.assertEqual(self.Api.customer_create('Ana again', email='Ana.SLC@Example.com'),
                         {'id': self.ana.id, 'name': 'Ana Slcustomer', 'created': False})
        self.assertEqual(self.Api.customer_create('Ana again', phone='50255551234')['id'], self.ana.id)
        new = self.Api.customer_create(' Luis Slcustomer ', phone='+502 4444 9876', email='luis.slc@example.com')
        self.assertTrue(new['created'])
        partner = self.env['res.partner'].browse(new['id'])
        self.assertEqual((partner.name, partner.phone, partner.email),
                         ('Luis Slcustomer', '+502 4444 9876', 'luis.slc@example.com'))
        again = self.Api.customer_create('Luis', phone='502-4444-9876')
        self.assertEqual((again['id'], again['created']), (new['id'], False), "the same customer is made once")
        # an email's _ is not a wildcard
        self.assertTrue(self.Api.customer_create('Other', email='ana_slc@example.com')['created'])
        with self.assertRaises(UserError):
            self.Api.customer_create('')

    def test_bikes_soft(self):
        bikes = self.Api.customer_bikes(self.ana.id)
        if 'repair.bike' not in self.env:
            self.assertEqual(bikes, [])
        with self.assertRaises(UserError):
            self.Api.customer_bikes(999999999)

    def test_caller_needs_the_group(self):
        Api = self.env['site.link.api'].with_user(self.plain_user)
        for call in (lambda: Api.customer_search('ana'), lambda: Api.customer_create('X'),
                     lambda: Api.customer_bikes(self.ana.id), lambda: Api.repair_status('R'),
                     lambda: Api.repair_quote('R', self.ana.id, [{'service': 'x', 'price': 1}]),
                     lambda: Api.repair_invoice('R')):
            with self.assertRaises(AccessError):
                call()
