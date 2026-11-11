# Changelog

Every version of this module, newest first. Tags: `git tag -l 'mtbg_backend_ui-*'`.

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
