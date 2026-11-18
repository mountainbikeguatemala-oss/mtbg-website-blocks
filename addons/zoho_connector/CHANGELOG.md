# Changelog

Every version of this extension, newest first. Tags: `git tag -l 'zoho_connector-*'`.

## 19.0.0.2.0 · 2026-11-18
- **Zoho Books expenses and vendors come here** (owner, 2026-11-18: "zoho connector should be global"), from the
  Tours' Zoho extension (0.5.2), under the same model and record names, so any site can use them without the Tours:
  - Import & Sync from Zoho Books: the Expense Categories (`mtbg.zoho.books.account`), a run
    (`mtbg.zoho.books.import`: the first sync, then every hour the changes) and its review list
    (`mtbg.zoho.books.review`), their pages, the two jobs and the block in Settings › Zoho. Extensions still bring the
    destinations (`_mtbg_destinations`, `_mtbg_suggest`, `_mtbg_import_line`, `_mtbg_apply_review`); without any, a
    category is skipped or counted as internal. Who may run it: the Zoho managers (`_mtbg_zoho_manager`:
    administrators, and each extension's own).
  - A vendor contact's Zoho Books vendor (`mtbg_zoho_vendor_id` and its sync fields on the contact),
    `_mtbg_zoho_vendor_ensure` and `_mtbg_zoho_push_vendors`. Which contacts are vendors: an extension's
    `mtbg_is_vendor` tick (a soft check); the jobs that push them: `_mtbg_zoho_vendor_crons` (extensions give theirs).
- **Nothing lost on an update**: a pre-migration (and the install hook) hands over the xml ids, the table constraints
  and the many2many table before this version loads: every table, row, setting, job and its state stays as it is,
  nothing is created twice, deleted or sent. The parameter names stay (`mtbg_tours.zoho_*`).
- Strings moved from the Tours' Zoho extension are English only here for now (its Spanish stays there).

## 19.0.0.1.0 · 2026-11-11
- **The Zoho connection, an extension of its own** (owner, 2026-11-11: the extensions split into their own releases;
  "authorized zoho connector"): taken over from the Tours' Zoho extension (0.4.7), which keeps the tours' Zoho Books
  work. Needs only Odoo: one login and the setup wizard, a switch per app (Books, Expense, Shifts), the client (paced,
  retried, logged), the references (`mtbg.zoho.ref`), the sync log (`mtbg.zoho.log`), the access token
  (`mtbg.zoho.token`), Settings › Zoho with its cards.
- Extensions plug in without the connector knowing them: their Zoho Books step in the wizard (`_mtbg_books_step`,
  `_mtbg_books_choices`, `_mtbg_books_finish`), their cards (`_mtbg_card_defaults`, glue module patterns, a glue's
  `zoho_connector_card`; `mtbg_tours_zoho_card` read too), the retry of their references (`_mtbg_retry`), who may
  retry (`_mtbg_zoho_manager`).
- On a site with the Tours' Zoho extension: its records are taken over under the same names (pre_init hook, xml ids
  moved, nothing created twice or deleted), the tables, rows, login and token stay as they are
  (`mtbg_takes_over`). The parameter names stay (`mtbg_tours.zoho_*`).
