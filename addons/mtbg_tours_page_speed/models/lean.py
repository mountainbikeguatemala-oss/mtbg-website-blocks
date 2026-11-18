"""Visitor pages without Odoo's extras (page speed 0.5.0, owner 2026-11-03: "the trim odoo extras should be an option
in the optimizer extension itself on/off"): every website page loads Odoo's whole frontend script bundle (4 MB, 738 KB
compressed on www), with pieces a visitor reading a page never uses: the editor's media dialog and Unsplash search, the
onboarding tours, the tax helper and the payment and delivery forms (checkout, invoices).

With the switch on, an anonymous visitor on an ordinary page gets a copy of that bundle without them
(``mtbg_tours_page_speed.assets_frontend_lazy_lean``); logged-in users (the editor) and the pages that need them
(portal, checkout, payment, invoices, the customers' token pages) keep Odoo's own bundle. Nothing is uninstalled.
The copy's removals are made for the modules installed (a module that is not installed cannot be named in a
bundle), again whenever modules change; what a kept file imports is never removed (checked by the tests).

0.6.0 (owner's code clean-up, 2026-11-04): the same switch trims the stylesheet every visitor page waits for. The
visitors get a copy of Odoo's frontend stylesheet (``assets_frontend_lean``) without the editor's and the back end's
own styles (the media dialog, the onboarding tours, the payment, delivery and portal security forms...). The website
editor's background shapes (``.o_we_shape``: 120 KB of classes, one per shape Odoo has) come in a stylesheet that
loads after the page has shown (``assets_frontend_late``); their base rules stay in the page's stylesheet
(static/src/scss/background_layers.scss), so a section keeps its layout. And the script copy also leaves out what
nothing on a visitor's page uses: the passkey login, the portal's address and signature forms, the editor's
utilities no kept file imports, and, where the website chat loads on its own (CFD's chat tab), the bus (live
messages) and mail's formatting helpers: they come with the chat's bundle instead.

0.7.11 (owner 2026-11-12: "trim font awesome"): the visitors' stylesheet carries Font Awesome's icons in two files,
the icons the site uses and Odoo's whole font for any other; a page fetches the whole font only if it draws an icon
the small file does not have. Logged-in users and the back end keep Odoo's."""
import json

from markupsafe import Markup

from odoo import api, models
from odoo.http import request

