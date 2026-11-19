# Changelog

## 19.0.1.0.0 (2026-11-19)
- New universal module (owner OK): the label printing first built in the bike shop core
  (bikeshop_shared_extensions 19.0.5.3.0) moves here so every site can print labels (the shop's products, the
  tours site's rental bikes). Settings › Label layout, the MakeID driver, Code 128, LabelPrintButton. Where the
  shop version is installed, the install hook takes over its records: the layout keeps its settings.
