# Changelog

Every version of this module, newest first. Tags: `git tag -l 'mtbg_backend_ui-*'`.

## 19.0.0.3.1 (2026-11-23)

- **A page opened on one board** (owner, 2026-11-23: menus "Leads Pipeline" and "Leads to be Contacted"): an action's
  context `mtbg_open_board` (a board's XML id, one of the page's boards) opens the board kanban on that board every
  time (`mtbg_board_settings()['open_board']`). Another board can still be picked there for the visit; nothing is kept
  in the browser, so the model's own page still opens on the viewer's board. Without the key: as before.

## 19.0.0.3.0 (2026-11-20)

- **The one expense form is here** (owner, 2026-11-20: the shop site records a used purchase "all in one go" with "the
  same expense form that we created for [the tours site] in the staff app"; the shop site has no Tours): the
  ``MtbgExpenseForm`` component (``static/src/expense_form``, templates ``mtbg_backend_ui.ExpenseForm*``, the client
  action ``mtbg_expense_form``) and its server side ``mtbg.expense.form`` (targets, the four standard fields, the vendor
  picker) moved from Tours Core 0.9.3, unchanged; Core's paths re-export them. Its Spanish came along.
- **Expenses without Tours** (``models/expense.py``): ``res.partner.mtbg_is_vendor`` (the vendor list; Tours Core has
  the same field), **Expense Categories** (``mtbg.expense.category``) and **Expense Payment Methods**
  (``mtbg.expense.method``, an optional currency it only pays in), each with *Offered in the form*; and the mixin
  ``mtbg.expense.source`` (date, description, amount and currency, category, paid with, vendor, receipt, recorded by)
  for a model whose records are expenses: ``_mtbg_expense_changed(deleted=False)`` after a create, a change of the
  expense's fields and before a delete, ``_mtbg_expense_reference()`` (``ODOO-<MODEL>-<id>``),
  ``_mtbg_expense_description()``, and the connector's status (``expense_sync_state`` / ``_error`` / ``_url``, Send
  again, Open). The receipt file belongs to its expense. A connector sends them (Zoho Connector 0.3.0); the lists' menus
  come from the module that records expenses.

## 19.0.0.2.1 (2026-11-18)

- **Every calendar's Day and Week view zooms sideways** (owner, 2026-11-18: "Calendar week view should allow
  horizontal pinch zoom across the entire suite of extensions"): a two-finger pinch widens or narrows the day columns,
  from the screen's width (Odoo's look, the smallest) to about one day per screen; the grid then scrolls sideways with
  its day header, the hours column stays pinned on the left, the time scale is unchanged. On a computer: Ctrl + wheel
  or a trackpad pinch. One-finger swipes scroll the columns while there is room; at either end they change the week as
  before (Odoo's swipe). The zoom is kept per model and view (day / week) on each device (local storage; nothing kept
  when it is blocked); a calendar opened zoomed shows today's column. Month and Year unchanged.
- How: a patch of Odoo's ``CalendarCommonRenderer`` (``static/src/calendar_zoom/``), so every calendar built on it gets
  it: Odoo's calendar view for any model, Tours Core's operations and panel calendars, Marketing's Autopost calendar.
  FullCalendar's own column width (``dayMinWidth``) needs its paid scroll grid, so the view harness is made wider
  (``--mtbg-cal-zoom``) and FullCalendar lays itself out for that width. Colours from the page's background, so light
  and dark.
- Test: hoot unit tests (``static/tests/calendar_zoom.test.js``, run by ``TestCalendarZoomJs``): the zoom's
  arithmetic, storage (also blocked), Ctrl + wheel, a two-finger pinch that does not reach the week swipe, the zoom kept
  on reopening, Month untouched.

## 19.0.0.2.0 (2026-11-16)

- **The admin on a phone** (owner, 2026-11-16: "All these fields should be larger and more mobile friendly across
  Odoo on mobile"): one stylesheet (``static/src/mobile/mobile_fields.scss``, in ``web.assets_backend``, so in the dark
  bundle too) for screens below 768px wide. Form and dialog fields (text, number, monetary, date, many2one with its
  buttons, selection, text areas, file name and buttons, and Bootstrap's ``form-control`` / ``form-select`` on the
  suite's own pages and dialogs) at least 48px high with 16px text (no iOS zoom); labels at 16px; checkboxes and
  radios 24px; the form's status bar and sheet buttons, the control panel's buttons, list and board record buttons and
  every dialog button 48px; the autocomplete list's rows 44px; dialogs the full width with their buttons in a sticky
  footer (above the phone's home bar). Sizes only, the theme's colours, so light and dark both follow. Desktop
  unchanged. Not in the Staff App (``mtbg_sa``) nor in a dialog opened while it is on screen.
- Test: a browser tour opens a contact's form in a dialog at 390px (light and dark: input 44px+ high, 16px+ text,
  the dialog button 44px+, sticky footer, nothing while the Staff App is on screen) and at 1366px (Odoo's size).

## 19.0.0.1.0 (2026-11-11)

- **New: the admin look, from Tours Core 0.7.0** (owner, 2026-11-11: one universal admin module, the approved exception
  to "no new modules"; it needs only Odoo's web client, no website and no Tours): lists with a side bar and a column
  picker (``mtbg.sidebar.mixin``), boards (``mtbg.board``, ``mtbg.board.mixin``: Things missing, Time to start),
  record cards and their editor (``mtbg.card.mixin``), the settings page behind the cog with Import / Export
  (``mtbg.data.transfer``), dark mode, each user's saved screen choices (``mtbg.user.pref``), the translated text
  settings (``mtbg.text.setting``, ``ir.config_parameter.mtbg_get_text``, their widget) and the settings pages'
  switches and long texts (``res.config.settings._mtbg_switch_parameters`` / ``_mtbg_text_parameters``).
- Names kept from Core: models, xml ids, registry keys, js_class and widget names, template names, saved-choice keys.
- On a site with Tours Core its records change hands with their ids before this module loads (pre_init_hook; Core
  0.7.0's pre-migrate does the same if it runs first). Never beside an older Core: the update stops first.
- Who may change boards, cards, settings pages and texts: administrators (``res.users._mtbg_ui_manager``); Tours Core
  keeps its managers.
