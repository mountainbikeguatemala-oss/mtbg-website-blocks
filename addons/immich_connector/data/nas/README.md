# Tour photo service (NAS)

This small service runs on your office NAS next to Immich. It:

- creates an Immich album for every tour day as soon as the departure exists on your website;
- serves an **office upload page**, so guides can send their photos from their phone over the office wifi;
- collects photos guides sent over **mobile data** from the Staff App;
- when you press **Publish day** on the website, it resizes and watermarks the photos you kept in the album,
  uploads them once to **Cloudflare R2**, and tells the website, which then sends the clients their photo link.

Original photos never leave the NAS. Clients only get the resized, watermarked copies, and those are deleted
from R2 automatically after 60 days.

## What you need

- A NAS that runs Docker containers (Synology Container Manager, UGREEN Docker, QNAP Container Station, or any
  Linux machine with Docker), with **Immich** already installed.
- A **Cloudflare** account with a domain you own (for the photo links).
- Your website with the Tour photos and Immich extensions installed.
- Your logo as a **PNG with a transparent background**.

## Step 1: A "Tours" account in Immich

1. Open Immich in your browser and log in as the administrator.
2. **Administration > Users > Create user**: name `Tours`, an email of your choice, a strong password.
3. Log out and log in as **Tours**.
4. **Account Settings > API Keys > New API Key**, name it `photo service`, give it all permissions, and copy it.
   This is `IMMICH_API_KEY`. It is shown only once.

The Tours account owns all tour albums. Staff who choose photos for clients log in as Tours, or get the albums
shared with them.

## Step 2: Cloudflare R2

1. Cloudflare dashboard > **R2** > enable R2 (Cloudflare asks for a payment method; small photo libraries cost a
   few cents a month and downloads are free).
2. **Create bucket**, e.g. `tour-photos`. This is `R2_BUCKET`. Copy the **Account ID** from the R2 overview page:
   that is `R2_ACCOUNT_ID`.
3. **Public address.** Bucket > Settings > **Custom Domains > Connect Domain**, e.g. `photos.example.com`. This
   is `PUBLIC_BASE_URL`. Enter the same value in the website's Tour photos settings.
4. **Auto-delete (lifecycle rules).** Bucket > Settings > **Object lifecycle rules > Add rule**, twice:
   - Name `client photos`, prefix `tours/`, **delete objects 60 days** after upload.
   - Name `mobile inbox`, prefix `inbox/`, **delete objects 14 days** after upload.
5. **Uploads from the Staff App (CORS).** Bucket > Settings > **CORS policy > Edit**, paste the following and
   replace the address with your website's address:
   ```json
   [
     {
       "AllowedOrigins": ["https://www.example.com"],
       "AllowedMethods": ["PUT", "GET", "HEAD"],
       "AllowedHeaders": ["content-type"],
       "ExposeHeaders": ["ETag"],
       "MaxAgeSeconds": 3600
     }
   ]
   ```
6. **Token.** R2 overview > **Manage API tokens > Create API token**:
   - Permissions: **Object Read & Write**.
   - Specify bucket: **only** your photo bucket (not "all buckets").
   - Create, then copy the **Access Key ID** (`R2_ACCESS_KEY_ID`) and **Secret Access Key** (`R2_SECRET_ACCESS_KEY`).
     The secret is shown only once.

## Step 3: Website

1. Settings > **Immich** > **Set up the photo server**: the wizard saves the office addresses, the secure office
   address (Step 4b), makes the website token (`NAS_TOKEN`, shown once) and downloads a zip with `config.env`,
   `tls/.env` and `tls/tls.env` filled in. Tip: give the NAS a fixed address in your router so it never changes.
2. On Finish, **Office upload page URL** becomes the secure office address, e.g. `https://nas.example.com` (or
   `https://nas.example.com:8443`). Without a secure address it stays `http://<your NAS address>:8090`.
3. Set the **public photo address** to your `PUBLIC_BASE_URL`.

## Step 4: Install on the NAS

1. Copy this whole folder to the NAS, e.g. to `/volume1/docker/tour-photos` (any shared folder for Docker).
2. Copy `config.env.example` to `config.env` and fill in every line marked REQUIRED. (If the website's setup
   wizard gave you a `config.env`, use that and add only the secrets it left empty.)
3. Watermark: upload your logo on the website (Tours > Configuration > Tour photos). The service fetches it and
   its placement by itself. (Alternative: put the PNG in a folder `data` next to `config.env` as
   `data/watermark.png`.)
