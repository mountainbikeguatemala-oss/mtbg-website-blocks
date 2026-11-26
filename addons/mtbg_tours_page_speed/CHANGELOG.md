# Changelog

Every version of this extension, newest first. Tags: `git tag -l 'mtbg_tours_page_speed-*'`.

## 19.0.0.12.0 · 2026-11-26

- **No English picture names on a page in another language** (owner 2026-11-26: "every text on the Spanish site must
  be Spanish"; live /es audit: 292 alts made from the pictures' file names, "Cal white", "Chat icon white",
  "5 stars 300px", "Difficulty Chart", "Early Bird" (the group banner's bird, on ~15 tour pages)…): on a page in
  another language than the website's own, a picture without an alt (or the editor's alt="" on a photo) is no longer
  named by its file's or attachment's name (written in the website's language). It takes, in the page's language:
  its figure's caption, else the heading of its section (a banner's title), else the heading it is under in the
  page's main area, else the page's title. A picture inside a link or button that has words (the banners' calendar
  and chat icons beside "Reservar ahora") is a decoration there (alt=""). An alt of its own (stored, translated)
  always stays; pages in the website's own language are named as before.
- **Links named in the page's language**: "Open photo", "Open the map" and "Home" (a link with nothing to say) are
  translatable ("Abrir foto", "Abrir el mapa", "Inicio"). On a page in another language, a link with nothing to say
  to one of the site's pages (the journal's cover links: "Guatemala mountain biking guide", the post's address in
  words) takes the words of another link to the same page (the card's title), else the page's title; a "Learn more"
  link is no longer told the address's words there.
- **Tests**: `test_a11y.py` (a Spanish page: caption, section heading, heading, decoration, card title, page title,
  no file or address words; the English page as before) and an /es page of the test site (`Abrir foto`, no file
  name).
- New strings (Spanish in es.po): "Open photo", "Open the map", "Home".

## 19.0.0.11.0 · 2026-11-21

- **A click answered at once on computers** (desktop INP, 2026-11-21: Google Search Console rated every computer page
  of the site poor, 575 ms; phones good): the visitors' scripts started in one long task each (at a slow computer's
  speed, 4x: the bundle's modules 300 ms, the page's interactions 500-700 ms), and a visitor's first click waited for
  them. Now they start in short slices (30 ms each), the page answering a click and drawing a frame between two:
  - the bundle's modules (`static/src/js/lazyloader.js`): while the visitors' scripts load, Odoo's module loader only
    takes note of each module defined; they then start in the same order, by Odoo's own loader, a slice at a time,
    each script's before the next one is evaluated. The page's start waits for the last one, as before
    (`allScriptsLoaded`); a module still missing one is reported as Odoo does.
  - the page's interactions (`static/src/js/sliced_start.js`, in the visitors' script copy only): the first start of
    the whole page, in Odoo's order (each interaction class in the registry's order, its elements in the page's), and
    a bundle loaded later that adds its interactions to a part of the page (the booking form's on a tour page; then
    Odoo's own start of that part for the public root's widgets). Any other start (a part of the page started again)
    is Odoo's own.
  Logged-in users (the editor) and the full pages (`FULL_PATHS`) keep Odoo's bundle and start, unchanged.
- **Tests**: `test_inp.py`, in a real browser at 4x slower: no long task and no long animation frame over 200 ms
  while the visitors' scripts start (Odoo's start: one task of 480 ms on the test site's contact page), and every
  module and interaction starts, once.

## 19.0.0.10.0 · 2026-11-18

- **Page speed on any website** (owner, 2026-11-18: page speed on the shop site, which has two websites and no Tours):
  the extension moves from the Tours repository to the universal one (technical name kept; its manifest names its new
  repository, so the updater takes it from there). It needs no Tours: it depends on Odoo's Website and the admin look
  (`mtbg_backend_ui` 0.2.0: the speed log's side bar list). The Tours parts stay soft: the tour pages and covers where
  Tours is installed, the business's time zone where Tours has one (else the user's, else UTC).
- **Each website on its own** (several websites on one database): the nightly speed log measures every website that
  has an address (Website › Settings › Domain; the default website without one: at the site's address), its
  homepages and its pages under /tours where it has any; each row names its website (list, filters, Group by, side
  bar). The dashboard shows one website at a time (a choice above the chart when there are several, kept in this
  browser); "See all rows" opens that website's rows. The pages themselves (first photo, screen copies, lean
  bundles, first screen, logo) already follow the website a visitor is on.
- **Shop pages without errors** (found on a site with the shop, `website_sale`): the visitors' script copy left out the
  payment, delivery, address and onboarding pieces, but kept the shop's checkout pieces that import them (visitor
  pages reported missing modules: `@website_sale/interactions/checkout`, `.../payment_form`, `.../address`, the pickup
  map). Those shop pieces (and the same pieces of the shop's companions: click and collect, loyalty, Mondial Relay, the
  country address forms) are left out of the copy too; /shop and the checkout keep Odoo's own bundle, as before.