PARAM = 'mtbg_tours.page_speed_lean'
# 0.7.7: the first screen first (models/first_screen.py), on unless switched off (mtbg_tours.*: a change empties
# Cloudflare's cache, the pages then come again as set)
FIRST_SCREEN_PARAM = 'mtbg_tours.page_speed_first_screen'
BUNDLE = 'mtbg_tours_page_speed.assets_frontend_lazy_lean'
CSS_BUNDLE = 'mtbg_tours_page_speed.assets_frontend_lean'
LATE_CSS_BUNDLE = 'mtbg_tours_page_speed.assets_frontend_late'
CHAT = 'cfd_website_chat_tab'
CHAT_BUNDLE = 'cfd_website_chat_tab.assets_chat'
# (module, glob[, only with this module installed too]): what the visitors' script copy leaves out
EXTRAS = (
    ('html_editor', 'html_editor/static/src/main/media/**/*'),       # the editor's media dialog
    ('website', 'website/static/src/components/media_dialog/**/*'),  # (imports it)
    ('web_unsplash', 'web_unsplash/static/src/**/*'),                 # Unsplash photo search (editor)
    ('web_tour', 'web_tour/static/src/**/*'),                         # onboarding tours (logged-in users)
    ('website', 'website/static/src/js/tours/**/*'),                  # (imports them)
    ('account', 'account/static/src/helpers/**/*'),                   # the tax helper, 118 KB (checkout, invoices)
    ('account', 'account/static/src/components/tests_shared_js_python/**/*'),
    ('account', 'account/static/src/interactions/**/*'),              # portal invoices
    ('payment', 'payment/static/src/**/*'),                           # payment forms
    ('account_payment', 'account_payment/static/src/**/*'),
    ('website_payment', 'website_payment/static/src/**/*'),
    ('payment_custom', 'payment_custom/static/src/**/*'),
    ('delivery', 'delivery/static/src/**/*'),                         # the pickup-point map (shop checkout)
    # 0.6.0
    ('auth_passkey', 'auth_passkey/static/**/*'),                     # passkey login (/web/login keeps Odoo's)
    ('auth_passkey_portal', 'auth_passkey_portal/static/src/**/*'),   # (imports it) passkeys in /my/security
    ('portal', 'portal/static/src/interactions/address.js'),          # address forms (checkout, /my)
    ('portal', 'portal/static/src/interactions/address_card.js'),
    ('portal', 'portal/static/src/interactions/portal_details.js'),
    ('portal', 'portal/static/src/interactions/portal_search_panel.js'),
    ('portal', 'portal/static/src/signature_form/**/*'),              # signing a quote (/my)
    ('html_editor', 'html_editor/static/src/components/html_viewer/**/*'),  # editor pieces no kept file imports
    ('html_editor', 'html_editor/static/src/components/switch/**/*'),
    ('html_editor', 'html_editor/static/src/position_hook.js'),
    ('html_editor', 'html_editor/static/src/utils/clipboard.js'),
    ('html_editor', 'html_editor/static/src/utils/color.js'),
    ('html_editor', 'html_editor/static/src/utils/drag_and_drop.js'),
    ('html_editor', 'html_editor/static/src/utils/fonts.js'),
    ('html_editor', 'html_editor/static/src/utils/functions.js'),
    ('html_editor', 'html_editor/static/src/utils/html.js'),
    ('html_editor', 'html_editor/static/src/utils/image.js'),
    ('html_editor', 'html_editor/static/src/utils/image_processing.js'),
    ('html_editor', 'html_editor/static/src/utils/perspective_utils.js'),
    ('html_editor', 'html_editor/static/src/utils/regex.js'),
    ('html_editor', 'html_editor/static/src/utils/resource.js'),
    ('html_editor', 'html_editor/static/src/utils/table.js'),
    ('html_editor', 'html_editor/static/src/utils/tracking.js'),
    # 0.7.12: the back end's own widgets (Odoo's frontend bundle carries them; no visitor page draws them, no kept file
    # imports them: the tests check), and the portal's two-factor and quote pieces (/my keeps Odoo's bundle)
    ('web', 'web/static/src/core/tree_editor/**/*'),                   # domain and condition editors
    ('web', 'web/static/src/core/domain_selector/**/*'),
    ('web', 'web/static/src/core/domain_selector_dialog/**/*'),
    ('web', 'web/static/src/core/expression_editor/**/*'),
    ('web', 'web/static/src/core/expression_editor_dialog/**/*'),
    ('web', 'web/static/src/core/model_field_selector/**/*'),
    ('web', 'web/static/src/core/model_selector/**/*'),
    ('web', 'web/static/src/core/record_selectors/**/*'),
    ('web', 'web/static/src/core/barcode/**/*'),                       # the barcode scanner
    ('web', 'web/static/src/core/signature/**/*'),                     # signing (/my keeps it)
    ('web', 'web/static/src/core/code_editor/**/*'),
    ('web', 'web/static/src/core/ir_ui_view_code_editor/**/*'),
    ('web', 'web/static/src/core/debug/**/*'),                         # the developer menu
    ('web', 'web/static/src/core/pager/**/*'),
    ('web', 'web/static/src/core/effects/**/*'),                       # the rainbow man
    ('web', 'web/static/src/core/colorlist/**/*'),
    ('web', 'web/static/src/core/virtual_grid_hook.js'),
    # 0.10.0 (the shop site): the shop's checkout pieces that import the payment, delivery, address and onboarding
    # pieces left out above (/shop keeps Odoo's bundle: they are used there only)
    ('website_sale', 'website_sale/static/src/interactions/address.js'),
    ('website_sale', 'website_sale/static/src/interactions/checkout.js'),
    ('website_sale', 'website_sale/static/src/interactions/payment_button.js'),
    ('website_sale', 'website_sale/static/src/interactions/payment_form.js'),
    ('website_sale', 'website_sale/static/src/js/location_selector/**/*'),
    ('website_sale', 'website_sale/static/src/js/tours/**/*'),
    ('website_sale_collect', 'website_sale_collect/static/src/interactions/checkout.js'),
    ('website_sale_collect', 'website_sale_collect/static/src/interactions/payment_form.js'),
    ('website_sale_collect', 'website_sale_collect/static/src/js/click_and_collect_availability/**/*'),
    ('website_sale_collect', 'website_sale_collect/static/src/js/location_selector/**/*'),
    ('website_sale_loyalty', 'website_sale_loyalty/static/src/interactions/checkout.js'),
    ('website_sale_mondialrelay', 'website_sale_mondialrelay/static/src/interactions/checkout.js'),
    ('l10n_br', 'l10n_br/static/src/interactions/address.js'),
    ('l10n_it_edi', 'l10n_it_edi/static/src/interactions/address.js'),
    ('l10n_pe', 'l10n_pe/static/src/interactions/address.js'),
    ('l10n_sa_edi', 'l10n_sa_edi/static/src/interactions/address.js'),
    ('l10n_tw_edi_ecpay_website_sale', 'l10n_tw_edi_ecpay_website_sale/static/src/js/address.js'),
    ('auth_totp_portal', 'auth_totp_portal/static/src/**/*'),          # two-factor settings (/my)
    ('sale', 'sale/static/src/interactions/**/*'),                     # quotes and orders (/my)
    ('sale_management', 'sale_management/static/src/**/*'),
    # the website chat's own needs, where CFD's chat tab loads the chat when it is wanted: they come with it (CHAT_TO)
    ('bus', 'bus/static/src/**/*', CHAT),
    ('mail', 'mail/static/src/utils/common/format.js', CHAT),
    # 0.7.12: the chat's widgets (emoji and colour pickers, its tabs, swipes and panels, its file upload)
    ('web', 'web/static/src/core/emoji_picker/**/*', CHAT),
    ('web', 'web/static/src/core/color_picker/**/*', CHAT),
    ('web', 'web/static/src/core/notebook/**/*', CHAT),
    ('web', 'web/static/src/core/action_swiper/**/*', CHAT),
    ('web', 'web/static/src/core/resizable_panel/**/*', CHAT),
    ('web', 'web/static/src/views/fields/file_handler.js', CHAT),
    ('web', 'web/static/src/views/fields/formatters.js', CHAT),
)
# what the chat's bundle then brings itself (Odoo leaves the page's bundle's copy alone where it has one)
CHAT_TO = ('bus/static/src/*.js', 'bus/static/src/services/**/*.js', 'bus/static/src/workers/*') + tuple(
    'web/static/src/core/%s/**/*.%s' % (folder, kind)
    for folder in ('emoji_picker', 'color_picker', 'notebook', 'action_swiper', 'resizable_panel')
    for kind in ('js', 'xml')) + ('web/static/src/views/fields/file_handler.js', 'web/static/src/views/fields/formatters.js')
