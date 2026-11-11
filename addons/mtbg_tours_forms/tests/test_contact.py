from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tools import html2plaintext


@tagged('post_install', '-at_install', 'mtbg')
class TestContactForms(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Fields = self.env['mtbg.form.fields']

    def test_contact_finds_by_phone_first_and_opens_a_lead(self):
        known = self.env['res.partner'].create({'name': 'Rita Known', 'phone': '+502 5555 2020'})
        result = self.Fields.mtbg_contact_submit({
            'name': 'Rita Other', 'email': 'rita.new@example.com', 'phone': '+502 5555 2020',
            'message': 'Do you ride in December?', 'whatsapp_optin': True, 'source': 'page'})
        self.assertTrue(result['ok'])
        self.assertEqual(known.email, 'rita.new@example.com', "the missing email is filled in")
        self.assertEqual(known.name, 'Rita Known', "a known name is not changed")
        if 'mtbg_whatsapp_opt_in' in known._fields:  # (Tours Core's field)
            self.assertFalse(known.mtbg_whatsapp_opt_in, "the contact forms take no texting consent (the booking form does)")
        lead = self.env['crm.lead'].search([('partner_id', '=', known.id)])
        self.assertEqual(html2plaintext(lead.description), 'Do you ride in December?')
        # the lead source (owner, 2026-11-08: which web form): the form's own, on the contact and its lead
        self.assertTrue(lead.source_id.name.startswith('Web form: '), lead.source_id.name)
        if 'mtbg_lead_source_id' in known._fields:  # Tours Core: the contact's first touch too
            self.assertEqual(lead.source_id, known.mtbg_lead_source_id)
            whatsapp = known._mtbg_set_lead_source('whatsapp')
            self.assertNotEqual(known.mtbg_lead_source_id, whatsapp, "first touch: the form's kept")

    def test_contact_checks_its_fields(self):
        result = self.Fields.mtbg_contact_submit({'name': 'X', 'email': 'nope', 'phone': '555', 'message': ''})
        self.assertFalse(result['ok'])
        self.assertEqual(set(result['errors']), {'name', 'email', 'phone', 'message'})

    def test_newsletter_signup(self):
        result = self.Fields.mtbg_newsletter_submit({'name': 'Nia Letter',
                                                     'email': 'nia@example.com', 'language': 'en'})
        self.assertTrue(result['ok'])
        partner = self.env['res.partner'].search([('email', '=', 'nia@example.com')])
        self.assertTrue(partner.mtbg_newsletter)
        self.assertIn('Newsletter', partner.category_id.mapped('name'))
        if 'mtbg_lead_source_id' in partner._fields:  # (Tours Core's first touch)
            self.assertEqual(partner.mtbg_lead_source_id, self.env.ref('utm.utm_source_newsletter'),
                             "came by the newsletter")
        opted = self.Fields.mtbg_newsletter_submit({'name': 'Sam Sms', 'email': 'sms@example.com', 'sms_optin': True})
        self.assertFalse(opted['ok'], "an SMS opt-in needs the number and the texting terms")
        self.assertEqual(set(opted['errors']), {'phone', 'terms'})


@tagged('post_install', '-at_install', 'mtbg')
class TestContactPages(HttpCase):

    def test_contact_page_and_popups(self):
        page = self.url_open('/contact-us')
        self.assertEqual(page.status_code, 200)
        self.assertIn('mtbg-contact-form--page', page.text)
        # the newsletter popup: a Form Designer popup form (19.0.0.4.0), on every page but tour and rental pages
        Form = self.env['mtbg.form'].sudo()
        form = Form._mtbg_make_newsletter_popup() or Form.search([('key', '=', 'newsletter_popup')])
        Form.search([('popup', '=', True), ('id', '!=', form.id)]).write({'popup': False})
        form.popup = True
        page = self.url_open('/contact-us')
        self.assertIn('id="mtbg_form_popup"', page.text)
        self.assertIn('id="mtbg_contact_popup"', page.text)
        # a tour page: no newsletter popup (the owner: nothing interrupts a booking); the contact popup stays
        if 'mtbg.tour' not in self.env:
            return
        tour = self.env['mtbg.tour'].create({'name': 'No Newsletter Ride', 'slug': 'no-newsletter-ride',
                                             'base_price': 100, 'is_published': True})
        page = self.url_open(f'/tours/{tour.slug}')
        self.assertEqual(page.status_code, 200)
        self.assertNotIn('id="mtbg_form_popup"', page.text)
        self.assertIn('id="mtbg_contact_popup"', page.text)


@tagged('post_install', '-at_install')
class TestCountryFromPhone(TransactionCase):
    """A form sets the contact's country from the country picked with their mobile, even over another one (the
    latest they chose); without a pick, the number's own region fills an empty country only."""

    def test_country_from_the_mobile(self):
        from odoo.addons.mtbg_tours_forms.models.partner import mtbg_phone_region
        self.assertEqual(mtbg_phone_region('+1 416 555 0199', 'CA'), 'CA', "the picked country, +1 being shared")
        self.assertEqual(mtbg_phone_region('+1 416 555 0199'), 'CA', "else the number's own region (Toronto)")
        self.assertEqual(mtbg_phone_region('+502 5555 1234', 'US'), 'GT', "a picked country the number is not of")
        self.assertIsNone(mtbg_phone_region('not a phone'))
        Partner = self.env['res.partner']
        new = Partner.create({'name': 'Carla Canada', 'phone': '+1 416 555 0199'})
        new._mtbg_fill_country('CA')
        self.assertEqual(new.country_id.code, 'CA')
        moved = Partner.create({'name': 'Gil Moved', 'phone': '+502 5555 1234', 'country_id': self.env.ref('base.us').id})
        moved._mtbg_fill_country()
        self.assertEqual(moved.country_id.code, 'US', "no pick: a country already set stays")
        moved._mtbg_fill_country('GT')
        self.assertEqual(moved.country_id.code, 'GT', "picked: the latest country they chose")

    def test_contact_form_sets_it(self):
        result = self.env['mtbg.form.fields'].mtbg_contact_submit({
            'name': 'Gabi Picker', 'email': 'gabi.picker@example.com',
            'phone': '+502 5555 7788', 'phone_country': 'GT', 'message': 'Hola', 'source': 'page'})
        self.assertTrue(result['ok'], result)
        partner = self.env['res.partner'].search([('email', '=', 'gabi.picker@example.com')])
        self.assertEqual(partner.country_id.code, 'GT')


@tagged('post_install', '-at_install', 'mtbg')
class TestChatPage(HttpCase):

    def test_chat_page(self):
        """/chat, for links in emails: the chat page (it opens the website chat by itself), the contact popup there."""
        page = self.url_open('/chat')
        self.assertEqual(page.status_code, 200)
        self.assertIn('mtbg-chat-page', page.text)
        self.assertIn('href="#livechat"', page.text)
        self.assertIn('id="mtbg_contact_popup"', page.text)


@tagged('post_install', '-at_install', 'mtbg')
class TestTextingConsent(TransactionCase):
    """The messaging terms (owner, 2026-10-28): two global texts (Core's text settings) shown with the contact forms'
    SMS / WhatsApp boxes and the marketing popup's promotions box; what is stored with an opt-in is the text shown,
    in the visitor's language, with the links sentence; every box optional and unticked."""

    LINKS = " See our Privacy Policy and Terms of Service."
    ES_MARKETING = ("Envíenme mensajes de texto promocionales ocasionales de %(company)s sobre nuevos tours, fechas y "
                    "ofertas (hasta 4 al mes). Pueden aplicarse tarifas de mensajes y datos. Responda STOP para darse "
                    "de baja. El consentimiento no es condición de compra. Consulta nuestra Política de Privacidad y "
                    "Términos del Servicio.")

    def setUp(self):
        super().setUp()
        self.Fields = self.env['mtbg.form.fields'].with_context(lang='en_US')
        self.ICP = self.env['ir.config_parameter'].sudo()
        # the built-in texts (whatever the database's settings say)
        for key in ('mtbg_tours.messaging_terms_booking', 'mtbg_tours.messaging_terms_promotions'):
            self.ICP.search([('key', 'like', key)]).unlink()

    def test_the_contact_form_asks_no_texting_consent(self):
        result = self.Fields.mtbg_contact_submit({
            'name': 'Tess Text', 'email': 'tess@example.com', 'phone': '+502 4123 3030', 'message': 'Hello',
            'sms_optin': True, 'whatsapp_optin': True, 'sms_marketing_optin': True, 'source': 'page'})
        self.assertTrue(result['ok'])
        tess = self.env['res.partner'].search([('email', '=', 'tess@example.com')])
        self.assertFalse(any(tess[f] for f in ('mtbg_sms_opt_in', 'mtbg_messaging_consent', 'mtbg_sms_marketing_opt_in')
                             if f in tess._fields),
                         "the contact forms show no texting box: nothing sent is kept")

    def test_the_marketing_popup_keeps_the_promotions_terms(self):
        from odoo.addons.mtbg_tours_forms.models.contact import MARKETING_TEXT, consent_values
        MARKETING_TEXT = MARKETING_TEXT % consent_values(self.env)
        self.assertEqual(self.Fields._mtbg_consent_text('marketing'), MARKETING_TEXT + self.LINKS)
        popup = self.env['mtbg.form'].with_context(lang='en_US').mtbg_get('newsletter_popup')
        if not popup:
            self.skipTest("no newsletter popup")
        result = popup.mtbg_submit({'name': 'Pia Promo', 'email': 'pia@example.com', 'phone': '+502 4123 5050',
                                    'sms_marketing_optin': True, 'sms_optin': True, 'source': 'popup'},
                                   {'variant': 'popup'})
        self.assertTrue(result['ok'], result)
        pia = self.env['res.partner'].search([('email', '=', 'pia@example.com')])
        self.assertTrue(pia.mtbg_sms_marketing_opt_in)
        self.assertTrue(pia.mtbg_sms_marketing_date)
        self.assertEqual(pia.mtbg_sms_marketing_text, MARKETING_TEXT + self.LINKS)
        if 'mtbg_sms_opt_in' in pia._fields:  # (Tours Core's field)
            self.assertFalse(pia.mtbg_sms_opt_in, "the popup shows no booking-texts box")

    def test_an_edited_text_is_shown_and_kept(self):
        from odoo.addons.mtbg_tours_forms.models.contact import CONSENT_TEXT, consent_values
        CONSENT_TEXT = CONSENT_TEXT % consent_values(self.env)
        self.assertEqual(self.Fields._mtbg_consent_text(), CONSENT_TEXT, "the booking texts terms (booking form)")
        # the saved wording (as Tours Core's settings page saves the main language's text), read by Forms
        self.env['ir.config_parameter'].sudo().set_param('mtbg_tours.messaging_terms_promotions', 'Offers now and then.')
        self.assertEqual(self.Fields._mtbg_consent_text('marketing'), 'Offers now and then.' + self.LINKS)

    def test_promotions_need_the_mobile(self):
        popup = self.env['mtbg.form'].mtbg_get('newsletter_popup')
        if not popup:
            self.skipTest("no newsletter popup")
        result = popup.mtbg_submit({'name': 'Nora Number', 'email': 'nora@example.com', 'sms_marketing_optin': True,
                                    'source': 'popup'}, {'variant': 'popup'})
        self.assertFalse(result['ok'])
        self.assertIn('phone', result['errors'])

    def test_the_terms_in_spanish(self):
        lang = self.env['res.lang']._activate_lang('es_ES')
        self.env['ir.module.module'].search([('name', '=', 'mtbg_tours_forms')])._update_translations(
            lang.code, overwrite=True)
        Fields = self.env['mtbg.form.fields'].with_context(lang='es_ES')
        from odoo.addons.mtbg_tours_forms.models.contact import consent_values
        self.assertEqual(Fields._mtbg_consent_text('marketing'), self.ES_MARKETING % consent_values(self.env))

    def test_only_the_popup_shows_a_box_unticked(self):
        render = lambda marketing: str(self.env['ir.qweb']._render('mtbg_tours_forms.texting_consent', {
            'texting_shown': True, 'texting_marketing': marketing, 'texting_terms': 'x'}))
        self.assertNotIn('type="checkbox"', render(False), "the contact forms show no texting box")
        body = render(True)
        self.assertIn('name="sms_marketing_optin"', body)
        for name in ('sms_optin', 'whatsapp_optin', 'checked', 'required'):
            self.assertNotIn(name, body)
