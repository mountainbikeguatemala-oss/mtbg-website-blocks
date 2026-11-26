"""Required, field by field (0.8.0; owner, 2026-11-25: "in the forms extension we need the ability to set any field
as mandatory (required)", on all forms): every field block's Optional / Required / Required when / unless, the
fields inside a form type's own blocks (``_mtbg_block_fields``, ``field_rules``), the ones a form type locks."""
from unittest.mock import patch

from odoo.tests import HttpCase, TransactionCase, tagged

from ..models.form import MtbgForm


def _fake_block_fields(self):
    """A form type's block with two fields inside (the Known visitor greeting, for the test): one to set, one locked."""
    return {'known': [{'key': 'inner_a', 'label': 'Inner A', 'default': 'never', 'locked': ''},
                      {'key': 'inner_b', 'label': 'Inner B', 'default': 'always', 'locked': 'Needed'}]}


@tagged('post_install', '-at_install', 'mtbg')
class TestRequiredFields(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Designer = self.env['mtbg.form.designer']
        self.form = self.env.ref('mtbg_tours_forms.form_contact')
        self.main = self.Designer.mtbg_get_page(self.form.id)['langs'][0]['code']

    def _add_field(self, page, key, label, require_mode='never'):
        page['blocks'].insert(len(page['blocks']) - 1, {
            'id': f'new_{key}', 'kind': 'text', 'key': key, 'width': 'full', 'active': True, 'show_mode': 'always',
            'show_rule': {}, 'require_mode': require_mode, 'require_rule': {}, 'texts': {'label': {self.main: label}}})

    def _submit(self, **extra):
        values = dict({'name': 'Ana Torres', 'email': 'ana.required@example.com', 'phone': '+1 202 555 0147',
                       'message': 'Hello'}, **extra)
        return self.form.mtbg_submit(values, {'variant': 'page', 'lang': 'en_US'})

    def test_field_block_required_and_optional(self):
        """A field set to Required blocks the submit on the server; Optional (or Required and filled in) passes."""
        page = self.Designer.mtbg_get_page(self.form.id)
        self._add_field(page, 'company', 'Company', 'always')
        self.Designer.mtbg_save(self.form.id, page)
        result = self._submit()
        self.assertFalse(result['ok'])
        self.assertEqual(result['errors'], {'company': 'Please fill in "Company"'})
        self.assertTrue(self._submit(company='ACME')['ok'], "filled in: sent")
        block = self.form.block_ids.filtered(lambda b: b.key == 'company')
        block.require_mode = 'never'
        self.assertTrue(self._submit()['ok'], "Optional: sent empty")
        # Required when: a rule on another answer
        block.write({'require_mode': 'when', 'require_rule': {
            'match': 'all', 'conditions': [{'subject': 'field:message', 'op': 'contains', 'value': 'invoice'}]}})
        self.assertTrue(self._submit()['ok'])
        self.assertIn('company', self._submit(message='Please send an invoice')['errors'])

    def test_name_locked_on_contact_forms(self):
        """A new contact needs a name: the Name field's Required option is locked (the designer shows why), a save
        cannot make it optional, the browser gets it required."""
        page = self.Designer.mtbg_get_page(self.form.id)
        self.assertIn('name', page['locked_fields'])
        self.assertEqual(page['locked_fields']['name']['mode'], 'always')
        self.assertTrue(page['locked_fields']['name']['reason'])
        for item in page['blocks']:
            if item['key'] == 'name':
                item['require_mode'] = 'never'
        self.Designer.mtbg_save(self.form.id, page)
        name = self.form.block_ids.filtered(lambda b: b.key == 'name')
        self.assertEqual(name.require_mode, 'always', "locked: stays required")
        name.require_mode = 'never'  # (written around the designer: still required)
        self.assertEqual(name._mtbg_def()['require'][0], 'always')
        self.assertIn('name', self._submit(name='')['errors'])

    def test_texting_boxes_locked_optional(self):
        """The SMS / WhatsApp opt-ins are listed with their Required option locked to Optional (consent is never a
        condition); a save cannot make them required."""
        page = self.Designer.mtbg_get_page(self.form.id)
        specs = page['block_fields']['texting']
        self.assertEqual({s['key'] for s in specs}, {'sms_optin', 'whatsapp_optin', 'sms_marketing_optin'})
        self.assertTrue(all(s['locked'] and s['default'] == 'never' for s in specs))
        texting = next(b for b in page['blocks'] if b['kind'] == 'texting')
        texting['field_rules'] = {'sms_optin': {'mode': 'always', 'rule': {}}}
        self.Designer.mtbg_save(self.form.id, page)
        block = self.form.block_ids.filtered(lambda b: b.kind == 'texting')
        self.assertFalse(block.field_rules, "a locked field keeps its default")
        self.assertEqual(self.form._mtbg_fields_required({'phone': '555 1234'}, {})['sms_optin'], False)
        self.assertTrue(self._submit()['ok'])

    def test_fields_inside_a_block(self):
        """A form type's block with fields inside: each one's Required option saved (only what differs from its
        default, never a locked one), worked out by the rules, and handed to the browser."""
        with patch.object(MtbgForm, '_mtbg_block_fields', _fake_block_fields):
            page = self.Designer.mtbg_get_page(self.form.id)
            self.assertEqual([s['key'] for s in page['block_fields']['known']], ['inner_a', 'inner_b'])
            known = next(b for b in page['blocks'] if b['kind'] == 'known')
            self.assertEqual(known['field_rules']['inner_a']['mode'], 'never')
            known['field_rules'] = {
                'inner_a': {'mode': 'when', 'rule': {'match': 'all', 'conditions': [
                    {'subject': 'field:message', 'op': 'filled', 'value': ''}]}},
                'inner_b': {'mode': 'never', 'rule': {}},  # locked: ignored
            }
            self.Designer.mtbg_save(self.form.id, page)
            block = self.form.block_ids.filtered(lambda b: b.kind == 'known')
            self.assertEqual(set(block.field_rules), {'inner_a'})
            ctx = {'known': False}
            self.assertEqual(self.form._mtbg_fields_required({'message': 'Hi'}, ctx), {'inner_a': True, 'inner_b': True})
            self.assertEqual(self.form._mtbg_fields_required({}, ctx), {'inner_a': False, 'inner_b': True})
            view = self.form.mtbg_view('page')
            self.assertIn('"inner_a"', view['form_fields'])
            self.assertEqual(view['fields_required'], {'inner_a': False, 'inner_b': True})
            # back to its default: nothing kept
            page = self.Designer.mtbg_get_page(self.form.id)
            known = next(b for b in page['blocks'] if b['kind'] == 'known')
            known['field_rules'] = {'inner_a': {'mode': 'never', 'rule': {}}}
            self.Designer.mtbg_save(self.form.id, page)
            self.assertFalse(block.field_rules)


# the contact page's form: a field set to Required stops the send in the browser, with its message and the field
# marked; filled in, the form is sent
BROWSER = """
const sent = [];
const open = XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open = function (method, url, ...rest) { sent.push(String(url)); return open.call(this, method, url, ...rest); };
const wait = (ms) => new Promise((ok) => setTimeout(ok, ms));
const fail = (what) => console.error('test failed: ' + what);
(async () => {
    await wait(800);  // (its interaction started)
    const form = document.querySelector('form.mtbg-form[data-form="contact"]');
    if (!form) { return fail('no contact form'); }
    const set = (sel, value) => { const el = form.querySelector(sel); el.value = value; el.dispatchEvent(new Event('input', {bubbles: true})); };
    set('[name="name"]', 'Ana Torres');
    set('[name="email"]', 'ana.browser@example.com');
    set('.mtbg-phone__input', '202 555 0147');
    set('[name="message"]', 'Hello');
    await wait(200);
    const block = form.querySelector('.mtbg-form__block[data-key="company"]');
    if (!block || !block.classList.contains('is-required')) { return fail('company not marked required'); }
    form.querySelector('.mtbg-contact-form__send').click();
    await wait(600);
    const box = form.querySelector('.mtbg-contact-form__error');
    if (sent.some((u) => u.includes('/mtbg_forms/submit'))) { return fail('sent with a required field empty'); }
    if (!box || box.hidden || !box.textContent.includes('Company')) { return fail('no message: ' + (box && box.textContent)); }
    if (!block.querySelector('input').classList.contains('is-invalid')) { return fail('field not marked'); }
    set('[name="company"]', 'ACME');
    form.querySelector('.mtbg-contact-form__send').click();
    for (let i = 0; i < 50 && !sent.some((u) => u.includes('/mtbg_forms/submit')); i++) { await wait(100); }
    if (!sent.some((u) => u.includes('/mtbg_forms/submit'))) { return fail('filled in: not sent'); }
    console.log('test successful');
})().catch((e) => fail(e.message));
"""


@tagged('post_install', '-at_install', 'mtbg')
class TestRequiredFieldsBrowser(HttpCase):

    def test_required_field_in_the_browser(self):
        form = self.env.ref('mtbg_tours_forms.form_contact')
        submit = form.block_ids.filtered(lambda b: b.kind == 'submit')
        self.env['mtbg.form.block'].create({'form_id': form.id, 'kind': 'text', 'key': 'company', 'label': 'Company',
                                            'sequence': submit.sequence - 1, 'require_mode': 'always'})
        self.browser_js('/contact-us', BROWSER, ready="!!(window.odoo && odoo.loader && odoo.loader.modules.get('@mtbg_tours_forms/form'))",
                        # (the forms' script loaded: a lazy bundle where Page Speed is installed)
                        login=None)
