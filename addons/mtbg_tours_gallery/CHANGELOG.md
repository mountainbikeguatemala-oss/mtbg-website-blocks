# Changelog

Every version of this extension, newest first. Tags: `git tag -l 'mtbg_tours_gallery-*'`.

## 19.0.0.6.1 (2026-11-11)

- **Fix: a full update from before 0.6.0 stopped.** A site going from before 0.6.0 straight to this release with a
  full update (`-u all`) reloads the Blog and the Catalog before Tours Website takes over the tours' gallery. Odoo
  still counted the post form's Gallery photos tab and the media form's focus point as this module's views, and
  checked them against fields that are only Tours Website's now: "Field mtbg_gallery_upload_ids does not exist". A
  pre-migrate now passes those two views to Tours Website as soon as this module loads, so Odoo skips them until Tours
  Website loads. The updater's changed-modules update already worked. Nothing else changes.

## 19.0.0.6.0 (2026-11-11)

- **Universal: from the Tours repository to Website Blocks** (owner, 2026-11-11, the split: "plain Odoo sites can
  use them"). Any Odoo website installs it with Website Blocks (mtbg_tours_content_blocks 0.11.1) alone; the technical
  name stays, so no data moves for the block; the updater takes its next versions from this repository
  (mtbg_github_source).
- What stays here: the Tiled Gallery block (pictures chosen in the editor), its layout, tiles and render route, the
  pictures' sizes, WebP copies and focus point (with its form widget), the page lightbox (now the base's shared
  viewer, @mtbg_tours_content_blocks/shared/lightbox) and the loading when the page scrolls near.
- **Record galleries from other modules**: `mtbg.gallery._mtbg_gallery_sources()` lists the kinds a block can show
  besides chosen pictures ({kind, model, domain, label, record_label, search_label, add, add_label, help});
  `_mtbg_record_items(kind, id)` gives a record's photos, `_mtbg_record_add(kind, id, pictures)` adds to them. The
  block options show one choice and a searchable picker per kind, "<kind>:page" being the record of the page holding
  the block (`data-mtbg-<kind>`, or the record whose HTML field is edited); routes `/mtbg_tours_gallery/sources` and
  `/mtbg_tours_gallery/record_add` (the old `tour_add` route goes).
