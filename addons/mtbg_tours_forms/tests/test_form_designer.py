from odoo.tests import HttpCase, TransactionCase, tagged

from ..models.form import evaluate


@tagged('post_install', '-at_install', 'mtbg')
class TestFormRules(TransactionCase):

    def test_evaluate(self):
        phone = {'match': 'any', 'conditions': [{'subject': 'field:phone', 'op': 'min_digits', 'value': '3'},
                                                {'subject': 'known_phone', 'op': 'yes'}]}
        self.assertFalse(evaluate(phone, {'phone': '+5'}, {}))
        self.assertTrue(evaluate(phone, {'phone': '555'}, {}))
        self.assertTrue(evaluate(phone, {}, {'known_phone': True}))
        self.assertTrue(evaluate({}, {}, {}), "no conditions: holds")
        rule = {'match': 'all', 'conditions': [{'subject': 'variant', 'op': 'is', 'value': 'popup'},
                                               {'subject': 'field:riders', 'op': 'gte', 'value': '4'}]}
        self.assertTrue(evaluate(rule, {'riders': '5'}, {'variant': 'popup'}))
        self.assertFalse(evaluate(rule, {'riders': '3'}, {'variant': 'popup'}))
        self.assertTrue(evaluate({'conditions': [{'subject': 'field:trip', 'op': 'is', 'value': 'Enduro'}]},
                                 {'trip': ['Enduro', 'XC']}, {}), "several choices: includes")
        self.assertTrue(evaluate({'conditions': [{'subject': 'field:ok', 'op': 'unchecked'}]}, {'ok': False}, {}))

    def test_default_contact_form(self):
        form = self.env.ref('mtbg_tours_forms.form_contact')
        self.assertEqual(form.mtbg_get('contact'), form)
        view = form.mtbg_view('sidebar')
        blocks = [b for section in view['sections'] for _i, b in section['blocks']]
        titles = {b.label for i, b in enumerate(blocks) if b.kind == 'heading' and i not in view['hidden']}
        self.assertEqual(titles, {'Questions about this tour?'}, "the sidebar's own heading")
        known = form.mtbg_view('page', known=True)
        hidden_keys = {b.key for section in known['sections'] for i, b in section['blocks'] if i in known['hidden']}
        self.assertTrue({'name', 'phone', 'email'} <= hidden_keys, "a known visitor's details are kept")

    def test_spanish_of_the_default_form(self):
        self.env['res.lang']._activate_lang('es_ES')
        self.env['mtbg.form']._mtbg_seed_translations()
        message = self.env.ref('mtbg_tours_forms.form_contact_message')
        self.assertEqual(message.with_context(lang='es_ES').label, 'Tu mensaje')
        self.assertEqual(self.env.ref('mtbg_tours_forms.form_contact').with_context(lang='es_ES').thanks_title, '¡Gracias{name}!')


