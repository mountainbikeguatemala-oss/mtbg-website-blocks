{
    "name": "Cloudflare Connector",
    "version": "19.0.1.5.0",
    "category": "Productivity/Connectors",
    "mtbg_tours_section": "connectors",
    "summary": "One Cloudflare connection: the account, its API token and R2 storage, for every extension that uses "
               "Cloudflare",
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
  zone (everything, or URLs / prefixes / hosts in batches of 30, waiting on rate limits; it never raises).
* Secrets stay with administrators and are cleared on a copy of the site (neutralize).

It depends on no product: it can be installed on any Odoo site.
""",
    "author": "MTBG Tours contributors",
    "license": "LGPL-3",
    "mtbg_github_source": {"repo": "git@github.com:mountainbikeguatemala-oss/mtbg-website-blocks.git", "subdir": "addons"},
    "depends": ["base_setup", "web"],
    "external_dependencies": {"python": ["requests"]},
    "data": [
        "security/ir.model.access.csv",
        "views/setup_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "installable": True,
}
