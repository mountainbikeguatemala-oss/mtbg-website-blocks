{
    'name': 'MTBG Website — Forms',
    'version': '19.0.0.6.0',
    # where the updater gets it (the universal repo; owner, 2026-11-11: universal, from the Tours repo)
    'mtbg_github_source': {'repo': 'git@github.com:mountainbikeguatemala-oss/mtbg-website-blocks.git', 'subdir': 'addons'},
    'category': 'Website',
    'summary': 'One set of customer fields for every form on the site (booking, website chat, pre-tour, contact): '
               'the mobile number with its country code picker, email and name, checked the same '
               'way in the browser and on the server; the contact forms (page, popup, tour sidebar)',
    'author': 'MTBG Tours contributors',
    'license': 'LGPL-3',
    # the website blocks' shared JavaScript (the chat under layers: Reusable Blocks 0.11.2) and the admin look's
    # translated text settings (0.1.0); updater 19.0.0.6.0+
    'mtbg_tours_requires': {'mtbg_tours_content_blocks': '19.0.0.11.2', 'mtbg_backend_ui': '19.0.0.1.0'},
    'depends': ['mtbg_backend_ui', 'mtbg_tours_content_blocks', 'website', 'website_crm', 'phone_validation',
                'im_livechat'],
    'description': """
The customer fields every form shares, and the Forms page (this extension's tile): every form of the site in one place, with the sections other extensions add (pre-tour forms and waivers); its Form Designer: each website form's blocks
(fields, headings, texts, numbered steps added inline) in order by drag and drop, their texts in every language of the
site, show / required rules (on the other answers, a known visitor, the page variant, the language), the look per
variant, with a live preview. First form on it: the contact form (page, popup, a page's sidebar).

Needs only Odoo's website and the website blocks with the admin look (since 0.5.0 / 0.6.0, owner 2026-11-11; in the
universal repository since 0.6.0). With Tours installed it uses Tours Core's contact rule, one
open lead per person and first-touch lead sources; Booking Form brings the tour pages (the tour sidebar form's
subject, the popups' tour and rental page rules, the designer's tour previews) and the messaging terms' editor.
""",
    'data': [
        'security/ir.model.access.csv',
        'data/forms.xml',
        'data/menu_form.xml',
        'data/newsletter_popup.xml',
        'views/templates.xml',
        'views/form_templates.xml',
        'views/contact_templates.xml',
        'views/designer_views.xml',
        'views/snippets.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'mtbg_tours_forms/static/src/*',
        ],
        'web.assets_backend': [
            'mtbg_tours_forms/static/src/designer/*',
        ],
        'website.website_builder_assets': [
            'mtbg_tours_forms/static/src/website_builder/*',
        ],
        # the website chat draws inside its own shadow DOM, styled by this bundle only
        'im_livechat.assets_embed_external': [
            'mtbg_tours_forms/static/src/fields.scss',
        ],
    },
    'installable': True,
}
