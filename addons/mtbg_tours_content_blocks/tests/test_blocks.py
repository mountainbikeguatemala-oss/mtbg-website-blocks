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


@tagged('post_install', '-at_install', 'mtbg')
class TestWebsiteBlocksMenu(TransactionCase):
    """The website blocks' own app menu (owner, 2026-10-26): Blocks, Block Library, Page Templates (and the Card
    Designer when installed), Extensions with every website block module."""

    def test_menu(self):
        root = self.env.ref('mtbg_tours_content_blocks.menu_website_blocks_root')
        self.assertFalse(root.parent_id, "an app of its own (left-hand menu)")
        children = root.child_id.sorted('sequence')
        names = children.mapped(lambda m: m.with_context(lang='en_US').name)
        self.assertEqual(names[:3], ['Blocks', 'Block Library', 'Page Templates'])
        self.assertEqual(names[-1], 'Extensions')
        content = self.env.ref('website.menu_content')
        self.assertFalse(content.child_id & children, "no longer under Website › Content")

    def test_extensions_page(self):
        Module = self.env['ir.module.module']
        Module._mtbg_wb_fill()
        action = self.env.ref('mtbg_tours_content_blocks.action_website_block_modules')
        from odoo.tools.safe_eval import safe_eval
        listed = Module.search(safe_eval(action.domain))
        self.assertIn('mtbg_tours_content_blocks', listed.mapped('name'))
        self.assertNotIn('website', listed.mapped('name'))
        base = listed.filtered(lambda m: m.name == 'mtbg_tours_content_blocks')
        self.assertTrue(base.mtbg_wb_has_page, "its page: the Block Library")
        self.assertEqual(base.action_mtbg_wb_open()['tag'], 'mtbg_content_block_library')
        with self.assertRaises(Exception):
            base.action_mtbg_wb_switch_off()
        # a manifest's key is read with the module list
        website = Module.search([('name', '=', 'website')])
        website._update_from_terp(dict(Module.get_module_info('website'), mtbg_website_blocks=True))
        self.assertTrue(website.mtbg_website_block)
