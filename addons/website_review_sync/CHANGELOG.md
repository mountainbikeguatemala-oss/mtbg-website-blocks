# Changelog

Every version of this extension, newest first. Tags: `git tag -l 'website_review_sync-*'`.

## 19.0.0.4.3 · 2026-11-04

- **The Reviews blocks' and the Counter's code load on the pages that have one only** (owner, 2026-11-04, JS consolidation part B): the slider, wall, preset and counter scripts and the Reviews styles moved out of every page's bundle into `website_review_sync.assets_reviews`, loaded with its styles by a ~1 KB loader (`js/review_assets.js`) on a page with a Reviews block or a counted number (the blocks draw themselves from the server, so nothing shows unstyled); the Reviews page's preview has the styles in its head. The website editor has the code and styles from the start (`website.assets_inside_builder_iframe`), so a block dropped on any page works. The Counter's own styles stay on every page. About 25 KB of script and 18 KB of styles off pages without reviews.

## 19.0.0.4.2 · 2026-11-03

- Spanish (bulk translation pass): the .pot regenerated from Odoo's export and es.po rebuilt from it; 4 new Spanish translations; 3 strings added to the .pot that were missing (they never loaded). No English text changed.

## 19.0.0.4.1 · 2026-11-03

- **Alt text on the review cards' pictures** (owner, 2026-11-03: "Alt text for every image on the page"): the
  reviewer's photo is named after the reviewer, a review's photos "Photo from <name>'s review", and the lightbox keeps
  those names. Every Reviews slider and wall had them alt="" (about 50 per page with reviews on www).

## 19.0.0.4.0 · 2026-10-26

- **Counter** block (Reviews group of the Blocks panel): numbers that count up from 0 once scrolled into view, with
  a label each. Each number's options: the number, text before and after it, decimals, how long it counts and its
  speed (the Reviews blocks' curves). Any element marked `data-mtbg-count` (with -prefix, -suffix, -decimals,
  data-count-ms, data-count-ease) counts the same way, e.g. a number in a tour's description. The page keeps the
  final value as its text. Sizes: the theme's headings.
- The count-up moved to a shared helper (`static/src/js/count_up.js`), used by the Reviews totals and the Counter.

## 19.0.0.3.0 · 2026-10-26

- Reviews page › a preset's card parts, speech bubbles: **two dividers, Bubble starts and Bubble ends**. Drag the
  parts between them to put them in the bubble, above them to show them over the bubble, below them to show them
  under it (any part: the reviewer, the stars, the link...). Saved presets keep their look (the dividers go where
  the bubble was). Cards don't use them.
- **Date only**: a card part of its own (hidden until switched on), to place anywhere; while it shows, the
  reviewer's line leaves its date out.

## 19.0.0.2.2 · 2026-10-25

- On Tours › Configuration › Extensions it shows in the **Custom blocks** section (with the other extensions
  whose main job is website editor blocks).

## 19.0.0.2.1 · 2026-10-24

- Its scheduled job is kept as the site set it: an upgrade no longer switches a paused job back on (noupdate).
- **Reversible: no data change.**

## 19.0.0.2.0 · 2026-10-22

- **Reviews page** (this extension's tile in Tours › Configuration › Extensions), with tabs:
  - **Presets**: pick one from a dropdown (New starts a copy), then edit it in three steps: 1 Sources, 2 Design, 3 Content and layout; the Reviews blocks' looks, with a live preview (desktop / phone, unsaved changes included). Per preset: speech bubbles or cards, bubble tail (left, centre, right, none), corners, shadow; light, dark or website colours plus your own colours (background, text, bubble, bubble text, stars, links); which reviews (platform, several sources, minimum rating, order, how many, this page's only, autoplay, arrows); the block's parts (heading, five-star total, reviews, button / filters) and a review's parts (stars, title, text, photos, link, reviewer) in order by drag and drop (or the arrow keys), each shown or hidden; texts in every language of the website; width, corners and spacing. New presets start as a copy; the five built-in ones cannot be deleted.
  - The preview shows only the block on a little of the page's background (no website header); its bar has the language (also of the texts edited), the currency, a light / dark page (the site's dark page look) and desktop / phone.
  - **Reviews**: the reviews table (search, source, rating, on website / hidden / featured / with photos), on website and featured switched in place, open one to edit it.
  - **Sources** and **Accounts** (administrators): sync now, open, add.
- In the Layout list, each part's settings sit under its row: the heading's text; the stars as a part of their own (one banner when next to the total); the five-star total's label, stacked or one line, and its count-up (time, and a speed curve: steady, smooth, slow finish, crawl to the top, logarithmic); the reviews' arrows (beside the reviews, never over them) and autoplay; the reviewer's platform logo (beside the reviewer, top right of the bubble, hidden); the button's text, link, solid or outline, size (small, medium, large) and own colours.
- The Reviews blocks are linked to a preset: a block on a page only names its preset (`data-preset`) and is drawn from it on each visit, so changing a preset changes every block using it. In the website editor, a block's options choose its preset. The five blocks of the Reviews list are now the five built-in presets (Speech bubbles, Cards, Dark, Website colours, Reviews wall), set up as they were.
- Blocks placed before this version keep their own content and options, and work as before.
- The Website › Configuration › Reviews menus are gone: everything is on the Reviews page.
- Spanish translations of everything new.

## 19.0.0.1.1 · 2026-10-21

- New app icon (Extensions panel).
- **Reversible: no data change.**

## 19.0.0.1.0 · 2026-10-20

- 2027 site V1: MTBG Tours suite archive point
