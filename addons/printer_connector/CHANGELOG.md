# Changelog

## 19.0.1.0.0 (2026-11-19)
- New global module for the tours site and the bike shop (owner OK): Printer Connector, "because we'll use it for
  our other printers too" (owner). First printer: MakeID label printers over Web Bluetooth (from the bike shop core,
  bikeshop_shared_extensions 19.0.5.3.0, and the unreleased label_printer): Settings › Label layout, the MakeID
  driver, Code 128, LabelPrintButton. Where the shop version is installed, the install hook takes over its records:
  the layout keeps its settings (mtbg_takes_over declares the move to the updater). Declares its GitHub source
  (mtbg_github_source) so the updater offers it.
