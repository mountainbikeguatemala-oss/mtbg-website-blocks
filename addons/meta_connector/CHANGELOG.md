# Changelog

Every version of this extension, newest first. Tags: `git tag -l 'meta_connector-*'`.

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
