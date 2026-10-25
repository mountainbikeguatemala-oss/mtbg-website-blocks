# Changelog

Every version of this extension, newest first. Tags: `git tag -l 'mtbg_tours_content_blocks-*'`.

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
