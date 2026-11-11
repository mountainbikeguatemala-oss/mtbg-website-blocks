# Changelog

Every version of this extension, newest first. Tags: `git tag -l 'mtbg_tours_edge_cache-*'`.

## 19.0.0.8.0 · 2026-11-11
- **Universal** (owner, 2026-11-11: general extensions in their own repositories, "used on other sites without installing tours core"): moves to the Website Blocks repository, keeps its technical name, settings and data, and needs only Website and Visits by Script. Any Odoo website can use it.
- **Each extension says what of it the pages show**, on its own models, no dependency either way (as the Alert Feed's sources): `_mtbg_edge_cache_watch` (models whose edits empty the cache: True or the watched fields), `_mtbg_edge_cache_param_prefixes` (system parameters), `_mtbg_edge_cache_static_prefixes` (public files given without a session), `_mtbg_edge_cache_fingerprint()` (what changes by itself: the site notice) and `_mtbg_edge_cache_live_values` (the live values, listed under the settings). Odoo's own website, its pages, menus and templates, and the blog stay watched here. The Tours extensions declare theirs in the same release (Catalog, Departures, Booking Form, Website, Rentals, Accommodations, Site Notice, Reusable Blocks): the same purges as before. A watched model's text translated in the editor now empties the cache for every watched model (it did for tours and their categories, not for hotels or towns).
- The undeclared live key warning wraps the live answer where an extension has it; the country of `/mtbg/session` is read here (Cloudflare's header, else Odoo's geo IP), no longer from Forms.
- A new install starts with the pages `/ /blog`; a site keeps its own list.
- Tests: the page-cache tests run on a plain website (purge tests skip without Cloudflare Connector); those needing tours, bookings, hotels or the notice move to those extensions.

## 19.0.0.7.1 (2026-11-10)

- The holding page (deploy/updating.html) ships with no business name or logo, just a plain header; the copy on a server is the operator's. Deploy notes use example addresses. Brand-free release (owner, 2026-11-10): no business names in code, data, samples, comments or tests.

## 19.0.0.7.0 (2026-11-10)
- Every Cloudflare call goes through Cloudflare Connector (owner: "yes we need to try and get all cloudflare functions
  in the single cloudflare connector extension"): the purge is `cloudflare.api.purge(everything=True)`, a soft check
  (`'cloudflare.api' in env`; without the connector the purge log says so). The Tours logic stays here (which pages,
  live values, when to purge, re-fill, stale-if-error).
- The Zone ID and API token settings are gone: Settings shows the connector's zone instead. The upgrade moves an
  existing zone and token into the connector's settings (only where the connector has none yet), so the site keeps
  purging with no new setup, and removes the old token.

## 19.0.0.6.8 (2026-11-08)

- The live values' table: the card keys (tour and departure price, spaces, full, status) are the Tours website's, where
  Tour Cards was merged (the module clean-up).

## 19.0.0.6.7 · 2026-11-08

- **The site stays up during updates** (owner: "is there anyway to keep the site live while we do backend updates?"):
  - the pages Cloudflare keeps now carry `stale-if-error=604800`: while the server restarts, updates or is down
    (502, 503, 504), Cloudflare still answers a kept page even when its time has run out, for up to a week. Prices
    and seats stay live (never kept), and fill once the site is back;
  - the holding page for everything else (booking, checkout and payment, forms, the chat, the back office):
    `deploy/updating.html`, in English and Spanish with the logo, "back in about 2 minutes", reloading by itself once
    the site answers. Served by nginx on the server with HTTP 503 and Retry-After: 120 (`deploy/nginx-updating.conf`),
    both while Odoo restarts and while it answers its own update 503. Cloudflare's Free plan has no custom error
    pages, so nginx serves it. Owner steps (Cloudflare's Always Online off, the nginx lines):
    `deploy/README.md`.

## 19.0.0.6.6 · 2026-11-05

- The page cache is emptied when a journal post's Gallery photos change (Tiled Gallery 0.5.8) and when a page template
  (tour, rental or blog post page) or its elements are saved; the template editor's unsaved preview is no change.

## 19.0.0.6.5 · 2026-11-03

- Spanish (bulk translation pass): the .pot regenerated from Odoo's export and es.po rebuilt from it; 13 new Spanish translations; 5 strings added to the .pot that were missing (they never loaded); 4 strings no longer in the code removed. No English text changed.

## 19.0.0.6.4 · 2026-11-03

- Live values: `tour:<id>:rental_table`, a rental page's Rental period discounts table (Bike Rentals 1.11.0).

## 19.0.0.6.3 · 2026-11-03

- Live values: `delivery:<id>:amount`, the Delivery prices block's charge of a pickup / return place (Bike Rentals
  1.10.0).

## 19.0.0.6.2 · 2026-11-03

- **One purge per update, not one per module** (www, 2026-11-03: while the night's updates ran, Cloudflare's copies
  were emptied about every 2 minutes; every module upgraded writes its website templates again, a change each).
  While modules are installed or upgraded (Update all, the updaters, a module's data loading) a change is only
  noted; the one-minute job purges once, when no update has noted one for 3 minutes. Edits made on a running site
  purge at once, as before.

## 19.0.0.6.1 · 2026-11-03

- **The cache is emptied when the site notice changes by itself** (owner: "yes when banner changes"): a departure
  full from bookings, its booking deadline passed, the next one taking its place, none left. Bookings never empty
  the cache (0.3.0), so the cached pages kept the notice as it was when they were made. Every 5 minutes a job
  ("Website: empty Cloudflare's page cache when the site notice changes") compares the notice as the pages would draw
  it now (its departures, their order and words, the one shown first, in each language; not its price, which is
  live) with the one they carry. When it differs, a change is noted as for an edit (the same purge after the save,
  the same 10-second spacing and one-minute catch-up job) and the purge keeps the new notice's fingerprint: one purge
  per change, a refused one tried again. On most days a few purges, or none. With the cache (on and off with it); nothing without Site Notice. The Big Tours
  banner is fetched live by its script, never kept by Cloudflare: nothing to do there.

## 19.0.0.6.0 · 2026-11-03

- **Filled live values are emptied, no longer a reason not to cache** (found on www 2026-11-03: the tour pages showed
  the same day-old "From USD $78" and "$1444.15" on every tour for a moment, and Cloudflare stopped keeping them):
  a tour page saved in the website editor while its script had filled the prices keeps them in its templates. A
  declared placeholder that arrives filled in a visitor's page is now emptied before the page leaves Odoo (the
  script fills it from /mtbg_tours/live as always) and logged with what it held; the page is cached as usual.
- **Every public page may be kept** (owner's search plan, 2026-11-03): each address in "Pages Cloudflare may keep"
  stands for every language (/blog is /es/blog too); the website's own pages (Website › Pages: About us, Contact
  us...) are kept wherever they are, unless behind a password, a login or a group. This version adds /blog and
  /tour-policies to the settings; new default: `/ /tours /blog /hotels /tour-policies`. Booking, payment, account,
  invoice and token pages stay out (never listed, never a website page).
- **No session for search engines' files:** /sitemap.xml (and its parts), /robots.txt and /favicon.ico no longer
  hand a new visitor a session cookie.
- **Blog edits empty the cache:** posts, blogs and their categories (a post's view count is not an edit).
- Cloudflare: the "Odoo: public pages" rule no longer needs a list of addresses (Odoo's header decides); see the
  handoff note.

## 19.0.0.5.2 · 2026-11-03

- **Live values declared for tour page {placeholders}** (Booking Form 0.4.31): `tour:<id>:spots_left`,
  `tour:<id>:next_date` (availability), `tour:<id>:from_price`, `tour:<id>:early_bird_deadline` (price). They are
  made in the visitor's browser from the names typed in the page; the page's HTML only has `{spots_left}` etc.

## 19.0.0.5.1 · 2026-11-02

- **"Purge cache now" button** (owner: "need button on the extension to purge cache"): on the Cloudflare page cache
  settings (it was the small "Test purge" link) and at the top of the purge log. Cloudflare empties the whole page
  cache at once, whatever was edited; logged as "Purged by hand"; the homepages are filled again a minute later.
  Administrators only.
- **Town edits empty the cache** (for Accommodations 0.8.0's hotels by town): a town (Catalog's Locations: its name,
  blog category, hotel list, upgrades) and a town's hotel list lines, created, changed or deleted. Watched where they
  exist, like the hotels (no dependency): without 0.8.0 only the towns themselves. A hotel's publishing, name, address,
  photos and description and a room type's hotel were already watched (0.5.0). Blog pages are not among the pages
  Cloudflare keeps (settings › Pages), so a blog category page shows a town's hotels as soon as they change.

## 19.0.0.5.0 · 2026-11-01

- **The hotel pages are kept by Cloudflare too** (owner's direction: everything cached long-term except the live
  values): /hotels/<slug> and /es/hotels/<slug> (Accommodations' public hotel pages) join the pages Cloudflare may
  keep (this version's migration adds them to the settings); a room type's price per night is a declared live value
  (hotel_class:<id>:price), never in the page.
- **A hotel's photos carry no session cookie** for a new visitor (as the site's files since 0.2.1), so Cloudflare keeps
  them (/hotels/photo/…, a year for the versioned address).
- **Hotel edits empty the cache:** a hotel, a room type or a hotel photo created, changed or deleted. Accommodations
  stays optional (no dependency, no glue module): where it is installed its models are watched when the registry
  loads; a failure there is logged and never stops the save. Room prices and availability are live, not watched.
- **Reusable content blocks empty the cache** (a gap until now): an edit to a block used on tour pages or as a hotel's
  description no longer stays in Cloudflare's copy.

## 19.0.0.4.0 · 2026-11-01

- **The live values' declarations** (owner, 2026-11-01: "a table of declarations of any live pricing values that need
  to be excluded from cache global"; "this list should live only in your extension"): every price, availability,
  status and booking-form value the public pages load after they open is declared here (models/live_values.py: its
  key, what it shows in English and Spanish, the extension answering it, its kind), and listed read-only under
  Settings › Website › Cloudflare page cache › Live values. Enforcement, all in this extension:
  - a page whose declared placeholder arrives filled is not given to Cloudflare (logged): no price or count is kept
    for a month by mistake;
  - the live route warns about a key nobody declared (it still answers it, so a visitor never sees an empty price);
  - the tests open the home pages, the catalog, a tour page, a rental page and a tour page with a hotel upgrade
    (where there is one): every live key declared ("undeclared live key: …" otherwise), every placeholder empty, and
    none of the live answer's prices or counts in the page.

## 19.0.0.3.0 · 2026-11-01

- **Edit-only: Cloudflare keeps the pages a month** (owner, 2026-11-01: "99% of the page is static … we shouldn't
  have to clear the entire cache of the page just to change a few numbers"; prices, seats, dates' status load live
  from /mtbg_tours/live, never cached):
  - the cache is emptied only when what the pages show is edited: tours, pages, menus, templates, categories,
    regions, the site's settings, and a departure created or deleted or its tour, dates, times, state, visibility,
    places, description, photo or notice/Big Tours fields changed; never for a booking, seats, a price rule or a
    departure's back-office notes, logistics or links;
  - a page stays 30 days (2592000 s; this version's migration sets it);
  - the homepages (/ and /es) are asked for again a minute after a purge (once for a burst of edits) and every night
    at 00:05 Guatemala time (Cloudflare drops copies nobody asks for); the other pages fill on their first visit;
  - 0.2.0's 15-minute and 6-hour pre-fill and its nightly purge are removed (the live script hides departures that
    have passed or closed).

## 19.0.0.2.1 · 2026-11-01

- **The site's script bundles and files reach Cloudflare's cache** (coordinator's check of www, 2026-11-01): Odoo
  handed a new visitor a session cookie with every script bundle (/web/assets) and file (/web/content), and
  Cloudflare never keeps a response that sets a cookie. Those requests no longer start a session for a visitor without
  one who is not logged in (nothing is kept in it for a file; Odoo's /web/image already does the same). A private file
  stays private: Odoo still sends it to a logged-in user marked "private" and answers "not found" to anyone else.

## 19.0.0.2.0 · 2026-11-01

- **The homepage is already in Cloudflare when a visitor comes** (owner, 2026-10-31: "Front page is the page I am
  most concerned about that can cache and serve as quick as possible"; www answers a cached page in 0.14–0.19 s,
  a page Cloudflare does not have yet in 0.5–1.4 s). Cloudflare keeps a page only once someone asked for it, and www
  gets a few dozen views an hour, so Odoo now asks for the cached pages itself, through Cloudflare, as an anonymous
  visitor (no cookie, no login, one page at a time with a pause, at most 10 minutes a round; no visitor or visit is
  recorded):
  - the homepages (/ and /es) every 15 minutes, every cached page (catalog, tours, categories, regions, each language)
    every 6 hours, and both soon after every purge;
  - a nightly purge at 00:05 Guatemala time for what a new date changes (early-bird prices, past departures); a
    booking deadline passing within the day is already followed by the pages' scripts on the visitor's clock;
  - the three jobs are switched on and off with the cache; an upgrade no longer switches them off (0.1.x's job file
    switched the catch-up purge off at every upgrade, so saves stopped purging until the settings were saved again):
    the jobs are created once, and this version's migration switches all of them on where the cache is on, no Save
    needed;
  - a page now stays a day in Cloudflare by default (every change in Odoo still empties it at once); www keeps the
    value set in its settings.

## 19.0.0.1.1 · 2026-10-30

- **The "Purge log" button works** (owner, www 2026-10-30: "TypeError: ResConfigSettings.action_mtbg_edge_cache_log()
  takes 1 positional argument but 2 were given"): it was declared as a model method, but a settings button is
  called on the settings record. Tests press both buttons as the web client does (Purge log, Test purge with
  Cloudflare answering yes and no).

## 19.0.0.1.0 · 2026-10-30

- **Cloudflare page cache** (owner, 2026-10-30: page speed plan, phase 3), **shipped switched OFF**: Settings ›
  Website › "Cloudflare page cache", with the zone's ID, an API token (Zone › Cache Purge › Purge only), the pages
  Cloudflare may keep (to start: `/ /es/ /tours /es/tours`) and for how long (300 s).
- Switched on, an anonymous visitor's GET of a listed page (status 200, not debug or the editor) carries
  `Cache-Control: public, max-age=0, s-maxage=<seconds>` and no cookie at all; every other page is untouched, so
  Cloudflare's rule ("use the cache-control header, bypass without one") keeps only those.
- `mtbg_auth=1` is set while the session has a user (login) and removed without one (logout): Cloudflare never
  serves a cached page to a logged-in user.
- `/mtbg/session` (never cached) gives a cached page's visitor their own form token and country when they start
  filling a form (`window.mtbgSession`); Forms 19.0.0.4.6 opens the phone field on that country.
- After every save that changes a tour, departure, a booking's seats, a price rule, category, region, website page,
  template, menu, the website's own settings (the chat tab...) or an `mtbg_tours.*` setting, one Cloudflare "purge
  everything" once the save is committed (at most one every 10 s per worker; the one-minute job, on with the switch,
  sends the rest and retries refusals). The last 200 purges are listed (Settings › Purge log). Copies are switched off
  and lose the token (neutralize).
- Another extension can ask for a purge with `env['mtbg.edge.cache']._mtbg_changed()` when it is installed (soft
  call: e.g. Communication Flows when the chat tab's WhatsApp or text number changes).
- Needs Visits by Script (mtbg_tours_visit), so cached pages keep counting visits.
