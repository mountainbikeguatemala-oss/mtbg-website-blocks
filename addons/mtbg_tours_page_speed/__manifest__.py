{
    'name': 'MTBG Tours — Page Speed',
    'version': '19.0.0.11.1',
    'category': 'Website/Website',
    'summary': "The website's pictures as fast as the screen allows: the first one at once, phone and tablet sizes "
               "of the background photos, every photo's size",
    'description': """
Page speed, phase 4 (owner, 2026-10-30). On a page sent to an anonymous visitor, the first picture of the page's main
area (a photo, or a section's background photo) is the one the visitor waits for: it no longer waits its turn as a
lazy image, and the browser is told to fetch it first (a preload with high priority in the page's head).

A section's background photo comes as its ready phone (800 px) and tablet (1280 px) WebP copy, the original on
computers; a photo of the content gets its width and height (the page does not jump while it loads) and its ready
smaller copies (srcset). Only public image attachments, and only copies lighter than the original: a picture
without one stays as it is (never broken, never heavier).
The words before the pictures and icons (0.3.0): the theme's font stylesheets are fetched with the site's
stylesheet instead of after it, and the icon font is no longer preloaded ahead of the stylesheet.
The mobile menu's "back" button of a mega menu gets a label for screen readers.
Accessibility and search (0.4.0, owner's search plan): a picture without an alt gets its file's name in words (else
the page's title), at render time (nothing stored changes); the header logo is not lazy; a link with nothing to say
gets a name, a "Learn more" link says where it leads; links in a page's text are underlined. The photos' screen copies
are made again at WebP quality 70 by a job, kept only when lighter.
Visitor pages without Odoo's extras (0.5.0, a switch): anonymous visitors on ordinary pages get copies of Odoo's script
bundle (0.5.0) and stylesheet (0.6.0) without the editor's, the portal's and the back end's own pieces; the editor's
background shapes load after the page has shown.
The icons in two files (0.7.11, same switch): the icons the site uses in a small copy of Font Awesome, Odoo's whole font
for any other, fetched only by a page that draws one.
Lighter visitor pages (0.7.12, same switch): the back end's widgets out of the visitors' scripts, the chat's into the
chat's own bundle; the first screen's rules without unused animations or repeated selectors; the next page fetched
when the visitor points at a link.
The cover paints first (0.8.0, owner 2026-11-16): the first screen's rules only (the header, the content's first
screen), the menus' hidden content after the page's content, the visitors' scripts after the first paint; the speed
log retries a page Google could not measure, measures a slow phone page three times (its median) and flags a page
slow two nights in a row, with Lighthouse's LCP breakdown.
The speed log's dashboard (0.9.0, owner 2026-11-17): one big chart of every stat over the nights (phone and computer, a
second stat, the limit, a page's own line), last night against the week before, the worst pages and their main cause;
every night's rows, with each page's title, on their own page.
Any website (0.10.0, owner 2026-11-18): the extension moves to the universal repository (technical name kept) and needs
no Tours, only Odoo's Website and the admin look (side bar lists); several websites on one database are each measured
on their own (their address, their homepages), the dashboard shows one website at a time.
A click at once (0.11.0, desktop INP 2026-11-21): the visitors' scripts start in short slices, the page answers a
click between two: the bundle's modules (in Odoo's order), then the page's interactions (in Odoo's order), also those
of a bundle loaded later (the booking form's).
""",
    'author': 'MTBG Tours contributors',
    'license': 'LGPL-3',
    'mtbg_github_source': {'repo': 'git@github.com:mountainbikeguatemala-oss/mtbg-website-blocks.git', 'subdir': 'addons'},
    'depends': ['website', 'mtbg_backend_ui'],
    # the admin look's side bar lists (0.2.0)
    'mtbg_tours_requires': {'mtbg_backend_ui': '19.0.0.2.0'},
    'mtbg_tours_section': 'website',
    'data': ['security/ir.model.access.csv', 'views/templates.xml', 'views/speed_log_views.xml',
             'views/settings_views.xml', 'data/cron.xml', 'data/speed_log.xml'],
    'assets': {
        'web.assets_frontend': ['mtbg_tours_page_speed/static/src/scss/a11y.scss'],
        # 0.9.0: the speed log's dashboard (Chart.js from Odoo's own bundle, loaded when it opens)
        'web.assets_backend': ['mtbg_tours_page_speed/static/src/dashboard/*'],
        'web.assets_tests': ['mtbg_tours_page_speed/static/tests/tours/*'],
        # 0.8.0: the visitors' copy of Odoo's first small scripts, its lazyloader starting the script bundle after the
        # first paint and the first screen's stylesheets (static/src/js/lazyloader.js)
        'mtbg_tours_page_speed.assets_frontend_minimal_lean': [
            ('include', 'web.assets_frontend_minimal'),
            ('replace', 'web/static/src/legacy/js/public/lazyloader.js',
             'mtbg_tours_page_speed/static/src/js/lazyloader.js'),
        ],
        # the visitors' copy of Odoo's script bundle (models/lean.py: its removals follow the switch)
        # 0.11.0: its interactions start in short slices (static/src/js/sliced_start.js; its modules start in
        # slices too: static/src/js/lazyloader.js)
        'mtbg_tours_page_speed.assets_frontend_lazy_lean': [('include', 'web.assets_frontend_lazy'),
                                                            'mtbg_tours_page_speed/static/src/js/sliced_start.js'],
        # the visitors' copy of Odoo's stylesheet (0.6.0, same switch: its removals in models/lean.py)
        'mtbg_tours_page_speed.assets_frontend_lean': [('include', 'web.assets_frontend')],
        # ... and what comes after the page has shown: the editor's background shapes (their base rules stay)
        'mtbg_tours_page_speed.assets_frontend_late': [
            ('include', 'web._assets_helpers'),
            ('include', 'web._assets_frontend_helpers'),
            'web/static/src/scss/pre_variables.scss',
            'web/static/lib/bootstrap/scss/_variables.scss',
            'web/static/lib/bootstrap/scss/_variables-dark.scss',
            'web/static/lib/bootstrap/scss/_maps.scss',
            'html_builder/static/src/scss/background.scss',
        ],
    },
    'installable': True,
}