CHAT_NOT = ('bus/static/src/services/assets_watchdog_service.js', 'bus/static/src/simple_notification_service.js',
            'bus/static/src/workers/bus_worker_script.js',
            'web/static/src/core/emoji_picker/emoji_data.js')  # (the emojis themselves: Odoo loads them when wanted)
# the editor's backgrounds: their base rules in their place (the cascade unchanged), their shapes late
BACKGROUND = 'html_builder/static/src/scss/background.scss'
BACKGROUND_BASE = 'mtbg_tours_page_speed/static/src/scss/background_layers.scss'
# 0.7.11 (owner 2026-11-12: "trim font awesome"): the icon font as two files, the icons the site uses (22 KB) and Odoo's
# whole font (75 KB) for any other; a page fetches only the file of the icons it draws (tools/font_awesome_visitors.py)
FONT_AWESOME = 'web/static/src/libs/fontawesome/css/font-awesome.css'
FONT_AWESOME_VISITORS = 'mtbg_tours_page_speed/static/src/css/font_awesome_visitors.css'
# (module, glob): what the visitors' stylesheet leaves out: the editor's and the back end's own styles
CSS_EXTRAS = (
    ('html_editor', 'html_editor/static/src/main/media/media_dialog/**/*'),  # the editor's media dialog
    ('html_editor', 'html_editor/static/src/components/switch/**/*'),
    ('html_editor', 'html_editor/static/src/main/selection_placeholder_plugin.scss'),
    ('html_editor', 'html_editor/static/src/others/qweb_plugin.scss'),
    ('web_tour', 'web_tour/static/src/**/*'),                          # onboarding tours
    ('payment', 'payment/static/src/**/*'),                            # payment forms
    ('delivery', 'delivery/static/src/**/*'),                          # the pickup-point map
    ('stock', 'stock/static/src/scss/stock_traceability_report.scss'),  # a back-end report
    ('auth_totp_portal', 'auth_totp_portal/static/src/**/*'),          # two-factor settings (/my)
    ('sale', 'sale/static/src/scss/sale_portal.scss'),                 # quotes and orders (/my)
    # the back end's own widgets (Odoo's frontend bundle carries their styles; no visitor page draws them)
    ('web', 'web/static/src/core/colorlist/**/*.scss'),
    ('web', 'web/static/src/core/color_picker/**/*.scss'),
    ('web', 'web/static/src/core/tags_list/**/*.scss'),
    ('web', 'web/static/src/core/notebook/**/*.scss'),
    ('web', 'web/static/src/core/effects/**/*.scss'),                  # the rainbow man
    ('web', 'web/static/src/core/record_selectors/**/*.scss'),
    ('web', 'web/static/src/core/model_field_selector/**/*.scss'),
    ('web', 'web/static/src/core/model_selector/**/*.scss'),
    ('web', 'web/static/src/core/ir_ui_view_code_editor/**/*.scss'),
    ('web', 'web/static/src/core/emoji_picker/**/*.scss'),             # (the chat has its own, in its shadow root)
    ('web', 'web/static/src/core/barcode/**/*.scss'),
    ('web', 'web/static/src/core/pager/**/*.scss'),
    ('web', 'web/static/src/webclient/navbar/navbar.scss'),            # the back end's top bar
    ('web', 'web/static/src/views/fields/translation_dialog.scss'),
    ('web', 'web/static/src/views/fields/signature/signature_field.scss'),
)
# where Odoo's own bundle stays (its extras are used there), with or without the language
FULL_PATHS = ('/my', '/shop', '/payment', '/website/payment', '/donation', '/invoice', '/invoice-detail', '/i/',
              '/pretour', '/cancellation', '/tour-cancelled', '/cards', '/account', '/staff', '/web', '/odoo',
              '/mtbg_tours/secure-pay', '/quote', '/report')

