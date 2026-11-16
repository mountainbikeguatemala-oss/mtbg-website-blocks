# Immich Connector

## 19.0.1.2.1 (2026-11-16)

- The photo server's sync (data/nas/app/sync.py) matches the office: the "Download all" zip is built and uploaded by a background worker after an early /synced (EARLY_SYNCED=1), so the 45-second tight-sync rounds keep going; thread-safe state saves; days being zipped are skipped and a restart redoes a pending zip. Tour Photos §19: finalized ("watch") days are staged without the #ready check; the slim /staged retry keeps asset ids; a resync deletes the published files no longer in the album; an emptied album is logged.

## 19.0.1.2.0 (2026-11-16)

- **The secure office address is watched** (owner-approved, 2026-11-16): if its https front breaks (certificate not renewed, the Cloudflare token deleted, a router reset turning DNS rebind protection back on, the container down), phones at the office quietly upload over mobile data; now somebody is told.
  - The photo server (new `app/office_tls.py`, only with `NAS_HOSTNAME` in `config.env`): a background check every 15 minutes, never blocking the sync: `https://NAS_HOSTNAME:NAS_HTTPS_PORT/ping` with the name resolved as a phone at the office would, the certificate verified and its end date read; when that fails it also connects to its own office address (`NAS_LAN_IP`, else IMMICH_URL's host, else the Docker host) with the name (SNI), so the error tells a DNS problem from a stopped front. The latest result rides on every website call as the `X-Office-Tls` header: `{"ping_ok": bool, "ping_error": str (when false), "cert_expires": "YYYY-MM-DD", "checked_at": ISO}`. The setup check (`check.py`) has a `Secure` line.
  - Odoo keeps each new check (`_check_bearer`, by `checked_at`: the same one resent is not counted twice) and shows it in Settings › Immich under the last call-in: "Secure office address: ✓ working · certificate until 14 Feb 2027 (checked …)" or "✗ not answering since …: <error>".
  - One alert per problem: no answer on 2 checks in a row (15 minutes apart), the certificate ending within 20 days, or no check for 24 hours while the photo server still calls in (and the office address is https; nothing for http or none). With the Alert Feed installed: its rule "Secure office address (photo server)" (Logistics, To do; an alert source, no dependency). Without it: a to-do for each Settings administrator (on the company's contact), again at most daily once done while the problem lasts. Cleared when it works again. Never a message to customers.
  - The wizard's `config.env`: `NAS_HOSTNAME`, `NAS_HTTPS_PORT`, `NAS_LAN_IP`. README: Maintenance (the token: do not delete it; reserve the NAS's address; the router's rebind setting after a reset; back up `tls/data`).
- The photo server's files brought in line with the office's (header sync with Odoo and Immich, last choice wins: `POST /cover`, the change feed and `/changes/done`; tight sync `TIGHT_SYNC_SECONDS`, 45; `EARLY_SYNCED`, 0 by default: `/synced` before the zip; albums read through `/search/metadata` for Immich 3; the uploader kept in `uploaders.jsonl`; duplicates counted in `/tickets/<t>/uploaded`; a website HTML error page no longer crashes a round); `config.env.example`, README and the wizard's `config.env` with the new settings (also `STAGE_MINUTES`).
- `_at_office` deprecated (the Staff App's upload decides by its `/ping` probe): kept with the same answer for older Staff App versions and the office banner.
- Spanish for the new words (es.po and .pot); neutralize clears the new parameters.

## 19.0.1.1.1 (2026-11-16)

- Fix the released `tls/Caddyfile` (checked with `caddy validate` on the real image at the office): the site origins are matched with a CEL expression (a `header Origin` matcher refuses a space-separated list), and the certificate skips Caddy's local DNS pre-check (`propagation_delay 30s`, `propagation_timeout -1`, no `resolvers`: many routers intercept LAN DNS); the proxy streams big uploads (`flush_interval -1`, 15 min read/write timeouts).

## 19.0.1.1.0 (2026-11-16)

- The secure office address (owner-approved, 2026-11-16): a secure (https) page can't send to the photo server's plain `http://<office address>:8090`, so office uploads from the Staff App went over the internet. "Set up the photo server" now sets up `https://nas.<domain>[:port]`, which only works on the office network:
  - Office network: "Secure office address" (`nas.` + a domain: the short-link domain by default, else the Cloudflare zone, else the website's; editable; empty = skip) and "HTTPS port" (443; e.g. 8443 when the NAS keeps 443 for itself).
  - New step "Secure address": the DNS record (A `nas.<domain>` → the photo server's office address, DNS only), with "Create the record" through Cloudflare (the token typed here, or the Cloudflare connector's saved one; a soft check, no new dependency) or added by hand; the certificate's Cloudflare token (Zone › DNS › Edit), kept on the wizard's row only and blanked on Finish; "Check the name" (it must resolve to the photo server).
  - The zip: `tls/` (its own compose project `tour-photos-tls`: Caddy 2.10.2 with the Cloudflare DNS module, a Let's Encrypt certificate by DNS-01, `/ping`, CORS for the website's origins with private network access, proxy to the upload page on Immich's network), `tls/.env` (NAS_HOSTNAME, NAS_HTTPS_PORT, SITE_ORIGINS) and `tls/tls.env` (CLOUDFLARE_API_TOKEN, the only place the token goes); the upload page also answers `GET /ping` and joins Immich's network as `tour-photos-upload`; README Step 4b (with the router DNS-rebind note).
  - Check: the https check from a phone on the office wifi (`https://nas.<domain>/ping`); Finish sets "Office upload page URL" to the https address.
- New setting "Office secure address" and `immich.connector._office_base()`: the https base for the Staff App, False with only plain http.

## 19.0.1.0.4 (2026-11-15)

- The photo server's files brought up to date: every photo and video format is accepted on the office upload page (the type is taken from the file name, so a phone sending no type is fine), originals kept as sent; HEIC/HEIF, AVIF, WebP, PNG, TIFF, GIF and BMP converted to the web JPEG, DNG/RAW through their built-in preview; HEIC capture times read; HDR video tone-mapped; photos up to 200 MB.

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
