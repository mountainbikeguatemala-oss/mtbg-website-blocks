"""The protocol a site offers to its linked sites, called through Odoo's /json/2 API:

    POST /json/2/site.link.api/<method>   (Authorization: bearer <API key>, X-Odoo-Database: <db>)

The caller is the technical user of the API key; it needs the group "Site Link: calls from a linked site" (or to be
an administrator). The methods then work with the rights they need (sudo), in the user's company. The inventory
methods are offered only where Inventory is installed (soft check: no dependency). See README.md."""
from odoo import api, models, release
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_round

PROTOCOL_VERSION = 1
BASE_METHODS = ['health']
INVENTORY_METHODS = ['part_lookup', 'part_consume']
CONSUME_LOCATION_NAME = 'Internal use (linked sites)'


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

    def _site_link_methods(self):
        return BASE_METHODS + (INVENTORY_METHODS if self._site_link_has_inventory() else [])

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
        }

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
