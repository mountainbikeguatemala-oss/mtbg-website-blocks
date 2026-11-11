# Changelog

Every version of this extension, newest first. Tags: `git tag -l 'mtbg_tours_visit-*'`.

## 19.0.0.1.5 · 2026-11-11

- Moved to the universal extensions repository (owner, 2026-11-11: extensions that are not only for running tours live in their own repository, installable without Tours Core). Its manifest names its new repository, so the updater takes it from there; nothing else changes (no data, no behaviour).

## 19.0.0.1.4 · 2026-11-10

- The visit beacon sends the page's referrer (document.referrer), for Visit Analytics' "source" (owner OK via the
  coordinator, 2026-11-10; Communication Flows' Website Visitors 1.3.0): /mtbg/visit hands it on as
  ``request.cfd_referrer`` (a string only, at most 2048 characters) before Odoo records the visit. Nothing else in the
  beacon contract changes. Pages Cloudflare cached before the update send no referrer until they are cached again.

## 19.0.0.1.3 · 2026-11-03

- Spanish (bulk translation pass): the .pot regenerated from Odoo's export and es.po rebuilt from it; 1 new Spanish translations. No English text changed.

## 19.0.0.1.2 · 2026-10-30

- **People in the apps' browsers counted** (owner, 2026-10-30; www 11:10-17:45 UTC: 149 visits sent, 71 recorded,
  against about 40 human page views an hour by Cloudflare's count): a link opened inside Instagram, Facebook,
  WhatsApp or Pinterest opens in the app's own browser, and Odoo's bot list ("instagram", "whatsapp", "pinterest",
  "preview") refused it. The visit comes from the page's script, so from a browser that ran the page: only crawlers
  and page tools by name are refused now (bot, crawl, spider, Google's and Meta's fetchers, headless Chrome,
  Lighthouse / PageSpeed...).
- **Why a visit is not recorded is in the log**: `visit refused: <reason>` (crawler (name), another address (host),
  too many, page not tracked...), never who sent it. `grep "visit refused"` counts them per reason.

## 19.0.0.1.1 · 2026-10-30

- **Every visit counted again** (www, 2026-10-30: about 100 real page views an hour by Cloudflare's count, 2-3
  recorded): the visit script was in the site's JavaScript bundle, which loads last (4.2 MB on www); a visitor who
  left or moved on before it finished was never recorded. The visit is now sent by a few lines in the page itself, as
  soon as its content is there (DOMContentLoaded), or when the visitor leaves first (pagehide); as plain text, which
  every browser sends with sendBeacon (JSON can be refused). The server and what it records are unchanged.

## 19.0.0.1.0 · 2026-10-30

- **Visits recorded by the page's script** (owner, 2026-10-30: page speed plan, phase 2): an anonymous visitor's
  page view is no longer recorded while the page is built; the pages Odoo tracks carry a tag, and a light script
  posts the view to `/mtbg/visit` once the page has loaded. The server records it with Odoo's own visitor code, as
  the page itself: the same visitor (IP, browser, session), the page, its address and language, country and city
  (Cloudflare), the marketing (UTM) cookies, and Communication Flows' page title, device and place.
- Logged-in users, bots and forms: as before. Settings › Website › "Visits recorded by the page's script" (on):
  off goes back to recording while the page is built, at once.
- What differs: a browser without JavaScript (most scrapers) is no longer recorded; a visit is recorded about a
  second after the page loads.
- Tests: a page view recorded by the script equals the one recorded while building the page (visitor, page view,
  country, city, page title and language, UTM cookie); one visitor per session; another site's address, bots and
  garbage refused; logged-in users and the switch off as before.
