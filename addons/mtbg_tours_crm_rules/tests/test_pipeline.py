"""The contact pipeline (0.4.0, owner 2026-11-18: the same pipeline on every site): contact type, stage, source
channel, the paying customer's hook. Runs with Tours or without it (the shop); the Communication Flow Designer's part
only when it is installed. Nothing is ever sent."""
from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestContactPipeline(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Partner = cls.env['res.partner']
        cls.Source = cls.env['utm.source']

    def test_sources_seeded(self):
        keys = self.Source._mtbg_lead_source_keys()
        for key, name in (('whatsapp', 'WhatsApp'), ('email', 'Email'), ('webchat', 'Webchat'),
                          ('website_sale', 'Website sale')):
            self.assertIn(key, keys)
            source = self.Source._mtbg_lead_source(key)
            self.assertEqual(source.name, name, key)
            self.assertEqual(source, self.env.ref(keys[key][1]), "seeded under its XML id: %s" % key)
        self.assertEqual(self.Source._mtbg_lead_source('facebook'), self.env.ref('utm.utm_source_facebook'))

    def test_new_contact_is_a_lead_then_first_touch(self):
        ana = self.Partner.create({'name': 'Ana Pipeline'})
        self.assertEqual((ana.mtbg_contact_type, ana.mtbg_is_lead, ana.mtbg_contact_type_manual), ('lead', True, False))
        self.assertIn(ana.mtbg_stage, ('new', 'lead'))
        ana._mtbg_set_lead_source('whatsapp')
        ana._mtbg_set_lead_source('email')
        self.assertEqual(ana.mtbg_lead_source_id.name, 'WhatsApp', "first touch: kept")
        if 'mtbg_tours_completed' not in self.Partner._fields:  # Tours computes its stages from its bookings
            self.assertEqual(ana.mtbg_stage, 'lead', "she reached us: a lead")
        ana.mtbg_lost = True
        self.assertEqual(ana.mtbg_stage, 'lost')

    def test_mark_customer_hook(self):
        bob = self.Partner.create({'name': 'Bob Buyer', 'email': 'bob@pipeline-test.example'})
        self.assertEqual(bob._mtbg_mark_customer(source='website_sale'), bob)
        self.assertEqual((bob.mtbg_contact_type, bob.mtbg_is_lead, bob.mtbg_contact_type_manual),
                         ('client', False, False))
        self.assertEqual(bob.mtbg_lead_source_id.name, 'Website sale')
        self.assertIn(bob.mtbg_stage, ('customer', 'past_client'), "Customer (Tours: from its bookings)")
        self.assertFalse(bob._mtbg_mark_customer(source='whatsapp'), "already a client: nothing changes")
        self.assertEqual(bob.mtbg_lead_source_id.name, 'Website sale', "first touch")
        # wrote first on WhatsApp, then bought: keeps WhatsApp
        cleo = self.Partner.create({'name': 'Cleo Chat'})
        cleo._mtbg_set_lead_source('whatsapp')
        cleo._mtbg_mark_customer(source='website_sale')
        self.assertEqual((cleo.mtbg_contact_type, cleo.mtbg_lead_source_id.name), ('client', 'WhatsApp'))
        # a vendor or a type chosen by hand: left as it is
        vendor = self.Partner.create({'name': 'Parts Supplier'})
        vendor.mtbg_contact_type = 'vendor'
        self.assertTrue(vendor.mtbg_contact_type_manual, "chosen by a person")
        self.assertFalse(vendor._mtbg_mark_customer(source='website_sale'))
        self.assertEqual(vendor.mtbg_contact_type, 'vendor')
        self.assertFalse(vendor.mtbg_stage)
        self.assertFalse(vendor.mtbg_lead_source_id, "no source for a vendor")

    def test_classification(self):
        company = self.env.company.partner_id
        self.assertEqual(self.Partner._mtbg_guess_contact_type(company), ('internal', True))
        lead = self.Partner.create({'name': 'Dan Nobody'})
        self.assertEqual(self.Partner._mtbg_guess_contact_type(lead)[0], 'lead')
        lead.with_context(mtbg_auto_type=True).mtbg_contact_type = 'client'
        self.assertFalse(lead.mtbg_contact_type_manual, "the automatic classification is no choice by hand")

    def test_board_stages_and_views(self):
        keys = self.Partner._group_expand_mtbg_stage(None, [])
        for key in ('new', 'lead', 'customer', 'lost'):
            self.assertIn(key, keys)
        self.assertEqual(self.Partner._group_expand_mtbg_stage(None, [('mtbg_stage', 'in', ['lead', 'lost'])]),
                         [k for k in keys if k in ('lead', 'lost')])
        action = self.env.ref('mtbg_tours_crm_rules.action_contact_pipeline')
        self.assertEqual(action.res_model, 'res.partner')
        for view_type in ('kanban', 'list', 'form', 'search'):
            self.Partner.get_views([(False, view_type)])
        arch = self.Partner.get_view(self.env.ref('mtbg_tours_crm_rules.view_partner_pipeline_kanban').id,
                                     'kanban')['arch']
        self.assertIn('mtbg_stage', arch)
        self.Source.get_views([(self.env.ref('mtbg_tours_crm_rules.view_utm_source_list_pipeline').id, 'list')])

    def test_first_message_sets_the_source(self):
        """The Communication Flow Designer (when installed) tells the pipeline where a contact first wrote from."""
        if 'omni.conversation' not in self.env:
            self.skipTest("no Communication Flow Designer")
        Conversation, Message = self.env['omni.conversation'], self.env['omni.message']
        for channel, name in (('whatsapp', 'WhatsApp'), ('email', 'Email'), ('livechat', 'Webchat')):
            partner = self.Partner.create({'name': 'Writer %s' % channel})
            conversation = Conversation._omni_get(channel, 'acct', 'pipe-%s' % channel, partner=partner)
            Message._omni_upsert(conversation, {'external_id': 'pipe-m-%s' % channel, 'direction': 'in',
                                                'body': 'Hola', 'sent_at': fields.Datetime.now()})
            self.assertEqual(partner.mtbg_lead_source_id.name, name, channel)
            self.assertEqual(partner.mtbg_contact_type, 'lead')
        # the history backfill: a contact whose first message came before the pipeline
        late = self.Partner.create({'name': 'Late Writer'})
        conversation = Conversation._omni_get('whatsapp', 'acct', 'pipe-late', partner=late)
        Message.with_context(cfd_history=True)._omni_upsert(conversation, {
            'external_id': 'pipe-late-1', 'direction': 'in', 'body': 'old', 'sent_at': fields.Datetime.now()})
        self.assertFalse(late.mtbg_lead_source_id, "history sets nothing live")
        self.Partner._mtbg_fill_sources_from_history()
        self.assertEqual(late.mtbg_lead_source_id.name, 'WhatsApp')
