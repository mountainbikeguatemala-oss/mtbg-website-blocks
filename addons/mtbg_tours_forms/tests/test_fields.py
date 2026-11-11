from odoo.tests import TransactionCase, tagged

from ..models.fields import mtbg_normalize_phone
from ..models.partner import mtbg_phone_open_country


@tagged('post_install', '-at_install', 'mtbg')
class TestFormFields(TransactionCase):

    def test_checks(self):
        check = self.env['mtbg.form.fields']._mtbg_check
        self.assertEqual(check('name', '  Ana   Torres '), ('Ana Torres', None))
        self.assertTrue(check('name', 'A')[1])
        self.assertEqual(check('email', 'Ana@Example.com')[0], 'ana@example.com')
        self.assertTrue(check('email', 'ana@')[1])
        self.assertEqual(check('phone', '+502 5555 1234')[0], '+502 5555 1234')
        self.assertTrue(check('phone', '5555 1234')[1], "a number needs its country code")
        self.assertEqual(check('phone', '5555 1234', country_code='GT')[0], '+502 5555 1234')

    def test_phone_picker(self):
        picker = self.env['res.country'].mtbg_phone_picker()
        gt = next(c for c in picker['countries'] if c['code'] == 'GT')
        self.assertEqual((gt['dial'], gt['lengths']), ('502', '8'))
        self.assertEqual(mtbg_normalize_phone('+15415550123'), '+1 541-555-0123')


@tagged('post_install', '-at_install', 'mtbg')
class TestSharedDialCodes(TransactionCase):
    """Dial codes several countries share (owner, 2026-10-28: a US contact's +1 number opened on a Caribbean flag and
    would have written that country to the contact)."""

    def test_picker_opens_on_the_right_country(self):
        cases = [
            (('+14435421382', 'US'), 'US'),     # the contact's own country
            (('+14435421382', None), 'US'),     # else the area code (443: Maryland)
            (('+14165550123', None), 'CA'),     # 416: Toronto
            (('+12684601234', None), 'AG'),     # 268: Antigua and Barbuda
            (('+14435421382', 'GT'), 'US'),     # a contact's country without that dial code: the area code
            (('+15550000000', None), 'US'),     # no area code known: the main country of +1
            (('+447700900123', 'JE'), 'JE'),    # +44: the contact's Jersey
            (('+447700900123', None), 'GB'),
            (('+77011234567', None), 'KZ'),     # +7 70x: Kazakhstan
            (('+50255551234', 'US'), 'GT'),     # one country's code: that country
            (('not a number', 'US'), None),
        ]
        for args, expected in cases:
            self.assertEqual(mtbg_phone_open_country(*args), expected, args)
        Country = self.env['res.country']
        self.assertEqual(Country.mtbg_phone_open('+14435421382', 'US', 'GT'), 'US')
        self.assertEqual(Country.mtbg_phone_open('', 'US', 'GT'), 'GT', "no number: the visitor's")

    def test_a_shared_dial_code_never_replaces_a_contacts_country(self):
        us, ca, gt = (self.env.ref(f'base.{c}') for c in ('us', 'ca', 'gt'))
        brendan = self.env['res.partner'].create({'name': 'Shared Dial', 'phone': '+14435421382', 'country_id': us.id})
        for picked in ('AS', 'CA', 'PR', ''):
            brendan._mtbg_fill_country(picked, '+14435421382')
            self.assertEqual(brendan.country_id, us, picked or 'no pick')
        brendan._mtbg_fill_country('CA', '+14165550123')  # even a valid Canadian number: +1 is shared
        self.assertEqual(brendan.country_id, us)
        brendan._mtbg_fill_country('GT', '+50255551234')  # a dial code of one country: the latest they chose
        self.assertEqual(brendan.country_id, gt)
        new = self.env['res.partner'].create({'name': 'No Country'})
        new._mtbg_fill_country('CA', '+14165550123')
        self.assertEqual(new.country_id, ca, "an empty country is filled")
