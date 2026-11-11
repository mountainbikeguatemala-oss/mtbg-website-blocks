# Changelog

Every version of this extension, newest first. Tags: `git tag -l 'zoho_connector-*'`.

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
