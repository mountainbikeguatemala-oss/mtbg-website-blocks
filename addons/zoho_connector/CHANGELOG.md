# Changelog

Every version of this extension, newest first. Tags: `git tag -l 'zoho_connector-*'`.

## 19.0.0.3.1 · 2026-11-20
- **Zoho through a linked site** (owner, 2026-11-20: one Self Client for both sites): where Site Link Connector's
  link to another site ticks **Use its Zoho login** (a soft check, no dependency), this site needs no Zoho login of
  its own: every Zoho Books call goes to that site (`zoho_request`, Site Link Connector 0.2.6), which makes it with its
  login and its organization. Here still decide: Zoho Books On and Writes allowed (a write with Writes allowed off is
  never sent); there its Writes allowed applies too. Settings › Zoho says it is connected through that site. Files
  (an expense's receipt download for Import & Sync) and the organization list are not read through a link.

## 19.0.0.3.0 · 2026-11-20
- **Expenses recorded in Odoo go to Zoho Books** (owner, 2026-11-20: the shop's used purchases, "record it as an
  expense in zoho books"; the rule that every Odoo expense is in Zoho Books): any model with Admin Look's expense
  mixin (``mtbg.expense.source``, now a dependency) is a Zoho Books expense once its save is committed: its category's
  account, its payment method's paid through account, its vendor contact as the Zoho vendor (found by name, else
  made), its receipt attached, its currency at Zoho Books' rate (Odoo's when Zoho has none) unless it is Zoho's base,
  described with what it is and who recorded it, its reference ``ODOO-<MODEL>-<id>`` (the marker a retry finds it by:
  never twice). A change updates it, a deletion deletes it. A category or method without an account, or a refusal:
  Error on the record with the reason, tried again every hour (the job "Zoho Books: expenses recorded in Odoo", also
  run right after each save); Writes allowed off: Waiting. The job pushes the waiting vendor contacts first.
- **Sync from Zoho Books** on Expense Categories (Zoho's expense, cost of goods sold and other expense accounts) and
  Expense Payment Methods (its bank, cash, card and clearing accounts, with their currency): new ones come in
  unticked, for a manager to offer in the form; a known one keeps its name here.
- Reference kind ``expense_out`` (Open in Zoho goes to the expense); Import & Sync never brings these back in.

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
