import re
from markupsafe import Markup

from odoo.exceptions import UserError
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

    # ------------------------------------------------------------------ reusable blocks inside reusable blocks
    def _block(self, name, body):
        return self.env['mtbg.tours.content.block'].create({'name': name, 'body': body})

    def test_nested_blocks_render(self):
        """A block placed inside another block's content is filled too, for visitors and in the editor."""
        outer = self._block('Why Ride', Markup('<h3>Why</h3>') + placeholder_html(self.bring.id))
        Block = self.env['mtbg.tours.content.block']
        out = str(Block._mtbg_expand(placeholder_html(outer.id)))
        self.assertIn('<h3>Why</h3>', out)
        self.assertIn('<li>Helmet</li>', out, "the inner block's content is in the page's HTML")
        self.assertNotIn('s_mtbg_content_block_placeholder', out)
        editor = str(Block._mtbg_expand(placeholder_html(outer.id), editable=True))
        self.assertIn(f'data-oe-id="{self.bring.id}" data-oe-field="body"', editor, "the inner block is its own field")
        self.assertIn('data-mtbg-label="What to Bring"', editor, "and shows its name, locked")

    def test_block_inside_itself_renders_once(self):
        """A in B in A: each shows once, then it stops (the editor marks where)."""
        first = self._block('First', Markup('<p>first-content</p>'))
        second = self._block('Second', Markup('<p>second-content</p>') + placeholder_html(first.id))
        first.body = Markup('<p>first-content</p>') + placeholder_html(second.id)
        Block = self.env['mtbg.tours.content.block']
        out = str(Block._mtbg_expand(placeholder_html(first.id)))
        self.assertEqual(out.count('first-content'), 1)
        self.assertEqual(out.count('second-content'), 1)
        self.assertNotIn('s_mtbg_content_block_placeholder', out, "visitors see nothing where it would repeat")
        editor = str(Block._mtbg_expand(placeholder_html(first.id), editable=True))
        self.assertIn('data-mtbg-cycle="self"', editor)

    def test_nesting_stops_after_five_levels(self):
        blocks = []
        for level in range(7, 0, -1):
            inner = placeholder_html(blocks[-1].id) if blocks else Markup('')
            blocks.append(self._block(f'Level {level}', Markup('<p>level-%s</p>') % level + inner))
        out = str(self.env['mtbg.tours.content.block']._mtbg_expand(placeholder_html(blocks[-1].id)))
        for level in range(1, 6):
            self.assertIn(f'level-{level}<', out)
        self.assertNotIn('level-6<', out, "at most five blocks deep")

    def test_used_on_counts_blocks_that_contain_it(self):
        before = self.bring.usage_total
        self._block('Holder', placeholder_html(self.bring.id))
        self.bring.invalidate_recordset(['usage_total'])
        self.assertEqual(self.bring.usage_total, before + 1)
        library = self.env['mtbg.content.block.library']
        self.assertEqual(library.mtbg_used_inside([self.bring.id, self.book.id]), {'What to Bring': ['Holder']},
                         "archiving it asks first: it would empty the Holder block")

    def test_editor_block_knows_the_blocks_around_it(self):
        outer = self._block('Around', placeholder_html(self.bring.id))
        inner = self._block('Inner', placeholder_html(outer.id))
        html = self.env['mtbg.tours.content.block'].mtbg_editor_block(inner.id, [outer.id])['html']
        self.assertIn('data-mtbg-cycle="self"', str(html), "placed inside Around, Inner does not show Around again")

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


