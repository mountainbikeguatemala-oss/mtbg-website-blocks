{
    'name': 'MTBG Tours — Reusable Blocks',
    'version': '19.0.0.10.0',
    # where the updater gets it (the website blocks pack's repo)
    'mtbg_github_source': {'repo': 'git@github.com:mountainbikeguatemala-oss/mtbg-website-blocks.git', 'subdir': 'addons'},
    # its section on the Extensions panel: Custom blocks (its main job is website editor blocks)
    'mtbg_tours_section': 'blocks',
    'category': 'Website',
    'summary': 'Reusable Block and Group building blocks: shared content placed visually; one background behind several blocks',
    'description': """
Shared content (What to Bring, How to Book, policies...) placed visually in the website editor.

* "Reusable Block" building block: drop it anywhere (a tour's description or any page), choose the
  shared block in a search / preview picker, move it like any other content
* The page stores only the block id; its current content is filled in when the page is rendered, so
  an edit shows on every page that uses it (and stays indexable, without JavaScript)
* Edit in place: unlock the shared content right on the page, saving writes the block itself
* Open in the back office, create a new block from the picker, or make a local copy for one page
* Its own app menu, Website Blocks: the blocks (board and list), the Block Library, the Page Templates, the Card
  Designer (mtbg_website_cards) and the Extensions page (every website block module, its switch and its page)
* Block Library (Website Blocks › Block Library, the extension's tile): every block with where it is
  used, organised by type and tags (drag blocks onto a tag, act on several at once), a live preview, and the full
  website builder for the content
* Page templates (Website Blocks › Page Templates): layouts of the kinds of page other modules draw (e.g. Tours'
  tour and rental pages), a Desktop and a Mobile one, edited visually with a live preview

Part of the MTBG website blocks: needs only Odoo's website (Tours plugs its pages in: mtbg_tours_page_templates).
""",
    'author': 'MTBG Tours contributors',
    'license': 'LGPL-3',
    'depends': ['website'],
    'data': [
        'security/ir.model.access.csv',
        'views/website_blocks_menu.xml',
        'views/snippets.xml',
        'views/backend_views.xml',
        'views/block_page_templates.xml',
        'views/block_library.xml',
        'views/page_template_views.xml',
        'views/website_blocks_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'mtbg_tours_content_blocks/static/src/snippets/s_mtbg_content_block/content_block.scss',
            'mtbg_tours_content_blocks/static/src/snippets/s_mtbg_group/group.scss',
        ],
        'web.assets_backend': [
            'mtbg_tours_content_blocks/static/src/library/*',
            'mtbg_tours_content_blocks/static/src/template_editor/*',
        ],
        'website.assets_inside_builder_iframe': [
            'mtbg_tours_content_blocks/static/src/snippets/s_mtbg_content_block/content_block.edit.scss',
            'mtbg_tours_content_blocks/static/src/snippets/s_mtbg_group/group.edit.scss',
        ],
        'website.website_builder_assets': [
            'mtbg_tours_content_blocks/static/src/website_builder/**/*',
        ],
        'web.assets_tests': [
            'mtbg_tours_content_blocks/static/tests/tours/**/*',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
}