- A page's own photos join the lightbox where the page names them: `data-mtbg-lightbox-photos` (a selector) on any
  element, `data-mtbg-lightbox-always` on a photo opened whatever its size (a tour's cover); no tour classes here.
- **Moved to Tours Website 0.10.49** (it takes the records over with their ids): the tours' gallery (the tour page
  element and its saved area, "A tour's gallery", adding to a tour's Media Library, the focus point on the Catalog's
  media form, the tour photos' sizes and copies) and the journal posts' Gallery photos (model mtbg.blog.post.photo,
  the post form's tab, the post page element). The 0.5.0 / 0.5.5 migrations go: a site below 0.5.5 updates through
  Tours' last Tiled Gallery release (0.5.9) first. Never beside a Tours Website older than 0.10.49 (the update stops
  before anything changes).
- Tests on a plain page with chosen pictures: tiles, the render route (public pictures only, unknown kinds), the
  sources route, no heading, WebP copies served, the lightbox (elsewhere, older browsers, a page's own photos, marked
  photo sets, a phone) and the loading when scrolled near.

## 19.0.0.5.9 · 2026-11-10

- **The gallery loads when the page nears it** (owner, 2026-11-10: "there is no reason to load the gallery until the
  page scrolls that far down"): a Tiled Gallery block fetched its tiles as soon as the page's scripts started; now it
  waits until it comes within about a screen of the view (on carmona-bike-park, 10,000px down on a phone: nothing
  fetched until then, 18 tiles once there). A tap on any photo first loads the galleries not reached yet, so the
  lightbox still opens with every photo of the page (cover tap: "1 / 10"). In the website editor the tiles come at once,
  as before.

## 19.0.0.5.8 · 2026-11-05

- **Gallery photos on journal posts** (owner, 2026-11-04): a post's "Gallery photos" tab takes several pictures at
  once (Add photos), dragged into order, each with a caption and alt text. The post page shows them with the Tiled
  Gallery (the block tour pages use: `post:<id>`), its WebP copies and the page lightbox (Core's shared viewer). The
  photos are made public, measured and their WebP copies made when added. The post page's element "Gallery" (Page
  Templates: "Blog post").

## 19.0.0.5.7 · 2026-11-03

- Spanish (bulk translation pass): the .pot regenerated from Odoo's export and es.po rebuilt from it; 6 strings no longer in the code removed. No English text changed.

## 19.0.0.5.6 · 2026-11-03

- **The gallery heading moves to the tour page** (owner, 2026-11-03: "we use tiled galleries inside other pages ...
  the header logic should live in the tours template not in the tiled gallery block"): the "<tour name> - Gallery"
  H2 is written by the tour page (Website 0.10.32, needed), before the gallery element; this extension no longer
  writes it (`_mtbg_gallery_heading` moved to Website). The Tiled Gallery block, on a tour page or any other page,
  has no heading of its own. The 0.5.5 clean-up of the saved static "Gallery" title stays.

## 19.0.0.5.5 · 2026-11-03

- **The gallery's heading is the tour's own** (owner, 2026-11-03: "the h2 before the gallery should be dynamic text
  {product title} - Gallery"): on every tour and rental page (all page templates) the gallery element writes an H2
  "Carmona Bike Park - Gallery" from the tour's name, in the page's language, above the gallery area; only when the
  tour has gallery photos (no heading for designers on a tour without photos). The static "Gallery" title block is
  gone from the area's default content, and the upgrade removes it from a gallery area saved in the website editor
  (only that title block; the rest of the area stays). The page keeps its one H1.

## 19.0.0.5.4 · 2026-11-03

- **The photo viewer is Core's** (Core 0.5.28, `@mtbg_tours_core/shared/lightbox`): the page lightbox keeps choosing
  which photos open and in which order (tiles, a tour page's photos, marked sets) and their captions; opening them,
  PhotoSwipe itself (moved to Core) and the viewer's styles are Core's. Nothing changes for visitors.

## 19.0.0.5.3 · 2026-11-03

- **Marked photo sets open in the page's lightbox** (owner, 2026-11-03: "the different gallery images in the hotel
  upgrade section should link to lightbox"): on any page, the photos inside an element marked `data-mtbg-photo-set`
  open in the same PhotoSwipe lightbox, as a set of their own (only that set's photos, "2 / 5"), starting at the one
  clicked, each at its `data-mtbg-full` picture (the page shows a smaller copy). An extension only marks its markup
  (Accommodations' hotel cards and hotel page photos); no lightbox of its own, no dependency. The photos show a
  zoom-in pointer. Nothing changes in the website editor (the lightbox does not run there).

## 19.0.0.5.2 · 2026-11-02

- Fix (www, 2026-11-02): the website editor could hang ("Edit" kept loading, nothing editable) on a page with this
  block: when the editor stopped the block while it was still loading (Edit clicked during the load), its start never
  finished and the editor waited for it forever (tour 238). A block stopped while loading now ends its wait (and
  doesn't draw); otherwise it loads and draws as before, in the editor too. Nothing else changes.

## 19.0.0.5.1 · 2026-10-25

- On Tours › Configuration › Extensions it shows in the **Custom blocks** section (with the other extensions
  whose main job is website editor blocks).

## 19.0.0.5.0 · 2026-10-25

- The tour page's Tiled Gallery area is a **page element** (`tour_el_gallery`, in place of Website's masonry
  gallery). Same output as before.
- Migration: the gallery area saved in the website editor (its title, corners...) moves onto the element view, under
  the key the editor saves it to next time. Then the old xpath view `tour_page_gallery` is removed. Ships with Website
  19.0.0.9.0.

## 19.0.0.4.2 · 2026-10-25

- The extension's icon is the Image gallery block's own icon in the website editor (the owner).

## 19.0.0.4.1 · 2026-10-24

- **The lightbox shows the photos on phones**: it opened black there (no photo, no buttons). Odoo's website
  stylesheet sets every section's height to automatic on phones, which collapsed PhotoSwipe's scroll layer.
- The lightbox opens on older phones too (iOS before 17.4, Chrome before 105): a tap on a gallery photo used to open
  the bare picture there (a browser feature the lightbox relied on is missing in those versions).
- Its own icon in the Extensions panel and the Updates page (the Tiled Gallery block's icon in the website editor), instead of a borrowed one.
- **Reversible: no data change.**

## 19.0.0.4.0 · 2026-10-23

- **One lightbox for the page's photos, built for phones** (PhotoSwipe 5.4.4, MIT, bundled in `static/lib`; loaded on
  the first touch of a photo): photos edge to edge, swipes that follow the finger, pinch and double-tap zoom, swipe
  down to close, caption and "3 / 15", full-size pictures. On a tour page it shows the cover, the description's and
  blocks' photos and every Tiled Gallery photo, in page order (it replaces Odoo's boxed lightbox there); elsewhere
  the page's Tiled Gallery photos. The gallery's own viewer is gone.
- **Reversible: no data change** (uninstalling brings the previous lightbox back).

## 19.0.0.3.0 · 2026-10-23

- Block options: **Photos** is "A tour's gallery" (then a **searchable tour** field; the page's own tour stays "this
  page's tour") or "Pictures I choose"; **Rounded corners** and **Spacing** in px (default 0 and 6). Corners chosen
  with the earlier presets are kept until changed.
- On a tour page the tiles open the **page's lightbox** (Booking Form 19.0.0.3.9): one lightbox for the cover, the
  description's photos and the gallery, full size. The gallery's own viewer remains for other pages.
- **Reversible: no data change.**

## 19.0.0.2.0 · 2026-10-23

- **Tiled Gallery block next to the GPX blocks** (inner content), so it is in the blocks list.
- **The tour page's gallery is a Tiled Gallery block**: click it in the editor for its options. It sits in an editable
  area shared by every tour page (a look set once for all tours), each page showing its own tour's photos; visitors
  see nothing on a tour without gallery photos.
- Block options: **Corners** (square, small, medium, large); **Photos** (this tour's gallery, another tour's, or
  pictures chosen here); **Add to the tour** (pictures from the media library join the tour's gallery in the Media
  Library) or **Add / Remove all** for chosen pictures.
- The tiles are fetched when the page loads (the block keeps only its settings), on the tour page too.
- The tour page keeps the line the Tour reviews block is placed by.
- **Reversible: no data change** (the shared area's edits stay in the website's page customisations).

## 19.0.0.1.0 · 2026-10-23

- **New extension: Tiled Gallery.** Photo galleries laid out like the old site's Jetpack Tiled Gallery
  ("rectangular"): rows of one big photo beside two stacked ones (the big one swapping sides), then pairs, every
  photo cropped to fill its tile.
  - Row heights and column widths kept within limits (the big photo takes 55-70 % of its row, a pair 40-60 %), so
    mixed portrait and landscape photos keep an even rhythm. Phones get simpler rows (one, a pair, one big + two).
  - Laid out on the server from the photos' stored sizes: nothing moves while they load.
  - **Focus point** per photo (Media Library: click the photo where the subject is): the tiles crop around it.
  - **Full-screen viewer**: arrows, arrow keys, swipe, Esc, caption, "3 of 15".
  - The **tour page gallery** is tiled (the tour's "In Gallery" photos, in order).
  - **Tiled Gallery** website block (Images group): a tour's gallery, or pictures chosen in the editor, on any page.
  - **WebP**: Odoo does not resize WebP, so the tiles use the pictures' screen-sized copies ("resize: 480 / 800 /
    1280", made by the migration, and by this extension when a photo is added and on install, marked as optimized
    copies so the media library hides them); the viewer opens the full-size original. JPEG and PNG are resized by
    Odoo.
- **Reversible: uninstalling brings the previous gallery back; the stored sizes, focus points and WebP copies stay
  on the pictures (unused).**
