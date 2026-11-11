# Changelog

Every version of this extension, newest first. Tags: `git tag -l 'google_connector-*'`.

## 19.0.1.5.2 · 2026-11-11

- Moved to the universal extensions repository (owner, 2026-11-11: extensions that are not only for running tours live in their own repository, installable without Tours Core). Its manifest names its new repository, so the updater takes it from there; nothing else changes (no data, no behaviour). Author: MTBG Tours contributors.

## 19.0.1.5.1 · 2026-11-10

- **Review photos** (owner, 2026-11-10: a customer's review pictures did not come in): the review parser returns each review's media items (Business Profile v4.9, 2026-04-20: `reviewMediaItems`, on reviews.list / get / batchGetReviews) as `media`: `photo_url` (FIFE), `label`, `video_url`. `google.connector._google_review_photo(url)` fetches one photo (at most 1600px, public, no sign-in; None when it is not an image, over 15 MB or Google does not answer; never raises): the app keeps its own copy, since FIFE URLs change. Customer location photos (media.customers.list) are not read.

## 19.0.1.5.0 · 2026-11-10

- **Events for the Google apps** (owner, 2026-11-10, the Google clean-up: connector code lives only in the connector): the dispatcher of the Tours' Google glue (`mtbg_tours_google`) is the connector's: `mtbg.google.broadcast` (`_mtbg_google_events()`, `_mtbg_google_notify(event, records, vals)`, the `mtbg_google_silent` context) and the mixin `mtbg.google.broadcaster`. It names no business model: each app adds its events and puts the mixin on its records; an event two apps add counts once.
- `mtbg_tours_google` is retired into the connector (its pre- and end-migrate, with the Tours Core's `retire_into` / `retire_finish` where it is on the server): its xml ids become the connector's, it is marked uninstallable. Nothing removed, nothing sent.

## 19.0.1.4.0 · 2026-11-08

- **PageSpeed Insights app** (owner, 2026-11-08: "the new pagespeed should get its api info from our main google connector there is no reason for it to have its own google link"): Page Speed's nightly speed log measures through this connector. A "PageSpeed Insights" card (Install while Page Speed is not installed), its API in the APIs step, and `google.connector._google_pagespeed_ready()` / `_google_pagespeed_run(url, strategy)` (the runPagespeed call, here per the rule that a connector's API code lives in the connector). No Google account needed.
- **Server API key** (Set up Google › 6. API keys, the step formerly "Maps key"): a key for calls from this site's server (PageSpeed), separate from the Maps key (which is limited to the website's pages). Apps declare `uses_server_key`; their status says "No API key" without it. Never shown; a copy of the site drops it.
- The client takes a per-call timeout (a PageSpeed measurement takes up to a minute or more).

## 19.0.1.3.0 · 2026-11-07

- **Google Business Profile reviews are read here** (owner, 2026-11-07: "any connector should live in a seperate extension and any connector script should not live in a main extension"). The accounts, locations and reviews calls, the review parser (Google's machine translation dropped) and the plain-words errors moved here from the Tours' Reviews: `google.connector._google_reviews_ready()`, `_google_reviews_locations()` and `_google_reviews_fetch(account_ref, location_ref)`. The errors are: 429 + quota means access is not approved yet; 403 means the APIs or the access; anything else is Google's message, shortened. This module declares the "reviews" app itself once Reviews is installed. Reviews asks for it only when the connector is installed, with no dependency either way.

## 19.0.1.2.2 · 2026-11-07

- **Google Business Profile in the catalog** (the Tours' Reviews 0.6.0 app "reviews"). Its card shows in Settings › Google. Set up Google › APIs lists the three Business Profile APIs; Google grants them on request before they can be enabled. The consent step explains the `business.manage` access in plain words. The last step says to find the locations and sync. No API change.

## 19.0.1.2.1 · 2026-11-03

- Spanish (bulk translation pass): the .pot regenerated from Odoo's export and es.po rebuilt from it; 19 strings no longer in the code removed. No English text changed.

## 19.0.1.2.0 · 2026-10-27

- **Set up Google, step by step in Google Cloud's order, with a link to each page** (owner, 2026-10-27: "clearer and
  have links to each step in the cloud platform with clear steps in order"):
  1. the project (its ID makes every link open in it; Google's project limit, billing for Maps);
  2. the apps;
  3. the APIs those apps need, one link each (Gmail, People, Calendar, Places (New), Geocoding, Maps Static,
     Maps JavaScript);
  4. the consent screen: Branding, Data access with every scope to paste, Audience "In production" (Testing ends
     the sign-in every 7 days);
  5. the OAuth client with the redirect address of every site address;
  6. Maps billing and key;
  7. sign in;
  8. Check access, naming the missing access per app.

## 19.0.1.1.0 · 2026-10-27

- **Moved to the mtbg-tours repository** (owner, 2026-10-26: "centralize all connectors"), beside the Zoho
  connector. Same module, same data: nothing to set up again. The Communication Flows channels (Gmail, Google Voice,
  Google Contacts photos) keep connecting through it. Updates now come from the mtbg-tours source.

Earlier versions were released from the communication-flow-designer repository (tags `google_connector-19.0.1.0.*`).
