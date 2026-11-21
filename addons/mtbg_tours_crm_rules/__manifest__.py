{
    'name': 'MTBG — Contact Rules',
    'version': '19.0.0.5.2',
    # where the updater gets it (the universal repo; owner, 2026-11-18: contact rules go global, from the Tours repo)
    'mtbg_github_source': {'repo': 'git@github.com:mountainbikeguatemala-oss/mtbg-website-blocks.git', 'subdir': 'addons'},
    'category': 'Productivity',
    'summary': 'The contact pipeline (leads and clients, their stage and source channel) and stock contact helpers that keep contacts tidy on their own (country and state from the phone, '
               'possible duplicates, language from the country), on their own page (with Tours: Rules & Alerts), '
               'logged with undo',
    'description': """
The Contact rules (named CRM Rules before 0.2.0; the technical name stays): stock helpers, each off until switched
on, on their own page (Contact Rules: its Contact rules tab, its Changes tab). Each runs when a record is created or changes, when a message comes in, or every day,
with its own logic; a dry run shows what it would change; every change is logged and can be undone.

* Country and state from the phone (a contact's number; a US / Canadian area code gives the state)
* Country and state from a message's number (when a message comes in: the channels queue it)
* Possible duplicates by phone or email (flagged on Possible Duplicates; never merged)
* De-duplicate (0.5.2) in a contact's gear menu, in place of Duplicate: its likely duplicates (email, phone, a
  "(copy)" name) in Odoo's merge dialog, the most complete proposed as the one kept; merged only on a person's click
* Spanish for Spanish-speaking countries
* Extensions bring their own helpers with ``_mtbg_crm_rule_sources()`` on their own model, like the Alert Feed's sources

The contact pipeline (0.4.0, owner 2026-11-18: the same pipeline on every site; moved here from Tours, same names):

* Each contact's type: Lead, Client, Staff, Vendor, Internal (``mtbg_contact_type``, ``mtbg_is_lead``); a new contact
  is a lead (a WhatsApp number that writes in, an email sender made a contact, a website buyer), a paying customer a
  client, for good; a type chosen by a person is kept; the sure types (suppliers, ourselves) every day.
* Its stage: New, Lead, Negotiation, Customer, Lost (``mtbg_stage``); Tours adds Past client and Repeat client from
  its bookings. Negotiation (0.5.0): a quote made for a New or Lead contact (``res.partner._mtbg_mark_negotiation()``,
  called by a shop with a soft check), or the Negotiation box by hand; never backwards.
* A stage picked by a person on another screen: ``res.partner._mtbg_set_stage(stage)`` (New, Lead, Negotiation,
  Customer, Lost).
* Its source channel (``mtbg_lead_source_id``, Odoo's UTM sources): first touch only, set by the Communication Flow
  Designer from the first message received (WhatsApp, Email, Webchat...), by a website sale (Website sale) or a form.
* The hook for a sale paid: ``res.partner._mtbg_mark_customer(source=None)`` (a lead becomes a client, stage
  Customer; ``source`` its source channel when it has none). Other extensions call it with a soft check.
* Without Tours: the stage and type on the contact's page, the Contacts board (leads and clients by stage) and the
  Source Channels in this extension's menu. With Tours, its Contacts page and contact page show them.

Needs only Odoo and the admin look (0.3.0, owner 2026-11-18: in the universal repository, no Tours). Who may change
the rules: the admin look's managers (administrators; with Tours, its managers). With Tours, the Alert Feed brings the
Tours parts: the Contact rules and Changes tabs on its Rules & Alerts page, the Tours menus and the Tours groups'
access, and the rules' alerts in the feed; this extension's own menu is then not shown.
""",
    'author': 'MTBG Tours contributors',
    'license': 'LGPL-3',
    'depends': ['mtbg_backend_ui', 'base_automation', 'mail', 'utm'],
    # the admin look's boards, cards, side bar and settings page (0.2.0)
    'mtbg_tours_requires': {'mtbg_backend_ui': '19.0.0.2.0'},
    'data': [
        'security/ir.model.access.csv',
        'data/cron.xml',
        'data/boards.xml',
        'data/sync.xml',
        'data/pipeline.xml',
        'data/pipeline_cron.xml',
        'views/rule_views.xml',
        'views/pipeline_views.xml',
        'views/menus.xml',
        'views/contact_dedupe_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mtbg_tours_crm_rules/static/src/crm_tab/*',
            'mtbg_tours_crm_rules/static/src/crm_page/*',
        ],
        'web.assets_tests': [
            'mtbg_tours_crm_rules/static/tests/tours/*',
        ],
    },
    'pre_init_hook': 'pre_init_hook',
    'post_init_hook': 'post_init_hook',
    'installable': True,
}
