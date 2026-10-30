# Changelog

Every version of this extension, newest first. Tags: `git tag -l 'mtbg_website_cards-*'`.

## 19.0.0.4.0 · 2026-10-30

- **One card system, one slider for the website** (owner, 2026-10-29: "put everything in one module with the same
  settings and template system"; "Sliding is sliding and cards are cards. Then we interperate them with different
  designs on top"): the one slider (`mtbg_website_cards.slider`, slider.js: how many at once by its own width, arrows,
  autoplay, loop, stacked on narrow screens) draws every sliding row of cards; layouts Grid, Slider, Masonry wall and
  One under another.
- **Card Uses** (Website Blocks › Card Uses): each place of the website that shows cards, its design and layout (how
  many side by side on desktop, tablet and phone, gap, arrows, autoplay); extensions bring their places as data.
- **Card Settings** (Website Blocks › Card Settings): the Book button of every card: its words (EN/ES), icon, colours
  (the design's accent, the theme's Primary or Secondary button, or its own), size, shape, full width, capitals.
- **Card Designer**:
  - a design's frame (card, none, speech bubble), words left or centred, photo size (or no photo);
  - per field: Max words (then "…"), Lines with Read more, text size and line height (down / up buttons), bold and
    upper case toggles; the tour name's heading level (H3, H4, H5); icons only for stats fields;
  - the ratings: icon size, spacing, up / down, optional labels (above their icons, with the same text controls);
    each icon in a box of the same width, the rows lined up;
  - **Ribbons**: their own section in the card; corner, top and badge ribbons in many styles (diagonal, triangle,
    tab, circle, flag, pill, tag, 3D ribbons, seal and folds, ribbon shapes after css-generators.com), their side and
    colours; set only in that section;
  - new field kinds: compare box, avatar, photos, logo; fields on one line ("Same line") and Bold;
  - fields in the photo's centre in white, readable on the photo;
  - dark admin: the plan's photo areas and the drop-down lists in the page's colours;
  - fix: number settings no longer fail ("v34 is not a function").

## 19.0.0.3.0 · 2026-10-29

- **Layout: Grid or Slider** (owner, 2026-10-29): a slider shows the same cards (designs, fields, filters) in one row,
  as many at once as its Columns (two on tablets, most of one on phones with the next one peeking), scrolled
  sideways and snapping to a card; arrows on desktop (gone at either end and on touch screens), a swipe on phones.
  The mega menu's Image Cards (slider) look. Block option Layout (`data-layout="slider"`).
- **Short descriptions at most 3 lines** with "…" in every card design (rental cards grew very tall).
- **Fix: the block's options open again when its source has card designs** (the Design list called `String()` in
  its template: "ctx.String is not a function", the options panel failed).

## 19.0.0.2.0 · 2026-10-26

- **Regions** (owner, 2026-10-26: "like our current confirmed departure cards"): a card is its **Header** (above
  it, no colour), its photo's **Top strip**, **Center** and **Bottom strip** (each shown always or on hover; the
  strips coloured, the bottom one also as a shade), **Below** and its **Footer line** (fields side by side, e.g.
  the price and Book). The early bird turns its strip yellow.
- **Fields go anywhere**: drag a field from the list into any region, drag placed fields between regions or within
  one, place a field more than once (e.g. the price as the center pill and in the footer). Each placed field has
  its **look** (plain, pill, button, bar), its **words** (empty: the field; or words with fields in them, e.g.
  "Book (from {price})"), its **icon**, and on the photo **when it shows** (like its region, always, on hover).
- Every source has a **Book button** (a link to the record).
- The preview can **show the hover** state; the designs of 19.0.0.1.x become regions as they are read.
- A field's value may carry another module's classes and data, so its scripts keep working on the cards (e.g.
  Tours: the price's currency, the early bird countdown); the Cards block starts them on its cards.

## 19.0.0.1.1 · 2026-10-26

- The Card Designer is on the website blocks' own menu: **Website Blocks › Card Designer** (was Website › Content ›
  Card Designs). Needs Reusable Blocks 19.0.0.10.0 (the menu's base).

## 19.0.0.1.0 · 2026-10-26

- **Card Designer** (Website › Content › Card Designs): card designs made visually, each for a source of records a
  module gives (card sources protocol). Style (text below, over or above the photo), photo frame, corners, shadow;
  the source's fields in order (drag and drop), each on the photo (top left, top right, bottom), in the text or
  hidden; hover (zoom, darken the photo); colours for light and for dark pages (the preview's switch); a live
  preview on real records, computer or phone.
- **Cards** building block: a source's records (its filters, how many, 2-4 columns) in a design; booking countdowns
  tick on the visitor's clock.
