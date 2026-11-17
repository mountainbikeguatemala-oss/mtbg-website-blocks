# Changelog

Every version of this module, newest first. Tags: `git tag -l 'mtbg_backend_ui-*'`.

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
