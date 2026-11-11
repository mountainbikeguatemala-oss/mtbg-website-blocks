{
    'name': 'MTBG Website — Cloudflare Page Cache',
    'version': '19.0.0.8.0',
    'category': 'Website/Website',
    'summary': "Anonymous visitors get the public pages from Cloudflare's cache; Odoo says what may be cached and "
               "empties the cache on every change",
    'description': """
Ships switched OFF: Settings › Website › Cloudflare page cache. Needs no other extension than Visits by Script: any
Odoo website can use it.

* Odoo marks the pages Cloudflare may keep: anonymous GET pages on the list of addresses in the settings (to start:
  the homepage and the blog) and the website's own public pages, never for a logged-in user (cookie ``mtbg_auth``,
  set at login and removed at logout), never in debug or the editor. Such a page carries no cookie (no session, no
  language cookie) and ``Cache-Control: public, max-age=0, s-maxage=<seconds>, stale-if-error=604800``; every other
  page is untouched.
* The form token of a cached page comes from ``/mtbg/session`` when a visitor starts filling a form
  (``window.mtbgSession``), with their country for the phone field.
* An edit to a website page, view, menu, the website's settings or the blog empties Cloudflare's cache (the zone's
  "purge everything", through Cloudflare Connector), once per save, with a one-minute catch-up job. Every purge is
  logged.
* Other extensions say themselves what of theirs the pages show (0.8.0, no dependency either way): the models to
  watch, system parameter prefixes, public file addresses, what changes by itself, and the live values (prices,
  availability, statuses loaded after the page opens: listed under the settings, never kept by Cloudflare). See
  models/sources.py and models/live_values.py.
* Needs Visits by Script (visits recorded by the page's script) so cached pages keep counting visits.
""",
    'author': 'MTBG Tours contributors',
    'license': 'LGPL-3',
    'depends': ['website', 'mtbg_tours_visit'],
    'mtbg_github_source': {'repo': 'git@github.com:mountainbikeguatemala-oss/mtbg-website-blocks.git', 'subdir': 'addons'},
    'mtbg_tours_section': 'website',
    'data': [
        'security/ir.model.access.csv',
        'data/config.xml',
        'data/cron.xml',
        'views/templates.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_frontend': ['mtbg_tours_edge_cache/static/src/js/session.js'],
    },
    'installable': True,
}
