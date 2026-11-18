{
    "name": "Cloudflare Connector",
    "version": "19.0.2.1.0",
    "category": "Productivity/Connectors",
    "mtbg_tours_section": "connectors",
    "summary": "One Cloudflare connection: the account, its API token, R2 storage and the website's page cache, for "
               "every extension that uses Cloudflare",
    "description": """
One Cloudflare connection, like Google and Meta have theirs:

* Set up Cloudflare (a guided wizard): paste one setup token, then pick the bucket (a new one, with its name,
  location and lock explained and priced, or one the account has) and the website whose cache Odoo may clear.
  Odoo creates the bucket and its lock, makes its own keys (R2 limited to that bucket; cache purge limited to that
  zone), tests them and deletes the setup token in Cloudflare. If R2 is off on the account, it says how to turn it on.
* Settings › Cloudflare: the account ID, an API token (Check API token) and an R2 bucket with its access key
  (Test R2 connection: a write, a read and a delete).
* ``cloudflare.r2``: an S3-compatible client for R2 (AWS Signature V4, streamed multipart uploads, SHA-256 checked
  by R2 on every upload). Other extensions use it through a soft check, e.g. off-site backups.
* ``cloudflare.api``: calls to the Cloudflare REST API with the saved token, and the cache purge for the site's
  zone (everything, or URLs, prefixes, hosts or cache tags in batches, waiting on rate limits; it never raises).
* **Website page cache** (19.0.2.0.0: formerly the extension "Cloudflare Page Cache", ``mtbg_tours_edge_cache``,
  merged in with its data and settings; owner, 2026-11-16: the fewest extensions). Ships switched OFF: Settings ›
  Website › Cloudflare page cache. Odoo marks the pages Cloudflare may keep (anonymous GET pages on the list of
  addresses and the website's own public pages; never for a logged-in user, cookie ``mtbg_auth``; never in debug or
  the editor): no cookie and ``Cache-Control: public, max-age=0, s-maxage=<seconds>, stale-if-error=604800``. A
  cached page's form token comes from ``/mtbg/session`` (``window.mtbgSession``). An edit to a website page, view,
  menu, the website's settings or the blog empties Cloudflare's copies of the pages (19.0.2.0.1: by the pages' cache
  tags and address prefixes, whatever the cache rules' cache key; never scripts, styles or pictures), then a few of
  them are asked for to check Cloudflare really emptied them; the purged "Pages to re-fill" are asked for again in the
  background and every night. Every purge is logged, with what changed. Other extensions say themselves what of theirs the pages show (models,
  system parameter prefixes, public files, what changes by itself, live values), no dependency either way: see
  models/sources.py and models/live_values.py. Visits by Script (``mtbg_tours_visit``), where installed, keeps
  cached pages counting visits.
* Secrets stay with administrators and are cleared on a copy of the site (neutralize).

* Several websites on one database (19.0.2.1.0): each website its own Cloudflare zone (Website › Settings › Cloudflare
  page cache) for its purges and its page cache; the zone of Settings › Cloudflare stays the default website's.

It depends on no product, only on Odoo's Website: it can be installed on any Odoo website.
""",
    "author": "MTBG Tours contributors",
    "license": "LGPL-3",
    "mtbg_github_source": {"repo": "git@github.com:mountainbikeguatemala-oss/mtbg-website-blocks.git", "subdir": "addons"},
    "depends": ["base_setup", "web", "website"],
    # the page cache's former extension: its records are this module's (pre_init_hook, 19.0.2.0.0 pre-migrate)
    "mtbg_takes_over": ["mtbg_tours_edge_cache"],
    "external_dependencies": {"python": ["requests"]},
    "data": [
        "security/ir.model.access.csv",
        "views/setup_views.xml",
        "views/photos_setup_views.xml",
        "views/res_config_settings_views.xml",
        "data/page_cache_config.xml",
        "data/page_cache_cron.xml",
        "views/page_cache_templates.xml",
        "views/page_cache_settings_views.xml",
    ],
    "assets": {
        "web.assets_frontend": ["cloudflare_connector/static/src/js/session.js"],
    },
    "pre_init_hook": "pre_init_hook",
    "post_init_hook": "post_init_hook",
    "installable": True,
}
