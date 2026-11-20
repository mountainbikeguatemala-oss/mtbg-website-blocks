"""A vendor contact's Zoho Books vendor (vendor/form release 2, owner 2026-11-08: "vendor contacts in zoho books should
be vendors in odoo"; Zoho Connector's since 0.2.0, 2026-11-18): the contact itself holds its Zoho Books vendor id, for
every expense that names it (staff expenses, a unit's expenses). Kept apart from the customer's Zoho Books contact
(Invoicing's mtbg_zoho_contact_id), so a vendor is never treated as a customer.

* Which contact is a vendor: the ``mtbg_is_vendor`` tick of an extension that has one (a soft check: without it, no
  contact is queued by itself, and ``_mtbg_zoho_vendor_ensure`` still works for the contact an expense names).

* A vendor contact made in Odoo (typed in an expense form, added on the Vendors page) goes to Zoho Books in the
  background: found there by its name, else made, then linked (``_mtbg_zoho_push_vendors``, run first by the expense
  jobs; it waits while Books writes are off).
* ``_mtbg_zoho_vendor_ensure`` gives the id to send an expense with: the known one, else found or made by name.
"""
import logging

from odoo import api, fields, models

from ..services.client import ZohoError, ZohoWriteBlocked

_logger = logging.getLogger(__name__)

VENDOR_OUT = 'vendor_out'  # a vendor contact made in Odoo, pushed to Zoho Books


class ResPartnerZohoVendor(models.Model):
    _inherit = 'res.partner'

    mtbg_zoho_vendor_id = fields.Char(string='Zoho Books Vendor', index=True, copy=False,
                                      help="This vendor's Zoho Books vendor contact (empty: not in Zoho Books yet)")
    mtbg_zoho_vendor_synced_at = fields.Datetime(string='Vendor Synced', readonly=True, copy=False)
    mtbg_zoho_vendor_modified = fields.Char(readonly=True, copy=False,
                                            help="Zoho Books' last change of the vendor as read")
    mtbg_zoho_vendor_details_of = fields.Char(readonly=True, copy=False,
                                              help="The Zoho Books change its details (address, people) were read for")

    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        partners._mtbg_zoho_vendor_queue()
        return partners

    def write(self, vals):
        res = super().write(vals)
        if vals.get('mtbg_is_vendor'):
            self._mtbg_zoho_vendor_queue()
        return res

    def _mtbg_zoho_is_vendor(self):
        """Whether this contact is a vendor: the ``mtbg_is_vendor`` tick, when an extension gives contacts one."""
        self.ensure_one()
        return bool('mtbg_is_vendor' in self._fields and self.mtbg_is_vendor)

    @api.model
    def _mtbg_zoho_vendor_domain(self):
        """The domain of the vendor contacts (empty without a vendor tick)."""
        return [('mtbg_is_vendor', '=', True)] if 'mtbg_is_vendor' in self._fields else []

    @api.model
    def _mtbg_zoho_vendor_crons(self):
        """The xml ids of the jobs that push the waiting vendors (the first one found is triggered). Extensions that
        send expenses give theirs (0.3.0: the expenses recorded in Odoo, this connector's own)."""
        return ['zoho_connector.cron_zoho_expense_out']

    def _mtbg_zoho_vendor_queue(self):
        """The vendor contacts not in Zoho Books yet: waiting to be pushed (never their contact people, never one
        read from Zoho Books)."""
        if self.env.context.get('mtbg_zoho_vendor_sync'):
            return
        new = self.filtered(lambda p: p._mtbg_zoho_is_vendor() and not p.parent_id and not p.mtbg_zoho_vendor_id)
        if not new:
            return
        Ref = self.env['mtbg.zoho.ref'].sudo()
        for partner in new:
            if not Ref._mtbg_find(partner, 'books', VENDOR_OUT):
                Ref._mtbg_set(partner, 'books', VENDOR_OUT, state='waiting')
        for xmlid in self._mtbg_zoho_vendor_crons():
            cron = self.env.ref(xmlid, raise_if_not_found=False)
            if cron:
                cron.sudo()._trigger()
                break

    def _mtbg_zoho_vendor_ensure(self, books, cache=None):
        """The Zoho Books vendor to send an expense with, linked here: the known one, else found in Zoho Books by its
        name, else created there (Books writes on). Archived (merged away there): the active vendor of its name."""
        from odoo.addons.zoho_connector.services.vendors import find_or_create_vendor, vendor_key
        self.ensure_one()
        partner = self.sudo()
        if partner.mtbg_zoho_vendor_id and partner.active:
            return partner.mtbg_zoho_vendor_id
        key = vendor_key(partner.name)
        same = partner.search([('mtbg_zoho_vendor_id', '!=', False), ('parent_id', '=', False),
                               ('id', '!=', partner.id)] + partner._mtbg_zoho_vendor_domain()).filtered(
            lambda p: vendor_key(p.name) == key)[:1] if key else partner.browse()
        if same:
            return same.mtbg_zoho_vendor_id
        if partner.mtbg_zoho_vendor_id:
            return partner.mtbg_zoho_vendor_id
        vendor_id = find_or_create_vendor(books, partner.name, cache)
        if vendor_id and not partner.search_count([('mtbg_zoho_vendor_id', '=', vendor_id)]):
            partner.with_context(mtbg_zoho_vendor_sync=True).mtbg_zoho_vendor_id = vendor_id
        return vendor_id

    @api.model
    def _mtbg_zoho_push_vendors(self, books, cache=None, limit=50):
        """The vendor contacts made in Odoo and not yet in Zoho Books: found there or made, then linked. Writes off:
        they wait."""
        Ref = self.env['mtbg.zoho.ref'].sudo()
        for ref in Ref.search([('system', '=', 'books'), ('kind', '=', VENDOR_OUT), ('res_model', '=', self._name),
                               ('state', 'in', ('waiting', 'error'))], order='id', limit=limit):
            partner = self.sudo().with_context(active_test=False).browse(ref.res_id).exists()
            if not partner:
                ref.write({'state': 'skipped', 'error': False})
                continue
            try:
                with self.env.cr.savepoint():
                    contact_id = partner._mtbg_zoho_vendor_ensure(books, cache)
                    Ref._mtbg_set(partner, 'books', VENDOR_OUT, state='done', zoho_id=contact_id or False, error=False)
            except ZohoWriteBlocked:
                Ref._mtbg_set(partner, 'books', VENDOR_OUT, state='waiting',
                              error=self.env._("Waiting for Zoho Books “Writes allowed”."))
            except ZohoError as error:
                _logger.warning("Zoho Books vendor %s not pushed: %s", partner.name, error)
                Ref._mtbg_set(partner, 'books', VENDOR_OUT, state='error', error=str(error)[:500])
