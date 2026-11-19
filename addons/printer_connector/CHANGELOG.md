# Changelog

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
