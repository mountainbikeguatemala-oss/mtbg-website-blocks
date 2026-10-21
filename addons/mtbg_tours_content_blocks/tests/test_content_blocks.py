import re
from markupsafe import Markup

from odoo.tests import HttpCase, TransactionCase, tagged

from odoo.addons.mtbg_tours_content_blocks.hooks import post_init_hook
from odoo.addons.mtbg_tours_content_blocks.models.content_block import placeholder_html


@tagged('post_install', '-at_install', 'mtbg')
class TestContentBlocks(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Block = cls.env['mtbg.tours.content.block']
        cls.bring = Block.create({'name': 'What to Bring', 'block_type': 'what_to_bring',
                                  'body': '<ul><li>Helmet</li><li>Water</li></ul>'})
        cls.book = Block.create({'name': 'How to Book', 'block_type': 'how_to_book', 'body': '<p>Pick a date.</p>'})
        cls.tour = cls.env['mtbg.tour'].create({'name': 'Ridge Loop', 'slug': 'cb-ridge-loop', 'is_published': True})

    def _place(self, *blocks):
        self.tour.description = Markup('<p>Intro</p>') + Markup('').join(placeholder_html(b.id) for b in blocks)

    def test_expand_for_visitors(self):
        html = Markup('<div><p>Intro</p>%s</div>') % placeholder_html(self.bring.id)
        out = self.env['mtbg.tours.content.block']._mtbg_expand(html)
        self.assertIn('<li>Helmet</li>', out)
        self.assertNotIn('s_mtbg_content_block_placeholder', out)
        self.assertNotIn('data-oe-model', out, "no editor branding for visitors")

    def test_expand_in_editor_is_locked_field_of_the_block(self):
        out = self.env['mtbg.tours.content.block']._mtbg_expand(placeholder_html(self.bring.id), editable=True)
        self.assertIn(f'data-oe-model="mtbg.tours.content.block" data-oe-id="{self.bring.id}" data-oe-field="body"', out)
        self.assertIn('data-oe-readonly="1"', out, "shared content is locked until Edit in place")
        self.assertIn('data-mtbg-label="What to Bring"', out)

    def test_missing_or_archived_block(self):
        self.book.active = False
        html = placeholder_html(self.book.id) + placeholder_html(999999)
        self.assertEqual(str(self.env['mtbg.tours.content.block']._mtbg_expand(html)), '')
        self.assertIn('s_mtbg_content_block_placeholder', self.env['mtbg.tours.content.block']._mtbg_expand(html, True),
                      "the editor still shows the block, to choose another one")

    def test_edit_in_place_saves_the_shared_block(self):
        """The editor saves an edited block body as an embedded field of the block (ir.ui.view.save)."""
        body = self.bring._mtbg_body_html(True).replace('Helmet', 'Helmet and gloves')
        self.env['ir.ui.view'].browse(self.bring.id).save(str(body))
        self.assertIn('Helmet and gloves', self.bring.body)

    def test_used_on_follows_the_description(self):
        self._place(self.bring, self.book, self.bring)
        self.assertEqual([l.block_id.id for l in self.tour.block_line_ids.sorted('sequence')],
                         [self.bring.id, self.book.id, self.bring.id])
        self.assertEqual(self.bring.usage_count, 1)
        self._place(self.book)
        self.assertEqual(self.tour.block_line_ids.block_id, self.book)
        self.assertEqual(self.bring.usage_count, 0)

    def test_picker_and_create(self):
        data = self.env['mtbg.tours.content.block'].mtbg_picker_data()
        entry = next(b for b in data['blocks'] if b['id'] == self.bring.id)
        self.assertEqual(entry['excerpt'], 'Helmet Water')
        self.assertEqual(entry['type_label'], 'What to Bring')
        new = self.env['mtbg.tours.content.block'].mtbg_create_from_editor('Rain Policy')
        self.assertTrue(new['id'])
        self.assertIn('data-oe-field="body"', new['html'])

    def test_install_moves_placements_into_the_description(self):
        tour = self.env['mtbg.tour'].create({'name': 'Old Style', 'slug': 'cb-old-style', 'description': '<p>Text</p>'})
        self.env['mtbg.tour.block.line'].create([
            {'tour_id': tour.id, 'block_id': self.bring.id, 'sequence': 1, 'title': 'Packing'},
            {'tour_id': tour.id, 'block_id': self.book.id, 'sequence': 2},
        ])
        self.env.flush_all()
        post_init_hook(self.env)
        description = str(tour.description)
        self.assertTrue(description.startswith('<p>Text</p>'))
        self.assertLess(description.index('Packing'), description.index(f'data-mtbg-block="{self.bring.id}"'))
        self.assertLess(description.index(f'data-mtbg-block="{self.bring.id}"'), description.index(f'data-mtbg-block="{self.book.id}"'))
        self.assertEqual([l.block_id.id for l in tour.block_line_ids.sorted('sequence')], [self.bring.id, self.book.id])
        out = self.env['mtbg.tours.content.block']._mtbg_expand(tour.description)
        self.assertIn('<li>Helmet</li>', out)
        self.assertIn('Pick a date.', out)


@tagged('post_install', '-at_install', 'mtbg')
class TestContentBlockPage(HttpCase):

    def test_tour_page_shows_the_shared_content(self):
        block = self.env['mtbg.tours.content.block'].create({'name': 'Rain Policy', 'body': '<p>We ride in the rain.</p>'})
        self.env['mtbg.tour'].create({'name': 'Wet Loop', 'slug': 'cb-wet-loop', 'is_published': True,
                                      'description': Markup('<p>Intro</p>') + placeholder_html(block.id)})
        html = self.url_open('/tours/cb-wet-loop').text
        self.assertIn('We ride in the rain.', html)
        self.assertNotIn('s_mtbg_content_block_placeholder', html)
        block.body = '<p>Ponchos provided.</p>'
        self.assertIn('Ponchos provided.', self.url_open('/tours/cb-wet-loop').text, "pages follow the shared block")

    def test_editor_choose_and_edit_in_place(self):
        """Website editor: drop the block, pick it in the picker, edit it in place, save."""
        block = self.env['mtbg.tours.content.block'].create({'name': 'Rain Policy', 'body': '<p>We ride in the rain.</p>'})
        tour = self.env['mtbg.tour'].create({'name': 'Editor Tour', 'slug': 'cb-editor-tour', 'is_published': True,
                                             'description': '<p>Intro text</p>'})
        self.start_tour(self.env['website'].get_client_action_url('/tours/cb-editor-tour', True),
                        'mtbg_content_block_tour', login='admin', timeout=180)
        self.assertIn('Ponchos are provided.', str(block.body), "Edit in place writes the shared block")
        saved = str(tour.description)
        self.assertIn(f'data-mtbg-block="{block.id}"', saved)
        self.assertNotIn('Ponchos', saved, "the page stores only the block id, not its content")
        self.assertNotIn('data-oe-model', saved)
        self.assertEqual(tour.block_line_ids.block_id, block)

    def test_editor_blocks_inside_a_block(self):
        """Unlocked, a reusable block's content is native blocks with their own options; blocks drop into it."""
        from markupsafe import Markup
        from odoo.addons.mtbg_tours_content_blocks.models.content_block import placeholder_html
        block = self.env['mtbg.tours.content.block'].create({
            'name': 'Why Ride', 'body': '<section class="s_text_block o_cc o_cc5 pt48 pb48" data-snippet="s_text_block" '
                                        'data-name="Text"><div class="container s_allow_columns"><h3>Why Ride With Us?</h3>'
                                        '<p>We are direct.</p></div></section>'})
        tour = self.env['mtbg.tour'].create({'name': 'Nested Tour', 'slug': 'cb-nested-tour', 'is_published': True,
                                             'description': Markup('<p>Intro</p>') + placeholder_html(block.id)})
        self.start_tour(self.env['website'].get_client_action_url('/tours/cb-nested-tour', True),
                        'mtbg_content_block_nested_tour', login='admin', timeout=180)
        saved = str(tour.description)
        self.assertIn('s_alert', str(block.body), "the dropped block is saved in the shared block")
        self.assertNotIn('s_alert', saved, "the page stores only the block id, not its content")
        self.assertRegex(saved, r'class="[^"]*\bs_mtbg_content_block\b[^"]*\bo_not_editable\b',
                         "the stored placeholder stays locked")


    def test_block_editor_page(self):
        """The block alone in the website layout, its content the block's own field (full website builder)."""
        block = self.env['mtbg.tours.content.block'].create({'name': 'Builder Page Block',
                                                            'body': '<p>Edited with the builder.</p>'})
        action = block.action_mtbg_edit_in_builder()
        self.assertIn('path=%2Fmtbg%2Fblock%2F' + str(block.id), action['url'])
        self.assertIn('enable_editor=1', action['url'])
        anonymous = self.url_open(f'/mtbg/block/{block.id}')
        self.assertNotIn('Edited with the builder.', anonymous.text, "not a public page")
        self.authenticate('admin', 'admin')
        page = self.url_open(f'/mtbg/block/{block.id}')
        self.assertEqual(page.status_code, 200)
        self.assertIn('Edited with the builder.', page.text)
        self.assertIn(f'data-oe-model="mtbg.tours.content.block" data-oe-id="{block.id}" data-oe-field="body"',
                      page.text)
        self.assertEqual(self.url_open('/mtbg/block/999999').status_code, 404)

    def test_group_block(self):
        """Group: one background behind several blocks, inserted and styled with the website builder."""
        block = self.env['mtbg.tours.content.block'].create({'name': 'Group Host', 'body': '<p>Before the group.</p>'})
        self.start_tour(self.env['website'].get_client_action_url(f'/mtbg/block/{block.id}', True),
                        'mtbg_group_tour', login='admin', timeout=180)
        body = str(block.body)
        self.assertIn('s_mtbg_group', body)
        self.assertIn('s_mtbg_group_boxed', body)
        self.assertRegex(body, r'(?s)class="s_mtbg_group[^"]*"[^>]*>\s*<div class="oe_structure[^"]*">.*'
                               r'<section class="s_cover.*<section class="s_text_block',
                         "the group's blocks are inside its drop area")
        cover = re.search(r'<section class="(s_cover[^"]*)"', body)
        self.assertTrue(cover, "the dropped Cover is saved in the group")
        self.assertNotIn('oe_img_bg', cover.group(1), "a block dropped into a group is transparent")
        self.assertNotRegex(cover.group(1), r'\bo_cc\d?\b')