- The rows logged before get their website by their address (else the first website), in a post-migrate; nothing
  else changes (switches, jobs and their times as they were).

## 19.0.0.9.2 · 2026-11-17

- The lean page switches (`mtbg_tours.page_speed_*`) declared for the page cache here, now that Catalog no longer purges on every `mtbg_tours.*` (www, 2026-11-17: the page cache's log showed "Changes saved · Every page" every hour and after the photo server's posts, nothing on the pages changed).

## 19.0.0.9.1 (2026-11-17)

Owner, 2026-11-17, after the speed log's night (phone average LCP 3.5 s, 22 pages over 4 s, mostly tour pages; the
Christmas enduro tour 9.6 s, its LCP element the header's logo).

- **The cover is the tour page's one urgent picture, at the size a phone shows it.** The pictures' preloads went at the
  very top of the head, before the page's `<meta name="viewport">`: a phone read them taking the page as 980 px wide,
  so the cover's `imagesizes` chose its 1920 px original (326 KB on www, at high priority) besides the ~800 px copy the
  page then showed. The preloads now come right after the viewport (still before the inlined rules).
- **A page background behind the page's photo is never urgent** (a tour's tile): it was preloaded at high priority,
  beside the cover, and, painted under a phone's whole first screen, the browser took it as the page's largest picture
  (its LCP; Website 19.0.0.10.58 paints it below the top section on phones). It is now preloaded for computers only
  (`media="(min-width: 992px)"`), without priority, and its phone and tablet copies are no longer preloaded ahead of
  the cover (they come with the page's rules, also in `--mtbg-page-bg` for the tour page's phone layer).
- **The header logo at an address Cloudflare keeps**: `/web/image/website/1/logo/logo.svg?unique=...` (its file type
  from the logo; the version kept) instead of `/logo/<site name>`, which went to the server on every visit.
- **Smaller first-screen rules** (the inlined CSS): left for the whole stylesheet (asked for once the page has loaded)
  are the rules of what a visitor does (`:hover`, `:focus`, `:focus-visible`, `:focus-within`, `:active`, unless
  inside `:not()` and the like), of what is inside a closed menu or popup (a rating's popup `.mtbg-tip` is hidden
  content now too; a hidden element keeps what places, sizes and hides it), fonts no kept rule names (and one
  `@font-face` per family, style, weight and range), transitions and the pointer's look, `@media print`, and lists
  nested deeper than the first screen's. The content's first screen is counted without long attribute values (a
  20 KB inlined icon in a style filled it). www's Christmas tour: ~57 KB of rules on a fresh render (200 KB in
  Cloudflare's stale copy), ~49 KB now; worked out once per stylesheet version and page shape, as before.
- **Speed log dashboard**: when the LCP breakdown's parts (timed on Google's unslowed load) sum to less than half the
  LCP (its slowed-down estimate), a worst page's card says so and names the LCP element instead of a small part:
  "LCP element: header logo; the breakdown doesn't explain the time" (header logo, tour cover, page background,
  title, else the element). Spanish (tú) in es.po and the .pot.
- Tests: the first screen's rules (states, closed menus, fonts, lists, transitions, print), the fold without long
  values, the cache per stylesheet version and page shape, a rendered tour page's rules (under 60 KB, header and cover
  in), the cover's preload after the viewport and the only urgent one, the background's, the logo's address, the
  dashboard's cause.

## 19.0.0.9.0 (2026-11-17)

Owner, 2026-11-17: "Redo the website speed log page: include cards for worst performing pages, average scores over
time, charts for progression over time by stat type at the top, and all existing functionality. Include in the table
the page title"; "the chart should be first on the page, big, with buttons for different stats and overlays"; "table
should be its own page"; "make this whole page mobile compatible".

- **Website › Reporting › Speed log is a dashboard** (a client action, `static/src/dashboard`):
  - **One big chart first**: the nights' averages of a stat chosen by its button (Score, LCP, First paint, Blocking
    time, CLS, Server response, Page weight), phone and computer as two lines (each can be hidden); overlays: a second
    stat on a right axis (dashed), the stat's limit (LCP 4 s phone / 2.5 s computer, the others Lighthouse's "good"
    marks: score 90, first paint 1.8 s, blocking 200 ms, CLS 0.1, server 800 ms, weight 1,600 KB), one of the worst
    pages' own line; 7, 30 or 90 nights. The choice is kept in the browser. Chart.js from Odoo's own bundle
    (`web.chartjs_lib`, loaded when the page opens, as the graph view does), its colours for light and dark.
  - **Last night against the 7 nights before**, phone and computer: average score, average LCP, pages over the limit,
    pages not measured, each with its change and an arrow (green when better).
  - **Worst performing pages** (phone or computer, 5): title and address, score, LCP, the LCP breakdown's biggest part
    ("render delay 1.6 s"), Over the limit / Slow tonight, nights slow in the range. A click opens that page's rows on
    that screen (filters that can be removed); "Latest night" opens its latest row.
  - All in one call (`mtbg_speed_dashboard`, SQL grouped by night and screen; administrators only).