@tagged('post_install', '-at_install', 'mtbg')
class TestFormDesigner(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Designer = self.env['mtbg.form.designer']
        self.form = self.env.ref('mtbg_tours_forms.form_contact')
        self.page = self.Designer.mtbg_get_page(self.form.id)
        self.main = self.page['langs'][0]['code']

    def add(self, page, kind, key, label, index=None, **extra):
        item = {'id': f'new_{key}', 'kind': kind, 'key': key, 'width': 'full', 'active': True, 'show_mode': 'always',
                'show_rule': {}, 'require_mode': 'never', 'require_rule': {},
                'texts': {'label': {self.main: label}}, **extra}
        blocks = page['blocks']
        blocks.insert(len(blocks) - 1 if index is None else index, item)
        return item

    def test_save_steps_rules_and_extra_answers(self):
        page = self.page
        self.add(page, 'step', '', 'About your trip', index=0)
        self.add(page, 'select', 'trip', 'Which trip?', texts={'label': {self.main: 'Which trip?'},
                                                                 'choices': {self.main: 'Day ride\nMulti-day'}},
                 require_mode='always')
        self.add(page, 'number', 'nights', 'How many nights?', show_mode='when',
                 show_rule={'match': 'all', 'conditions': [{'subject': 'field:trip', 'op': 'is', 'value': 'Multi-day'}]},
                 require_mode='always')
        page['style'] = {'sidebar': {'accent': '#ff0000', 'radius': 12, 'bogus': 1}}
        saved = self.Designer.mtbg_save(self.form.id, page)
        self.assertEqual([b['kind'] for b in saved['blocks']][:1], ['step'], "the page's order")
        self.assertEqual(self.form.style, {'sidebar': {'accent': '#ff0000', 'radius': 12}})
        self.assertIn('--mtbg-form-accent: #ff0000', self.form.mtbg_style('sidebar'))
        self.assertIn('--mtbg-form-radius: 12px', self.form.mtbg_style('sidebar'))

        values = {'name': 'Lia Rider', 'email': 'lia.form@example.com', 'phone': '+502 5555 3030',
                  'message': 'Hello', 'trip': 'Day ride', 'source': 'page'}
        self.assertTrue(self.env['mtbg.form.fields'].mtbg_contact_submit(values)['ok'],
                        "nights is hidden for a day ride: not asked")
        lead = self.env['crm.lead'].search([('email_from', '=', 'lia.form@example.com')])
        self.assertEqual(lead.mtbg_form_answers, {'trip': 'Day ride'})
        self.assertIn('Which trip?', str(lead.description))
        result = self.env['mtbg.form.fields'].mtbg_contact_submit(dict(values, trip='Multi-day'))
        self.assertEqual(set(result['errors']), {'nights'}, "shown by its rule, and required")
        result = self.env['mtbg.form.fields'].mtbg_contact_submit(dict(values, trip='Bus'))
        self.assertEqual(set(result['errors']), {'trip'}, "not one of the choices")

    def test_translations_and_system_blocks(self):
        page = self.page
        if len(page['langs']) < 2:
            self.env['res.lang']._activate_lang('es_ES')
            self.env['website'].get_current_website().language_ids |= self.env.ref('base.lang_es')
            page = self.Designer.mtbg_get_page(self.form.id)
        other = page['langs'][1]['code']
        submit = next(b for b in page['blocks'] if b['kind'] == 'submit')
        submit['texts']['label'] = {self.main: 'Send it', other: 'Envíalo'}
        known = next(b for b in page['blocks'] if b['kind'] == 'known')
        saved = self.Designer.mtbg_save(self.form.id, dict(page, blocks=[b for b in page['blocks'] if b is not known]))
        self.assertTrue(any(b['kind'] == 'known' for b in saved['blocks']), "the form's own blocks are not deleted")
        block = self.env['mtbg.form.block'].browse(submit['id'])
        self.assertEqual(block.with_context(lang=self.main).label, 'Send it')
        self.assertEqual(block.with_context(lang=other).label, 'Envíalo')
        with self.assertRaises(Exception):
            self.Designer.mtbg_save(self.form.id, dict(page, blocks=[b for b in page['blocks'] if b['kind'] != 'submit']))

    def test_preview_shows_every_block(self):
        import re
        page = self.page
        html = str(self.Designer.mtbg_preview(self.form.id, page, 'page', self.main))
        self.assertTrue(re.search(r'data-block="\d+" hidden', html), "the popup's heading: hidden on the page")
        self.assertNotIn('mtbg-rule-off', html)
        html = str(self.Designer.mtbg_preview(self.form.id, page, 'page', self.main, show_all=True))
        self.assertFalse(re.search(r'data-block="\d+" hidden', html), "every block shown")
        self.assertIn('mtbg-rule-off', html, "the ones their rules hide, marked")

    def test_full_preview_sample_answers(self):
        page = self.page
        self.add(page, 'select', 'trip', 'Which trip?', texts={'label': {self.main: 'Which trip?'},
                                                                 'choices': {self.main: 'Day ride\nMulti-day'}})
        html = str(self.Designer.mtbg_preview(self.form.id, page, 'page', self.main, sample=True))
        self.assertIn('value="ana@example.com"', html)
        self.assertIn('value="Day ride" selected', html.replace('selected="selected"', 'selected'))
        self.assertIn('5555 1234', html, "the mobile too")
        self.assertNotIn('ana@example.com', str(self.Designer.mtbg_preview(self.form.id, page, 'page', self.main)))

    def test_one_step_at_a_time(self):
        page = self.page
        self.assertNotIn('data-steps', str(self.Designer.mtbg_preview(self.form.id, page, 'page', self.main)))
        self.assertIn('data-steps', str(self.Designer.mtbg_preview(self.form.id, page, 'page', self.main, walk=True)),
                      "the full preview: step by step")
        self.Designer.mtbg_save(self.form.id, dict(page, step_by_step=True))
        self.assertTrue(self.form.step_by_step)
        self.assertTrue(self.form.mtbg_view('page')['steps'], "customers see it step by step")
        self.assertFalse(self.form.mtbg_view('page', show_all=True)['steps'], "not with every block shown")

    def test_preview_of_unsaved_blocks(self):
        page = self.page
        self.add(page, 'step', '', 'Your ride', index=0)
        self.add(page, 'text', 'bike', 'Your bike')
        html = str(self.Designer.mtbg_preview(self.form.id, page, 'popup', self.main))
        self.assertIn('Your ride', html)
        self.assertIn('Your bike', html)
        self.assertIn('mtbg-form__step-num', html)
        self.assertFalse(self.form.block_ids.filtered(lambda b: b.key == 'bike'), "nothing saved")


@tagged('post_install', '-at_install', 'mtbg')
class TestFormDarkLook(TransactionCase):
    """A Light and a Dark look per variant: the Dark one's tokens go on the form for dark pages (form.scss)."""

    def test_dark_look(self):
        form = self.env.ref('mtbg_tours_forms.form_contact')
        style = self.env['mtbg.form.designer']._mtbg_clean_style({
            'sidebar': {'bg': '#ffffff', 'accent': '#ff0000'},
            'sidebar:dark': {'bg': '#13283D', 'input_border': '#3B5672', 'text': 'nope', 'bogus': '#000000'}})
        self.assertEqual(set(style['sidebar:dark']), {'bg', 'input_border', 'text'})
        form.style = style
        css = form.mtbg_style('sidebar')
        self.assertIn('--mtbg-form-bg: #ffffff', css)
        self.assertIn('--mtbg-form-dark-bg: #13283D', css)
        self.assertIn('--mtbg-form-dark-input-border: #3B5672', css)
        self.assertNotIn('--mtbg-form-dark-text', css, "a bad colour is left out")
        view = form.mtbg_view('sidebar')
        classes = view['style_classes'].split()
        self.assertIn('mtbg-form--accent', classes)
        self.assertIn('mtbg-form--dark-bg', classes)
        self.assertIn('mtbg-form--dark-input_border', classes)
        self.assertNotIn('mtbg-form--dark-accent', classes)
        html = str(self.env['ir.qweb']._render('mtbg_tours_forms.form', {'form_view': view, 'variant': 'sidebar'}))
        self.assertIn('mtbg-form--dark-bg', html)
        self.assertNotIn('dark', form.mtbg_style('page'), "no Dark look for the page variant")


@tagged('post_install', '-at_install', 'mtbg')
class TestBlockTextLook(TransactionCase):
    """A block's own text size and colours (light / dark pages), a heading's level (the theme's fonts)."""

    def test_block_text_look(self):
        form = self.env.ref('mtbg_tours_forms.form_contact')
        Designer = self.env['mtbg.form.designer']
        vals = Designer._mtbg_block_vals({'kind': 'heading', 'heading_level': 'h5', 'text_color': '#b8bbc1',
                                          'text_color_dark': 'grey', 'text_size': 400}, 1)
        self.assertEqual((vals['heading_level'], vals['text_color'], vals['text_color_dark'], vals['text_size']),
                         ('h5', '#b8bbc1', False, 200))
        self.assertEqual(Designer._mtbg_block_vals({'kind': 'heading', 'heading_level': 'h1'}, 1)['heading_level'], 'h3')
        heading = form.block_ids.filtered(lambda b: b.kind == 'heading')[:1]
        message = form.block_ids.filtered(lambda b: b.key == 'message')[:1]
        heading.write({'heading_level': 'h4', 'text_color_dark': '#9a9ea6', 'text_size': 120})
        message.write({'text_size': 90, 'text_color': '#333333'})
        classes, style = heading._mtbg_text_look()
        self.assertEqual(classes, 'has-dark-color', "a heading's size is the theme's")
        self.assertIn('--mtbg-block-text-dark: #9a9ea6', style)
        classes, style = message._mtbg_text_look()
        self.assertEqual(classes.split(), ['has-text-color'], "no text size any more (the owner, 2026-10-27)")
        self.assertNotIn('--mtbg-block-size', style)
        html = str(self.env['ir.qweb']._render('mtbg_tours_forms.form', {
            'form_view': form.mtbg_view('sidebar'), 'variant': 'sidebar'}))
        self.assertIn('<h4 class="mtbg-contact-form__title"', html)
        self.assertIn('--mtbg-block-text: #333333', html)
        block = next(b for b in Designer.mtbg_get_page(form.id)['blocks'] if b['id'] == heading.id)
        self.assertEqual((block['heading_level'], block['text_color_dark']), ('h4', '#9a9ea6'))


@tagged('post_install', '-at_install', 'mtbg')
class TestFormPages(HttpCase):

    def test_designer_live_preview(self):
        code = """
        (async () => {
            const wait = async (fn, what) => {
                for (let i = 0; i < 200; i++) {
                    const found = fn();
                    if (found) { return found; }
                    await new Promise((r) => setTimeout(r, 100));
                }
                throw new Error('timeout: ' + what);
            };
            const doc = () => document.querySelector('.mtbg_fd_frame')?.contentDocument;
            await wait(() => doc()?.querySelector('form.mtbg-form .mtbg-contact-form__send'), 'preview');
            // a step added inline at the top shows numbered in the preview
            document.querySelector('.mtbg_fd_addbtn').click();
            const stepBtn = await wait(() => [...document.querySelectorAll('.mtbg_fd_palette button')].find((b) => b.textContent.includes('Step')), 'palette');
            stepBtn.click();
            await wait(() => doc().querySelector('.mtbg-form__step-num'), 'step in the preview');
            // rules run in the preview: the texting opt-ins appear once a mobile number is typed
            const phone = doc().querySelector('.mtbg-phone__input');
            const texting = doc().querySelector('.mtbg-form__block--texting');
            if (!texting.hidden) { throw new Error('opt-ins shown before typing'); }
            phone.value = '555';
            phone.dispatchEvent(new Event('input', { bubbles: true }));
            await wait(() => !doc().querySelector('.mtbg-form__block--texting').hidden, 'opt-ins after typing');
            // a click on a block of the preview opens it in the list
            doc().querySelector('.mtbg-form__block--heading:not([hidden])').click();
            await wait(() => document.querySelector('.mtbg_fd_row.is-open .mtbg_fd_more'), 'the block opened');
            // "Show every block": the popup's heading (hidden on the page) shows, marked
            document.getElementById('mtbg_fd_all').click();
            await wait(() => doc()?.querySelector('.mtbg-rule-off'), 'hidden blocks shown');
            // the full preview: step by step, a sample answer in every field
            document.querySelector('.mtbg_fd_walkbtn').click();
            const walk = () => document.querySelector('.mtbg_fd_walk_frame')?.contentDocument;
            await wait(() => walk()?.querySelector('form[data-steps] .mtbg-steps__nav'), 'one step at a time, Back / Next under the form');
            await wait(() => walk().querySelector('input[type="email"]')?.value === 'ana@example.com', 'sample answers');
            document.querySelector('.mtbg_fd_walk_close').click();
            await wait(() => !document.querySelector('.mtbg_fd_walk'), 'closed');
            console.log('test successful');
        })().catch((e) => console.error(e.message));
        """
        self.browser_js('/odoo/action-mtbg_tours_forms.action_mtbg_extension_page', code, login='admin', timeout=90)

    def test_contact_form_on_the_site(self):
        html = self.url_open('/contact-us').text
        self.assertIn('mtbg-form', html)
        self.assertIn('data-form="contact"', html)
        self.assertIn('Contact form', html)


@tagged('post_install', '-at_install')
class TestNewWebsiteForm(HttpCase):
    """The form list's "+ New form": a new website form (a copy of the open one), shown by a Form block on any page
    and sent like the contact form."""

    def test_new_form_and_its_block(self):
        designer = self.env['mtbg.form.designer']
        contact = self.env['mtbg.form'].mtbg_get('contact')
        page = designer.mtbg_new_form('website', contact.id)
        form = self.env['mtbg.form'].browse(page['form']['id'])
        self.assertEqual((form.handler, form.variants), ('contact', 'page'))
        self.assertNotEqual(form.key, 'contact')
        self.assertEqual(len(form.block_ids), len(contact.block_ids), "the contact form's blocks, copied")
        self.assertIn(form.id, [f['id'] for f in page['forms']])
        self.assertNotEqual(designer.mtbg_new_form('website', contact.id)['form']['id'], form.id, "each its own key")
        self.assertEqual(page['form_types'][0]['key'], 'website', "the website's forms first, with their + New")
        self.assertIn(form.key, [f['key'] for f in self.env['mtbg.form'].mtbg_block_forms()])
        # the Form block draws it, by its key
        html = self.make_jsonrpc_request('/mtbg_forms/block', {'key': form.key})['html']
        self.assertIn(f'data-form="{form.key}"', html)
        self.assertIn('mtbg-contact-form__send', html)
        self.assertEqual(self.make_jsonrpc_request('/mtbg_forms/block', {'key': 'nope'})['html'], '')
        # a visitor sends it: a contact and a lead, as with the contact form
        result = self.make_jsonrpc_request(f'/mtbg_forms/submit/{form.key}', {'values': {
            'name': 'Nova Block', 'email': 'nova.block@example.com', 'phone': '+502 5555 3030',
            'message': 'Hello from a new form', 'source': 'page'}})
        self.assertTrue(result.get('ok'), result)
        self.assertTrue(self.env['res.partner'].search([('email', '=', 'nova.block@example.com')]))
