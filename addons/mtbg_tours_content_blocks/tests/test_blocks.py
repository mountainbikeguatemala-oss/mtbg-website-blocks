from unittest.mock import patch

from odoo.tests import HttpCase, TransactionCase, tagged

from odoo.addons.mtbg_tours_content_blocks.models.content_block import placeholder_html


@tagged('post_install', '-at_install', 'mtbg')
class TestBlocksOnTheirOwn(TransactionCase):
    """Reusable blocks and page templates with only the website (no Tours): the pack's base on its own."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Block = cls.env['mtbg.tours.content.block']
        cls.block = cls.Block.create({'name': 'Store Hours', 'body': '<p>Open 9 to 5</p>'})

    def test_expand_and_picker(self):
        html = '<div>%s</div>' % placeholder_html(self.block.id)
        self.assertIn('Open 9 to 5', self.Block._mtbg_expand(html))
        self.assertIn(self.block.id, [b['id'] for b in self.Block.mtbg_picker_data()['blocks']])
        self.assertEqual(self.block.usage_count, 0, "no other module places it")

    def test_library(self):
        Library = self.env['mtbg.content.block.library']
        page = Library.mtbg_get_library()
        row = next(r for r in page['blocks'] if r['id'] == self.block.id)
        self.assertEqual(row['usage'], 0)
        self.assertEqual(page['list_action'], self.env.ref('mtbg_tours_content_blocks.action_content_block').id)
        new_id = Library.mtbg_create_block('Returns Policy')
        self.assertEqual(self.Block.browse(new_id).name, 'Returns Policy')
        self.assertFalse(Library.mtbg_get_block(self.block.id)['used_on'])

    def test_page_kinds_protocol(self):
        """A module gives a kind of page: its Default template lays the page out, Desktop or Mobile."""
        Template = self.env['mtbg.page.template']
        if Template._mtbg_page_kinds():
            return  # (a module drawing pages is installed: its own tests cover it)
        kinds = [('shop', 'Shop page')]
        slots = [{'code': 'top', 'name': 'Top', 'description': ''}, {'code': 'bottom', 'name': 'Bottom', 'description': ''}]
        registry = {'title': {'code': 'title', 'name': 'Title', 'template': 'web.layout', 'slot': 'top', 'sequence': 10,
                              'kind': 'own', 'icon': 'fa-header', 'description': ''}}
        cls = type(Template)
        with patch.object(cls, '_mtbg_page_kinds', lambda self: kinds), \
                patch.object(cls, '_mtbg_page_slots', lambda self, kind=None: slots), \
                patch.object(cls, '_mtbg_page_registry', lambda self, kind=None: registry):
            Template._mtbg_ensure_defaults()
            template = Template._mtbg_template_for_kind('shop')
            self.assertTrue(template.is_default)
            self.assertEqual([e['code'] for e in template._mtbg_layout()['top']], ['title'])
            lines = template._mtbg_line_dicts()
            template.mtbg_editor_save(lines, [dict(lines[0], id=0, slot='bottom')])
            self.assertEqual(list(template._mtbg_layout(layout='mobile')), ['bottom'])
            self.assertEqual(list(template._mtbg_layout()), ['top'], "Desktop unchanged")


@tagged('post_install', '-at_install', 'mtbg')
class TestBlockPage(HttpCase):

    def test_block_page_for_editors_only(self):
        block = self.env['mtbg.tours.content.block'].create({'name': 'Promo', 'body': '<p>Free shipping</p>'})
        self.assertNotIn('Free shipping', self.url_open(f'/mtbg/block/{block.id}').text, "visitors: the login page")
        self.authenticate('admin', 'admin')
        self.assertIn('Free shipping', self.url_open(f'/mtbg/block/{block.id}').text)