- **Every night's rows on their own page**: Website › Reporting › Speed log: all nights (the dashboard's "See all
  rows"): the list, its filters, group-bys, side bar and form as before, with a **Page title** column (then the page),
  searchable and a group-by; on phones the rows as cards (title, address, night, phone/computer, score, LCP, flags),
  a tap opens the row.
- **Page title** stored on each night's row: the website page's name when the address is one, else the page's own
  `<title>` (its head only, the site's name after "|" left out). Rows logged before: the migration gives them the
  title their page has on another night or its website page's name (nothing fetched during the update); the others
  get their page's `<title>` from the speed log's job (ten pages a run, started a minute after the update; a page
  that does not answer is tried again on the next run).
- Phones: the chart full width (260 px), the stat and overlay buttons as rows of chips scrolled sideways (44 px to
  tap), the legend under the chart, two cards a row, the worst pages one under the other, no side scroll.
- Spanish for the new texts (es.po and .pot).

## 19.0.0.8.1 (2026-11-16)

- Tests: the visitors' lean script bundle keeps the page cache's session script, now `/cloudflare_connector/static/src/js/session.js` (the page cache merged into Cloudflare Connector 19.0.2.0.0; checked where `mtbg.edge.cache` is there). No behaviour change.

## 19.0.0.8.0 (2026-11-16)

Owner, 2026-11-16: fixes A ("the cover paints first") and C (the speed log), after the PageSpeed check of www (phone
lab LCP swinging 1-11 s: the cover arrived in ~0.3 s but painted ~1.1 s later, behind ~200 KB of inlined rules, a
cover at byte ~340,000 of the page, a forced reflow and the visitors' scripts).

- **The first screen's rules are the first screen's** (A1). The inlined rules were those of everything the page's
  HTML holds (a tour page: 156 KB, nearly the whole stylesheet). They are now those of what the first screen shows:
  the header and what is above the content, and the content's first 15 KB of markup. A closed menu, the phone menu, a
  modal, an element with `hidden` or Bootstrap's `d-none` brings its own element's rules (the ones that hide it), not
  its content's. A rule asking for an attribute needs an element with that attribute; the custom properties
  (`--x`, ~2,500 in `:root`) only where a kept rule, a kept property or the page uses them. On a local copy: a tour
  page 57 KB instead of 156 KB, the homepage 49 KB instead of 106 KB. The rest of the page gets its rules with the
  whole stylesheet, asked for once the page has loaded, as before.
- **The cover earlier in the page** (A2). The menus' hidden content (the computer's mega menus, the phone menu: ~70-90
  KB of markup before the content) is sent after `</main>` in `<template>`s and put back in its place by a small
  script right there, before any of the visitors' scripts runs (menus, mega menus, Bootstrap's offcanvas find every
  element where it was). A menu with a script of its own stays. Local tour page: the cover at byte 85,000 instead of
  248,500.
- **The visitors' scripts after the first paint** (A3). A visitors' copy of Odoo's lazyloader (the same code and
  module name, `static/src/js/lazyloader.js`, bundle `assets_frontend_minimal_lean`) starts the script bundle after
  the load and a painted frame, once the first screen's whole stylesheets are in (at most 3 s); a tap, click or key
  starts it at once, and a button pressed before it waits and is pressed again, as in Odoo's.
- **No forced reflow in the header** (A4): in Website 19.0.0.10.54 (its full-screen height script reads the layout in
  a `ResizeObserver`).
- **The header logo at low priority** (A5). The phone header draws its logo 229 x 36 px; at normal priority it
  painted before the cover in every local run, so a Lighthouse run that missed the cover's paint kept the logo as the
  page's LCP. It now asks for low priority (never lazy), so the cover, preloaded at high priority, comes first.
- **Speed log** (C):
  - Opens on both screens: no Phone filter by default (it hid the 657 Computer rows), and the side bar counts Phone
    and Computer each without the other's filter. A form shows each row in full.
  - A page Google could not measure (no performance score, FAILED_DOCUMENT_REQUEST, a refusal) is tried again 20
    minutes later, twice, before it is "Not measured"; its reason stays visible meanwhile.
  - A phone page slow on its first run (LCP over 4 s) is measured twice more, 10 minutes apart once the night's first
    pass has moved on, and keeps its median run (each run's LCP in "LCP runs"): about 150 calls a night plus two per
    slow phone page. The night ends 4 hours after it started: a page still waiting keeps what it has.
  - "Over the limit" now means slow two nights in a row; "Slow tonight" is the night's own flag (the update sets it
    on the nights already logged and recomputes their "Over the limit").
  - Lighthouse's LCP breakdown on every row (server, load delay, load time, render delay, in ms; Lighthouse 13's
    `lcp-breakdown-insight` or the older `largest-contentful-paint-element`) and the LCP element's selector, in the
    list and the form.

