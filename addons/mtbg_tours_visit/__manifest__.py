{
    'name': 'MTBG Tours — Visits by Script',
    'version': '19.0.0.1.5',
    'category': 'Website/Website',
    'summary': "The website's visits recorded by a light script after the page loads, so pages can be cached",
    'description': """
Page speed, phase 2 (owner, 2026-10-30): Odoo records an anonymous visitor's page view while it builds the page, so
every page has to be built for every visitor. With this extension the page carries a small tag on the pages Odoo
tracks, and a few lines in the page post the visit to ``/mtbg/visit`` as soon as its content is there. The server records it with
Odoo's own visitor code, exactly as before: the same visitor (IP, browser, session), the page and its address, the
language, the country and city (Cloudflare), the marketing (UTM) cookies, and the Communication Flows visitor
details (page title, device, place).

* Logged-in users, bots and forms are recorded as before (while the page is built).
* Settings › Website › "Visits recorded by the page's script" (on by default): off records anonymous visits while
  the page is built again, at once.
* What differs: a browser without JavaScript (most scrapers) is no longer recorded; a visit is recorded about a
  second after the page loads instead of while it is built; people browsing inside the Instagram, Facebook,
  WhatsApp and Pinterest apps are recorded (Odoo's bot list counts those browsers as bots, so they never were).
* A visit not recorded is logged with its reason ("visit refused: crawler (bot)"), never who sent it.
""",
    'author': 'MTBG Tours contributors',
    'license': 'LGPL-3',
    'mtbg_github_source': {'repo': 'git@github.com:mountainbikeguatemala-oss/mtbg-website-blocks.git', 'subdir': 'addons'},
    'depends': ['website', 'utm'],
    'mtbg_tours_section': 'website',
    'data': [
        'data/config.xml',
        'views/templates.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
}
