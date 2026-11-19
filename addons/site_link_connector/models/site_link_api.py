"""The protocol a site offers to its linked sites, called through Odoo's /json/2 API:

    POST /json/2/site.link.api/<method>   (Authorization: bearer <API key>, X-Odoo-Database: <db>)

The caller is the technical user of the API key; it needs the group "Site Link: calls from a linked site" (or to be
an administrator). The methods then work with the rights they need (sudo), in the user's company. The inventory
methods are offered only where Inventory is installed, the repair methods only where Sales is (soft checks: no
dependency; Repair and a customer bike model are used where they are installed); ``inbox_unread`` only where the shared
inbox of Communication Flows (its side panel) is; ``staff_clock`` only where another extension answers
``res.users._site_link_staff_clock(user)``. See README.md."""
import hashlib
import json
import logging
import re

from odoo import api, models, release
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_round

from .site_link import is_local_path
from .site_link_sso import SSO_GROUP, SSO_TTL, is_admin_user

_logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 1
BASE_METHODS = ['health', 'sso_ticket', 'user_sync', 'customer_search', 'customer_create', 'customer_bikes']
INVENTORY_METHODS = ['part_lookup', 'part_consume']
REPAIR_METHODS = ['repair_quote', 'repair_status', 'repair_invoice']
# where Communication Flows' side panel is installed (the shared inbox, its "Pop up new client messages")
INBOX_METHODS = ['inbox_unread']
# where another extension answers res.users._site_link_staff_clock(user) (e.g. a staff app's shift clock)
STAFF_CLOCK_METHODS = ['staff_clock']
CONSUME_LOCATION_NAME = 'Internal use (linked sites)'
LABOUR_PRODUCT_CODE = 'SITE_LINK_LABOUR'
SEARCH_LIMIT_MAX = 50
# no follower added, no "created" note, no assignment mail: nothing reaches a customer from these calls
QUIET = {'mail_create_nosubscribe': True, 'mail_create_nolog': True, 'mail_auto_subscribe_no_notify': True}


def escape_like(text):
    """``text`` for an =ilike comparison: its % and _ are plain characters."""
    return text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