## 19.0.0.7.12 (2026-11-14)

- **Visitors' scripts 14% lighter** (page speed, priority 2): 1.73 MB instead of 2.04 MB, 418 KB compressed instead
  of 486 KB. The visitors' copy of Odoo's script bundle also leaves out the back end's own widgets, which no visitor
  page draws: the domain and condition editors, field and record selectors, the barcode scanner, signing, the code
  editor, the developer menu, the pager, the rainbow man. It also leaves out the portal's two-factor and quote pieces
  (/my keeps Odoo's bundle). The website chat's own widgets (emoji and colour pickers, tabs, swipes, panels, file
  upload) now come with the chat's bundle, loaded when the chat opens, just like the bus already did. The tests check
  that no kept file imports a removed one, and that the chat's code finds everything it imports.
- **The first screen's inlined rules are about 12% smaller**: 106 KB instead of 120 KB on the homepage, and 156 KB
  instead of 172 KB on a tour page. An animation's `@keyframes` is kept only when a kept rule or the page itself names
  it; the others arrive with the whole stylesheet. A selector listed twice in the same rule is written once.
- **Instant pages**: on visitor pages, the next page is fetched when the visitor points at a link or touches it, so
  it opens at once. Chrome and Edge use their own speculation rules (`eagerness: moderate`), which they switch off by
  themselves under Save-Data, battery saver or low memory. Other browsers that support it get a prefetch link, never
  on Save-Data or 2G. Never fetched: Odoo's back end, the portal, the shop, checkout and payment, the customers'
  token pages, the website's own routes and the chat, with or without the language prefix. Also skipped: links with
  a query string, downloads, new-tab links, nofollow links and files. Only the page's HTML is fetched, and its visit
  is still recorded by the page's script once it opens.

## 19.0.0.7.11 (2026-11-12)

- **Font Awesome trimmed on visitor pages** (owner, 2026-11-12: "trim font awesome"). The visitors' stylesheet now
  loads Font Awesome as two files. The first is a small copy (22 KB) with the 233 icons the site uses. The second is
  Odoo's whole font (75 KB), for any other icon. The browser fetches a file only for the icons a page draws
  (`unicode-range`), so no icon can go missing. Pages using only the site's icons fetch 22 KB instead of 75 KB, at the
  same time as the cover. Logged-in users and the back end keep Odoo's.
- The icon list comes from a copy of the site: the 328 sitemap pages in both languages, the scripts visitors load
  (including the ones loaded on demand), the stored templates, blocks and content, and the stylesheets' own icons.
  To change the list or follow a new Odoo font-awesome.css, run `tools/font_awesome_visitors.py`; a test fails if
  Odoo's file changes.

## 19.0.0.7.10 (2026-11-12)

- **Phones: the tour's cover comes first** (owner, 2026-11-12: the speed log's phone LCP, a median 4.6 s, 61 of 73
  pages over 2.5 s; the cover itself is light, 84-94 KB, but it shared slow 4G with ~550 KB the first screen does not
  use). What changed:
  - **The first photo's preload is at the top of the head** (after the charset), not after the ~200 KB of inlined
    first-screen rules: a phone starts the cover at ~0.6 s instead of ~1.6-2 s.
  - **A page background** (a tour's, in #wrap's own style) **no longer takes the cover's preload**: both are preloaded.
  - **Section backgrounds after the page's first photo wait until they come near the screen**, whatever their rank
    (the first two were always fetched at once: on a tour page, its description's sections far below the cover).
  - **The whole stylesheets** (the site's and an extension's, after the page's own inlined rules) **are asked for
    once the page has loaded** (`data-mtbg-late-href`), not beside the cover; `<noscript>` keeps them as before.
  - **A video block's player** (YouTube and the other sites Odoo plays) **loads when the video comes near the
    screen**: the page carries Odoo's own iframe with `loading="lazy"`; Odoo's video block finds it and keeps it
    (autoplay and all). Not with the cookies approval (Odoo's own way).
- Measured on a copy of the site with phone throttling (slow 4G, 4x CPU), three runs each: a tour cover drawn at
  5.0 s instead of 8.1-8.4 s, another's arriving at 5.4 s instead of 8.4 s (the copy sends uncompressed pictures,
  2-3x the bytes of the live site).

## 19.0.0.7.9 (2026-11-10)

- A link to the site's own address is named as one of its pages: the address comes from the request (its host, the website's domain), not from the code. Brand-free release (owner, 2026-11-10): no business names in code, data, samples, comments or tests.

## 19.0.0.7.8 · 2026-11-10

- **Speed log: the LCP element is recorded again** (owner, 2026-11-10: "what do you mean we are not recording LCP? in
  our log? fix it"). Google's PageSpeed now runs Lighthouse 13, which gives the LCP element in its
  "lcp-breakdown-insight" audit; the log read only the older "largest-contentful-paint-element" path, so the column
  stayed empty every night (the LCP time itself was always recorded). Both shapes are read now; the next night fills it.

## 19.0.0.7.7 · 2026-11-08

- **The first screen first** (owner: "yes" to splitting the stylesheet; Google's phone test, Nov 8: the site
  stylesheet, 852 KB, 160 KB as sent, was the one file holding every page's first paint, 1.8 s of it, with 142 KB of
  it unused on a tour page). On the visitors' pages without Odoo's extras, each page now carries in its head the rules
  of that stylesheet its own HTML can match (24–28 KB as sent on the home, tour, region, rental and blog pages), and
  the whole stylesheet comes right after it without holding the page, at the same place, so every rule then applies
  as before. The theme's fonts are linked in the head (they were fetched only once the stylesheet had arrived).
  Compared on www's home, /es, a tour, a region, a rental and the blog, phone and desktop: the first screen drawn
  with the page's rules alone is the same as with the whole stylesheet.
- A switch on the Page Speed settings page, "First screen first", on by default (shown with "Visitor pages without
  Odoo's extras", which it needs). Logged-in users and the portal, checkout and payment pages are not concerned.

## 19.0.0.7.6 · 2026-11-08

- **"Not measured", not a score of 0** (www, Nov 8: the homepage and five tour pages logged on a phone with score 0
  and no main-picture time): when Google's Lighthouse cannot finish a page (its runtime error, e.g. "no Largest
  Contentful Paint", or no performance score in its answer), the row is Not measured with Google's reason in its
  message, and never counts as over the limit.

## 19.0.0.7.5 · 2026-11-08

- **Fix: the first night was a day late, and every update pushed it again** (www: on, Google connected, no night
  measured): the job's time came from the module's data ("tomorrow, 08:30 UTC" when installed or updated), so the
  first run after a late-evening install was the night after next, and each update moved it to "tomorrow" again. The
  job's time is now the code's alone, never an update's.
- **The speed log follows the site's time zone** (owner: "it should follow the global time zone"): it runs at 02:30 in
  Settings › Operator Timezone, set when it is turned on, by this update, and again whenever that time zone changes.
  The settings page shows the next night.
- **Measure now** on the settings page: tonight's list is made and measured right away, in the background, a few
  pages a minute.

## 19.0.0.7.4 · 2026-11-08

- **The speed log measures through the Google connector** (owner: "the new pagespeed should get its api info from our
  main google connector there is no reason for it to have its own google link"; connectors and their API code live
  only in connector extensions). Page Speed has no Google key or Google call of its own any more: the connector's
  "PageSpeed Insights" app and its server API key (Settings › Google › Set up Google › 6. API keys) do the
  measuring, asked softly (no dependency): without the connector or with the app off, the speed log does nothing and
  its settings say "Connect Google (Settings › Google) and switch on PageSpeed".
- **Set up** is four steps: enable the PageSpeed Insights API in the Google project (and give the connector a server
  key), switch on PageSpeed in Settings › Google (with its state, and Open Set up Google), Test (one homepage
  measurement through the connector, Google's refusal in plain words), turn on nightly. It writes only the speed
  log's switch.
- The settings page shows "Google connection" (OK or what to do) with Set up Google instead of a key of its own.
- Update: a key set in Page Speed (0.7.0-0.7.3) becomes the connector's server API key when the connector has none,
  then Page Speed's own is deleted (the connector not installed: it stays until then).

## 19.0.0.7.3 · 2026-11-07

- **Fix: updating from 0.6.x/0.7.0/0.7.1 failed** (www, release -17, rolled back): 0.7.2 removed the General Settings
  field of the "Visitor pages without Odoo's extras" switch, but the old General Settings view naming it stays in the
  database until the update ends, and Edge Cache's General Settings view was checked against it meanwhile ("Field
  mtbg_page_speed_lean does not exist in model res.config.settings"). The field is kept (not shown on the General
  Settings page; the switch lives on Page Speed's own settings page).

## 19.0.0.7.2 · 2026-11-07

- **One Page Speed settings page** (owner: "the setup link should be in a central page-speed review settings area"):
  Website › Configuration › Page Speed, also the Speed log's cog (the Speed log is now Core's list, with a side bar:
  over the limit, phone, computer, not measured). On it: the nightly speed log's state (on, key saved yes/no, the key
  never shown, last night measured and how it went) with **Set up** and **Open the speed log**; the "Visitor pages
  without Odoo's extras" switch, moved here from the General Settings page; the photo copies job (last run, big
  photos looked at, copies) with **Run now**; what is always on. Its Save writes only Page Speed's own switch (on www
  a General Settings save rewrites every parameter): nothing of Page Speed's is on the General Settings page any more.
