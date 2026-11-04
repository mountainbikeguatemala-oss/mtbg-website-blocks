{
    'name': 'Website Reviews (Google & Tripadvisor)',
    'version': '19.0.0.4.4',
    # where the updater gets it (the website blocks pack's repo)
    'mtbg_github_source': {'repo': 'git@github.com:mountainbikeguatemala-oss/mtbg-website-blocks.git', 'subdir': 'addons'},
    # its section on the Extensions panel: Custom blocks (its main job is website editor blocks)
    'mtbg_tours_section': 'blocks',
    'category': 'Website',
    'summary': 'Google Business Profile and Tripadvisor reviews synced into Odoo, shown with a Reviews slider block',
    'description': """
Reviews of any number of Google Business Profile locations and Tripadvisor listings, pulled into a local table
and shown on the website with a "Reviews" building block (a slider of review cards).

* Reviews page (the extension's tile in Tours > Configuration > Extensions): presets for the Reviews blocks with a
  live preview (speech bubbles or cards, tail, corners, colours, which reviews, the block's and a review's parts in
  order by drag and drop, texts in every language), the reviews table, sources and accounts in one place. A block on
  a page names its preset, so a change to the preset changes every block using it.
* Review Accounts: a Google account (the business owner signs in with
  Google once; every location it manages can be added) or a Tripadvisor Content API key.
* Review Sources: one per Google location / Tripadvisor listing; synced daily and on demand. Google returns
  every review; Tripadvisor the latest ones on each sync, so the local table keeps the whole history.
* Reviews can be hidden, featured, added by hand or by CSV import (older reviews).
* Reviews blocks: drop one on any page and choose its preset.
""",
    'author': 'MTBG Tours contributors',
    'license': 'LGPL-3',
    'depends': ['website'],
    'external_dependencies': {'python': ['requests']},
    'data': [
        'security/ir.model.access.csv',
        'data/cron.xml',
        'data/presets.xml',
        'views/review_views.xml',
        'views/snippets.xml',
        'views/preset_templates.xml',
        'views/assets_templates.xml',
    ],
    'assets': {
        # every page: the Counter's look and a small loader; the blocks' code and the reviews' styles are in their own
        # bundle, loaded on the pages that have a Reviews block or a counter (owner, 2026-11-04, JS consolidation
        # part B: static/src/js/review_assets.js)
        'web.assets_frontend': [
            'website_review_sync/static/src/snippets/s_mtbg_counter/counter.scss',
            'website_review_sync/static/src/js/review_assets.js',
        ],
        'website_review_sync.assets_reviews': [
            'website_review_sync/static/src/js/count_up.js',
            'website_review_sync/static/src/snippets/s_mtbg_counter/counter.js',
            'website_review_sync/static/src/snippets/s_review_slider/review_slider.scss',
            'website_review_sync/static/src/snippets/s_review_slider/review_card.js',
            'website_review_sync/static/src/snippets/s_review_slider/review_slider.js',
            'website_review_sync/static/src/snippets/s_review_wall/review_wall.scss',
            'website_review_sync/static/src/snippets/s_review_wall/review_wall.js',
            'website_review_sync/static/src/snippets/s_review_preset/review_preset.scss',
            'website_review_sync/static/src/snippets/s_review_preset/review_preset.js',
        ],
        # the website editor: the blocks' code and styles are there from the start (a block dropped on any page)
        'website.assets_inside_builder_iframe': [
            ('include', 'website_review_sync.assets_reviews'),
        ],
        'web.assets_backend': [
            'website_review_sync/static/src/settings_page/*',
        ],
        'website.website_builder_assets': [
            'website_review_sync/static/src/js/count_up.js',
            'website_review_sync/static/src/website_builder/**/*',
        ],
    },
    'installable': True,
}
