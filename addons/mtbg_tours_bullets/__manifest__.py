{
    'name': 'MTBG Tours — Bullets',
    'version': '19.0.0.1.1',
    # where the updater gets it (the website blocks pack's repo)
    'mtbg_github_source': {'repo': 'git@github.com:mountainbikeguatemala-oss/mtbg-website-blocks.git', 'subdir': 'addons'},
    'category': 'Website',
    'summary': 'A "Bullets" website block: lists whose bullets are icons (check box, bookmark, cross or any icon)',
    'description': """
A list whose bullets are icons, as a website block (website editor › Text › Bullets): on pages, in tour descriptions
and in reusable blocks.

* Its options: a style (Check box, Bookmark, Cross, None), or any icon from the icon picker with its colour and size,
  a box behind it (colour, size, corners) and the space after it.
* Wrapped lines hang under the text; right-to-left languages put the icon on the right.
* The old site's lists keep their look with no change to the content: .highlights (bookmark), .checkbullet (check
  box) and .xbullet (cross).
""",
    'author': 'MTBG Tours contributors',
    'license': 'LGPL-3',
    'depends': ['website'],
    # its section on the Extensions panel: Custom blocks (its main job is a website editor block)
    'mtbg_tours_section': 'blocks',
    'data': [
        'views/snippets.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'mtbg_tours_bullets/static/src/snippets/s_mtbg_icon_list/icon_list.scss',
        ],
        'website.website_builder_assets': [
            'mtbg_tours_bullets/static/src/builder/icon_list_option.xml',
            'mtbg_tours_bullets/static/src/builder/icon_list_option_plugin.js',
        ],
    },
    'installable': True,
}