- **Set up is a guided wizard** (owner: "need a wizard for this pagespeed setup with link to site and instructions"):
  1. Get a key: Google Cloud's project picker (the same project as Settings › Google if you like), the PageSpeed
     Insights API to enable, Credentials › Create credentials › API key, the optional restriction to that API, and
     Google's own guide, each opening in a new tab. 2. Paste the key, **Test key**: one measurement of the homepage on
     a phone with it, its score, or Google's refusal in plain words (key not valid, API not enabled in that project,
     key limited to other sites, daily allowance used up); nothing saved. 3. Turn on: "Measure every night", the time
     (02:30) and the pages it covers, Save: only the speed log's switch and key are written.
- Page Speed now depends on Core (the base): its list, side bar and settings cog.

## 19.0.0.7.1 · 2026-11-07

Owner's go, 2026-11-07, on the speed check's recommendations:
- **Phones take the main picture's ~800 px copy** (the tour pages' cover): a phone with a 2.6x screen chose the 1280
  px copy, about 340 KB on www (Agua's phone LCP 4.9 s; 13 tour pages over 4 s on 3 Nov). The first picture's sizes
  steer phones to its ~800 px copy (about 120 KB), still sharp on a phone; its preload chooses the same.
- **Computers get a lighter copy of the big photos** instead of the photo itself: the homepage's first photo, the
  Contact us cover, the sections' backgrounds near the top and the tour pages' main photo were 250-390 KB originals
  (www homepage after 0.7.0: those four, 1.3 MB, still the most of what loads first). A 1920 px copy (the photo's own
  width when narrower) at WebP quality 70, used only when at most 80 % of the photo: on computers through the
  backgrounds' media rules and preload, and in the main photo's srcset.
- The photos job makes those copies for the backgrounds and the tour pages' main photo (phone, tablet and computer
  copies the photo lacks), each photo looked at once: a photo too small for a copy no longer brings the job back every
  minute. A picture the editor made from another (cropped or optimized, like www's homepage photo) gets them too: the
  job used to skip it as a copy.

## 19.0.0.7.0 · 2026-11-07

- **The later sections' background photos load when the visitor nears them** (owner's GTmetrix records: the
  homepage getting slower; measured 2026-11-07 on a computer: about ten section photos further down, 250-380 KB each,
  about 3.5 MB, fetched at once with the first one: its LCP 0.7 → 1.8-4.2 s, the fonts at 3-4 s, the page loaded at
  6.8 s). The first two section backgrounds load at once as before (the first still preloaded); each later one
  waits until its section is within 400 px of the screen (a carousel's slides together, with their carousel).
  Visitors only (logged-in users and the editor as before); a background written in a page's stylesheet is untouched.
- **Nightly speed log** (owner: "we should do it from our own www server"): every night the site asks Google
  PageSpeed Insights (Lighthouse, run on Google's computers) for its homepage, its Spanish homepage and every page
  under /tours, on a phone and on a computer, a few pages a minute; Website › Reporting › Speed log keeps each
  page's score, LCP, first paint, blocking time, layout shift, server answer and weight for 180 days, the pages over
  the limits flagged (LCP over 4 s on a phone, 2.5 s on a computer). Speed log › **Set up** (administrators): the
  switch and the owner's own PageSpeed API key (without one, Google's shared allowance is used up by everyone else),
  saved alone, never through the Settings page (on www a Settings save rewrites every parameter). Database copies
  turn it off and forget the key.

## 19.0.0.6.0 · 2026-11-04

- **The stylesheet too, same switch** ("Visitor pages without Odoo's extras"; owner's code clean-up: "not loading
  scripts that are not needed on each page"). Every visitor page waited for Odoo's whole frontend stylesheet, with the
  website editor's and the back end's own styles in it. With the switch on, anonymous visitors on ordinary pages get a
  copy without them (`mtbg_tours_page_speed.assets_frontend_lean`): the editor's media dialog, switch, placeholder and
  QWeb styles, the onboarding tours, the payment, delivery, portal security and quote styles, a back-end report and
  the back end's own widgets (colour list and picker, tags, notebook, rainbow man, field and record selectors, code
  editor, emoji picker, barcode, pager, top bar, translation dialog, signature field).
  The editor's background shapes (`.o_we_shape`: 252 classes, 120 KB) load after the page has shown
  (`assets_frontend_late`, not render-blocking); their base rules (a section holds its filter and shape layers) stay in
  place in the page's stylesheet (`static/src/scss/background_layers.scss`, Odoo's rules as they are), so the cascade
  does not change. Logged-in users (the editor), the portal, checkout, payment and invoice pages keep Odoo's own
  stylesheet. Measured on a copy of DEV1: 1,079 → 912 KB minified render-blocking CSS (149 → 134 KB compressed).
