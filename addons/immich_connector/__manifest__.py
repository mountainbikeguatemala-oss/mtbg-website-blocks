{
    "name": "Immich Connector",
    "version": "19.0.1.0.3",
    "category": "Productivity/Connectors",
    "mtbg_tours_section": "connectors",
    "summary": "One connection to an office photo server running Immich: its token, its office upload page and wifi, "
               "album links, an optional internet-facing Immich client, and a setup wizard with the server's files",
    "description": """
One connection to a photo server (a NAS running Immich and a small sync service), for any Odoo site:

* The photo server's token: made in Odoo (shown once, stored hashed), checked in constant time with a fresh read on
  every call (``env['immich.connector']._check_bearer(request)``), so a new token works at once in every worker; the
  last time the server called in is kept.
* The office upload page's address and the office wifi name (staff are told to connect to it before uploading).
* Immich's address on the office network, for album links (``<Immich URL>/albums/<id>``).
* Optional: "Immich reachable from the internet", with an API key: a small client (create, read and rename albums,
  Test connection), so an extension can make albums itself instead of waiting for the photo server.
* Set up the photo server (a wizard): what is needed, the office addresses, the token, a zip with the server's files
  (config.env filled in from this site's settings, secrets left blank; docker-compose.yml; the sync service; the
  install steps), then "Waiting for the photo server to call in".
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
