# Cloudflare Connector

## 19.0.1.5.0 (2026-11-11)

- **Set up Cloudflare is a guided wizard** (owner, 2026-11-11: "it should guide creation of bucket for R2"), in four steps with Back and Next:
  1. *Connect*: the setup token is checked and the account is read. When the token sees several accounts, the wizard asks which one. When R2 is off on the account, it says so, with a button that opens R2 on the dashboard; Next checks again.
  2. *Bucket*: create a new bucket or use one the account has (listed with location and creation date). A new bucket has a name, checked against Cloudflare's rules and the account's buckets, and a location, with the closest one explained. The lock and the price (10 GB free, then about $0.015 per GB a month) are explained. An existing bucket that has lock rules keeps them. A second run offers the site's saved bucket.
  3. *Website cache*: the zone whose cache Odoo may clear, picked from the account's zones (the site's own zone comes first), or none.
  4. *Review*: what will happen, then Set up. Its checklist ticks each step.
- New transient model `cloudflare.setup.choice` holds the accounts, buckets and zones offered.
- Tests: every step, the R2-off case, the bucket-name rules, existing buckets with and without lock rules. The tests no longer read the site's own saved settings.

## 19.0.1.4.2 (2026-11-11)

- Moved to the universal extensions repository (owner, 2026-11-11: extensions that are not only for running tours live in their own repository, installable without Tours Core). Its manifest names its new repository, so the updater takes it from there; nothing else changes (no data, no behaviour).

## 19.0.1.4.1 (2026-11-11)
- No site or company names in the release (owner rule: "all releases should be free of the site and company names"): author "MTBG Tours contributors", example.com in the tests. No behaviour change.

## 19.0.1.4.0 (2026-11-10)
- The setup token is account-owned now (Cloudflare's account template URL), so the wizard can delete it at the end.
  On www the first real run made it under My Profile, and Cloudflare refused the delete (9109). Checked on the
  live dashboard: all four permissions still come pre-filled. The button's next step is "Review token".
- Private download links: `cloudflare.r2.download_url(key, expires=3600, filename=None)` (R2Client.presign_get, AWS
  Signature V4 query signing, at most 7 days). The bucket stays private; the off-site backups list uses it.
  Tested with AWS's published presigned example, and live: the file downloads with its name, and an expired link
  gets 403.

## 19.0.1.3.0 (2026-11-10)
- Set up Cloudflare without looking for anything on Cloudflare (owner: "we need to make the wizard as easy as
  possible for the end user ... can we do a copy paste permissions string like zoho?"): *Create the token on
  Cloudflare* opens Cloudflare's Create Token page through a template URL with the four permissions already ticked
  (Workers R2 Storage Edit, Account API Tokens Edit, Zone Read, Cache Purge). The user presses Continue to summary ›
  Create Token, copies it, pastes it and presses Set up. Checked on the live dashboard: all four came pre-filled.
- The Setup token is no longer required on the form (Set up still refuses an empty one), so the button opens the
  page without a "Missing required fields" save.

## 19.0.1.2.1 (2026-11-10)
- Set up Cloudflare: "Open Cloudflare token page" is a plain link now. As an object button it first saved the
  wizard, which the empty (required) Setup token refused ("Missing required fields"), so the page never opened
  (owner on www: "token page can't open from the button").

## 19.0.1.2.0 (2026-11-10)
- Every Cloudflare function in this one connector (owner: "yes we need to try and get all cloudflare functions in
  the single cloudflare connector extension"): `cloudflare.api.purge(everything / urls / prefixes / hosts)` for
  the site's zone, with the purge token Set up Cloudflare creates. Lists go in batches of 30; a 429 waits
  (Retry-After, at most 10 s) and is tried again; it never raises (returns ok / requests / error).
  `cloudflare.api.zone()` gives the saved zone.
- Settings › Cloudflare shows the zone and its ID.

## 19.0.1.1.0 (2026-11-10)
- Set up Cloudflare wizard (owner: "I want the most amount of config from the site itself without having to open
  cloudflare"): one setup token → the account is found, the R2 bucket is created (or kept) with a bucket lock, an
  R2 key limited to that bucket and a cache-purge token limited to the site's zone are created and saved, R2 is
  tested, and the setup token is deleted in Cloudflare. The setup token is never kept in the database; a run that
  stops keeps what it finished and says where it stopped. Running it again replaces (and revokes) the earlier R2 key.

## 19.0.1.0.0 (2026-11-10)
- New connector (owner exception to the no-new-modules rule, 2026-11-10: "lets setup the new cloudflare connector
  and install it on both sites").
- Settings › Cloudflare: account ID, API token (Check API token), R2 bucket and access key (Test R2 connection).
- `cloudflare.r2`: R2 client (Signature V4, streamed multipart above 64 MiB, SHA-256 on every upload), list, head,
  download, delete. `cloudflare.api`: REST calls with the saved token.
- Neutralize clears the token and R2 keys on a site copy.
