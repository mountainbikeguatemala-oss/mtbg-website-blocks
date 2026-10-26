{
    'name': 'MTBG Tours — Reusable Blocks',
    'version': '19.0.0.7.0',
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
* Reusable Blocks page (the extension's tile, Catalog › Reusable Blocks): every block with where it is used,
  organised by type and tags (drag blocks onto a tag, act on several at once), a live preview, and the full
  website builder for the content
* Existing tour block placements become reusable blocks at the end of the description on install
""",
    'author': 'MTBG Tours contributors',
    'license': 'LGPL-3',
    'depends': ['website', 'mtbg_tours_website'],
    'data': [
        'security/ir.model.access.csv',
        'views/snippets.xml',
        'views/backend_views.xml',
        'views/block_page_templates.xml',
        'views/block_library.xml',
        'views/page_template_views.xml',
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
