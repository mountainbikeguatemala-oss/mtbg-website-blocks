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
