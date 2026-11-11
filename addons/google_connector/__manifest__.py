{
    "name": "Google Connector",
    "version": "19.0.1.5.2",
    "category": "Productivity/Connectors",
    "summary": "One Google login for every Google app (Gmail, Voice, Calendar, Maps): setup wizard, switches, shared "
               "client with limits and retries, sync log",
    "description": """
One Google connection for the apps that use Google, like the Zoho extension does for Zoho:

* Set up Google: a step-by-step wizard, the only place Google credentials are entered (the Google Cloud OAuth
  client and its redirect address, the apps and the access they need, the Google accounts, the Maps API key,
  Check access).
* A card per Google app in Settings: on / off, writes allowed, its Google account, its status.
* One client for every call to Google: token refresh, rate limits, retries; a sync log.
* Secrets stay with administrators and are cleared on a copy of the site (neutralize).

It depends on no product: apps (e.g. Communication Flows' Gmail and Google Voice, the Tours' Calendar and Maps)
plug into it.

* Events for the Google apps (mtbg.google.broadcast): a record announces what happened to it and each app listens;
  the apps bring the events and the records that announce them (the connector names no business model).
""",
    "author": "MTBG Tours contributors",
    "license": "LGPL-3",
    "mtbg_github_source": {"repo": "git@github.com:mountainbikeguatemala-oss/mtbg-website-blocks.git", "subdir": "addons"},
    "depends": ["base_setup", "web"],
    "external_dependencies": {"python": ["requests"]},
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/setup_views.xml",
        "views/connector_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "google_connector/static/src/**/*",
        ],
    },
    "installable": True,
}