4. Start it.
   - **With SSH:** in the folder, run
     ```
     docker compose --env-file config.env up -d --build
     ```
   - **With your NAS's Docker app:** create a new *Project* (Synology/UGREEN) or *Application* (QNAP), point it at
     this folder so it uses `docker-compose.yml`, and start it. If the app has no "env file" option, change the
     port line in `docker-compose.yml` from `${UPLOAD_PORT:-8090}` to the number you want, e.g. `8090`.
5. Two containers appear: `photos-sync` and `photos-upload`. Both restart by themselves after a NAS reboot.
   `photos-upload` also joins Immich's Docker network (`IMMICH_NETWORK`, default `immich_default`) as
   `tour-photos-upload`, for the https front below. If Immich's network has another name (`docker network ls`), set
   `IMMICH_NETWORK` in `config.env` and `tls/.env`.

## Step 4b: The secure office address (https)

The Staff App is an https page, and a browser does not let an https page send to a plain `http://` address. So
the photo server gets its own https address that **only works on the office network**, e.g.
`https://nas.example.com`. At the office, phones then upload from the app straight to the NAS: the photos never
go over the internet.

1. **DNS record** (the wizard can make it in Cloudflare): type `A`, name `nas.<your domain>`, address = the NAS's
   office address (e.g. `192.168.1.50`), proxy status **DNS only** (grey cloud). The name is public; the address
   is private, so it answers only inside the office.
2. **Certificate**: the front gets a real Let's Encrypt certificate by proving the domain through Cloudflare DNS
   (DNS-01), so nothing has to be opened to the internet. It needs a Cloudflare API token:
   Cloudflare > My Profile > API Tokens > Create Token > **Edit zone DNS**, Zone Resources: only your domain. The wizard writes it into
   `tls/tls.env` (`CLOUDFLARE_API_TOKEN`); keep that file private.
3. **Port**: `NAS_HTTPS_PORT` in `tls/.env`, 443 by default. Many NAS systems keep 80 and 443 for their own pages;
   then use e.g. `8443` (the address becomes `https://nas.example.com:8443`, and the wizard's "HTTPS port" field
   has to say the same).
4. **Start it** (after the photo service, which creates its network link): in the `tls` folder, run
   ```
   docker compose up -d --build
   ```
   A container `tour-photos-tls` appears (the official Caddy 2.10.2 image built with the Cloudflare DNS module,
   tagged `tour-photos-tls:2.10.2-cf`). The first certificate takes up to a minute: `docker logs tour-photos-tls`.
   The certificate is kept in `tls/data` and renews by itself.
5. **What it does** (`tls/Caddyfile`): `GET /ping` answers `{"ok":true}` itself; every other request goes to the
   upload page (`tour-photos-upload:8090`): `GET /upload?t=<ticket>`, `PUT /upload/file?t=<ticket>` (the file;
   headers `X-File-Name` URI-encoded, `X-File-Type`, `X-Last-Modified` in ms), `POST /upload/batch?t=<ticket>`
   (`{"count": n}` after each batch). For the website's addresses (`SITE_ORIGINS`, space-separated, e.g.
   `https://www.example.com https://example.com`) every answer carries the CORS headers
   (`Access-Control-Allow-Origin` = that address, `Vary: Origin`, `Access-Control-Allow-Private-Network: true`),
   and a preflight (`OPTIONS`) gets `204` with methods `GET, POST, PUT, OPTIONS`, headers
   `Content-Type, X-File-Name, X-Last-Modified, X-File-Type`, max age 600. Other addresses get no CORS headers.
   The plain `http://<NAS address>:8090` keeps working on the office network.
6. **Router (DNS rebinding protection)**: some routers refuse public names that point to a private address. If
   `nas.<your domain>` does not resolve on the office wifi but does elsewhere, allow it: on OpenWrt (e.g. GL.iNet)
   Network > DHCP and DNS > Filter > **Domain whitelist** (dnsmasq `rebind_domain`), add your domain, e.g.
   `uci add_list dhcp.@dnsmasq[0].rebind_domain='example.com'; uci commit dhcp; /etc/init.d/dnsmasq restart`.
   Phones with "private DNS" (Android) or a VPN may skip the office's DNS; they still resolve the public record.

## Step 5: Test

1. Run the setup check:
   ```
   docker compose --env-file config.env run --rm photos-sync /app/check.py
   ```
   Every line should say **OK**. A **PROBLEM** line says what to fix. The check writes one tiny test file to R2
   and deletes it again; it changes nothing else.
