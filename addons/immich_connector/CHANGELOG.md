# Immich Connector

## 19.0.1.0.1 (2026-11-14)

- Spanish (es.po and .pot): the settings and the "Set up the photo server" wizard.

## 19.0.1.0.0 (2026-11-14)

- New connector (owner-approved, 2026-11-14), installable on any Odoo site: the photo server's token (made once, stored hashed, checked with a fresh read in constant time, last call-in recorded), the office upload page URL and wifi name, Immich's URL for album links, an optional internet-facing Immich client (albums create, read, rename; Test connection), and "Set up the photo server": what is needed, the office addresses, the token, a zip (config.env filled from this site's settings with the secrets blank, docker-compose.yml, the sync service, README.md), then a check that the server calls in.
