from odoo.exceptions import ValidationError
from odoo.tests import HttpCase, tagged

from odoo.addons.mtbg_tours_content_blocks.models.page_template import SYNC_PARAM


def codes(layout):
    return {slot: [el['code'] for el in elements] for slot, elements in layout.items()}


@tagged('post_install', '-at_install', 'mtbg')
class TestPageTemplates(HttpCase):
    """Stored page templates lay out the tour page (docs/architecture/page-templates.md)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Template = cls.env['mtbg.page.template']
        cls.Template._mtbg_ensure_defaults()
        cls.tour_tpl = cls.Template.search([('kind', '=', 'tour'), ('is_default', '=', True)])
        cls.rental_tpl = cls.Template.search([('kind', '=', 'rental'), ('is_default', '=', True)])
        cls.tour = cls.env['mtbg.tour'].create({'name': 'Template Test Ride', 'slug': 'template-test-ride',
                                                'is_published': True, 'description': '<p>Long words</p>'})
        cls.block = cls.env['mtbg.tours.content.block'].create({'name': 'Template Notice', 'block_type': 'generic',
                                                                'body': '<p>Placed by the template</p>'})

    def _line(self, code, template=None):
        return (template or self.tour_tpl).line_ids.filtered(lambda l: l.element_code == code)

    def _page(self):
        res = self.url_open('/tours/template-test-ride')
        self.assertEqual(res.status_code, 200)
        return res.text

    def test_defaults_are_todays_page(self):
        self.assertEqual(len(self.tour_tpl), 1)
        self.assertEqual(len(self.rental_tpl), 1)
        Tour = self.env['mtbg.tour']
        for template in self.tour_tpl | self.rental_tpl:
            registry = Tour._mtbg_tour_page_registry(template.kind)
            self.assertEqual(set(template.line_ids.mapped('element_code')), set(registry))
            self.assertEqual(codes(template._mtbg_layout()), codes(Tour._mtbg_layout_from(registry.values())))
        self.assertEqual(codes(self.tour._mtbg_tour_page_layout()), codes(self.tour_tpl._mtbg_layout()))

    def test_ensure_defaults_is_idempotent(self):
        before = self.tour_tpl.line_ids
        self.Template._mtbg_ensure_defaults()
        self.assertEqual(self.Template.search_count([('kind', '=', 'tour'), ('is_default', '=', True)]), 1)
        self.assertEqual(self.tour_tpl.line_ids, before)

    def test_register_hook_makes_the_defaults(self):
        self.env['ir.config_parameter'].sudo().set_param(SYNC_PARAM, '1')
        self._line('title').unlink()
        self.Template._register_hook()
        self.assertFalse(self.env['ir.config_parameter'].sudo().get_param(SYNC_PARAM))
        self.assertTrue(self._line('title'), "the missing element is stored again")

    def test_moving_a_line_moves_the_element(self):
        self._line('title').write({'slot': 'bottom', 'sequence': 999})
        self.assertEqual(codes(self.tour._mtbg_tour_page_layout())['bottom'][-1], 'title')
        html = self._page()
        self.assertGreater(html.find('mtbg-tour-title'), html.find('id="mtbg_tour_bottom"'))

    def test_switched_off_line_hides_the_element(self):
        self._line('title').active = False
        self.assertNotIn('title', codes(self.tour._mtbg_tour_page_layout())['top'])
        self.assertNotIn('mtbg-tour-title', self._page())

    def test_unknown_element_is_skipped(self):
        self.env['mtbg.page.template.line'].create({'template_id': self.tour_tpl.id, 'element_code': 'not_installed',
                                                    'slot': 'top', 'sequence': 1})
        self.assertNotIn('not_installed', sum(codes(self.tour._mtbg_tour_page_layout()).values(), []))
        self.assertIn('Long words', self._page())
        line = self._line('not_installed')
        self.assertIn('not installed', line.element_name)

    def test_unseen_element_shows_at_its_default_place(self):
        self._line('title').unlink()
        self.assertIn('title', codes(self.tour._mtbg_tour_page_layout())['top'])
        self.assertIn('mtbg-tour-title', self._page())

    def test_block_line_renders_the_reusable_block(self):
        self.env['mtbg.page.template.line'].create({'template_id': self.tour_tpl.id, 'block_id': self.block.id,
                                                    'slot': 'under_title', 'sequence': 10})
        html = self._page()
        self.assertIn('Placed by the template', html)
        self.assertLess(html.find('Placed by the template'), html.find('mtbg-tour-main'))
        self.block.active = False
        self.assertNotIn('Placed by the template', self._page())

    def test_line_is_an_element_or_a_block(self):
        with self.assertRaises(Exception), self.cr.savepoint():
            self.env['mtbg.page.template.line'].create({'template_id': self.tour_tpl.id, 'slot': 'top'})

    def test_duplicate(self):
        copy = self.tour_tpl.copy()
        self.assertFalse(copy.is_default)
        self.assertIn('(copy)', copy.name)
        self.assertEqual(sorted(copy.line_ids.mapped('element_code')), sorted(self.tour_tpl.line_ids.mapped('element_code')))

    def test_one_default_per_kind(self):
        other = self.tour_tpl.copy({'name': 'Day tours'})
        with self.assertRaises(ValidationError):
            other.is_default = True
        other.action_make_default()
        self.assertTrue(other.is_default)
        self.assertFalse(self.tour_tpl.is_default)
        with self.assertRaises(ValidationError):
            other.active = False

    def test_rental_pages_use_the_rental_template(self):
        rental = self.env['mtbg.tour'].create({'name': 'Template Test Bike', 'slug': 'template-test-bike',
                                               'product_kind': 'rental'})
        self.assertEqual(self.Template._mtbg_template_for(rental), self.rental_tpl)
        self._line('title', self.rental_tpl).active = False
        self.assertNotIn('title', codes(rental._mtbg_tour_page_layout())['top'])
        self.assertIn('title', codes(self.tour._mtbg_tour_page_layout())['top'])


@tagged('post_install', '-at_install', 'mtbg')
class TestPageTemplateEditor(HttpCase):
    """The template editor (phase 2): its data, the preview of unsaved lines, saving."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Template = cls.env['mtbg.page.template']
        cls.Template._mtbg_ensure_defaults()
        cls.tpl = cls.Template.search([('kind', '=', 'tour'), ('is_default', '=', True)])
        cls.tour = cls.env['mtbg.tour'].create({'name': 'Editor Test Ride', 'slug': 'editor-test-ride',
                                                'is_published': True, 'description': '<p>Editor words</p>'})
        cls.block = cls.env['mtbg.tours.content.block'].create({'name': 'Editor Notice', 'block_type': 'generic',
                                                                'body': '<p>Placed in the editor</p>'})

    def _lines(self):
        return [dict(line) for line in self.tpl.mtbg_editor_data(self.tpl.id)['lines']]

    def test_editor_data(self):
        data = self.Template.mtbg_editor_data(self.tpl.id)
        self.assertEqual(data['template']['id'], self.tpl.id)
        self.assertTrue({'top', 'reviews', 'gallery'} <= {s['code'] for s in data['slots']})
        self.assertIn('title', {e['code'] for e in data['elements']})
        self.assertIn(self.tour.id, [t['id'] for t in data['tours']])
        self.assertTrue(data['langs'])
        stats = [e for e in data['elements'] if e.get('group') == 'stats']
        if stats:  # Stats installed: one card for its two parts, with the Tour Stats settings as its panel
            self.assertEqual({e['code'] for e in stats}, {'stats_ratings', 'stats_columns'})
            self.assertEqual({e['panel'] for e in stats}, {'mtbg_tour_stats_page'})

    def test_preview_keeps_the_site_as_saved(self):
        """The owner's check: the gallery above the reviews, seen in the preview only until saved."""
        lines = self._lines()
        gallery = next(l for l in lines if l['code'] == 'gallery')
        gallery['slot'] = 'reviews'
        lines.remove(gallery)
        first_review = next(n for n, l in enumerate(lines) if l['slot'] == 'reviews')
        lines.insert(first_review, gallery)
        lines.append({'id': 0, 'code': False, 'block_id': self.block.id, 'slot': 'under_title', 'active': True})
        self.tpl.mtbg_editor_preview(lines)
        self.assertIn('gallery', codes(self.tpl._mtbg_layout(draft=True))['reviews'])
        self.assertNotIn('gallery', codes(self.tpl._mtbg_layout()).get('reviews', []), "the site keeps the saved page")
        self.authenticate('admin', 'admin')
        preview = self.url_open(f'/tours/editor-test-ride?mtbg_template_preview={self.tpl.id}').text
        self.assertIn('Placed in the editor', preview)
        self.authenticate(None, None)
        self.assertNotIn('Placed in the editor', self.url_open('/tours/editor-test-ride?mtbg_template_preview=%s' % self.tpl.id).text,
                         "a visitor never sees the draft")
        data = self.tpl.mtbg_editor_save(lines)
        self.assertFalse(self.tpl.sudo().draft_layout)
        self.assertIn('gallery', codes(self.tpl._mtbg_layout())['reviews'])
        reviews_lines = [l['code'] for l in data['lines'] if l['slot'] == 'reviews']
        self.assertEqual(reviews_lines[0], 'gallery', "saved in the order given")
        self.assertIn('Placed in the editor', self.url_open('/tours/editor-test-ride').text)

    def test_clean_lines(self):
        lines = self.tpl._mtbg_clean_lines([
            {'code': 'title', 'slot': 'top'}, {'code': 'title', 'slot': 'bottom'},  # an element once
            {'code': 'price', 'slot': 'nowhere'},  # unknown insert point
            {'code': 'faq', 'block_id': self.block.id, 'slot': 'bottom'},  # both
            {'block_id': self.block.id, 'slot': 'bottom'}, {'code': 'faq', 'slot': 'bottom', 'active': False},
        ])
        self.assertEqual([(l['code'], l['block_id'], l['slot'], l['sequence']) for l in lines],
                         [('title', 0, 'top', 10), (False, self.block.id, 'bottom', 10), ('faq', 0, 'bottom', 20)])
        self.assertFalse(lines[-1]['active'])

    def test_designers_only(self):
        user = self.env['res.users'].create({'name': 'No Designer', 'login': 'no_designer_pte',
                                             'group_ids': [(6, 0, [self.env.ref('base.group_user').id])]})
        with self.assertRaises(Exception):
            self.Template.with_user(user).mtbg_editor_data(self.tpl.id)

    def test_editor_in_the_browser(self):
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
            await wait(() => document.querySelector('.mtbg_pte_slot'), 'the page outline');
            const chips = document.querySelectorAll('.mtbg_pte_chip').length;
            if (chips < 5) { throw new Error('too few elements on the page: ' + chips); }
            // leave the title out: the change is unsaved, and the title is offered back in the "Add…" lists
            const title = [...document.querySelectorAll('.mtbg_pte_chip')].find((c) => /Title/.test(c.textContent));
            title.querySelector('.fa-eye-slash').closest('button').click();
            await wait(() => document.querySelector('.mtbg_pte_head .badge.text-bg-warning'), 'unsaved changes');
            const add = await wait(() => [...document.querySelectorAll('.mtbg_pte_add')].find((s) =>
                [...s.options].some((o) => o.textContent.trim() === 'Title')), 'the title offered back');
            add.value = [...add.options].find((o) => o.textContent.trim() === 'Title').value;
            add.dispatchEvent(new Event('change', { bubbles: true }));
            await wait(() => [...document.querySelectorAll('.mtbg_pte_chip')].some((c) => /Title/.test(c.textContent)), 'the title placed again');
            if ([...document.querySelectorAll('.mtbg_pte_add option')].some((o) => o.textContent.trim() === 'Title')) {
                throw new Error('a placed element is still offered');
            }
            const frame = await wait(() => document.querySelector('.mtbg_pte_frame'), 'the preview');
            await wait(() => frame.contentDocument?.querySelector('.mtbg-tour-main'), 'the preview page');
            console.log('test successful');
        })().catch((e) => console.error(e.message));
        """
        self.browser_js('/odoo/action-mtbg_tours_content_blocks.action_page_template_editor', code, login='admin', timeout=120)
