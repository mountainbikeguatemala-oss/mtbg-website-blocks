# Changelog

Every version of this extension, newest first. Tags: `git tag -l 'website_review_sync-*'`.

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
