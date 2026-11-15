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

1. Settings > **Immich** > **Set up the photo server**: the wizard makes the website token (`NAS_TOKEN`, shown once) and can download a filled-in `config.env` for you.
2. In the same settings, set **Office upload page URL** to `http://<your NAS address>:8090`, e.g.
   `http://192.168.1.50:8090`. Tip: give the NAS a fixed address in your router so this never changes.
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

## Step 5: Test

1. Run the setup check:
   ```
   docker compose --env-file config.env run --rm photos-sync /app/check.py
   ```
   Every line should say **OK**. A **PROBLEM** line says what to fix. The check writes one tiny test file to R2
   and deletes it again; it changes nothing else.
2. Within 5 minutes, Immich (logged in as Tours) shows albums for your upcoming departures, named like
   `2026-11-14 · Tour name` or `· Day 2` for multi-day tours. Each departure on the website links to its albums.
3. On a phone on the office wifi, open a departure day in the Staff App and tap **Upload photos**. Pick a few
   photos: each shows its progress and then **Done**. They appear in that day's album in Immich.
4. In Immich, remove any photos you don't want, and pick the header with **Set as album cover**.
5. On the website, press **Publish day**. Within 5 minutes the album description in Immich ends with
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

## Troubleshooting

- **See what it is doing:** `docker logs --tail 100 photos-sync` (and `photos-upload`).
- **The upload page says the link expired:** links from the Staff App last 12 hours; open it again. The page
  only works on the office network.
- **Nothing publishes:** the day must be *Publish day* on the website (not only "Done uploading"), and the album
  must have at least one photo that is not archived or hidden.
- **Wrong photo times or days:** check `TIMEZONE` in `config.env`.
- **Change a setting:** edit `config.env`, then run `docker compose --env-file config.env up -d` again.
