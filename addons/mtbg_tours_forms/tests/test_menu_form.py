import re

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install', 'mtbg')
class TestMenuContactForm(HttpCase):

    def _panel_form(self):
        """The form the phone menu's Contact us panel names on the home page."""
        tag = re.search(r'<div class="mtbg-mmenu-contact-panel[^>]*>', self.url_open('/').text)
        self.assertTrue(tag, "the phone menu's contact panel")
        return re.search(r'data-form="([^"]*)"', tag.group(0)).group(1)

    def test_menu_contact_form(self):
        form = self.env.ref('mtbg_tours_forms.form_menu_contact')
        self.assertEqual(form.key, 'menu_contact')
        self.assertEqual(form.variants, 'menu')
        keys = [b.key for b in form.block_ids if b.key]
        self.assertIn('name', keys, "one Name field")
        self.assertFalse({'first_name', 'last_name'} & set(keys))
        if self.env['res.lang']._lang_get('es_ES'):
            name = form.block_ids.filtered(lambda b: b.key == 'name')
            self.assertEqual(name.with_context(lang='es_ES').label, 'Nombre')
        # the phone menu opens it (the contact form when it is gone)
        self.assertEqual(self._panel_form(), 'menu_contact')
        html = self.make_jsonrpc_request('/mtbg_forms/block', {'key': 'menu_contact', 'variant': 'menu'})['html']
        self.assertIn('name="name"', html)
        result = self.make_jsonrpc_request('/mtbg_forms/submit/menu_contact', {'values': {
            'name': 'Mia Menu', 'email': 'mia.menu@example.com', 'phone': '+502 5555 6060', 'message': 'Hi from the menu',
            'source': 'menu'}})
        self.assertTrue(result.get('ok'), result)
        lead = self.env['crm.lead'].search([('email_from', '=', 'mia.menu@example.com')])
        self.assertEqual(lead.partner_id.name, 'Mia Menu')
        missing = self.make_jsonrpc_request('/mtbg_forms/submit/menu_contact', {'values': {
            'name': 'M', 'email': 'm@example.com', 'phone': '+502 5555 6061', 'message': 'x', 'source': 'menu'}})
        self.assertEqual(set(missing.get('errors') or {}), {'name'})
        form.unlink()
        self.assertEqual(self._panel_form(), 'contact')
