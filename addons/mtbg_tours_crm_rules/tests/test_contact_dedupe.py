"""De-duplicate a contact (0.5.2, owner 2026-11-21): no Duplicate on a contact, De-duplicate in its gear menu (Odoo's
merge dialog with its likely duplicates, the most complete proposed as the one kept). Nothing is sent."""
from datetime import date

from lxml import etree

from odoo.tests import HttpCase, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestContactDedupe(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Partner = cls.env['res.partner']

    def _wizard(self, action):
        self.assertEqual(action['res_model'], 'base.partner.merge.automatic.wizard', action)
        return self.env[action['res_model']].browse(action['res_id'])

    # -- no Duplicate on a contact -------------------------------------------------------------------------------

    def test_no_duplicate_on_contacts_only(self):
        for view_type in ('form', 'list'):
            arch = etree.fromstring(self.Partner.get_views([(False, view_type)])['views'][view_type]['arch'])
            self.assertEqual(arch.get('duplicate'), '0', "no Duplicate on the contact's %s" % view_type)
        Other = self.env['res.partner.category']  # any other model keeps Odoo's Duplicate
        if 'product.template' in self.env:
            Other = self.env['product.template']
        arch = etree.fromstring(Other.get_views([(False, 'form')])['views']['form']['arch'])
        self.assertNotEqual(arch.get('duplicate'), '0', "%s keeps Duplicate" % Other._name)

    def test_dedupe_in_the_gear_menu(self):
        action = self.env.ref('mtbg_tours_crm_rules.action_contact_dedupe')
        self.assertEqual(action.binding_model_id.model, 'res.partner')
        self.assertEqual(action.binding_view_types, 'form')
        toolbar = self.Partner.get_views([(False, 'form')], {'toolbar': True})['views']['form']['toolbar']
        self.assertIn(action.id, [a['id'] for a in toolbar.get('action', [])])

    # -- finding them --------------------------------------------------------------------------------------------

    def test_finds_by_email(self):
        ana = self.Partner.create({'name': 'Ana Dedupe', 'email': 'Ana.Dedupe@Example.com'})
        other = self.Partner.create({'name': 'A. D.', 'email': 'ana.dedupe@example.com'})
        self.Partner.create({'name': 'Someone Else', 'email': 'else@example.com'})
        self.assertEqual(ana._mtbg_dedupe_find(), {other: 'email'})

    def test_finds_by_phone_with_or_without_country_code(self):
        ben = self.Partner.create({'name': 'Ben Phone', 'phone': '+502 5555-1234'})
        local = self.Partner.create({'name': 'Benny', 'phone': '5555 1234'})
        spaced = self.Partner.create({'name': 'B P', 'phone': '(502) 55 55 12 34'})
        self.Partner.create({'name': 'Not Ben', 'phone': '+502 5555-9999'})
        self.assertEqual(ben._mtbg_dedupe_find(), {local: 'phone', spaced: 'phone'})
        self.assertEqual(local._mtbg_dedupe_find(), {ben: 'phone', spaced: 'phone'})

    def test_finds_copy_by_name(self):
        ellie = self.Partner.create({'name': 'Ellie Dedupetest', 'email': 'ellie@dedupe-test.example'})
        copy = ellie.copy()
        self.assertTrue(copy.name.endswith('(copy)'), copy.name)
        copy.email = False  # the copy keeps no email: found by its name
        copia = self.Partner.create({'name': 'ELLIE DEDUPETEST (copia)'})
        company = self.Partner.create({'name': 'Ellie Dedupetest', 'is_company': True})
        found = ellie._mtbg_dedupe_find()
        self.assertEqual(found, {copy: 'name', copia: 'name'}, "a company is not the person")
        self.assertNotIn(company, found)
        self.assertIn(ellie, copy._mtbg_dedupe_find())

    def test_same_name_different_emails_are_two_people(self):
        one = self.Partner.create({'name': 'John Dedupesmith', 'email': 'john1@dedupe-test.example'})
        self.Partner.create({'name': 'John Dedupesmith', 'email': 'john2@dedupe-test.example'})
        self.assertFalse(one._mtbg_dedupe_find())

    def test_own_company_people_not_duplicates(self):
        acme = self.Partner.create({'name': 'Dedupe Co', 'is_company': True, 'phone': '+502 2222 3333'})
        worker = self.Partner.create({'name': 'Worker', 'parent_id': acme.id, 'phone': '+502 2222 3333'})
        self.assertFalse(acme._mtbg_dedupe_find())
        self.assertFalse(worker._mtbg_dedupe_find())

    # -- the one kept --------------------------------------------------------------------------------------------

    def test_keeper_is_the_most_complete(self):
        thin = self.Partner.create({'name': 'G G', 'email': 'gg@dedupe-test.example'})
        full = self.Partner.create({'name': 'Gabriel Dedupegamez', 'email': 'gg@dedupe-test.example',
                                    'phone': '+502 5555 0101', 'city': 'Antigua',
                                    'country_id': self.env.ref('base.gt').id})
        wizard = self._wizard(thin.action_mtbg_dedupe())
        self.assertEqual(wizard.partner_ids, thin | full)
        self.assertEqual(wizard.dst_partner_id, full, "the fuller one is proposed as the one kept")
        self.assertEqual(wizard.state, 'selection')
        self.assertTrue(thin.exists() and full.exists(), "nothing merged without a click")

    def test_keeper_original_over_copy_and_most_linked(self):
        ellie = self.Partner.create({'name': 'Ellie Dedupekeep', 'email': 'ek@dedupe-test.example'})
        copy = ellie.copy()
        self.assertEqual((ellie | copy)._mtbg_dedupe_keeper(), ellie, "an original over its (copy)")
        twin = self.Partner.create({'name': 'Ellie Dedupekeep', 'email': 'ek@dedupe-test.example'})
        twin.message_post(body="a message")
        self.assertEqual((ellie | twin)._mtbg_dedupe_keeper(), twin, "a tie: the most linked")

    def test_no_duplicates_notice(self):
        lone = self.Partner.create({'name': 'Lonely Dedupeperson', 'email': 'lonely@dedupe-test.example'})
        action = lone.action_mtbg_dedupe()
        self.assertEqual(action['tag'], 'display_notification')
        self.assertEqual(action['params']['message'], 'No duplicates found for Lonely Dedupeperson')

    def test_server_action_runs(self):
        lone = self.Partner.create({'name': 'Lonely Dedupeaction'})
        action = self.env.ref('mtbg_tours_crm_rules.action_contact_dedupe').with_context(
            active_model='res.partner', active_id=lone.id, active_ids=lone.ids).run()
        self.assertEqual(action['tag'], 'display_notification')

    # -- the merge -----------------------------------------------------------------------------------------------

    def test_merge_moves_chatter_and_fills_details(self):
        keep = self.Partner.create({'name': 'Mia Dedupemerge', 'email': 'mia@dedupe-test.example'})
        dup = self.Partner.create({'name': 'Mia Dedupemerge (copy)', 'phone': '+502 5555 7777'})
        note = dup.message_post(body="Asked about the volcano ride")
        wizard = self._wizard(keep.action_mtbg_dedupe())
        self.assertEqual(wizard.dst_partner_id, keep)
        wizard.action_merge()
        self.assertFalse(dup.exists())
        self.assertEqual((note.model, note.res_id), ('res.partner', keep.id), "the chatter moved to the one kept")
        self.assertEqual(keep.name, 'Mia Dedupemerge', "the kept contact's details stay")
        self.assertEqual(keep.phone, '+502 5555 7777', "an empty detail filled")
        logged = keep.message_ids.filtered(lambda m: 'Details taken from the merged contacts' in (m.body or ''))
        self.assertTrue(logged, "every detail filled in the chatter")
        self.assertIn('+502 5555 7777', logged[0].body)

    def test_merge_moves_a_booking(self):
        if 'mtbg.tour.booking' not in self.env:
            self.skipTest("Tours Booking is not installed")
        tour = self.env['mtbg.tour'].create({'name': 'Dedupe Ride', 'slug': 'dedupe-ride-test', 'duration_days': 1,
                                             'capacity': 4})
        dep = self.env['mtbg.tour.departure'].create({'tour_id': tour.id, 'start_date': date(2031, 6, 10)})
        keep = self.Partner.create({'name': 'Rob Dedupebook', 'email': 'rob@dedupe-test.example',
                                    'phone': '+502 5555 4444', 'city': 'Antigua'})
        dup = self.Partner.create({'name': 'Rob Dedupebook', 'email': 'ROB@dedupe-test.example'})
        booking = self.env['mtbg.tour.booking'].create({'partner_id': dup.id, 'tour_id': tour.id,
                                                        'departure_id': dep.id})
        note = dup.message_post(body="Booked by phone")
        wizard = self._wizard(dup.action_mtbg_dedupe())
        self.assertEqual(wizard.dst_partner_id, keep)
        wizard.action_merge()
        self.assertFalse(dup.exists())
        self.assertEqual(booking.partner_id, keep, "the booking moved to the one kept")
        self.assertEqual(note.res_id, keep.id, "the chatter moved to the one kept")

    def test_merge_moves_reference_links(self):
        keep = self.Partner.create({'name': 'Ref Dedupekeep', 'email': 'ref@dedupe-test.example'})
        dup = self.Partner.create({'name': 'Ref Dedupekeep', 'email': 'ref@dedupe-test.example'})
        third = self.Partner.create({'name': 'Other Person'})
        Flag = self.env['mtbg.crm.duplicate']
        own = Flag.create({'res_model': 'res.partner', 'res_id': keep.id, 'other_id': dup.id, 'reason': 'email',
                           'value': 'ref@dedupe-test.example'})
        other = Flag.create({'res_model': 'res.partner', 'res_id': dup.id, 'other_id': third.id, 'reason': 'phone',
                             'value': '55554444'})
        self._wizard(dup.action_mtbg_dedupe()).action_merge()
        self.assertFalse(own.exists(), "the flag between the merged contacts settled")
        self.assertEqual(other.res_id, keep.id, "a link kept as a model and an id moved")


@tagged('post_install', '-at_install')
class TestContactDedupeBrowser(HttpCase):
    """At phone size: the gear menu has De-duplicate (no Duplicate); it opens the merge dialog with both."""

    browser_size = '390x844'
    touch_enabled = True

    def test_dedupe_phone(self):
        ellie = self.env['res.partner'].create({'name': 'Ellie Tourtest', 'email': 'ellie@tour-test.example'})
        ellie.copy()
        self.start_tour('/odoo/res.partner/%d' % ellie.id, 'mtbg_contact_dedupe', login='admin')