@tagged('post_install', '-at_install', 'mtbg')
class TestBlockLibrary(TransactionCase):
    """The Reusable Blocks page: where blocks are used, duplicates, tags and actions on several blocks."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Block = cls.env['mtbg.tours.content.block']
        cls.Lib = cls.env['mtbg.content.block.library']
        cls.used = Block.create({'name': 'Lib Used', 'body': '<p>Shared policy text.</p>'})
        cls.twin = Block.create({'name': 'Lib Twin', 'body': '<p>Shared policy text.</p>'})
        cls.empty = Block.create({'name': 'Lib Empty', 'body': '<style>.x{}</style>'})
        cls.outer = Block.create({'name': 'Lib Outer', 'body': Markup('<p>Outer</p>') + placeholder_html(cls.used.id)})
        cls.tour = cls.env['mtbg.tour'].create({'name': 'Lib Tour', 'slug': 'lib-tour',
                                                'description': placeholder_html(cls.used.id)})

    def _row(self, data, block):
        return next(b for b in data['blocks'] if b['id'] == block.id)

    def test_library_rows(self):
        data = self.Lib.mtbg_get_library()
        used = self._row(data, self.used)
        self.assertEqual(used['usage'], 2, "the tour and the block that contains it")
        self.assertTrue(used['duplicate'] and self._row(data, self.twin)['duplicate'], "same content")
        self.assertTrue(self._row(data, self.empty)['empty'])
        self.assertEqual(self._row(data, self.twin)['usage'], 0)
        details = self.Lib.mtbg_get_block(self.used.id)
        kinds = sorted((u['kind'], u['name']) for u in details['used_on'])
        self.assertEqual(kinds, [('block', 'Lib Outer'), ('tour', 'Lib Tour')])
        self.assertEqual(next(u for u in details['used_on'] if u['kind'] == 'tour')['url'], '/tours/lib-tour')

    def test_details_and_tags(self):
        tag = self.Lib.mtbg_save_tag(False, 'Policies')
        with self.assertRaises(UserError):
            self.Lib.mtbg_save_tag(False, 'policies')
        details = self.Lib.mtbg_save_block(self.twin.id, {'name': 'Lib Twin 2', 'block_type': 'policy',
                                                          'note': 'Old copy', 'tag_ids': [tag], 'active': False})
        self.assertEqual((details['name'], details['type'], details['note'], details['tag_ids']),
                         ('Lib Twin 2', 'policy', 'Old copy', [tag]))
        self.assertTrue(self.twin.active, "only the page's fields are written")
        self.Lib.mtbg_save_tag(tag, 'Policy', 3)
        self.assertEqual((self.twin.tag_ids.name, self.twin.tag_ids.color), ('Policy', 3))
        picker = self.env['mtbg.tours.content.block'].mtbg_picker_data()
        self.assertIn(tag, next(b for b in picker['blocks'] if b['id'] == self.twin.id)['tag_ids'])
        self.assertIn('Policy', [t['name'] for t in picker['tags']])
        self.Lib.mtbg_delete_tag(tag)
        self.assertFalse(self.twin.tag_ids)
        self.assertTrue(self.twin.exists())

    def test_bulk(self):
        tag = self.Lib.mtbg_save_tag(False, 'Bulk')
        blocks = self.twin | self.empty
        self.Lib.mtbg_bulk(blocks.ids, 'add_tag', tag)
        self.assertEqual(blocks.tag_ids.ids, [tag])
        self.Lib.mtbg_bulk(blocks.ids, 'remove_tag', tag)
        self.assertFalse(blocks.tag_ids)
        self.Lib.mtbg_bulk(blocks.ids, 'set_type', 'faq')
        self.assertEqual(set(blocks.mapped('block_type')), {'faq'})
        copies = self.env['mtbg.tours.content.block'].browse(self.Lib.mtbg_bulk([self.twin.id], 'duplicate'))
        self.assertEqual(copies.name, 'Lib Twin (copy)')
        self.Lib.mtbg_bulk(blocks.ids, 'archive')
        self.assertFalse(any(blocks.mapped('active')))
        self.Lib.mtbg_bulk(blocks.ids, 'restore')
        self.assertTrue(all(blocks.mapped('active')))
        with self.assertRaises(UserError):
            self.Lib.mtbg_bulk([self.used.id], 'delete')
        self.assertTrue(self.used.exists(), "a block still used is never deleted")
        self.Lib.mtbg_bulk(copies.ids, 'delete')
        self.assertFalse(copies.exists())

    def test_builtin_blocks(self):
        """Blocks an extension creates (its data) count as used and are never deleted."""
        builtin = self.env['ir.model.data'].search([('model', '=', 'mtbg.tours.content.block')], limit=1)
        if not builtin:
            self.skipTest("no built-in block installed")
        block = self.env['mtbg.tours.content.block'].browse(builtin.res_id)
        row = self._row(self.Lib.mtbg_get_library(), block)
        self.assertTrue(row['builtin'])
        self.assertGreaterEqual(row['usage'], 1)
        self.assertEqual(self.Lib.mtbg_get_block(block.id)['used_on'][0]['kind'], 'extension')
        with self.assertRaises(UserError):
            self.Lib.mtbg_bulk([block.id], 'delete')
        self.assertTrue(block.exists())

    def test_create(self):
        tag = self.Lib.mtbg_save_tag(False, 'New ones')
        block = self.env['mtbg.tours.content.block'].browse(self.Lib.mtbg_create_block('Fresh', [tag], 'faq'))
        self.assertEqual((block.name, block.block_type, block.tag_ids.ids), ('Fresh', 'faq', [tag]))


@tagged('post_install', '-at_install', 'mtbg')
class TestBlockLibraryPage(HttpCase):

    def test_preview_and_page(self):
        Block = self.env['mtbg.tours.content.block']
        block = Block.create({'name': 'Lib Preview', 'body': '<p>Preview me.</p>'})
        Block.create({'name': 'Lib Other', 'body': '<p>Other.</p>'})
        self.authenticate('admin', 'admin')
        page = self.url_open(f'/mtbg/block/{block.id}?preview=1&theme=dark').text
        self.assertIn('Preview me.', page)
        self.assertIn('mtbg-theme-dark', page)
        self.assertNotIn('Back to Reusable Blocks', page, "the preview shows the block alone")
        self.assertIn('Back to Reusable Blocks', self.url_open(f'/mtbg/block/{block.id}').text)
        code = f"""
            const deadline = Date.now() + 20000;
            (function check() {{
                const items = [...document.querySelectorAll('.mtbg_bl_item')].map((i) => i.textContent);
                const frame = document.querySelector('.mtbg_bl_frame');
                const name = document.querySelector('.mtbg_bl_name');
                if (items.some((t) => t.includes('Lib Other')) && frame && name && name.value === 'Lib Preview') {{
                    console.log('test successful');
                }} else if (Date.now() > deadline) {{
                    console.error(`items=${{items.length}} frame=${{!!frame}} name=${{name && name.value}}`);
                }} else {{ setTimeout(check, 300); }}
            }})();
        """
        self.browser_js(f'/odoo/action-mtbg_tours_content_blocks.action_mtbg_extension_page?block={block.id}', code,
                        ready="document.readyState === 'complete'", login='admin', timeout=90)
