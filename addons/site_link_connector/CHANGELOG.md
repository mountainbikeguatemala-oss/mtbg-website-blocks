# Changelog

Every version of this extension, newest first. Tags: `git tag -l 'site_link_connector-*'`.

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
