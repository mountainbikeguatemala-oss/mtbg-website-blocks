# Changelog

## 19.0.1.4.0 (2026-11-19)
- A text's spacing (owner: "text should have padding settings to (top bottom only)"): Code, Name and Price get a
  top and a bottom spacing (mm), kept as set when the rest shrinks to fit.
- Fix: on a layout not saved from the editor yet, clicking an item now selects it (its ids are by place, the same on
  every read; before, the page could make new ones and the click found nothing).

## 19.0.1.3.0 (2026-11-19)
- Rows (owner: "we need to be able to put things in the same row so we need left right center per row"): the label
  is rows top to bottom, each with its Left, Center and Right; the items of one place stand side by side. Add, move
  up / down and remove rows; drag items between any row's places. 1.2.0's layouts (three regions) and older ones are
  read as rows: they print as before.
- The logo's spacing (owner: "set spacing around logo left right top bottom"): top, right, bottom and left, in mm.

## 19.0.1.2.0 (2026-11-19)
- A drag and drop editor on the Label layout page (owner: "the preview in the label settings is terrible it should
  update whenever you update on the page. and allow drag / drop", "make it a drag and drop field editor like our
  tour cards extension", "reorder the items"): the fields (Logo, Barcode, Code, Name, Price) dragged into the label's
  Left, Center or Right, dragged to reorder or move, clicked for their size, bold, lines, turn, or "on the same
  line" as the one before (Center). Saved as the layout's items (``elements``); a layout not edited yet is made
  from its settings, so it prints as before.
- The label above the editor is redrawn at once on every change on the page (the editor, the logo, the font, the
  sizes...), 3 × real size.

## 19.0.1.1.0 (2026-11-19)
- A logo on a layout (owner: "allow the template to include a small logo in our case its our crown"): left, right
  or above the rest, its size, a small rotation; printed in black and white.
- Font select (owner: "we need custom font select"): the fonts that come with Odoo (Roboto, Montserrat, Oswald,
  Lato, Raleway, Open Sans, Fira Mono, Khand, handwritten ones), loaded from the site; "My own font": a font file
  uploaded on the layout (e.g. one the business has a licence for).
- "Used for" (usage): each screen prints with its own layout (extensions add uses), else the first "Every screen".
- The code can go on the right of the barcode; a name shrinks before it is cut.
- Print label prints one label a press: no copies (owner: the printer does not cut labels).

## 19.0.1.0.0 (2026-11-19)
- New global module for the tours site and the bike shop (owner OK): Printer Connector, "because we'll use it for
  our other printers too" (owner). First printer: MakeID label printers over Web Bluetooth (from the bike shop core,
  bikeshop_shared_extensions 19.0.5.3.0, and the unreleased label_printer): Settings › Label layout, the MakeID
  driver, Code 128, LabelPrintButton. Where the shop version is installed, the install hook takes over its records:
  the layout keeps its settings (mtbg_takes_over declares the move to the updater). Declares its GitHub source
  (mtbg_github_source) so the updater offers it.
