"""The admin's top bar icons (owner, 2026-10-29: "remove the name of the logged in person show only the icon, after that
the clock, visits, notifications, emails, messaging. all alert bubbles should line up" and "push this fucionality
into the menu designer then we can rearrange notifications there. figure out a way to hide the company name with a
switch").

The icons are Odoo's systray items, each known by its registry key (``cfd_inbox``, ``mail.activity_menu``…): the
order and the hidden ones are kept here for everyone and sent with the session; the web client puts the items in
that order (``static/src/topbar``). A key of a module not installed is skipped there, an item not listed keeps its
place on the left. The user menu (and the phone's menu button) always stay on the far right.

The phone's side menu (0.11.6, owner 2026-11-21: "everything that is horizontal on the main menu is in the vertical
(icon) menu on the mobile backend"): with ``phone_menu`` on, the side menu of a phone (Odoo's menu button, left of the
top bar, below 768px) lists every app with its whole top bar, not only the app open; a menu with its own page and
menus under it gets its own row. A computer's top bar does not change. Switched on by the Menu Designer's preset
"Phone: every menu in the side menu" or its switch under the top bar icons.
"""
import json

from odoo import _, api, models
from odoo.exceptions import AccessError

PARAM_ITEMS = 'mtbg_tours_content_blocks.topbar_items'
PARAM_COMPANY_NAME = 'mtbg_tours_content_blocks.topbar_company_name'
PARAM_PHONE_MENU = 'mtbg_tours_content_blocks.topbar_phone_menu'

# left to right (owner, 2026-10-29): messaging, emails, notifications, visits, the clock, the company (an icon)
DEFAULT_ORDER = ['cfd_inbox', 'cfd_mailbox', 'mtbg_tours_alerts.alert_menu', 'cfd_visitors_online',
                 'mail.activity_menu', 'SwitchCompanyMenu']
PINNED = ('burger_menu', 'web.user_menu')  # far right, never moved or hidden


class MtbgTopbar(models.AbstractModel):
    _name = 'mtbg.topbar'
    _description = 'Admin top bar icons'

    @api.model
    def _mtbg_check(self):
        if not self.env.su and not self.env.user.has_group('base.group_system'):
            raise AccessError(_("Only administrators can change the top bar."))

    @api.model
    def mtbg_topbar_settings(self):
        """{items: [{key, hidden}] left to right, company_name: bool, phone_menu: bool}: what the web client
        applies."""
        Param = self.env['ir.config_parameter'].sudo()
        try:
            items = json.loads(Param.get_param(PARAM_ITEMS) or 'null')
        except ValueError:
            items = None
        if not isinstance(items, list):
            items = [{'key': key, 'hidden': False} for key in DEFAULT_ORDER]
        items = [{'key': str(i['key']), 'hidden': bool(i.get('hidden'))} for i in items
                 if isinstance(i, dict) and i.get('key') and i['key'] not in PINNED]
        return {'items': items, 'company_name': Param.get_param(PARAM_COMPANY_NAME) == '1',
                'phone_menu': Param.get_param(PARAM_PHONE_MENU) == '1'}

    @api.model
    def mtbg_topbar_save(self, items=None, company_name=None, phone_menu=None):
        """Keep the order (``items``: [{key, hidden}] left to right), the company name switch and the phone's side
        menu switch, for everyone."""
        self._mtbg_check()
        Param = self.env['ir.config_parameter'].sudo()
        if items is not None:
            seen, clean = set(), []
            for item in items:
                key = str(item.get('key') or '') if isinstance(item, dict) else ''
                if key and key not in PINNED and key not in seen:
                    seen.add(key)
                    clean.append({'key': key, 'hidden': bool(item.get('hidden'))})
            Param.set_param(PARAM_ITEMS, json.dumps(clean))
        if company_name is not None:
            Param.set_param(PARAM_COMPANY_NAME, '1' if company_name else '0')
        if phone_menu is not None:
            Param.set_param(PARAM_PHONE_MENU, '1' if phone_menu else '0')
        return self.mtbg_topbar_settings()

    @api.model
    def mtbg_topbar_reset(self):
        """Back to the default order, every icon shown, the company name off, the phone's side menu as Odoo's."""
        self._mtbg_check()
        Param = self.env['ir.config_parameter'].sudo()
        Param.set_param(PARAM_ITEMS, False)
        Param.set_param(PARAM_COMPANY_NAME, False)
        Param.set_param(PARAM_PHONE_MENU, False)
        return self.mtbg_topbar_settings()