class SiteLinkApi(models.AbstractModel):
    _name = 'site.link.api'
    _description = 'Linked site: protocol'

    # ------------------------------------------------------------------ helpers (private: not callable remotely)

    def _site_link_check_caller(self):
        user = self.env.user
        if not (user.has_group('site_link_connector.group_site_link_remote') or user._is_system()):
            raise AccessError(self.env._("User %s may not answer linked sites: give it the group "
                                         "\"Site Link: calls from a linked site\".", user.login))

    def _site_link_has_inventory(self):
        return 'stock.move' in self.env and 'stock.quant' in self.env

    def _site_link_require_inventory(self):
        if not self._site_link_has_inventory():
            raise UserError(self.env._("This site has no Inventory: it offers no part lookup or consumption."))

    def _site_link_has_sales(self):
        return 'sale.order' in self.env and 'sale.order.line' in self.env

    def _site_link_require_sales(self):
        if not self._site_link_has_sales():
            raise UserError(self.env._("This site has no Sales: it offers no repair quotes or invoices."))

    def _site_link_has_repair(self):
        return 'repair.order' in self.env and 'repair_line_type' in self.env['stock.move']._fields

    def _site_link_bike_model(self):
        """The customer bike model (``repair.bike``, from another extension) when it is installed, else None."""
        Bike = self.env.get('repair.bike')
        if Bike is None or 'partner_id' not in Bike._fields:
            return None
        return Bike.sudo()

    def _site_link_has_inbox(self):
        Conversation = self.env.get('omni.conversation')
        return Conversation is not None and hasattr(Conversation, '_cfd_popup_waiting_count')

    def _site_link_has_staff_clock(self):
        return hasattr(self.env['res.users'], '_site_link_staff_clock')

    def _site_link_methods(self):
        return (BASE_METHODS + (INVENTORY_METHODS if self._site_link_has_inventory() else [])
                + (REPAIR_METHODS if self._site_link_has_sales() else [])
                + (INBOX_METHODS if self._site_link_has_inbox() else [])
                + (STAFF_CLOCK_METHODS if self._site_link_has_staff_clock() else []))

    def _site_link_served(self, method, message):
        """A call this site answered, in the log (with the call's transaction)."""
        self.env['site.link.log'].sudo()._site_link_event('served', method, message)

    def _site_link_find_product(self, product):
        """A product.product (sudo) by id (int) or barcode (str); raises UserError when there is none."""
        Product = self.env['product.product'].sudo()
        if isinstance(product, bool) or not isinstance(product, (int, str)):
            raise UserError(self.env._("product must be a product id (number) or a barcode (text)."))
        if isinstance(product, int):
            found = Product.browse(product).exists()
        else:
            found = Product.search([('barcode', '=', product.strip())], limit=1) if product.strip() else Product
        if not found:
            raise UserError(self.env._("No product %s on this site.", product))
        return found.with_company(self.env.company)

    def _site_link_consume_location(self, company):
        """The location parts leave stock to (usage Inventory loss, like a scrap), one per company, made once."""
        Location = self.env['stock.location'].sudo()
        location = Location.search([('name', '=', CONSUME_LOCATION_NAME), ('usage', '=', 'inventory'),
                                    ('company_id', '=', company.id)], limit=1)
        if not location:
            parent = self.env.ref('stock.stock_location_locations_virtual', raise_if_not_found=False)
            location = Location.create({'name': CONSUME_LOCATION_NAME, 'usage': 'inventory',
                                        'company_id': company.id, 'location_id': parent.id if parent else False})
        return location

    def _site_link_unit_cost(self, product):
        return product.sudo().with_company(self.env.company).standard_price

    # ------------------------------------------------------------------ the protocol (public: /json/2)

    @api.model
    @api.readonly
    def health(self):
        """This side: protocol version, Odoo and module version, database, the calling user, the methods offered."""
        self._site_link_check_caller()
        module = self.env['ir.module.module'].sudo().search([('name', '=', 'site_link_connector')], limit=1)
        return {
            'protocol': PROTOCOL_VERSION,
            'module': 'site_link_connector',
            'module_version': module.installed_version or module.latest_version,
            'odoo_version': release.version,
            'database': self.env.cr.dbname,
            'user': self.env.user.login,
            'company': self.env.company.name,
            'methods': self._site_link_methods(),
            # 19.0.0.2.4: the sign-in link opens ``return`` (a path here, or a full address on this site's host)
            'sso_return': True,
            'paths': self._site_link_paths(),
        }

    def _site_link_paths(self):
        """The named paths of this site a linked site may open (health's ``paths``, read by
        site.link._site_link_partner_url there): what another extension's ``res.users._site_link_paths()`` answers
        ({name: path}; no dependency on this connector needed), paths only."""
        Users = self.env['res.users'].sudo()
        if not hasattr(Users, '_site_link_paths'):
            return {}
        try:
            paths = Users._site_link_paths() or {}
        except Exception:  # noqa: BLE001 - another extension's hook never breaks the health check
            _logger.warning("site link: res.users._site_link_paths() failed", exc_info=True)
            return {}
        if not isinstance(paths, dict):
            return {}
        return {name: path for name, path in paths.items()
                if isinstance(name, str) and name and isinstance(path, str) and is_local_path(path)}

    @api.model
    @api.readonly
    def part_lookup(self, barcode):
        """The product with this barcode: {'found': False, 'barcode'} when none, else its name, internal reference,
        barcode, quantity on hand, unit cost, sale price, main vendor and image address."""
        self._site_link_check_caller()
        self._site_link_require_inventory()
        if not isinstance(barcode, str) or not barcode.strip():
            raise UserError(self.env._("barcode is required (text)."))
        barcode = barcode.strip()
        product = self.env['product.product'].sudo().search([('barcode', '=', barcode)], limit=1)
        if not product:
            return {'found': False, 'barcode': barcode}
        product = product.with_company(self.env.company)
        seller = product.seller_ids[:1] if 'seller_ids' in product._fields else None
        has_image = bool(product.with_context(bin_size=True).image_128)
        return {
            'found': True,
            'id': product.id,
            'name': product.display_name,
            'default_code': product.default_code or None,
            'barcode': product.barcode,
            'qty_available': product.qty_available,
            'uom': product.uom_id.name,
            'unit_cost': self._site_link_unit_cost(product),
            'sale_price': product.lst_price,
            'currency': self.env.company.currency_id.name,
            'vendor': seller.partner_id.name if seller else None,
            'image_url': f"{product.get_base_url()}/web/image/product.product/{product.id}/image_512"
                         if has_image else None,
        }

    @api.model
    def part_consume(self, product, qty, reference, note=None):
        """Take ``qty`` of ``product`` (a product id or a barcode) out of stock as internal use: one validated stock
        move from the company's main stock to "Internal use (linked sites)". Idempotent on ``reference``: a second
        call with the same reference consumes nothing and answers the first call's result (already_done True)."""
        self._site_link_check_caller()
        self._site_link_require_inventory()
        _ = self.env._
        if not isinstance(reference, str) or not reference.strip():
            raise UserError(_("reference is required (text): it makes the consumption happen once."))
        reference = reference.strip()[:200]
        Consumption = self.env['site.link.consumption'].sudo()
        done = Consumption.search([('reference', '=', reference)], limit=1)
        if done:
            return done._site_link_answer(already_done=True)
        if isinstance(qty, bool) or not isinstance(qty, (int, float)) or qty <= 0:
            raise UserError(_("qty must be a number above 0."))
        product = self._site_link_find_product(product)
        if product.type != 'consu':
            raise UserError(_("%s is not a stocked good (it is a service or a combo).", product.display_name))
        if 'tracking' in product._fields and product.tracking != 'none':
            raise UserError(_("%s is tracked by lot or serial number: consume it on this site.",
                              product.display_name))
        company = self.env.company
        warehouse = self.env['stock.warehouse'].sudo().search([('company_id', '=', company.id)], limit=1)
        if not warehouse.lot_stock_id:
            raise UserError(_("Company %s has no warehouse.", company.name))
        # the reference is taken first: a call running at the same time with the same reference waits on this row
        # (and then fails to serialize; Odoo retries it, and the retry answers already_done)
        self.env.cr.execute("""
            INSERT INTO site_link_consumption (reference, create_uid, write_uid, create_date, write_date)
            VALUES (%s, %s, %s, now() at time zone 'UTC', now() at time zone 'UTC')
            ON CONFLICT (reference) DO NOTHING RETURNING id
        """, (reference, self.env.uid, self.env.uid))
        row = self.env.cr.fetchone()
        if not row:
            Consumption.invalidate_model()
            return Consumption.search([('reference', '=', reference)], limit=1)._site_link_answer(already_done=True)
        source = warehouse.lot_stock_id
        dest = self._site_link_consume_location(company)
        Move = self.env['stock.move'].sudo().with_company(company)
        move_vals = {
            'origin': reference,
            'company_id': company.id,
            'product_id': product.id,
            'product_uom': product.uom_id.id,
            'product_uom_qty': qty,
            'location_id': source.id,
            'location_dest_id': dest.id,
            'picked': True,
            'move_line_ids': [(0, 0, {
                'product_id': product.id,
                'product_uom_id': product.uom_id.id,
                'quantity': qty,
                'location_id': source.id,
                'location_dest_id': dest.id,
            })],
        }
        if note and 'description_picking_manual' in Move._fields:
            move_vals['description_picking_manual'] = note
        move = Move.create(move_vals)
        move._action_done()
        if move.state != 'done':
            raise UserError(_("The stock move for %s could not be validated.", product.display_name))
        unit_cost = self._site_link_unit_cost(product)
        total = abs(move.value) if 'value' in move._fields and move.value else unit_cost * qty
        currency = company.currency_id
        consumption = Consumption.browse(row[0])
        consumption.write({
            'move_id': move.id,
            'product_id': product.id,
            'product_name': product.display_name,
            'qty': qty,
            'uom': product.uom_id.name,
            'unit_cost': float_round(total / qty, precision_digits=6),
            'total_cost': currency.round(total),
            'currency': currency.name,
            'note': note or False,
        })
        return consumption._site_link_answer(already_done=False)


    # ------------------------------------------------------------------ the shared inbox (soft)

    @api.model
    @api.readonly
    def inbox_unread(self, login):
        """How many conversations wait for a reply for this site's user ``login`` (Communication Flows' "Pop up new
        client messages": the conversations they may see whose last message came from the customer, until anyone
        answers): {count, enabled}. ``enabled`` False: the popups are off here (count 0). An unknown, archived or
        portal login: count 0. Read only, not logged (the Staff App asks every minute)."""
        self._site_link_check_caller()
        if not self._site_link_has_inbox():
            raise UserError(self.env._("This site has no shared inbox: it offers no unread count."))
        if not isinstance(login, str) or not login.strip():
            raise UserError(self.env._("login is required (text)."))
        Users = self.env['res.users'].sudo()
        user = Users.search([('login', '=ilike', escape_like(login.strip()))], limit=1)
        count = self.env['omni.conversation'].sudo()._cfd_popup_waiting_count(user if not user.share else Users)
        if count is None:
            return {'count': 0, 'enabled': False}
        return {'count': int(count or 0), 'enabled': True}

    # ------------------------------------------------------------------ the staff clock (soft)

    @api.model
    @api.readonly
    def staff_clock(self, login):
        """Whether this site's user ``login`` is clocked in now (a staff app's shift clock, answered by another
        extension's ``res.users._site_link_staff_clock(user)``; no dependency): {clocked_in, since}, ``since`` the
        clock-in time in UTC ('YYYY-MM-DD HH:MM:SS') or None. An unknown, archived or portal login: not clocked in.
        Read only, not logged (the linked site asks every couple of minutes)."""
        self._site_link_check_caller()
        if not self._site_link_has_staff_clock():
            raise UserError(self.env._("This site has no staff clock: it offers no clock-in state."))
        if not isinstance(login, str) or not login.strip():
            raise UserError(self.env._("login is required (text)."))
        Users = self.env['res.users'].sudo()
        user = Users.search([('login', '=ilike', escape_like(login.strip()))], limit=1)
        answer = None
        if user and not user.share:
            try:
                answer = Users._site_link_staff_clock(user)
            except Exception:  # noqa: BLE001 - another extension's hook never breaks the answer
                _logger.warning("site link: res.users._site_link_staff_clock() failed", exc_info=True)
        if not isinstance(answer, dict) or not answer.get('clocked_in'):
            return {'clocked_in': False, 'since': None}
        since = answer.get('since')
        return {'clocked_in': True, 'since': since if isinstance(since, str) and since else None}

    # ------------------------------------------------------------------ single sign-on

    @api.model
    def sso_ticket(self, login):
        """A one-time sign-in link for this site's user ``login``: {url: '/site_link/sso/<token>', expires_in: 60}.
        Only for active internal users in the group "Site Link: single sign-on allowed", never user ids 1 and 2.
        Every ticket, given or refused, is in the log."""
        self._site_link_check_caller()
        _ = self.env._
        Log = self.env['site.link.log'].sudo()
        if not isinstance(login, str) or not login.strip():
            raise UserError(_("login is required (text)."))
        login = login.strip()
        user = self.env['res.users'].sudo().with_context(active_test=False).search(
            [('login', '=ilike', escape_like(login))], limit=1)
        Ticket = self.env['site.link.sso.ticket'].sudo()
        refusal = Ticket._site_link_sso_refusal(user)
        if refusal:
            Log._site_link_event('sso', 'sso_ticket', _("Ticket refused for %(login)s (asked by %(caller)s): %(why)s",
                                                         login=login, caller=self.env.user.login, why=refusal),
                                 status=403, user=user or None, own_cursor=True)
            raise UserError(_("No single sign-on for %(login)s: %(why)s.", login=login, why=refusal))
        token = Ticket._site_link_issue(user)
        Log._site_link_event('sso', 'sso_ticket', _("Ticket given for %(login)s (asked by %(caller)s).",
                                                     login=user.login, caller=self.env.user.login), user=user)
        return {'url': f"/site_link/sso/{token}", 'expires_in': SSO_TTL}

    # ------------------------------------------------------------------ one employee list

    def _site_link_shop_groups(self):
        """The groups shop access gives: single sign-on, and the Shop Access Groups of the active linked sites."""
        groups = self.env.ref(SSO_GROUP).sudo()
        return groups | self.env['site.link'].sudo().search([]).shop_group_ids

    @api.model
    def user_sync(self, users):
        """The linked site's employee list, ``users`` = [{login, name, email, active, shop_access}], made true here:
        users matched by login (case does not matter); a missing user is made (internal, without a password: it signs
        in by single sign-on) only when it is active and ``shop_access`` is True, otherwise only existing users change; name and email kept up to date; archived there = archived here (and back);
        ``shop_access`` True gives the shop groups (single sign-on and the Shop Access Groups), False takes them away,
        null leaves them. Never user ids 1 and 2, administrators (Settings or Access Rights), the calling user or
        portal users: they are answered with ``skipped``. Users not in the list are left
        alone. Nothing is sent to anyone. Answers [{login, user_id, created, updated}]."""
        self._site_link_check_caller()
        _ = self.env._
        if not isinstance(users, list):
            raise UserError(_("users is required: a list of {login, name, email, active, shop_access}."))
        Users = self.env['res.users'].sudo().with_context(active_test=False, no_reset_password=True, **QUIET)
        shop_groups = self._site_link_shop_groups()
        internal = self.env.ref('base.group_user')
        answer, notes = [], []
        for entry in users:
            if not isinstance(entry, dict) or not isinstance(entry.get('login'), str) or not entry['login'].strip():
                raise UserError(_("Each user is an object with a login (text)."))
            login = entry['login'].strip()
            name = entry.get('name') if isinstance(entry.get('name'), str) and entry['name'].strip() else login
            name = name.strip()
            email = entry.get('email') if isinstance(entry.get('email'), str) else None
            email = (email or '').strip() or False
            active = entry.get('active', True) is not False
            shop = entry.get('shop_access')
            user = Users.search([('login', '=ilike', escape_like(login))], limit=1)
            row = {'login': login, 'user_id': user.id or None, 'created': False, 'updated': False}
            answer.append(row)
            if user and is_admin_user(user):
                row['skipped'] = _("administrator (user id 1 or 2, or Settings or Access Rights rights): never "
                                   "changed by the employee list")
                notes.append(_("%s skipped (administrator)", login))
                continue
            if user and (user == self.env.user or user.share):
                row['skipped'] = _("the calling user") if not user.share else _("portal user")
                continue
            if not user:
                # access to this site comes only with shop access: no user is made for anyone else
                if not active or shop is not True:
                    continue
                vals = {'login': login, 'name': name, 'email': email,
                        'group_ids': [(4, internal.id)] + [(4, g.id) for g in shop_groups]}
                user = Users.create(vals)
                row.update(user_id=user.id, created=True)
                notes.append(_("%s made", login))
                continue
            vals = {}
            if user.name != name:
                vals['name'] = name
            if (user.email or False) != email:
                vals['email'] = email
            if user.active != active:
                vals['active'] = active
            if shop is True:
                vals['group_ids'] = [(4, g.id) for g in shop_groups - user.group_ids]
            elif shop is False:
                vals['group_ids'] = [(3, g.id) for g in shop_groups & user.group_ids]
            if not vals.get('group_ids'):
                vals.pop('group_ids', None)
            if vals:
                user.write(vals)
                row['updated'] = True
                notes.append(_("%(login)s updated (%(fields)s)", login=login, fields=', '.join(sorted(vals))))
        self._site_link_served('user_sync', _("%(n)s employees received from %(caller)s. %(notes)s", n=len(users),
                                              caller=self.env.user.login, notes='; '.join(notes) or _("No change.")))
        return answer

    # ------------------------------------------------------------------ customers

    @staticmethod
    def _site_link_digits(phone):
        return re.sub(r'\D', '', phone or '')

    def _site_link_partner_answer(self, partner):
        return {'id': partner.id, 'name': partner.display_name, 'phone': partner.phone or None,
                'email': partner.email or None}

    def _site_link_find_partner(self, partner_id):
        if isinstance(partner_id, bool) or not isinstance(partner_id, int):
            raise UserError(self.env._("partner_id must be a contact id (number)."))
        partner = self.env['res.partner'].sudo().browse(partner_id).exists()
        if not partner:
            raise UserError(self.env._("No contact %s on this site.", partner_id))
        return partner

    def _site_link_partners_by_phone(self, phone, limit=10):
        """Contacts whose phone has the same digits (the last 8 must match, then all digits of the shorter one)."""
        digits = self._site_link_digits(phone)
        if len(digits) < 6:
            return self.env['res.partner'].sudo().browse()
        tail = digits[-8:]
        pattern = '%' + '%'.join(tail) + '%'
        candidates = self.env['res.partner'].sudo().search([('phone', '=like', pattern)], limit=200)
        return candidates.filtered(
            lambda p: (lambda d: d and (d.endswith(digits) or digits.endswith(d)))(self._site_link_digits(p.phone))
        )[:limit]

    @api.model
    def customer_search(self, query, limit=10):
        """Contacts by name, email or phone: [{id, name, phone, email}] (at most ``limit``, 50 at most)."""
        self._site_link_check_caller()
        if not isinstance(query, str) or len(query.strip()) < 2:
            raise UserError(self.env._("query is required (text, 2 characters at least)."))
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            limit = 10
        limit = min(limit, SEARCH_LIMIT_MAX)
        query = query.strip()
        Partner = self.env['res.partner'].sudo()
        found = Partner.search(['|', '|', ('name', 'ilike', query), ('email', 'ilike', query),
                                ('phone', 'ilike', query)], limit=limit)
        if len(found) < limit and len(self._site_link_digits(query)) >= 6:
            found |= self._site_link_partners_by_phone(query, limit)
        self._site_link_served('customer_search', self.env._("%(n)s contacts for \"%(q)s\".", n=len(found[:limit]),
                                                              q=query))
        return [self._site_link_partner_answer(p) for p in found[:limit]]

    @api.model
    def customer_create(self, name, phone=None, email=None):
        """A new contact, or the existing one with this email or phone: {id, name, created}."""
        self._site_link_check_caller()
        _ = self.env._
        if not isinstance(name, str) or not name.strip():
            raise UserError(_("name is required (text)."))
        for label, value in (('phone', phone), ('email', email)):
            if value is not None and not isinstance(value, str):
                raise UserError(_("%s must be text.", label))
        email = (email or '').strip() or None
        phone = (phone or '').strip() or None
        Partner = self.env['res.partner'].sudo()
        existing = Partner.browse()
        if email:
            existing = Partner.search([('email', '=ilike', escape_like(email))], limit=1)
        if not existing and phone:
            existing = self._site_link_partners_by_phone(phone, 1)
        if existing:
            return {'id': existing.id, 'name': existing.display_name, 'created': False}
        partner = Partner.with_context(**QUIET).create({'name': name.strip(), 'phone': phone or False,
                                                        'email': email or False})
        self._site_link_served('customer_create', _("Contact %(name)s (%(id)s) made.", name=partner.display_name,
                                                    id=partner.id))
        return {'id': partner.id, 'name': partner.display_name, 'created': True}

    @api.model
    def customer_bikes(self, partner_id):
        """The contact's bikes where a customer bike model is installed: [{id, name, serial}] ([] elsewhere)."""
        self._site_link_check_caller()
        partner = self._site_link_find_partner(partner_id)
        Bike = self._site_link_bike_model()
        if Bike is None:
            self._site_link_served('customer_bikes', self.env._("No bike model on this site."))
            return []
        bikes = Bike.search([('partner_id', 'child_of', partner.commercial_partner_id.id)])
        answer = []
        for bike in bikes:
            serial = bike.frame_serial if 'frame_serial' in bike._fields else None
            if not serial and 'lot_id' in bike._fields and bike.lot_id:
                serial = bike.lot_id.name
            answer.append({'id': bike.id, 'name': bike.display_name, 'serial': serial or None})
        self._site_link_served('customer_bikes', self.env._("%(n)s bikes of contact %(id)s.", n=len(answer),
                                                             id=partner.id))
        return answer

    # ------------------------------------------------------------------ customer repairs (quotation, invoice)

    def _site_link_parse_lines(self, lines):
        """``lines`` checked: (parts, services). parts: [(product, qty)] of goods, one per product; services:
        [(name, price, hours, product or None)] (labour, or a service product given by id or barcode)."""
        _ = self.env._
        if not isinstance(lines, list) or not lines:
            raise UserError(_("lines is required: a list of {product, qty} (parts) and {service, price, hours} "
                              "(labour)."))
        parts, services = {}, []

        def number(value, label, allow_none=False):
            if value is None and allow_none:
                return None
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise UserError(_("%s must be a number (0 or more).", label))
            return float(value)

        for line in lines:
            if not isinstance(line, dict):
                raise UserError(_("Each line is an object: {product, qty} or {service, price, hours}."))
            if 'service' in line:
                name = line.get('service')
                if not isinstance(name, str) or not name.strip():
                    raise UserError(_("service is the labour's name (text)."))
                services.append((name.strip(), number(line.get('price', 0), 'price'),
                                 number(line.get('hours'), 'hours', allow_none=True), None))
            elif 'product' in line:
                qty = number(line.get('qty', 1), 'qty')
                if not qty:
                    raise UserError(_("qty must be a number above 0."))
                product = self._site_link_find_product(line['product'])
                if not product.sale_ok:
                    raise UserError(_("%s cannot be sold.", product.display_name))
                if product.type == 'service':
                    services.append((product.display_name, None, None, (product, qty)))
                elif product.type == 'combo':
                    raise UserError(_("%s is a combo: send its parts.", product.display_name))
                else:
                    parts[product] = parts.get(product, 0.0) + qty
            else:
                raise UserError(_("Each line needs product (a part) or service (labour)."))
        return list(parts.items()), services

    def _site_link_lines_hash(self, partner, parts, services, note, bike):
        data = [partner.id, [(p.id, q) for p, q in parts],
                [(n, pr, h, (s[0].id, s[1]) if s else None) for n, pr, h, s in services], note or '', bike]
        return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()

    def _site_link_labour_product(self, company):
        """The service product for typed labour lines, made once (internal reference SITE_LINK_LABOUR)."""
        Product = self.env['product.product'].sudo().with_context(active_test=False)
        product = Product.search([('default_code', '=', LABOUR_PRODUCT_CODE),
                                  ('company_id', 'in', [company.id, False])], limit=1)
        if not product:
            vals = {'name': self.env._("Repair labour"), 'type': 'service', 'default_code': LABOUR_PRODUCT_CODE,
                    'sale_ok': True, 'purchase_ok': False, 'list_price': 0.0}
            if 'invoice_policy' in self.env['product.template']._fields:
                vals['invoice_policy'] = 'order'
            product = Product.create(vals)
        elif not product.active:
            product.active = True
        return product

    @staticmethod
    def _site_link_service_label(name, hours):
        return f"{name} ({hours:g} h)" if hours else name

    def _site_link_service_sol_vals(self, order, labour, name, price, hours, service):
        if service:
            product, qty = service
            return {'order_id': order.id, 'product_id': product.id, 'product_uom_qty': qty}
        return {'order_id': order.id, 'product_id': labour.id, 'product_uom_qty': 1,
                'name': self._site_link_service_label(name, hours), 'price_unit': price}

    def _site_link_quote_text(self, note, bike_text):
        text = '\n'.join(t for t in (bike_text and self.env._("Bike: %s", bike_text), note) if t)
        return text or False

    def _site_link_order_answer(self, order):
        order = order.sudo()
        return {
            'order_id': order.id,
            'name': order.name,
            'state': order.state,
            'amount_total': order.amount_total,
            'currency': order.currency_id.name,
            'portal_url': order.get_base_url() + order.get_portal_url(),
        }

    def _site_link_repair_row(self, reference):
        """The site.link.repair row of ``reference`` (made when missing), locked against a call running at the same
        time with the same reference (that call waits, then fails to serialize; Odoo retries it)."""
        self.env['site.link.repair'].flush_model()
        self.env.cr.execute("""
            INSERT INTO site_link_repair (reference, create_uid, write_uid, create_date, write_date)
            VALUES (%s, %s, %s, now() at time zone 'UTC', now() at time zone 'UTC')
            ON CONFLICT (reference) DO NOTHING
        """, (reference, self.env.uid, self.env.uid))
        self.env.cr.execute("SELECT id FROM site_link_repair WHERE reference = %s FOR UPDATE", (reference,))
        row_id = self.env.cr.fetchone()[0]
        Row = self.env['site.link.repair'].sudo()
        Row.invalidate_model()
        return Row.browse(row_id)

    def _site_link_check_reference(self, reference):
        if not isinstance(reference, str) or not reference.strip():
            raise UserError(self.env._("reference is required (text): it makes the quote and the invoice happen "
                                       "once."))
        return reference.strip()[:200]

    def _site_link_find_row(self, reference):
        reference = self._site_link_check_reference(reference)
        row = self.env['site.link.repair'].sudo().search([('reference', '=', reference)], limit=1)
        order = self.env['sale.order'].sudo().browse(row.order_id).exists() if row.order_id else None
        if not order:
            raise UserError(self.env._("No repair quote with reference %s on this site.", reference))
        return row, order

    def _site_link_fill_repair(self, repair, order, parts, services, text):
        """The repair order's parts (its moves; Repair puts them on the quotation) and the quotation's labour."""
        Move = self.env['stock.move'].sudo().with_context(**QUIET)
        wanted = dict(parts)
        kept = set()
        for move in repair.move_ids.filtered(lambda m: m.repair_line_type == 'add' and m.state != 'cancel'):
            product = move.product_id
            if product in wanted and product not in kept:
                kept.add(product)
                if move.product_uom.compare(move.product_uom_qty, wanted[product]) != 0:
                    move.product_uom_qty = wanted[product]
                continue
            # a part no longer sent (or a second move of one part): off the repair and off the quotation
            sale_line = move.sale_line_id
            move.unlink()
            if sale_line.exists() and order.state in ('draft', 'sent'):
                sale_line.unlink()
        for product, qty in wanted.items():
            if product not in kept:
                move = Move.create({'repair_id': repair.id, 'repair_line_type': 'add', 'product_id': product.id,
                                    'product_uom_qty': qty, 'product_uom': product.uom_id.id,
                                    'company_id': repair.company_id.id})
                if 'repair_price_subtotal' in move._fields and move.sale_line_id and not move.price_unit:
                    # another extension prices repair parts by the move's unit price (and copies it to the
                    # quotation when the quantity changes): it gets the quotation's price
                    move.price_unit = move.sale_line_id.price_unit
        if 'service_line_ids' in repair._fields:
            # another extension's repair services: they go on the quotation by themselves
            repair.service_line_ids.unlink()
            labour = self._site_link_labour_product(repair.company_id) if any(not s[3] for s in services) else None
            vals = []
            for name, price, hours, service in services:
                if service:
                    product, qty = service
                    vals.append({'repair_id': repair.id, 'product_id': product.id, 'name': product.display_name,
                                 'price_unit': product.lst_price, 'product_uom_qty': qty,
                                 'product_uom_id': product.uom_id.id})
                else:
                    vals.append({'repair_id': repair.id, 'product_id': labour.id, 'product_uom_id': labour.uom_id.id,
                                 'name': self._site_link_service_label(name, hours), 'price_unit': price,
                                 'product_uom_qty': 1})
            if vals:
                self.env['repair.service.line'].sudo().with_context(**QUIET).create(vals)
            if 'customer_notes' in repair._fields:
                repair.customer_notes = text
            return
        # standard Repair: the quotation lines that are not parts are this call's (labour and the note)
        order.order_line.filtered(lambda line: not line.move_ids.repair_id).unlink()
        self._site_link_plain_lines(order, [], services, text)

    def _site_link_plain_lines(self, order, parts, services, text):
        SaleLine = self.env['sale.order.line'].sudo().with_context(**QUIET)
        vals = []
        if text:
            vals.append({'order_id': order.id, 'display_type': 'line_note', 'name': text, 'sequence': 1})
        vals += [{'order_id': order.id, 'product_id': p.id, 'product_uom_qty': q, 'sequence': 10} for p, q in parts]
        labour = self._site_link_labour_product(order.company_id) if any(not s[3] for s in services) else None
        vals += [dict(self._site_link_service_sol_vals(order, labour, *s), sequence=100) for s in services]
        if vals:
            SaleLine.create(vals)

    @api.model
    def repair_quote(self, reference, partner_id, lines, note=None, bike=None):
        """Make, or change (same ``reference``, while it is a quotation), the quotation for a customer repair.
        ``lines``: [{product (id or barcode), qty}] for parts, [{service: name, price, hours}] for labour (one line
        at ``price``; the hours show in its description). ``note``: text on the quotation. ``bike``: the customer
        bike's id (customer_bikes) or a description. Where Repair is installed, a repair order holds the parts and
        is linked to the quotation. Nothing is sent: the quotation stays a draft.
        Answers {order_id, name, state, amount_total, currency, portal_url}."""
        self._site_link_check_caller()
        self._site_link_require_sales()
        _ = self.env._
        reference = self._site_link_check_reference(reference)
        partner = self._site_link_find_partner(partner_id)
        if note is not None and not isinstance(note, str):
            raise UserError(_("note must be text."))
        note = (note or '').strip() or None
        parts, services = self._site_link_parse_lines(lines)
        Bike = self._site_link_bike_model()
        bike_record, bike_text = None, None
        if isinstance(bike, bool) or (bike is not None and not isinstance(bike, (int, str))):
            raise UserError(_("bike must be a bike id (number) or a description (text)."))
        if isinstance(bike, int):
            if Bike is None:
                raise UserError(_("This site has no customer bikes: send the bike as a description (text)."))
            bike_record = Bike.browse(bike).exists()
            if not bike_record:
                raise UserError(_("No bike %s on this site.", bike))
            if bike_record.partner_id.commercial_partner_id != partner.commercial_partner_id:
                raise UserError(_("Bike %(bike)s is not %(partner)s's.", bike=bike_record.display_name,
                                  partner=partner.display_name))
        elif isinstance(bike, str) and bike.strip():
            bike_text = bike.strip()
        fingerprint = self._site_link_lines_hash(partner, parts, services, note, bike)

        row = self._site_link_repair_row(reference)
        order = self.env['sale.order'].sudo().browse(row.order_id).exists() if row.order_id else None
        if order and row.lines_hash == fingerprint:
            return self._site_link_order_answer(order)
        if order and order.state not in ('draft', 'sent'):
            raise UserError(_("Quotation %(name)s (reference %(ref)s) is no longer a quotation (state %(state)s): it "
                              "can no longer change. Use a new reference for more work.", name=order.name,
                              ref=reference, state=order.state))
        if order and order.partner_id != partner:
            raise UserError(_("Reference %(ref)s is %(other)s's quotation, not %(partner)s's.", ref=reference,
                              other=order.partner_id.display_name, partner=partner.display_name))
        company = self.env.company
        text = self._site_link_quote_text(note, bike_text)
        repair = None
        if self._site_link_has_repair():
            Repair = self.env['repair.order'].sudo().with_company(company).with_context(**QUIET)
            repair = Repair.browse(row.repair_id).exists() if row.repair_id else Repair
            if not repair:
                repair_vals = {'partner_id': partner.id, 'company_id': company.id,
                               'internal_notes': _("Customer repair from a linked site, reference %s", reference)}
                if bike_record and 'bike_id' in Repair._fields:
                    repair_vals['bike_id'] = bike_record.id
                repair = Repair.create(repair_vals)
            elif bike_record and 'bike_id' in repair._fields and repair.bike_id != bike_record:
                repair.bike_id = bike_record
            if not order:
                order = (repair.sale_order_id or repair._create_sale_order()).sudo()
            self._site_link_fill_repair(repair, order, parts, services, text)
        else:
            if not order:
                order = self.env['sale.order'].sudo().with_company(company).with_context(**QUIET).create(
                    {'partner_id': partner.id, 'company_id': company.id})
            else:
                order.order_line.unlink()
            self._site_link_plain_lines(order, parts, services, text)
        if order.client_order_ref != reference:
            order.client_order_ref = reference
        row.write({'partner_id': partner.id, 'order_id': order.id, 'repair_id': repair.id if repair else 0,
                   'lines_hash': fingerprint})
        self._site_link_served('repair_quote', _("Quotation %(name)s for reference %(ref)s (%(lines)s lines).",
                                                 name=order.name, ref=reference, lines=len(lines)))
        return self._site_link_order_answer(order)

    def _site_link_invoices(self, order):
        return order.invoice_ids.filtered(lambda inv: inv.state != 'cancel' and inv.move_type == 'out_invoice')

    @api.model
    def repair_status(self, reference):
        """The quotation of ``reference``: {name, state, approved, invoiced, paid, amount_total, portal_url}.
        approved: the customer accepted it (it is a sales order); invoiced: it has an invoice (draft or posted);
        paid: all its posted invoices are paid."""
        self._site_link_check_caller()
        self._site_link_require_sales()
        row, order = self._site_link_find_row(reference)
        invoices = self._site_link_invoices(order)
        posted = invoices.filtered(lambda inv: inv.state == 'posted')
        self._site_link_served('repair_status', self.env._("Status of %(name)s, reference %(ref)s.", name=order.name,
                                                            ref=row.reference))
        return {
            'name': order.name,
            'state': order.state,
            'approved': order.state == 'sale',
            'invoiced': bool(invoices),
            'paid': bool(posted) and posted == invoices and all(
                inv.payment_state in ('paid', 'in_payment') for inv in posted),
            'amount_total': order.amount_total,
            'portal_url': order.get_base_url() + order.get_portal_url(),
        }

    def _site_link_finish_repair(self, repair):
        """The repair order done (its parts leave stock, the quotation's parts count as delivered)."""
        if repair.state in ('done', 'cancel'):
            return
        if repair.state == 'draft':
            repair._action_repair_confirm()
        if repair.state == 'confirmed':
            repair.action_repair_start()
        for move in repair.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
            if move.product_uom.compare(move.quantity, move.product_uom_qty) < 0:
                move.quantity = move.product_uom_qty
            move.picked = True
        repair.action_repair_done()

    @api.model
    def repair_invoice(self, reference):
        """The invoice of the accepted quotation of ``reference``, made once (a draft: it is never posted or sent
        here). Where Repair is installed the repair order is finished first, so its parts leave stock and are
        invoiced. Answers {invoice_id, name, state, amount_total, portal_url}."""
        self._site_link_check_caller()
        self._site_link_require_sales()
        _ = self.env._
        reference = self._site_link_check_reference(reference)
        order = self._site_link_find_row(reference)[1]
        row = self._site_link_repair_row(reference)
        Move = self.env['account.move'].sudo()
        invoice = Move.browse(row.invoice_id).exists() if row.invoice_id else Move
        if not invoice or invoice.state == 'cancel':
            invoice = self._site_link_invoices(order)[:1]
        if not invoice:
            if order.state != 'sale':
                raise UserError(_("Quotation %(name)s is not accepted yet: no invoice.", name=order.name))
            repair = self.env['repair.order'].sudo().browse(row.repair_id).exists() \
                if row.repair_id and self._site_link_has_repair() else None
            if repair:
                self._site_link_finish_repair(repair.with_context(**QUIET))
            try:
                invoice = order.with_context(**QUIET)._create_invoices()[:1]
            except UserError as exc:
                raise UserError(_("Quotation %(name)s has nothing to invoice yet (%(why)s).", name=order.name,
                                  why=exc.args[0])) from exc
            self._site_link_served('repair_invoice', _("Invoice %(id)s (draft) for %(name)s, reference %(ref)s.",
                                                       id=invoice.id, name=order.name, ref=reference))
        else:
            self._site_link_served('repair_invoice', _("Invoice %(id)s for %(name)s, reference %(ref)s, already "
                                                       "made.", id=invoice.id, name=order.name, ref=reference))
        if row.invoice_id != invoice.id:
            row.invoice_id = invoice.id
        return {
            'invoice_id': invoice.id,
            'name': invoice.name if invoice.name and invoice.name != '/' else None,
            'state': invoice.state,
            'amount_total': invoice.amount_total,
            'portal_url': invoice.get_base_url() + invoice.get_portal_url(),
        }
