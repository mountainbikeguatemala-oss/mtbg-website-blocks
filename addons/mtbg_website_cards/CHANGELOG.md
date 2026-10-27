# Changelog

Every version of this extension, newest first. Tags: `git tag -l 'mtbg_website_cards-*'`.

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
