# Changelog

Every version of this extension, newest first. Tags: `git tag -l 'mtbg_tours_content_blocks-*'`.

## 19.0.0.11.2 (2026-11-11)

- Shared JavaScript for the website blocks: `@mtbg_tours_content_blocks/shared/chat` (the website chat hidden under a
  full-screen layer, as Tours Core's), for Forms now that it needs no Tours Core (owner, 2026-11-11). Nothing changes on
  a page.

## 19.0.0.11.1 (2026-11-11)

- **The website's shared photo viewer, from Tours Core** (owner, 2026-11-11, the split: the Tiled Gallery comes to this
  repository, and a plain Odoo website has no Tours Core): `@mtbg_tours_content_blocks/shared/lightbox` (PhotoSwipe 5,
  MIT, bundled in static/lib, loaded on the first photo opened; full screen, swipes, pinch and double-tap zoom, caption,
  "3 / 15"), unchanged; Tours Core 0.6.1 drops its copy and the Tours extensions that open photos (Itineraries, Reviews)
  use this one.

## 19.0.0.11.0 (2026-11-11)

- **The Menu Designer and the top bar icons, from Tours Core** (owner, 2026-11-11: a plain Odoo website installs them
  without Tours): Website › Configuration › Menu Designer (administrators), page /odoo/menu-designer. The admin's menus
  arranged for everyone (renamed, moved, ordered, hidden, removed, kept for some groups, folders and pages added), the
  presets (Odoo default; one's own saved; other modules' through `_mtbg_menu_presets()`, e.g. Tours' layouts) and the
  top bar icons' order and the company name switch.
- On a site that had it in Tours Core, its records change hands with their ids (both modules' pre-migrates, the first
  to run moves): the menu changes, the added folders and pages, the saved presets and the top bar settings stay.
  The settings are now `mtbg_tours_content_blocks.topbar_items` / `.topbar_company_name`.
- Update with Tours Core 0.6.0 in the same update: this version refuses to run beside a Tours Core that still has the
  designer (older than 0.6.0); the update stops before anything changes.

## 19.0.0.10.3 (2026-11-08)

- The Bullets block merged in (owner, 2026-11-08, the module clean-up): website editor › Text › Bullets, its options,
  and the old site's .highlights / .checkbullet / .xbullet list styles are part of the website blocks now. Where
  Bullets was installed its records are kept with their ids (the pack's own retire helper, tools/retire.py); the old
  extension is retired (uninstallable), nothing removed.

## 19.0.0.10.2 · 2026-11-05

- **Reusable blocks load fast: the list first, the cards after** (owner, 2026-11-04: "Reusable blocks take too long
  to load; we should load the list first (fast text), then have the card view (slow)"). Where the time went: every
  block counted its own uses with two text searches of all the website views and blocks, so a screen of 70 blocks ran
  ~150 queries and took over a second (the Blocks board, the Blocks list and the editor's picker alike). The uses are
  now counted for all the blocks at once (one search of the views, one of the blocks): ~1.1 s → ~20 ms.
- Website Blocks › Blocks opens on the **list** (plain text, at once); the board with its cards is the second view.
- The editor's **Reusable Block picker** opens at once with every block as text (name, type, tags, usage), usable
  right away: click to choose, search and filter by name, type and tag. Each card's preview (its text and a small
  picture) fills in as the card comes into view, a batch at a time, with a placeholder until then; the search then
  also matches the text.
- **Block Library**: the list shows at once as text; the excerpts, pictures and the Empty / Possible duplicates
  counts follow a moment later. The pictures load as they scroll into view.
- Pictures on the cards are small thumbnails (160×120, resized by the server) instead of the full photos (some
  1.6 MB); the browser keeps them, and a changed picture has a new address, so a card never shows an old one. The
  previews are worked out from the block's current content each time (no rendering, a few ms), so nothing is stale
  after an edit.

## 19.0.0.10.1 · 2026-11-03

- **Group is dragged straight from the Blocks panel** (owner, 2026-11-03: "I need access to it in the block editor
  drag and drop compose window for products"): a tile among the blocks under the categories, next to Reusable Block,
  so it goes into a tour's or rental's Description, a day's text, a reusable block or any page like the other
  blocks. Until now it was only inside the Content category's "Insert a block" window, as its last entry. It stays
  there too (Odoo lists Countdown and Map in both places as well). Its options (background, width, corners, shadow)
  work the same wherever it is dropped.

## 19.0.0.10.0 · 2026-10-26

- **Website Blocks**, the website blocks' own app menu (owner, 2026-10-26: out of Tours' Extensions page, into a
  left-hand menu of their own): **Blocks** (every reusable block as a board by type, and a list), **Block Library**
  (was Website › Content › Reusable Blocks), **Page Templates** (was Website › Content › Page Templates), the **Card
  Designer** (mtbg_website_cards) and **Extensions**: every website block module (its manifest says
  `'mtbg_tours_section': 'blocks'` or `'mtbg_website_blocks': True`), on or off, with its switch and its own page.
  Plain Odoo views; Tours gives them its look (mtbg_tours_page_templates).

## 19.0.0.9.0 · 2026-10-26

- **The website blocks pack's base** (repo mtbg-website-blocks): needs only Odoo's website now, so it runs on any
  Odoo website (Tours plugs its pages in with mtbg_tours_page_templates).
- The **reusable block model** (`mtbg.tours.content.block`) is this module's (until now Tours' Catalog's): same name,
  same rows; its list, form, search and action move here with their ids (pre-migrate 19.0.0.9.0), and the views
  this module drops are removed before the update.
- **Page templates for any kind of page**: a module gives its kinds of page (insert points, elements, sample pages)
  through the page kinds protocol (`_mtbg_page_kinds`, `_mtbg_page_slots`, `_mtbg_page_registry`,
  `_mtbg_page_samples`); a page renders `_mtbg_page_layout(kind)` (Desktop / Mobile, the editor's preview). The
  editor previews on the kind's sample pages.
- **Whole sections move** (owner, 2026-10-26): drag a section by its name (or its arrows) to reorder it within its
  area (the main column's, the full-width bottom's; the top and the booking column stay), Desktop and Mobile each
  their own order (`slot_order`; a layout is a `PageLayout` whose `order` gives the sections in page order).
- The editor's **Mobile** view is the page as a phone shows it: one phone-wide column, top to bottom. On Desktop,
  "Phones show this layout too" with an "Edit the Mobile layout" link (the earlier "no Mobile layout yet" read like
  an unsupported feature).
- Where a block is used: other modules add their records (`_mtbg_usage_records`); "Used On" counts them.
- Menus: Website › Content › Reusable Blocks and Page Templates; access for the website's designers and editors.
  Tours' boards, cards, Catalog menus and Tours groups: mtbg_tours_page_templates.

## 19.0.0.8.0 · 2026-10-26

- **Desktop and Mobile layouts** for every page template: the editor's Desktop / Mobile switch (the same as the
  preview's device) picks the layout you edit. Mobile starts as a copy of Desktop and follows it until you change
  it; "Use the Desktop layout on phones" drops it again. Phones (their browser says "Mobi") get the Mobile layout
  when the template has one, every other screen the Desktop one. Template lines: new field `layout`.

## 19.0.0.7.0 · 2026-10-26

- **The page template editor** (Catalog › Page Templates; Page templates phase 2), in two halves. On the left, the
  page outline with its insert points, laid out like the page (top, the top section's two columns, the main column,
  the full-width bands). Each insert point's **Add…** list offers what the page does not show yet (the elements left
  out, the reusable blocks not used), so it shrinks as things are placed; drag a placed element (or its arrows) to
  move it, the eye leaves it out (it is offered again). Templates are picked, created, duplicated, renamed, archived
  and made Default in the top bar; the list is a click away, and a template's form has "Open in the editor".
- On the right, the **preview**, as tall as the screen: a sample page of the template's kind with the unsaved changes
  (only to the person editing: ?mtbg_template_preview, website designers), on a desktop or a phone, in each language;
  the site keeps the saved page until Save. A narrow window shows it under the outline.
- Stats & ratings is one element there (its two parts are added, moved and left out together); its cog opens the Tour Stats settings.
- Spanish for the Reusable Blocks page's texts too (they were missing).

## 19.0.0.6.0 · 2026-10-25

- **Reusable blocks inside reusable blocks** (content and background apart, e.g. a background block holding "The MTB
  Guatemala Difference"): a block placed in another block's content is filled in turn, up to five deep, and is in the
  page's HTML for visitors and search engines; dynamic slots fill at every level. A block met again inside itself
  (A in B in A) shows once, then stops; the editor marks the spot.
- Editor: a Reusable Block can be dropped inside a block opened with "Edit in place"; saving keeps the inner one as
  its placeholder (only its id), and it shows locked with its name. Choosing a block that already contains this
  place is refused.
- Reusable Blocks page: "Used on" counts the other blocks that contain a block (also in the editor's label); the
  preview shows the blocks inside; archiving a block that other blocks contain asks first, and deleting it is
  refused (as for pages).

## 19.0.0.5.1 · 2026-10-25

- On Tours › Configuration › Extensions it shows in the **Custom blocks** section (with the other extensions
  whose main job is website editor blocks).

## 19.0.0.5.0 · 2026-10-25

- **Page templates** (Catalog › Page Templates): named layouts of the tour page, one kind for tour pages and one for
  bike rental pages. Duplicate, archive, and make one the Default of its kind. Each line places an element (from any
  installed extension) or a reusable block in an insert point; switch a line off to leave the element out (the
  template remembers it). Elements of extensions installed later show at their usual place.
- The **Default templates** (Tour page, Rental page) are the page as it has always been. They are made on install and
  by this update, once every module is loaded.
- The visual editor, conditions and category assignments come next (docs/architecture/page-templates.md).

## 19.0.0.4.0 · 2026-10-22

- **Reusable Blocks page** (the extension's tile; Catalog › Reusable Blocks): every block in one place.
  - Filters: all, not used anywhere, empty, possible duplicates (same name or content), no tag, archived; by type
    and by tag. Search name, text and tags; sort A–Z, last edited or most used.
  - **Tags** (new): create, rename, recolour and remove them in the left column; drag blocks onto a tag to tag them.
  - Several blocks at once: add or remove a tag, set the type, duplicate, archive, restore, delete (unused only).
  - The selected block: name, type, tags and an **internal note** (new), saved as you change them; where it is used
    (tours, website pages, templates, other blocks) with links; a live preview on a light or dark tour page,
    desktop or phone; **Edit in Website Builder** for the content, whose page links back here.
- The website editor's block picker filters by tag and shows each block's tags.
- **Reversible: no data change** (new tag table, block fields Tags and Internal Note).

## 19.0.0.3.1 · 2026-10-21

- New app icon (Extensions panel).
- **Reversible: no data change.**

## 19.0.0.3.0 · 2026-10-20

- 2027 site V1: MTBG Tours suite archive point
