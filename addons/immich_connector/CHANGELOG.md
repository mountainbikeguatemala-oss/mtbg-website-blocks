# Immich Connector

## 19.0.1.0.3 (2026-11-15)

- The photo server's files (Set up the photo server's zip) brought up to date: the office upload page reports what each guide sent (`POST /tickets/<ticket>/uploaded`), staged items carry the asset id, the uploader and a thumbnail (with pending items), the deletions queue (`GET /deletions`, `POST /deletions/done`), and the Dockerfile with the Intel video driver.

## 19.0.1.0.2 (2026-11-15)

- The office's public address is kept from the photo server's calls (the request's real client address, as the site reads every visitor's; refreshed as soon as it changes), with `_at_office(ip)`: yes only when the photo server called within the last 15 minutes from that address. Never shown to anyone; neutralize clears it.
- "Office wifi name" takes several networks separated by commas (`_wifi_names()`), in the settings and the wizard.
- The photo server's files (Set up the photo server's zip) brought up to date: the office upload page's "Back to the Staff App" and "Done" (back to the Staff App's tour, or its link), the watermark and quality from the website, the README.

## 19.0.1.0.1 (2026-11-14)

- Spanish (es.po and .pot): the settings and the "Set up the photo server" wizard.

## 19.0.1.0.0 (2026-11-14)

- New connector (owner-approved, 2026-11-14), installable on any Odoo site: the photo server's token (made once, stored hashed, checked with a fresh read in constant time, last call-in recorded), the office upload page URL and wifi name, Immich's URL for album links, an optional internet-facing Immich client (albums create, read, rename; Test connection), and "Set up the photo server": what is needed, the office addresses, the token, a zip (config.env filled from this site's settings with the secrets blank, docker-compose.yml, the sync service, README.md), then a check that the server calls in.
