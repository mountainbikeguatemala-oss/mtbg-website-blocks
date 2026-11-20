# Changelog

Every version of this extension, newest first. Tags: `git tag -l 'site_link_connector-*'`.

## 19.0.0.2.7 · 2026-11-20
- Fix: `zoho_request(app, verb, path, ...)`: the HTTP method is now `verb` (it was `method`, which the caller's
  `_site_link_call(site, model, method, ...)` already takes: every call through the link failed with "got multiple
  values for argument 'method'"). Zoho Connector 0.3.3 sends `verb`; ship both together. The test now runs the real
  `_site_link_call` (only the network faked) and checks the arguments sent are exactly `zoho_request`'s.

## 19.0.0.2.6 · 2026-11-20
- **One Zoho login for both sites** (owner, 2026-11-20: "we should just link via the site api the two sites zoho
  permission"; Zoho allows one Self Client, already used by the tours site): on the site with the Zoho login, a link's
  **May use our Zoho login** lets that other site make its Zoho Books calls here: `zoho_request(app, method, path,
  params, json, files, record)` (offered in `health()` only where Zoho Connector is installed and a link ticks it;
  soft, no dependency). Zoho Books only; reads anywhere, writes only to expenses, their receipts and vendor contacts;
  this site's switches and Writes allowed apply; a write is noted in the link's log. Answers `{body}`, `{blocked}`
  (Writes allowed off here) or `{error}`. On the other site, the link's **Use its Zoho login** makes Zoho Connector
  (0.3.1) send every Zoho call there (`site.link._site_link_zoho_via()`), with no Zoho login of its own.

## 19.0.0.2.5 · 2026-11-19
- **New: `staff_clock(login)`** (owner, 2026-11-19: the shop app shows "on shift since 08:02 · 3 h 12 min" while the
  employee is clocked in on the Staff App): `{clocked_in, since}` (`since` in UTC). Offered in `health()` only where
  another extension answers `res.users._site_link_staff_clock(user)` (soft, no dependency); unknown, archived or portal
  logins: not clocked in. Read only and not logged (asked every couple of minutes). Caller side:
  `_site_link_staff_clock(login, site='staff_source')`, None when not offered or no answer.
- `_site_link_sso_start_url(path, site)` makes one health call instead of two (the named path and the methods from
  the same answer): the shop app's way back to the Staff App opens sooner.

## 19.0.0.2.4 · 2026-11-19
- **Single sign-on both ways** (owner, 2026-11-19: the Staff App's Tour / Tienda switch, between the two sites):
  the sign-in link opens `return` (`redirect`, its older name, still read): a path of this site or a full address on
  this site's own host; anything else is refused (logged) and `/odoo` opens. `/site_link/sso/start` works on either
  site towards any linked site with an API key, passes the path as `return` (and `redirect` for older versions) and,
  with `fallback=1`, opens the address as it is when the other site gives no ticket for that login (logged).
- Employees sent with shop access (Send Employees) get *Site link: single sign-on allowed* on the sending site too
  (shop access false takes it away; never ids 1 and 2, administrators or portal users): the other site's app can
  sign them back in. Logged.
- `health()` answers `sso_return: true` and `paths`: the named paths of this site another extension gives through
  `res.users._site_link_paths()` (no dependency needed).
- Caller side: `_site_link_sso_url(login, site, return_path)`, `_site_link_partner_url(path, site)` (a path or a
  name from the other site's `paths`), `_site_link_partner_paths(site)`, `_site_link_sso_start_url(path, site)`.

## 19.0.0.2.3 · 2026-11-18
- **New: `inbox_unread(login)`** (owner, 2026-11-18: the shop's client messages pop up, and the Staff App's shop
  tile shows how many wait for a reply): `{count, enabled}`, the conversations that user may see whose last message
  came from the customer, until anyone answers (Communication Flows' side panel 1.10.0, "Pop up new client
  messages"; `enabled` false and count 0 while that setting is off). Unknown, archived or portal logins: 0. Offered
  in `health()` only where that inbox is installed (soft check, no dependency). Read only and not logged (asked every
  minute while the Staff App is open).

## 19.0.0.2.2 · 2026-11-18
- Employee list: when another extension defines `res.users._site_link_employees()` (same answer as
  `site.link._site_link_sync_users_list()`), that list is sent, so it needs no dependency on this connector. User ids
  1 and 2 and the template and public users are still never sent.
- `user_sync` makes a missing user only when it is active and has `shop_access` true (owner, 2026-11-18: access to
  the shop site comes only from the shop staff role). With false or null only an existing user is updated; false
  still takes the shop groups away (no single sign-on).

## 19.0.0.2.1 · 2026-11-18
- **Security**: administrators never come through the site link. Single sign-on refuses users with Settings
  (`base.group_system`) or Access Rights (`base.group_erp_manager`) rights besides user ids 1 and 2, when the ticket is
  asked for and again when the link is opened; `user_sync` never changes such a user (answered with `skipped`);
  Shop Access Groups may not be or imply those groups. (Otherwise the other site could make a user of the same login
  and sign in here as an administrator.)

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
