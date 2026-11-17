# Cloudflare Connector

One Cloudflare connection for every extension that uses Cloudflare: the account, its API token, R2 storage (backups,
photos) and, since 19.0.2.0.0, the website's page cache. It depends only on Odoo's Website.

## Parts

| Part | Where | What |
|---|---|---|
| Account, API token, cache purge | `models/connector.py` (`cloudflare.api`) | Settings › Cloudflare; purge everything, or by URL (30 a call), prefix, host or cache tag (100 a call) |
| R2 storage | `models/r2.py` (`cloudflare.r2`) | S3-compatible client; Set up Cloudflare / Set up photos storage wizards |
| Page cache | `models/edge_cache.py`, `ir_http.py`, `pages.py`, `sources.py`, `live_values.py` | Settings › Website › Cloudflare page cache (ships OFF) |

## The page cache merge (19.0.2.0.0)

The page cache was its own extension, "Cloudflare Page Cache" (`mtbg_tours_edge_cache`, last 19.0.0.9.0). The owner
asked on 2026-11-16 for it to be merged into this connector, because the fewest extensions is a governing rule. On a site that had it:

* Updating this connector to 19.0.2.0.0 (or installing it) hands every record of the former extension to this module
  with its id (`tools/retire.py`, run by the pre-migrate or the pre_init_hook): the four jobs, the system parameters
  (`mtbg_tours.edge_cache*`, keys unchanged), the views, the access rules, the models and fields with their tables,
  and the purge log rows. Nothing is dropped and nothing is made twice.
* The former extension is marked *uninstallable*: Odoo never lists, installs or loads it again. No uninstall runs. If
  its old folder is still on a server, this module keeps it uninstallable at every load and after Update Apps List,
  and the end-migrate removes anything the old folder made again in that run.
* A database whose page cache was older than 0.9.0 runs the former migrations it had not had
  (`tools/page_cache_upgrades.py`). At 0.9.0 it runs none.
* Extensions keep declaring what their pages show on their own models (`_mtbg_edge_cache_watch`,
  `_mtbg_edge_cache_pages`, `_mtbg_edge_cache_param_prefixes`, `_mtbg_edge_cache_static_prefixes`,
  `_mtbg_edge_cache_fingerprint()`, `_mtbg_edge_cache_live_values`), with no dependency. They check for
  `'mtbg.edge.cache' in env`. Only the Python path of the helpers changed: `odoo.addons.cloudflare_connector.models.*`.
* Visits by Script (`mtbg_tours_visit`) is no longer a dependency. Where it is installed, cached pages keep counting
  visits.

## How a page purge empties Cloudflare (19.0.2.0.1)

A purge by single URL only matches a copy stored under Cloudflare's default cache key. A cache rule with a custom
cache key (for example campaign links sharing one copy) or a rule that does not match the purge request makes it
match nothing, while Cloudflare still answers OK. So page purges use:

* cache tags: every cached page carries `Cache-Tag: pages-<site>,page-<address>` (Cloudflare strips it before the
  visitor). Every page = one tag call; some pages = their own tags (every language at once);
* prefixes (`www.example.com/tours/a-ride`) for each address except the homepage, 100 a call: they also empty copies
  made before the pages carried tags.

After the purge, up to 3 of the purged pages are asked for as a visitor. A copy Cloudflare still serves from its cache,
older than the purge, is logged "Cloudflare said OK but the page is still cached" (Checked: Still cached), never Done.
A save's own purge is checked by the one-minute job.

`deploy/` holds the holding page nginx serves while Odoo restarts or updates (see `deploy/README.md`).
