from odoo.tests import HttpCase, TransactionCase, tagged

from odoo.addons.mtbg_tours_forms.models.form import clean_popup, title_look


@tagged('post_install', '-at_install', 'mtbg')
class TestPopupForms(TransactionCase):
    """Any website form as a popup, on the pages its rule takes; the first popup in their order (the owner,
    2026-10-26); the newsletter popup as such a form."""

    def setUp(self):
        super().setUp()
        self.Form = self.env['mtbg.form'].sudo()
        self.Form.search([('popup', '=', True)]).write({'popup': False})
        self.contact = self.Form.mtbg_get('contact')

    def test_rules_and_order(self):
        a = self.contact.copy({'key': 'popup_a', 'popup': True, 'popup_sequence': 1, 'popup_settings': {
            'pages': 'only', 'include': {'kinds': ['blog'], 'words': ['antigua']},
            'exclude': {'kinds': [], 'words': ['antigua-old']}}})
        b = self.contact.copy({'key': 'popup_b', 'popup': True, 'popup_sequence': 2, 'popup_settings': {
            'exclude': {'kinds': ['tours', 'rentals']}}})
        self.assertEqual(self.Form.mtbg_popup_for('/blog/news'), a, "the first popup taking the page")
        self.assertEqual(self.Form.mtbg_popup_for('/rides/antigua'), a, "a word of the address")
        self.assertEqual(self.Form.mtbg_popup_for('/rides/antigua-old'), b, "excluded by a word: the next popup")
        self.assertEqual(self.Form.mtbg_popup_for('/'), b)
        tour = self.env['mtbg.tour'].create({'name': 'Popup Ride', 'slug': 'popup-ride'}) if 'mtbg.tour' in self.env else None
        if tour:
            self.assertFalse(self.Form.mtbg_popup_for('/tours/popup-ride', tour), "never on tour pages")

    def test_clean_popup(self):
        settings = clean_popup({'look': 'odd', 'images': ['/a.jpg', 'javascript:x', 'https://x.org/b.png'],
                                'overlay': 400, 'bar_color': 'red', 'include': {'kinds': ['nope', 'home'],
                                                                                'words': ' A , ,b '}})
        self.assertEqual(settings['look'], 'beside')
        self.assertEqual(settings['images'], ['/a.jpg', 'https://x.org/b.png'])
        self.assertEqual((settings['overlay'], settings['bar_color']), (90, '#111111'))
        self.assertEqual(settings['include'], {'kinds': ['home'], 'words': ['a', 'b']})
        self.assertTrue(settings['rotate'])
        self.assertEqual((settings['animation'], settings['backdrop']), ('fly', 80), "as since 2025 when not set")
        self.assertEqual(clean_popup({'animation': 'zoom', 'backdrop': 0})['backdrop'], 0)

    def test_newsletter_popup_form(self):
        self.Form.search([('key', '=', 'newsletter_popup')]).unlink()
        form = self.Form._mtbg_make_newsletter_popup()
        self.assertTrue(form.popup and form.newsletter)
        self.assertEqual(form.mtbg_popup()['look'], 'full')
        self.assertEqual(form.mtbg_popup()['exclude']['kinds'], ['tours', 'rentals'])
        self.assertIn('submit', form.block_ids.mapped('kind'))
        self.assertFalse(self.Form._mtbg_make_newsletter_popup(), "made once")
        # sending it subscribes the person
        result = form.mtbg_submit({'name': 'Nora News', 'email': 'nora.news@example.com'}, {'variant': 'popup'})
        self.assertTrue(result['ok'], result)
        partner = self.env['res.partner'].search([('email', '=', 'nora.news@example.com')], limit=1)
        self.assertTrue(partner.mtbg_newsletter)
        self.assertIn('Newsletter', partner.category_id.mapped('name'))

    def test_heading_line_spacing(self):
        heading = self.contact.block_ids.filtered(lambda b: b.kind == 'heading')[:1]
        heading.line_height = 130
        classes, style = heading._mtbg_text_look()
        self.assertIn('has-line-height', classes)
        self.assertIn('--mtbg-block-line: 1.3', style)
        heading.line_height = 0
        self.assertNotIn('has-line-height', heading._mtbg_text_look()[0], "0: the theme's")

    def test_title_look(self):
        self.assertEqual(title_look(), {'class': 'mtbg-title-look', 'style': None, 'size': None}, "nothing: as before")
        look = title_look(120, '#123456', 'bad', True, True, 'center')
        self.assertIn('is-bold', look['class'])
        self.assertIn('align-center', look['class'])
        self.assertIsNone(look['size'], "no text size (the owner, 2026-10-27)")
        self.assertNotIn('dark', look['style'])
        self.contact.header_look = {'level': 'h3', 'upper': True}
        self.assertEqual(self.contact.mtbg_header_look()['tag'], 'h3')
        self.contact.header_look = {'level': 'h3', 'sub_bold': True, 'sub_align': 'right'}
        self.assertIn('align-right', self.contact.mtbg_header_look()['subtitle']['class'], "the subtitle's style")
        self.contact.header_look = {'tour_upper': True}
        self.assertIn('is-upper', self.contact.mtbg_header_look()['tour']['class'], "the tour name's style")
        self.contact.header_look = {'level': 'h1'}
        self.assertEqual(self.contact.mtbg_header_look()['tag'], 'h1', "only H2-H5, else as before")


@tagged('post_install', '-at_install', 'mtbg')
class TestPopupOnThePage(HttpCase):

    def test_popup_on_the_page(self):
        Form = self.env['mtbg.form'].sudo()
        Form.search([('popup', '=', True)]).write({'popup': False})
        form = Form._mtbg_make_newsletter_popup() or Form.search([('key', '=', 'newsletter_popup')])
        form.popup = True
        # the contact page (a controller page: not in the website's page cache, which keeps a page for an hour)
        html = self.url_open('/contact-us').text
        self.assertIn('id="mtbg_form_popup"', html)
        self.assertIn('data-newsletter="1"', html)
        self.assertIn('mtbg-nl__offer', html)
        form.popup_settings = dict(form.mtbg_popup(), pages='only', include={'kinds': ['blog'], 'words': []})
        self.assertNotIn('id="mtbg_form_popup"', self.url_open('/contact-us').text)

    def test_newsletter_submit_is_tracked(self):
        """Communication Flows' visit tracking (Website Visitors 1.4.0, 2026-11-10): the newsletter form's send is
        data-cfd-track="newsletter" (no ref); another form's send carries none."""
        import re
        Form = self.env['mtbg.form'].sudo()
        Form.search([('popup', '=', True)]).write({'popup': False})
        form = Form._mtbg_make_newsletter_popup() or Form.search([('key', '=', 'newsletter_popup')])
        form.popup = True
        html = self.url_open('/contact-us').text
        popup = html[html.index('id="mtbg_form_popup"'):]
        send = re.search(r'<button type="submit"[^>]*mtbg-contact-form__send[^>]*>', popup).group(0)
        self.assertIn('data-cfd-track="newsletter"', send)
        self.assertNotIn('data-cfd-track-ref', send)
        others = [b for b in re.findall(r'<button type="submit"[^>]*mtbg-contact-form__send[^>]*>', html[:html.index('id="mtbg_form_popup"')])]
        self.assertTrue(all('data-cfd-track' not in b for b in others), "the contact form's send is not counted")
