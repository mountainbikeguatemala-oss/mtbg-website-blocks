{
    'name': 'MTBG Website — Card Designer',
    'version': '19.0.0.1.0',
    # where the updater gets it (the website blocks pack's repo)
    'mtbg_github_source': {'repo': 'git@github.com:mountainbikeguatemala-oss/mtbg-website-blocks.git', 'subdir': 'addons'},
    'mtbg_tours_section': 'blocks',
    'category': 'Website',
    'summary': 'Design the website\'s cards visually: text over or beside the photo, fields on the photo or below, hover',
    'description': """
Card designs for the website's cards, made visually (Website › Content › Card Designs): each design shows the
records of a source (a module gives its sources: e.g. Tours' tours and group departures).

* Style: text over the photo, below it or above it; the photo's frame (3:2, 4:3, 16:9, square), corners, shadow
* The source's fields in order (drag and drop), each on the photo (top left, top right, bottom) or in the text, or
  hidden
* Hover: zoom the photo, darken it
* Colours for light pages and for dark pages (the preview's light / dark switch picks which you set)
* A live preview on real records, on a computer or a phone
* The "Cards" building block: a grid of a source's records (its filters, how many, columns) in a design

Part of the MTBG website blocks: needs only Odoo's website.
""",
    'author': 'MTBG Tours contributors',
    'license': 'LGPL-3',
    'depends': ['website'],
    'data': [
        'security/ir.model.access.csv',
        'views/card_templates.xml',
        'views/snippets.xml',
        'views/backend_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'mtbg_website_cards/static/src/block/cards.scss',
            'mtbg_website_cards/static/src/block/cards_block.js',
        ],
        'web.assets_backend': [
            'mtbg_website_cards/static/src/designer/*',
        ],
        'website.website_builder_assets': [
            'mtbg_website_cards/static/src/website_builder/*',
        ],
    },
    'installable': True,
}