- **More left out of the visitors' scripts:** the passkey login (and the portal's passkey settings that import it), the
  portal's address, details, search panel and signature forms, and the editor's utilities no kept file imports (HTML
  viewer, switch, colour, image processing, drag and drop...). Where CFD's chat tab loads the website chat on its own,
  the bus (live messages, 73 KB) and mail's formatting helpers leave the page's scripts: the bus comes with the chat's
  bundle (`cfd_website_chat_tab.assets_chat`, added by this extension while the switch is on), Odoo's chat needs it
  there. The editor's HTML upgrades and embedded components (stored content uses them) stay.
  Measured: 2,221 → 2,105 KB minified (on top of 0.5.0).
- The theme's fonts are fetched early for the visitors' stylesheet too (0.3.0's preload read only Odoo's).

## 19.0.0.5.1 · 2026-11-03

- Spanish (bulk translation pass): the .pot regenerated from Odoo's export and es.po rebuilt from it; 11 new Spanish translations; 11 strings added to the .pot that were missing (they never loaded). No English text changed.

## 19.0.0.5.0 · 2026-11-03

- **"Visitor pages without Odoo's extras"** (owner: "the trim odoo extras should be an option in the optimizer
  extension itself on/off"; Website › Settings, off by default). Every website page loads Odoo's whole frontend
  script bundle, with pieces a visitor reading a page never uses: the editor's media dialog and Unsplash search, the
  onboarding tours, the tax helper, the payment and delivery forms. With the switch on, anonymous visitors on
  ordinary pages get a copy of the bundle without them (`mtbg_tours_page_speed.assets_frontend_lazy_lean`);
  logged-in users (the editor) and the portal, checkout, payment, invoice and customers' token pages keep Odoo's own.
  Nothing is uninstalled; the copy's removals are made for the modules installed, again when modules change, and
  whatever a kept file imports stays (tested). Measured on webspeed: 535 → 488 files, 2,471 → 2,205 KB minified,
  584 → 528 KB compressed.
- The lighter photo copies (0.4.0) load Pillow's WebP writer themselves: with Page Speed alone (no Website or Gallery
  extension) the copies failed with `KeyError: 'WEBP'` (found by the tests on a fresh database).

