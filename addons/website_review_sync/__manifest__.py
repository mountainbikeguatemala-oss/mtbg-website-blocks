{
    'name': 'Website Reviews (Google & Tripadvisor)',
    'version': '19.0.0.3.0',
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
    ],
    'assets': {
        'web.assets_frontend': [
            'website_review_sync/static/src/snippets/s_review_slider/review_slider.scss',
            'website_review_sync/static/src/snippets/s_review_slider/review_card.js',
            'website_review_sync/static/src/snippets/s_review_slider/review_slider.js',
            'website_review_sync/static/src/snippets/s_review_wall/review_wall.scss',
            'website_review_sync/static/src/snippets/s_review_wall/review_wall.js',
            'website_review_sync/static/src/snippets/s_review_preset/review_preset.scss',
            'website_review_sync/static/src/snippets/s_review_preset/review_preset.js',
        ],
        'web.assets_backend': [
            'website_review_sync/static/src/settings_page/*',
        ],
        'website.website_builder_assets': [
            'website_review_sync/static/src/website_builder/**/*',
        ],
    },
    'installable': True,
}
