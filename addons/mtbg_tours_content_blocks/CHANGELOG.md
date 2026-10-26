# Changelog

Every version of this extension, newest first. Tags: `git tag -l 'mtbg_tours_content_blocks-*'`.

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