# 0.7.12 instant pages (views/templates.xml instant_pages): never fetched ahead, with or without the language (with the
# addresses above): Odoo's back end and its routes, the website's own actions, the chat, the shop
NO_PREFETCH = FULL_PATHS + ('/website', '/mtbg', '/mtbg_forms', '/mtbg_tours', '/im_livechat', '/livechat', '/chat',
                            '/web_editor', '/html_editor', '/sitemap.xml', '/robots.txt')
# (and by the link: a query string, a download, a new tab, a link not to follow, a file)
NO_PREFETCH_LINKS = ('a[href*="?"]', 'a[download]', 'a[target="_blank"]', 'a[rel~="nofollow"]', 'a[href$=".pdf"]',
                     'a[href$=".xml"]', 'a[href$=".zip"]')


def _no_prefetch():
    """The addresses never fetched ahead, without their slashes, as regular expressions (both Chrome's address
    patterns and a script's: only the dots escaped; covered ones left out)."""
    paths = sorted({p.strip('/') for p in NO_PREFETCH})
    return [p.replace('.', '\\.') for p in paths if not any(p.startswith(o + '/') for o in paths)]


def _on(value):
    return value not in (False, None, '', '0', 'False', 'false')


class MtbgPageSpeedLean(models.AbstractModel):
    _name = 'mtbg.page.speed.lean'
    _description = 'Page speed: visitor pages without Odoo extras'

    @api.model
    def _mtbg_on(self):
        return _on(self.env['ir.config_parameter'].sudo().get_param(PARAM))

    @api.model
    def _mtbg_first_screen_on(self):
        """The first screen first: on by default (it acts only where the visitors' lean stylesheet is used)."""
        value = self.env['ir.config_parameter'].sudo().get_param(FIRST_SCREEN_PARAM)
        return value is None or value is False or _on(value)

    @api.model
    def _mtbg_wanted(self):
        """{(bundle, directive): [glob or (target, glob)]}: the copies' records for the modules installed; none while
        the switch is off."""
        if not self._mtbg_on():
            return {}
        installed = set(self.env['ir.module.module'].sudo().search([('state', '=', 'installed')]).mapped('name'))
        js = [glob for module, glob, *also in EXTRAS if module in installed and all(m in installed for m in also)]
        wanted = {(BUNDLE, 'remove'): js,
                  (CSS_BUNDLE, 'remove'): [glob for module, glob in CSS_EXTRAS if module in installed]}
        wanted[(CSS_BUNDLE, 'replace')] = [(FONT_AWESOME, FONT_AWESOME_VISITORS)]
        if 'html_builder' in installed:
            wanted[(CSS_BUNDLE, 'replace')].append((BACKGROUND, BACKGROUND_BASE))
        if 'bus/static/src/**/*' in js:
            wanted[(CHAT_BUNDLE, 'prepend')] = list(CHAT_TO)
            wanted[(CHAT_BUNDLE, 'remove')] = list(CHAT_NOT)
        return wanted

    @api.model
    def _mtbg_sync(self):
        """The copies' removals (and the chat bundle's additions), for the modules installed; none while the switch
        is off."""
        Asset = self.env['ir.asset'].sudo()
        wanted = self._mtbg_wanted()
        mine = Asset.search([('name', '=like', 'Page speed: %'),
                             ('bundle', 'in', [BUNDLE, CSS_BUNDLE, CHAT_BUNDLE])])
        records = []
        for (bundle, directive), globs in wanted.items():
            for glob in globs:
                target, path = glob if isinstance(glob, tuple) else (False, glob)
                records.append({'name': 'Page speed: visitors without %s' % (target or path).split('/')[0],
                                'bundle': bundle, 'directive': directive, 'target': target, 'path': path,
                                'sequence': 1 if directive == 'prepend' else 100})
        key = lambda r: (r['bundle'], r['directive'], r['target'] or '', r['path'], r['sequence'])  # noqa: E731
        if sorted(map(key, mine.read(['bundle', 'directive', 'target', 'path', 'sequence']))) != sorted(map(key, records)):
            mine.unlink()
            Asset.create(records)
        return sum(len(globs) for (bundle, directive), globs in wanted.items() if directive == 'remove')

    @api.model
    def mtbg_use_lean(self):
        """This page's request gets the visitors' copy: the switch on, an anonymous visitor, an ordinary page."""
        if not request or not self._mtbg_on() or not self.env.user._is_public():
            return False
        path = request.httprequest.path
        parts = path.split('/', 2)
        lang = getattr(request, 'lang', None)
        if len(parts) > 1 and lang and parts[1] == lang.url_code:
            path = '/' + (parts[2] if len(parts) > 2 else '')
        return not any(path == p or path.startswith(p + '/') or (p.endswith('/') and path.startswith(p))
                       for p in FULL_PATHS)

    @api.model
    def mtbg_prefetch_excluded(self):
        """The addresses never fetched ahead, as a regular expression's alternatives (the prefetch fallback's)."""
        return '|'.join('/' + p for p in _no_prefetch())

    @api.model
    def mtbg_speculation_rules(self):
        """Chrome's speculation rules for the visitor's page: the site's own links fetched when pointed at."""
        # (one address pattern: an optional language, one of the addresses, anything under it)
        patterns = '{/:lang}?/(%s){/*}?' % '|'.join(_no_prefetch())
        rules = {'prefetch': [{'source': 'document', 'eagerness': 'moderate', 'where': {'and': [
            {'href_matches': '/*'},
            {'not': {'href_matches': patterns}},
            {'not': {'selector_matches': ', '.join(NO_PREFETCH_LINKS)}},
        ]}}]}
        return Markup(json.dumps(rules, separators=(',', ':')).replace('</', '<\\/'))

    def _register_hook(self):
        super()._register_hook()
        # (modules installed or removed since the switch was turned on: its removals follow)
        try:
            if self._mtbg_on():
                self._mtbg_sync()
        except Exception:  # noqa: BLE001 - never in the way of the server starting
            pass