2. Within 5 minutes, Immich (logged in as Tours) shows albums for your upcoming departures, named like
   `2026-11-14 · Tour name` or `· Day 2` for multi-day tours. Each departure on the website links to its albums.
3. With the secure office address: on a phone on the office wifi open `https://nas.<your domain>/ping` (with the
   port, if not 443). It must say `{"ok":true}` with a padlock (a valid certificate).
4. On a phone on the office wifi, open a departure day in the Staff App and tap **Upload photos**. Pick a few
   photos: each shows its progress and then **Done**. They appear in that day's album in Immich.
5. In Immich, remove any photos you don't want, and pick the header with **Set as album cover**.
6. On the website, press **Publish day**. Within 5 minutes the album description in Immich ends with
   `✓ synced … photos …` and the website shows the day as synced. When every day of the departure is synced,
   the clients' email goes out (only if you have turned that email on).

Optional: to create empty albums for all past departures since a date, run once:
```
docker compose --env-file config.env run --rm -e BACKFILL_FROM=2026-07-01 photos-sync /app/sync.py
```

## Everyday use

- Photos **and videos** are accepted (photos up to 50 MB, videos up to 2 GB each). Videos are published as a
  web MP4 with a poster and a short looping preview; they are not in the download zips.
- Guides upload from the Staff App: on the office wifi through the upload page, or over mobile data (the NAS
  collects those every 15 minutes).
- Guides press **Done uploading**. Nothing is published yet.
- You choose the photos in Immich (remove, archive or hide what clients should not get) and set the cover.
- You press **Publish day**. Only then are photos resized, watermarked, uploaded and sent.
- A cancelled departure: its empty albums are deleted; albums that have photos are kept and renamed "(cancelled)".
- The day's header: chosen in Immich (**Set as album cover**) or on the website, the last choice wins; the service
  carries a website choice over to the Immich album cover.
- Timing (`config.env`): a full round every `POLL_MINUTES`; while departures are being uploaded or sent, those are
  checked every `TIGHT_SYNC_SECONDS` (45); `STAGE_MINUTES` of processing per round. `EARLY_SYNCED=1` reports a
  sent day as online before its download zip is ready (only with a website that accepts it; default 0).

## Maintenance (the secure office address)

If the secure office address stops working, phones at the office quietly upload over mobile data (slow). The
photo service checks it every 15 minutes (`NAS_HOSTNAME` in `config.env`) and the website shows the result in
Settings > Immich ("Secure office address: ✓ working · certificate until …"); staff are warned when it fails twice
in a row, when the certificate has less than 20 days left, or when no check arrived for 24 hours.

- **The Cloudflare token: do not delete it.** The certificate renews itself every ~60 days with the token in
  `tls/tls.env`. Name it clearly in Cloudflare (e.g. "photo server certificate - do not delete"). If it was
  deleted or expired: make a new one (Edit zone DNS, your domain only), put it in `tls/tls.env`, then in the `tls`
  folder `docker compose up -d --force-recreate`.
- **Reserve the NAS's office address on the router** (DHCP reservation): the DNS record `nas.<your domain>` points
  to it. If the address ever changes, change the record (Cloudflare) and `NAS_LAN_IP` in `config.env`.
- **After a router reset or replacement:** its DNS rebinding protection is usually back on; allow your domain
  again (Step 4b, point 6) and reserve the NAS's address again.
- **Back up `tls/data`** (the certificate and its account) with `tls/.env` and `tls/tls.env`: Let's Encrypt limits
  how many new certificates a name gets per week, so a reinstall should reuse them.
- **Restart the https front:** in the `tls` folder, `docker compose up -d` (or `docker restart tour-photos-tls`);
  then the setup check (Step 5) shows the `Secure` line.

## Troubleshooting

- **See what it is doing:** `docker logs --tail 100 photos-sync` (and `photos-upload`, `tour-photos-tls`).
- **The /ping check fails at the office:** the name must resolve to the NAS (`nslookup nas.<your domain>` on the
  office network; see the router note in Step 4b), the port must be the one in `tls/.env`, and
  `docker logs tour-photos-tls` shows whether the certificate was issued (a refused token: check its zone).
- **The upload page says the link expired:** links from the Staff App last 12 hours; open it again. The page
  only works on the office network.
- **Nothing publishes:** the day must be *Publish day* on the website (not only "Done uploading"), and the album
  must have at least one photo that is not archived or hidden.
- **Wrong photo times or days:** check `TIMEZONE` in `config.env`.
- **Change a setting:** edit `config.env`, then run `docker compose --env-file config.env up -d` again.
