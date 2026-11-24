{
    'name': 'Zoho Connector',
    'version': '19.0.0.3.4',
    'category': 'Services',
    'summary': 'One login for every Zoho app (Books, Expense, Shifts): setup wizard, a switch per app, the references '
               'of Odoo records in Zoho, the sync log; Zoho Books expenses Import & Sync; vendors in Zoho Books',
    'description': """
The Zoho connection any Odoo site can use, without any other extension (2026-11-11: the Zoho connector split; it
took this part over from the Tours' Zoho extension, which keeps the tours' Zoho Books work).

* One login and ONE setup wizard (Settings › Zoho › Set up Zoho): data centre, Self Client, the apps' combined scopes
  and the grant code, each app's organization, Check access. An extension may add its own Zoho Books step.
* Per app (Books, Expense, Shifts): On, and Writes allowed, both off by default; its organization.
* One client (``services/client.py``): calls paced per app and minute, retried when Zoho says too many (a write is
  never sent twice); one access token for every app, renewed once an hour (not a system parameter).
* References (``mtbg.zoho.ref``): which Zoho record an Odoo record is, per app and kind, its state and error; each
  extension retries its own kinds (``_mtbg_retry``).
* The sync log (``mtbg.zoho.log``): every write and every failed call, kept 90 days.
* The Zoho section of Settings: the connection, the sync log and references, and a card per integration (an
  extension gives its cards, ``_mtbg_card_defaults``; a glue module its manifest's ``zoho_connector_card``).
* Zoho Books expenses, Import & Sync (0.2.0, from the Tours' Zoho extension): the Expense Categories
  (``mtbg.zoho.books.account``, read only from Zoho Books) and where each one's expenses go, a run
  (``mtbg.zoho.books.import``: the first sync, then every hour the changes), its review list
  (``mtbg.zoho.books.review``). Extensions bring the destinations (``_mtbg_destinations``, ``_mtbg_suggest``,
  ``_mtbg_import_line``, ``_mtbg_apply_review``); without any, a category is skipped or counted as internal.
* A vendor contact's Zoho Books vendor (0.2.0, from the Tours' Zoho extension): ``mtbg_zoho_vendor_id`` on the
  contact, found or made by name (``_mtbg_zoho_vendor_ensure``), the vendors made here pushed in the background
  (``_mtbg_zoho_push_vendors``; which contacts are vendors: an extension's ``mtbg_is_vendor`` tick).
* Expenses recorded in Odoo (0.3.0): any model with Admin Look's expense mixin (``mtbg.expense.source``, e.g. the
  shop's used purchases) is a Zoho Books expense once saved: its category's account, its payment method's paid
  through account (both lists filled by Sync from Zoho Books), its vendor, its receipt, Zoho's rate; changes update
  it, a deletion deletes it, an error shows on the record and is retried every hour.
""",
    'author': 'MTBG Tours contributors',
    'license': 'LGPL-3',
    'depends': ['base', 'web', 'base_setup', 'mtbg_backend_ui'],
    'external_dependencies': {'python': ['requests']},
    'mtbg_github_source': {'repo': 'git@github.com:mountainbikeguatemala-oss/mtbg-website-blocks.git', 'subdir': 'addons'},
    # (the updater: a planned move, these modules' Zoho models and records come here; pre_init_hook and the 0.2.0
    # pre-migration move their ids)
    'mtbg_takes_over': ['mtbg_tours_zoho', 'mtbg_tours_invoicing'],
    'mtbg_tours_section': 'connectors',
    'data': [
        'security/ir.model.access.csv',
        'data/cron.xml',
        'views/zoho_views.xml',
        'views/books_expenses_views.xml',
        'views/settings_views.xml',
        'views/expense_out_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'zoho_connector/static/src/subextensions/*',
            'zoho_connector/static/src/setup/*',
        ],
    },
    'pre_init_hook': 'pre_init_hook',
    'installable': True,
}