## 19.0.0.4.2 · 2026-11-03

- **Pictures fetch the size they are shown at** (www search check, 2026-11-03: PageSpeed 1,019 KiB of image savings on
  the Agua tour page): a picture with a srcset but `sizes="100vw"` (or none), shown 250 px wide in the content,
  made browsers fetch its 1600-1920 px original. Its sizes are now its styled width (`width: 250px`), else its
  column's share of the page's container (col-lg-4: 380 px on a computer), else the container (1140 px). Sizes a
  picture has of its own are kept.
- **The tour pages' cover gets the lighter copy too:** the photos job lightens a public photo's screen copies even
  when the copy itself is not public (the cover's /web/image/<id>/1280x1280 is answered with it by Website); a
  private picture's copies are left alone.
- Not here: the "Join our next big tour" banner's photo (/web/image/<id>/1600x1000) is drawn by Site Notice's script
  after the page loads.

## 19.0.0.4.1 · 2026-11-03

- **Fix: a section background saved with single quotes was missed** (www's Contact us cover:
  `url(&#39;/web/image/2552&#39;)`): no preload, no phone copy. The quotes the editor writes are all known now.
- **Phone and tablet copies of the background photos that have none:** the editor makes them only when a picture is
  resized in it, so a cover could reach phones whole (Contact us: 1920 px, 355 KB; phone LCP 4.9 s). The photos job
  ("Page speed: lighter screen copies of the photos") now also makes the 800 and 1280 px WebP copies (quality 70,
  only when lighter than the photo) of every background photo used in the website's views, blog posts and content
  blocks that has none, 10 photos per run a minute apart, then empties Cloudflare's cache once (Edge Cache, where
  installed) so the pages take them. The tour pages' backgrounds (Website 0.10.28: the picture's own address, their
  phone LCP) are among them.
- **alt="" on a photo of the content or a picture with a title** (the 940 pictures the search crawl counted as
  without alt, 2026-11-03: the editor leaves alt="" on the photos it adds; the bike type pictures have their words
  in a title): the title, else the photo's file name in words, else the page's title. Icons, flags, logos and
  pictures marked as decoration (role="presentation", aria-hidden) keep alt="". The review slider's photos are drawn
  by its script after the page loads: not reached here (Reviews).
