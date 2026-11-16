# Immich Connector

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
