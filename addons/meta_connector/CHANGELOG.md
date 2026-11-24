# Changelog

Every version of this extension, newest first. Tags: `git tag -l 'meta_connector-*'`.

## 19.0.1.6.3 · 2026-11-24

- **Instagram: a picture is published only once Meta has it ready** (www, since 2026-11-22: some Instagram stories
  failed in the Marketing Queue with "Meta: The media with ... cannot be found"). `ig_publish` now follows Meta's
  documented flow: after the media container is made it asks its status (`GET /{container}?fields=status_code,status`)
  every 3 seconds, for at most a minute, and publishes once it is `FINISHED`; `ERROR` / `EXPIRED` fail with Meta's
  status text, and a picture still not ready after a minute fails with a clear reason (the picture is not posted).
  The publish step still tries again a few times while Meta answers "not ready", now also on "cannot be found".
  Feed pictures and stories alike; callers unchanged (`ig_container_wait`, and `poll` / `timeout` on `ig_publish`,
  are new and optional).

## 19.0.1.6.2 · 2026-11-22

- **The marketing engine: story and post templates for every marketing app** (owner, 2026-11-22: "the marketing
  template preview should be GLOBAL marketing extension I don't want to have to code everything twice for two
  websites"; the owner chose this extension as its home). Moved here from Tours Marketing (19.0.0.9.10), the same
  models, tables and ids (nothing copied or re-made): `mtbg.marketing.overlay` (a story / post template: its shape,
  photo, gradient, QR code, layers, live preview), `mtbg.marketing.overlay.layer`, `mtbg.marketing.font`, and the
  drawing (`models/overlay_render.py`: Pillow, dates, placeholders). Tours' overlays draw exactly as before.
- New for every template: a **website** (its logo and address: `{website_name}`, `{website_domain}` "example.com",
  `{website_url}`; empty: the website it is drawn for); the **photo** cut to fill, shown whole on a background colour
  in a box, or "auto" (fills when made for the shape, else whole); **sticker** layers (a text on a coloured badge,
  turned a few degrees, with a border); **Only when** on any layer (a flag of the record: a new product, a bargain,
  the last one...); a logo layer's **Logo From** (the company's, as before, or the website's); a text's turn and its
  box's border.
- **Sources**: an app plugs in by overriding `_mtbg_overlay_sources()` (its placeholders and flags, its code added
  to `source`), `_mtbg_source_values(record, lang, website=None, **options)`, `_mtbg_source_photo(record,
  **options)` and the preview hooks (`_mtbg_preview_values`, `_mtbg_preview_photo`); `_mtbg_render_record(record,
  lang, website=None, ...)` draws a record. `/meta_connector/overlay/<id>/preview/<model>/<id>` (internal users,
  read rights on both) draws one 360 px wide for a queue's or calendar's card.
- **`mtbg_marketing_picture`**: a field widget (image field or picture address) showing a drawing; a click shows it
  as the phone does (a story's bars, the account, the reply box). The template editor's preview uses it.
- The template editor (list and form) and the fonts' list are here (Tours and Bike Shop Marketing open them from
  their menus). Website designers may edit templates and fonts.
- Updater: `mtbg_takes_over: ['mtbg_tours_marketing']` (the models move from it, a planned move, never a duplicate).
- Translations: Spanish for the new and moved texts.

## 19.0.1.6.0 · 2026-11-18

- **Posting on several Pages** (owner, 2026-11-18: "yes bicipaca will get its own social channels"): several Facebook Pages and Instagram accounts can be ticked in Set up Meta (as before), and each Page now has **Default Page for Posts** and **Default Instagram for Posts** (one each per connection; ticking one unticks the other). `_meta_post(kind, caption, image_url, story=False, target=None)`: `target` (a `meta.connector.page` or its id) posts on that Page or its Instagram account; it must be ticked for that network, else a UserError says so. Without `target`, the default, else the first ticked: existing callers post where they did. `_meta_post_target(kind, target=None)` gives the Page used. The Posting checks name the defaults.
- Migration: on each connection, the Page posts went on until now (the first ticked Page, the first ticked Instagram account) becomes the default. A new login's first ticked Page is the default when there is none.

## 19.0.1.5.0 · 2026-11-11

- **Stories** (owner, 2026-11-11: "do we have a way to publish instagram / facebook stories?" ... "yes make the story templates"): `_meta_post(kind, caption, image_url, story=True)` posts the picture as a story. Instagram: a `STORIES` media container (no caption: a story shows none), then its publishing. Facebook Page: the photo uploaded unpublished, then `photo_stories`. The same permissions as posts (`instagram_content_publish`, `pages_manage_posts`). A story is gone after 24 hours, so it has no address.

## 19.0.1.4.2 · 2026-11-11

- **Posting without Marketing** (owner, 2026-11-11, on the shop site: "no posting scopes yet"): the Facebook login asks for the posting permissions (`pages_manage_posts`, `instagram_content_publish` and the reading ones they need), and Set up Meta shows its Posting step, when Marketing is installed **or** Posting is switched on in Settings › Meta. Before, only Marketing turned them on, so a site without it could never get them granted. The setup's posting texts no longer name Marketing.

## 19.0.1.4.1 · 2026-11-11

- Moved to the universal extensions repository (owner, 2026-11-11: extensions that are not only for running tours live in their own repository, installable without Tours Core). Its manifest names its new repository, so the updater takes it from there; nothing else changes (no data, no behaviour). Author: MTBG Tours contributors; the tests use example names.

## 19.0.1.4.0 · 2026-11-10

- **Posting** (for Marketing, owner 2026-11-10: "autopost new confirmed tours to instagram, facebook"; "we'll need
  to modify the wizard for our meta extension to include those permissions if marketing is installed"): with
  Marketing installed (a soft check), Set up Meta has a **Posting** step after the Pages: the use cases to add on
  the Meta app ("Manage everything on your Page", the Instagram API), the Instagram business account linked to the
  Page, App Review, a new Facebook login, then **Check**: each permission (`pages_show_list`,
  `pages_read_engagement`, `pages_manage_posts`, `instagram_basic`, `instagram_content_publish`) and the Page and
  Instagram IDs, green or red (also on the Done step). The login asks for those permissions only then. Without
  Marketing: the setup and its permissions as before. Settings › Meta › **Posting** (off by default) lets the apps
  post.
- For apps: `_meta_post(kind, caption, image_url)` posts a picture with its caption on the Page ("facebook") or the
  Instagram account ("instagram", Meta's container then publish) and gives `{id, url}`; it says why when it cannot
  (Posting off, not connected, no Page ticked, a permission not granted, Meta's answer). `_meta_posting_on()`.

## 19.0.1.3.0 · 2026-10-28

- **One Meta login for WhatsApp too** (owner, 2026-10-27: single Meta connector). Settings › Meta gains a
  **WhatsApp block** when Communication Flows' WhatsApp Cloud channel is installed: its numbers' status and the
  switch **WhatsApp sends with the Meta login** (on by default; off: each number keeps its own token).
- The login keeps **what Meta granted it** (permissions, and the assets limited ones reach, e.g. WhatsApp business
  accounts), read at each login and by the daily check; shown on Set up Meta.
- For apps: `_meta_login(scopes, permanent)` gives the login only with every permission asked (and, if asked, a
  login that never expires: Facebook Login for Business); `_meta_targets(scope)`; `_meta_whatsapp_status()`.

## 19.0.1.2.0 · 2026-10-27

- **Moved to the mtbg-tours repository** (owner, 2026-10-26: "centralize all connectors"), beside the Zoho and
  Google connectors. Same module, same login, Pages and kept posts: nothing to set up again. Communication Flows'
  Facebook & Instagram channel keeps connecting through it. Updates now come from the mtbg-tours source.
- **Settings › Meta: an Instagram block and a Facebook block**, each with its status and a switch per use
  (Instagram Feed block here; Communication Flows adds Chat and Contact photos). All on by default.
- **Instagram Feed block options** (owner, 2026-10-26): **header** (profile photo, @username, name, followers and
  posts), **columns** on desktop (2–6) and on phone (1–3) or automatic, **tile shape** (square, portrait 4:5,
  landscape 16:9) and **corners**, **max width** (full, 1200, 900, 600 px). The account's name, counts and photo
  are read with the hourly refresh (the photo kept here as WebP).

Earlier versions were released from the communication-flow-designer repository (tag `meta_connector-19.0.1.0.*`).
