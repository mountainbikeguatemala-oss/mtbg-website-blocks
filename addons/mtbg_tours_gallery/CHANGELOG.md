# Changelog

Every version of this extension, newest first. Tags: `git tag -l 'mtbg_tours_gallery-*'`.

## 19.0.0.6.9 (2026-11-21)

- **The photo gallery takes optional sizes and captions** (for Hotels and Accommodations 19.0.0.8.63's day galleries, owner 2026-11-21: "for multi-day in itinerary day-by day we should have the option to create a gallery for each day"). Additive: a photo of `gallery_photos` may also have `srcset` and `sizes` (the main photo's sizes: the browser picks its copy), `main` (a thumbnail's picture for the main photo's box, `data-mtbg-main`, already read since 19.0.0.6.7), `caption` (`data-mtbg-caption`: the lightbox shows it under the photo) and `width` (`data-mtbg-width`: the full picture's width, for the lightbox). A photo without them, and every gallery written so far (hotel sections, content blocks), is shown exactly as before.
- No new words.

## 19.0.0.6.7 (2026-11-20)

- **A thumbnail changes the main photo; the main photo opens the lightbox** (owner, 2026-11-20: "each small thumb should change the main photo above. and then clicking on the main photo launches the lightbox"). A tap on a thumbnail (a button: Enter or Space too) shows its photo in the main photo's box: the box keeps its size (nothing on the page moves), the picture is loaded before it shows (no blank box), the thumbnail shown is ringed (`mtbg-gallery__thumb--active`, `aria-pressed`). The main photo's picture for a thumbnail: its Odoo picture at the main photo's size (`/web/image/<id>/192x128` shows as `/web/image/<id>/512x341`), else the thumbnail's own picture when it is big enough (480 px or more, e.g. the hotels' 512 px photos), else its full picture; `data-mtbg-main` on a thumbnail's `img` names one. Tapping the ringed thumbnail again brings back the first photo. A tap on the main photo opens the page's lightbox at the photo it shows, with every photo of the gallery as one set (the ones beyond the grid too). The "+N" thumbnail opens the lightbox at its photo (it does not swap: "+N" means "see them all").
- **Thumbnails are `div`s** (the website editor merges identical neighbouring `span`s on save: a block's thumbnails ended up in one span; block 941 on www worked around it with `data-mtbg-thumb="1".."10"`). The template writes `div`s; the page still takes older blocks as they are: `span` thumbnails (with or without `data-mtbg-thumb`), a span holding several photos (split into one thumbnail each when the page loads, put back when the editor starts), a first thumbnail repeating the main photo (it is the first photo's button; the lightbox has each photo once).
- Everything the page's code adds (buttons, ring, "+N", split spans, the photo swapped in) is undone when the website editor starts: the block is saved as written. The page lightbox leaves `.mtbg-gallery` photos to the gallery's code.
- Hotels and Accommodations' night sections and upgrade slides (they call the template) get all of it with no change there.
- **Paste-ready markup for a content block** (one `div` per photo, any number; the sixth and on are hidden, the fifth gets "+N"):

```html
<div class="mtbg-gallery" data-mtbg-photo-set="iximche">
    <img class="mtbg-gallery__main" src="/web/image/101/512x341" data-mtbg-full="/web/image/101" alt="Iximché" loading="lazy" width="512" height="341"/>
    <div class="mtbg-gallery__thumbs">
        <div class="mtbg-gallery__thumb"><img src="/web/image/102/192x128" data-mtbg-full="/web/image/102" alt="Iximché" loading="lazy" width="96" height="64"/></div>
        <div class="mtbg-gallery__thumb"><img src="/web/image/103/192x128" data-mtbg-full="/web/image/103" alt="Iximché" loading="lazy" width="96" height="64"/></div>
        <div class="mtbg-gallery__thumb"><img src="/web/image/104/192x128" data-mtbg-full="/web/image/104" alt="Iximché" loading="lazy" width="96" height="64"/></div>
        <!-- one div per photo, as many as there are -->
    </div>
</div>
```

- Tests: a thumbnail shows its photo (the main photo's size kept, nothing moves, ringed, no lightbox), the main photo opens the lightbox at it (3 / 8, its full picture), Enter and Space, the ringed one brings back the first photo, "+N" at its photo (6 / 8); an older block (spans with `data-mtbg-thumb`, a merged span of 3, the first repeating the main photo: 8 thumbnails, "+4", each photo once: 3 / 8); the template's galleries the same (div thumbnails); a block with a gallery saved in the website editor (7 thumbnails stay 7 elements; nothing the page adds is saved; with spans the same test gives 1).
- New words (need Spanish): "Show photo %s", "Show all %s photos", "Open the photo full screen" (screen-reader labels).

## 19.0.0.6.5 (2026-11-20)

- **The photo gallery, for any page** (owner, 2026-11-20: content blocks such as "Iximché – Mayan Ruins (short)" use the same gallery as a tour's hotel section): moved here from Hotels and Accommodations (19.0.0.8.43's night gallery), its style and code in this extension's frontend assets (every website page). The main photo (3:2), the other photos in a grid of 5 under it that fits its width (never scrolled sideways); more than 5: the fifth says "+N" (the photos not seen), the rest are in the lightbox only. Every photo opens in the page's lightbox as one set (`data-mtbg-photo-set`), each at its `data-mtbg-full` picture when it names one (else its own).
- **For other modules**: `t-call="mtbg_tours_gallery.photo_gallery"` with `gallery_photos` (a list of `{'src', 'full', 'alt'}`, the first the main photo), `gallery_set` (the lightbox set's name), `gallery_alt` (when a photo has no alt). Lazy, every box sized before it loads.
- **In a content block** (the block's HTML, edited on the website): paste and change the pictures; list every thumbnail, any number: the sixth and on are hidden, the fifth gets "+N" when the page loads (`photo_gallery.js`; nothing is added to the saved block). One `data-mtbg-photo-set` name per gallery on a page (any word). Use `/web/image/<id>/512x341` for the main photo, `/web/image/<id>/192x128` for a thumbnail and `/web/image/<id>` for the full picture (from the media library: the picture's id):

```html
<div class="mtbg-gallery" data-mtbg-photo-set="iximche">
    <img class="mtbg-gallery__main" src="/web/image/101/512x341" data-mtbg-full="/web/image/101" alt="Iximché" loading="lazy" width="512" height="341"/>
    <div class="mtbg-gallery__thumbs">
        <span class="mtbg-gallery__thumb"><img src="/web/image/102/192x128" data-mtbg-full="/web/image/102" alt="Iximché" loading="lazy" width="96" height="64"/></span>
        <span class="mtbg-gallery__thumb"><img src="/web/image/103/192x128" data-mtbg-full="/web/image/103" alt="Iximché" loading="lazy" width="96" height="64"/></span>
        <span class="mtbg-gallery__thumb"><img src="/web/image/104/192x128" data-mtbg-full="/web/image/104" alt="Iximché" loading="lazy" width="96" height="64"/></span>
        <!-- one span per photo, as many as there are -->
    </div>
</div>
```

  The markup the template makes (also accepted by hand): `mtbg-gallery__thumb mtbg-gallery__thumb--more` with `data-more="+N"` on the fifth, and the photos beyond as `<img class="mtbg-gallery__hidden" ...>` inside `mtbg-gallery__thumbs`.
- Tests: the template (main photo, 5 thumbnails, "+3", 2 in the lightbox only, nothing without photos) and a block written by hand in the browser ("+3" on the fifth, the sixth not seen, no sideways scroll, the fifth opens the lightbox at 6 / 8, its full picture).
- No new words.

## 19.0.0.6.3 (2026-11-15)

- **Justified rows, bigger on phones** (owner, 2026-11-15: "tiles are too small and the gifs are still cropped heavily"): `justified()` now has three screens: phones (< 576 px) at most 2 a row, a landscape alone at full width, two portraits (or a portrait and a tall video) sharing a row, a lone portrait centred about 0.9 screen widths tall; tablets (576-991 px) at most 3 a row; desktops at most 4, rows about 320 px tall. Every photo keeps its exact shape (no crop but a few pixels at the gaps; no clamp any more). Layouts `.mtbg-tg-j-phone/-tablet/-desktop` inside `.mtbg-tg.mtbg-tg-justified`; narrow rows centred. The gallery block's own layouts are untouched.
- A site gallery's viewer keeps no Download and no video slides (test).

## 19.0.0.6.2 (2026-11-15)

- **Justified rows for other pages** (owner, 2026-11-15: the client photo album "should show the gifs scaled and
  cropped slightly to make justified grid. this should probably be part of the gallery extension itself"):
  `services.layout.justified(photos, screen)` lays out photos of known shapes (`ratio` = width / height) in rows of
  equal height, each at its own shape side by side (a crop only for extreme shapes: kept between 1:2 and 3.2:1), a
  short last row keeping its height. Phones: 2 or 3 a row, never one tile across the screen. Its rows use the Tiled
  Gallery's markup with the row class `mtbg-tg-just` (new CSS: the columns share the row by their shapes, the gaps
  included). The gallery block's own layout, look and lightbox are unchanged.

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
