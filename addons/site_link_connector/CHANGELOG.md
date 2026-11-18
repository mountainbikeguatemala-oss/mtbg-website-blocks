# Changelog

Every version of this extension, newest first. Tags: `git tag -l 'site_link_connector-*'`.

## 19.0.0.2.0 · 2026-11-18
- **New: single sign-on** (owner, 2026-11-18: the Staff App's shop tile opens the shop site signed in).
  `sso_ticket(login)` answers a one-time link `/site_link/sso/<token>`: random token, only its hash kept, used once,
  valid 60 seconds, only for active internal users in the new group "Site link: single sign-on allowed" (nobody by
  default), never user ids 1 and 2. The link signs the user in and opens `/odoo`; any other link opens the login
  page. Every ticket and sign-in, given or refused, is logged.
- **New: one employee list** (owner, 2026-11-18: one site's employees are the users of both). `user_sync(users)`
  (`[{login, name, email, active, shop_access}]`) matches users by login (case does not matter), makes the missing
  ones as internal users without a password (no invitation email), keeps name and email, archives (and brings back)
  them with the other site, and gives (`shop_access` true) or takes away (false) the group "Site link: single sign-on
  allowed" plus the new **Shop Access Groups** of the linked sites (null: groups left alone). Never user ids 1 and 2,
  the calling user or portal users; users not in the list are left alone. Answers `[{login, user_id, created,
  updated}]`, logged.
- Sending side: **Send Employees** on a linked site sends this site's internal users (hook
  `site.link._site_link_sync_users_list()`, for other extensions to say who has shop access) on every user change
  (the cron runs soon after), by a daily cron, and with **Sync employees now**; skipped when the other site offers no
  `user_sync`.
- **New: "Log in with your staff account"** on the login page of a site linked to a site with the new role **Staff
  accounts**: `/site_link/sso/start?return=<address>` there (login first when needed) asks this site for a ticket for
  the signed-in employee and sends them back signed in. The return address must be on a linked site's address
  (same scheme, host and port); the sign-in link only opens paths of its own site.
- **New: customers** `customer_search(query, limit)`, `customer_create(name, phone, email)` (the existing contact by
  email or phone when there is one), `customer_bikes(partner_id)` (where a customer bike model `repair.bike` is
  installed; `[]` elsewhere).
- **New: customer repairs** (where Sales is installed; soft check): `repair_quote(reference, partner_id, lines, note,
  bike)` makes the quotation once per reference and changes it while it is a quotation (the same lines again change
  nothing); with Repair installed a repair order holds the parts and is linked to it (and the bike, where the bike
  model is). `repair_status(reference)`; `repair_invoice(reference)` makes the invoice of the accepted quotation once
  (a draft; the repair order is finished first so its parts leave stock). Nothing is ever sent or posted to the
  customer from these calls.
- `health()` lists the new methods (the repair ones only where Sales is installed), so callers soft-check them.
- Caller side: `site.link._site_link_api(method, site, **kwargs)`, `_site_link_offers(method)`,
  `_site_link_sso_url(login)` and one-line helpers for each new method.
- The log now also keeps the calls this site answered and the single sign-on events (Settings › Site Link › Calls
  Answered and Sign-ins); Failed Calls shows failed calls only. Neutralize also removes the sign-on tickets.

## 19.0.0.1.0 · 2026-11-17
- **New: links two Odoo sites of one business** (owner, 2026-11-11: the one new extension allowed for this; the
  site with the inventory answers the other site's part lookups and consumptions). Odoo's own `/json/2` API with a
  technical user's API key; installs on any Odoo 19 site, no other extension needed (Inventory: soft check).
- Settings › Site Link: the linked sites (name, address, database, API key for administrators only, the other
  site's role, time limit), Test connection (the other side's health, kept on the site), the failed calls (90 days).
- `site.link._site_link_call(site, model, method, *ids, **kwargs)`: time limit, clear errors (`SiteLinkError`), every
  failed call logged in its own transaction.
- The protocol (`site.link.api`, group "Site Link: calls from a linked site"): `health()`, `part_lookup(barcode)`,
  `part_consume(product, qty, reference, note)` (one validated move to "Internal use (linked sites)", idempotent on
  the reference). README.md documents it.
- Neutralize: the API keys removed and the links archived on a copy of a site.