- The first picture of a page whose main area carries its background in its own style (the tour pages' #wrap) is
  seen too.

## 19.0.0.4.0 · 2026-11-03

Accessibility and search (owner's search plan, 2026-11-03; PageSpeed accessibility 85, SEO 92), on the page sent to
an anonymous visitor, at render time: nothing stored changes (posts, blocks and imported descriptions stay as they are).
- **Every picture has an alt** (956 of 7,077 on www had none, inside stored content): its file's name in words
  ("lake-atitlan-sunset_2-1024x683.jpg": "Lake atitlan sunset"; the attachment's name for an address without one),
  else the page's title for a camera's name (IMG_1234). A picture with alt="" (a decoration) keeps it.
- **The header logo is not lazy** (it is the first thing seen).
- **Links with no name get one:** a picture link "Open photo", a map link "Open the map", else where it leads.
  **"Learn more" / "Read more" links say where they lead** to screen readers ("Learn more: What level am i").
- **Links in a page's text are underlined** (paragraphs of the content, a blog post's lists, the ride facts note),
  never in menus, buttons or cards: no longer told apart by colour alone.
- **Lighter screen copies of the photos:** the 'resize: <px>' WebP copies (the ones phones and tablets get) are made
  again at WebP quality 70 from their original by a job ("Page speed: lighter screen copies of the photos"), 30 at a
  time a minute apart, then each night for new copies; kept only when at least a tenth lighter, same size on screen,
  same address. Measured on webspeed's largest copies: 20 to 30 % lighter (264 → 209 KB, 123 → 88 KB).
- Not here (other modules or the owner's theme): the review slider's photo links and the homepage "READ MORE" are
  drawn by script after the page loads; low-contrast brand colours (calendar day colours, the pink Wildcard tab, the
  blue CHAT button, the green "Group from" price) are design choices; Raleway served locally is the theme's font
  option.

## 19.0.0.3.2 · 2026-10-30

- **Fix: a page could answer "500" to visitors for up to an hour** (found by the coordinator on webspeed, in every
  version since 0.1.0): Odoo refreshes a page it cached more than an hour ago and hands back the very response it
  keeps in its cache; this extension then rewrote that response's body (as bytes), and every later visitor served
  from Odoo's cache got an error ("cannot use a string pattern on a bytes-like object") until the cached page was
  refreshed again or the caches cleared. The visitor now gets a copy of the refreshed page, as Odoo does for a page
  served from its cache, so nothing a request does to its page changes the cached one (the pictures and fonts here,
  and the Edge Cache extension's headers). Test of the refresh path added.

## 19.0.0.3.1 · 2026-10-30

- **Tour pages and the tour list paint sooner on a phone** (owner, 2026-10-30: "proceed with other optimizations";
  throttled phone, slow 4G, before → after): tour page first words 3.4 → 2.3 s, cover photo 5.7 → 3.0 s; /tours
  first words 2.4 → 2.0 s, first card 2.6 → 2.2 s:
  - the first picture's preload carries its srcset and sizes, so the phone fetches only the copy it shows (the tour
    page's cover: the 117 KB 800 px copy, no longer the 339 KB original besides it);
  - only the first picture loads at once: the main area's other photos marked eager (the catalog's first row of
    cards, three on a computer, one on a phone's screen) wait until the page is laid out and shows them, instead
    of slowing the site's stylesheet down.

## 19.0.0.3.0 · 2026-10-30

- **The words show about half a second sooner on a phone** (owner, 2026-10-30: page speed round 2; measured on a
  throttled phone, slow 4G: homepage 3.03 → 2.47 s, /tours 2.70 → 2.13 s to the first words):
  - the theme's font stylesheets (Raleway from Google, Journal), which the site's stylesheet only asks for once it
    has arrived (`@import`), are preloaded in the page's head, so they come with it instead of after it; Google's
    font server connection is opened at once;
  - the icon font (FontAwesome, 76 KB) is no longer preloaded ahead of the site's stylesheet: it comes with the
    stylesheet that uses it.

## 19.0.0.2.0 · 2026-10-30

- **Phone and tablet sizes of the background photos** (page speed, phase 4: the homepage's parallax/hero sections
  sent their 1920-px originals to phones): a section's background photo (a public image attachment) comes as its
  ready `resize: 800` WebP copy on phones and `resize: 1280` on tablets (by media query in the page's head), the
  original on computers; only a copy lighter than the original is used, so a picture without one stays exactly as
  it is (never broken, never heavier). A background photo first on the page is preloaded in the size of the
  visitor's screen.
- **Photos keep their room and come in smaller copies**: a content photo (`img-fluid`, no size of its own) gets its
  width and height from the picture (no jump while it loads), and a `srcset` of its ready smaller copies (those
  lighter than the original).
- The mobile menu's mega menu "back" button gets the label "Back" (accessibility).

## 19.0.0.1.0 · 2026-10-30

- **The first picture loads at once** (owner, 2026-10-30: page speed plan, phase 4): on a page sent to an anonymous
  visitor, the first picture of the main area (a photo, or a section's background photo such as the homepage's
  hero) is preloaded with high priority in the page's head, and an `<img>` no longer waits as a lazy image. The
  header's pictures and every later one stay as they were; logged-in users (the editor) get the page untouched.
