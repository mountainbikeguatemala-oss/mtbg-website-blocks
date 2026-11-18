{
    "name": "Site Link Connector",
    "version": "19.0.0.2.3",
    "category": "Productivity/Connectors",
    "mtbg_tours_section": "connectors",
    "summary": "Links two Odoo sites: each other's address, database and API key, a call helper with a log of failed "
               "calls, a health check, a small inventory protocol (part lookup, part consumption), customers, "
               "customer repairs (quotation, status, invoice) and single sign-on",
    "description": """
Two Odoo sites of one business talk to each other through Odoo's own external API (``/json/2``, an API key of a
technical user on the other side). Nothing else is needed on either side: it installs on any Odoo 19 site.

* Settings › Site Link: the linked sites (name, address, database, API key, the other site's role, e.g. inventory
  source), Test connection (the other side's health: version, database, the methods it offers), the failed calls.
* ``site.link._site_link_call(site, model, method, *ids, **kwargs)``: one call to the other site, with a time limit,
  clear errors (``SiteLinkError``) and every failed call logged.
* ``site.link.api`` (the protocol, called by the other site's key user, who needs the group "Site Link: calls from
  a linked site"): ``health()``; where Inventory is installed (soft check, no dependency) ``part_lookup(barcode)``
  and ``part_consume(product, qty, reference, note)`` (internal use out of stock, idempotent on the reference);
  ``sso_ticket(login)`` (a one-time sign-in link, users of the group "Site link: single sign-on allowed" only),
  ``customer_search``, ``customer_create``, ``customer_bikes`` (where a customer bike model is installed); where
  Sales is installed (Repair used where it is) ``repair_quote``, ``repair_status``, ``repair_invoice`` (idempotent
  on the reference; nothing is sent); where Communication Flows' shared inbox is installed ``inbox_unread(login)``
  (how many conversations wait for a reply for that user: the Staff App's shop tile badge). See README.md.
* One employee list: ``user_sync(users)`` makes the linked site's employees users here (matched by login, no
  password, archived with them, shop groups by ``shop_access``); a site with "Send Employees" sends its list on every
  user change, daily and with "Sync employees now" (hook ``site.link._site_link_sync_users_list``). A login page
  button "Log in with your staff account" signs in through the site with the role Staff accounts
  (``/site_link/sso/start``, its return address checked to be a linked site's).
* ``site.link._site_link_sso_url(login)``, ``_site_link_repair_quote(...)`` and the other one-line helpers, and
  ``_site_link_offers(method)`` (soft check of what the other side offers).
* The API keys stay with administrators and are cleared on a copy of the site (neutralize).
""",
    "author": "MTBG Tours contributors",
    "license": "LGPL-3",
    "mtbg_github_source": {"repo": "git@github.com:mountainbikeguatemala-oss/mtbg-website-blocks.git", "subdir": "addons"},
    # rpc: Odoo's /json/2 endpoint (part of Odoo, installed by itself on every site)
    "depends": ["base", "web", "rpc"],
    "external_dependencies": {"python": ["requests"]},
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/cron.xml",
        "views/site_link_views.xml",
        "views/settings_views.xml",
        "views/login_templates.xml",
    ],
    "installable": True,
}
