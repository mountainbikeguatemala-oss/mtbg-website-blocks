{
    'name': 'MTBG — Contact Rules',
    'version': '19.0.0.3.0',
    # where the updater gets it (the universal repo; owner, 2026-11-18: contact rules go global, from the Tours repo)
    'mtbg_github_source': {'repo': 'git@github.com:mountainbikeguatemala-oss/mtbg-website-blocks.git', 'subdir': 'addons'},
    'category': 'Productivity',
    'summary': 'Stock contact helpers that keep contacts tidy on their own (country and state from the phone, '
               'possible duplicates, language from the country), on their own page (with Tours: Rules & Alerts), '
               'logged with undo',
    'description': """
The Contact rules (named CRM Rules before 0.2.0; the technical name stays): stock helpers, each off until switched
on, on their own page (Contact Rules: its Contact rules tab, its Changes tab). Each runs when a record is created or changes, when a message comes in, or every day,
with its own logic; a dry run shows what it would change; every change is logged and can be undone.

* Country and state from the phone (a contact's number; a US / Canadian area code gives the state)
* Country and state from a message's number (when a message comes in: the channels queue it)
* Possible duplicates by phone or email (flagged on Possible Duplicates; never merged)
* Spanish for Spanish-speaking countries
* Extensions bring their own helpers with ``_mtbg_crm_rule_sources()`` on their own model, like the Alert Feed's sources

Needs only Odoo and the admin look (0.3.0, owner 2026-11-18: in the universal repository, no Tours). Who may change
the rules: the admin look's managers (administrators; with Tours, its managers). With Tours, the Alert Feed brings the
Tours parts: the Contact rules and Changes tabs on its Rules & Alerts page, the Tours menus and the Tours groups'
access, and the rules' alerts in the feed; this extension's own menu is then not shown.
""",
    'author': 'MTBG Tours contributors',
    'license': 'LGPL-3',
    'depends': ['mtbg_backend_ui', 'base_automation', 'mail'],
    # the admin look's boards, cards, side bar and settings page (0.2.0)
    'mtbg_tours_requires': {'mtbg_backend_ui': '19.0.0.2.0'},
    'data': [
        'security/ir.model.access.csv',
        'data/cron.xml',
        'data/boards.xml',
        'data/sync.xml',
        'views/rule_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mtbg_tours_crm_rules/static/src/crm_tab/*',
            'mtbg_tours_crm_rules/static/src/crm_page/*',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
}
