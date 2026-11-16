{
    "name": "Google Connector",
    "version": "19.0.1.7.0",
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
* Google Photos (google.photos, the Photos Library API): albums an app creates, renames, uploads into, lists and
  reads pictures of, for any app that declares Google Photos access (only the albums the app created; share links
  are made in Google Photos).
* Google Search Console (read only): the website's real searches (clicks, impressions, CTR, average position) by day,
  query, page, country and device, imported every night (16 months of history on first connect, 18 months kept), in
  Search Console reports (Website › Reporting when Website is installed, else their own menu), with an SEO summary
  (28 days against the 28 before) on the app's card.

Search Console setup:

1. The website's property exists and is verified in Google Search Console: a URL-prefix property
   (https://www.example.com/) or a domain property (sc-domain:example.com, verified by a DNS TXT record, e.g. in
   Cloudflare). A property already verified needs nothing more here.
2. The Google account connected in the connector is an Owner or Full user of that property (Search Console ›
   Settings › Users and permissions).
3. Settings › Google: switch Google Search Console on, then Google accounts › Reconnect that account and accept
   Search Console's read access (Set up Google › APIs lists the Google Search Console API to enable in the Cloud
   project, if it is not on yet).
4. The card's Settings: choose the property from the dropdown (a domain property is offered first when there is one,
   else the URL-prefix one), Save. The last 16 months come in over the next hours; every night the last 3 days are
   read again.
""",
    "author": "MTBG Tours contributors",
    "license": "LGPL-3",
    "mtbg_github_source": {"repo": "git@github.com:mountainbikeguatemala-oss/mtbg-website-blocks.git", "subdir": "addons"},
    "depends": ["base_setup", "web"],
    "external_dependencies": {"python": ["requests"]},
    "data": [
        "security/ir.model.access.csv",
        "views/setup_views.xml",
        "views/connector_views.xml",
        "views/search_console_views.xml",
        "data/ir_cron.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "google_connector/static/src/**/*",
        ],
    },
    "installable": True,
}
