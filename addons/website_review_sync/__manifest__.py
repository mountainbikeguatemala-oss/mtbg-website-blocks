{
    'name': 'Website Reviews (Google & Tripadvisor)',
    'version': '19.0.0.1.1',
    'category': 'Website',
    'summary': 'Google Business Profile and Tripadvisor reviews synced into Odoo, shown with a Reviews slider block',
    'description': """
Reviews of any number of Google Business Profile locations and Tripadvisor listings, pulled into a local table
and shown on the website with a "Reviews" building block (a slider of review cards).

* Review Accounts (Website > Configuration > Reviews): a Google account (the business owner signs in with
  Google once; every location it manages can be added) or a Tripadvisor Content API key.
* Review Sources: one per Google location / Tripadvisor listing; synced daily and on demand. Google returns
  every review; Tripadvisor the latest ones on each sync, so the local table keeps the whole history.
* Reviews can be hidden, featured, added by hand or by CSV import (older reviews).
* Reviews block: drop it on any page; options: source / platform, minimum rating, number of reviews, autoplay.
""",
    'author': 'MTBG Tours contributors',
    'license': 'LGPL-3',
    'depends': ['website'],
    'external_dependencies': {'python': ['requests']},
    'data': [
        'security/ir.model.access.csv',
        'data/cron.xml',
        'views/review_views.xml',
        'views/snippets.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'website_review_sync/static/src/snippets/s_review_slider/review_slider.scss',
            'website_review_sync/static/src/snippets/s_review_slider/review_card.js',
            'website_review_sync/static/src/snippets/s_review_slider/review_slider.js',
            'website_review_sync/static/src/snippets/s_review_wall/review_wall.scss',
            'website_review_sync/static/src/snippets/s_review_wall/review_wall.js',
        ],
        'website.website_builder_assets': [
            'website_review_sync/static/src/website_builder/**/*',
        ],
    },
    'installable': True,
}
