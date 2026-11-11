{
    'name': 'MTBG — Admin Look',
    'version': '19.0.0.1.0',
    # where the updater gets it (the universal repo; owner, 2026-11-11: the one admin module, from Tours Core 0.7.0)
    'mtbg_github_source': {'repo': 'git@github.com:mountainbikeguatemala-oss/mtbg-website-blocks.git', 'subdir': 'addons'},
    'category': 'Productivity',
    'summary': 'One admin look for every module: lists with a side bar and a column picker, boards, record cards, '
               'a settings page per model, dark mode, saved screen choices and translated text settings',
    'description': """
The admin's shared screens, for any Odoo database (no website needed; Tours Core and the universal modules use it):

* Lists with a side bar (``mtbg.sidebar.mixin``, ``js_class="mtbg_sidebar_list"``): the model's records as a tree with
  their counts, every field in the column picker, a search per column.
* Boards (``mtbg.board.mixin``, ``js_class="mtbg_board_kanban"``): a kanban laid out by the board chosen above it
  (columns, order, a total per column), folds, colours per stage, "Things missing" and "Time to start" columns.
* Record cards (``mtbg.card.mixin``): one card per model, drawn the same everywhere; its look set in the card editor.
* The settings page (the lists' and boards' cog): the card, the boards, the modules' own tabs, Import / Export.
* Dark mode for the whole admin (the user menu's switch).
* Each user's screen choices kept on the server (columns picked, folds), on every browser and device.
* Translated text settings (a system parameter per language) with their editor widget.

Who may change boards, cards, settings pages and texts: administrators (a suite may set its own managers).
""",
    'author': 'MTBG Tours contributors',
    'license': 'LGPL-3',
    'depends': ['web', 'html_editor'],
    'data': [
        'security/ir.model.access.csv',
    ],
    'assets': {
        'web.assets_backend': [
            # each user's screen choices on the server (columns picked, folds): shared by every page
            'mtbg_backend_ui/static/src/user_prefs/*',
            'mtbg_backend_ui/static/src/text_setting/*',
            'mtbg_backend_ui/static/src/record_card/*',
            'mtbg_backend_ui/static/src/choice_buttons/*',
            'mtbg_backend_ui/static/src/card_editor/*',
            'mtbg_backend_ui/static/src/dark/color_scheme.js',
            'mtbg_backend_ui/static/src/view_modes/*',
            'mtbg_backend_ui/static/src/board_kanban/*',
            'mtbg_backend_ui/static/src/model_settings/*',
            'mtbg_backend_ui/static/src/sidebar_list/*',
            'mtbg_backend_ui/static/src/list_column_search/*',
            'mtbg_backend_ui/static/src/board_badge/*',
            'mtbg_backend_ui/static/src/board_statusbar/*',
            'mtbg_backend_ui/static/src/data_transfer/*',
        ],
        # the admin in dark (the user menu's switch): the palette turned over, in Odoo's dark bundles only
        'web.assets_web_dark': [
            ('before', 'web/static/src/scss/primary_variables.scss',
             'mtbg_backend_ui/static/src/dark/primary_variables.dark.scss'),
            'mtbg_backend_ui/static/src/dark/admin.dark.scss',
        ],
        'web.assets_backend_lazy_dark': [
            ('before', 'web/static/src/scss/primary_variables.scss',
             'mtbg_backend_ui/static/src/dark/primary_variables.dark.scss'),
        ],
    },
    # the installed modules whose models / xml ids it takes over (its pre_init_hook moves them; the updater checks it)
    'mtbg_takes_over': ['mtbg_tours_core'],
    'pre_init_hook': 'pre_init_hook',
    'installable': True,
}
