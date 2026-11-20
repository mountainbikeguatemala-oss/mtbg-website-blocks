"""Expenses any module can record with the one expense form (owner, 2026-11-20: the shop site records a used purchase
as an expense "all in one go", with the same form as the tours' Staff App), without Tours:

* ``res.partner.mtbg_is_vendor``: the vendor contacts, one list for every form (Tours Core has the same field).
* ``mtbg.expense.category``: what an expense is (used parts, consumables...). A connector books each on its account.
* ``mtbg.expense.method``: what it was paid with (the shop's cash, the company card). A connector gives each the
  account the money left from.
* ``mtbg.expense.source``: the mixin of a model whose records are expenses (date, category, vendor, amount, paid with,
  receipt). A connector sends them (Zoho Connector 0.3.0: each one a Zoho Books expense, its receipt attached).
  ``_mtbg_expense_changed(deleted=False)`` is called after a create, a change of ``_mtbg_expense_fields`` and before a
  delete; the connectors extend it.
"""
from odoo import api, fields, models

SYNC_STATES = [('none', 'Not sent'), ('waiting', 'Waiting'), ('error', 'Error'), ('done', 'Sent'),
               ('skipped', 'Skipped')]
EXPENSE_FIELDS = ('date', 'amount', 'currency_id', 'category_id', 'method_id', 'vendor_id', 'receipt_id', 'name')


class ResPartnerVendor(models.Model):
    _inherit = 'res.partner'

    mtbg_is_vendor = fields.Boolean(string='Vendor', index=True,
                                    help="A business or person the company pays: offered as an expense's vendor")


class MtbgExpenseCategory(models.Model):
    _name = 'mtbg.expense.category'
    _description = 'Expense category'
    _order = 'sequence, name, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    in_app = fields.Boolean(string='Offered in the form', default=True,
                            help="Staff can pick it in the expense form (a category read from an accounting app "
                                 "starts unticked)")


class MtbgExpenseMethod(models.Model):
    _name = 'mtbg.expense.method'
    _description = 'Expense payment method'
    _order = 'sequence, name, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    in_app = fields.Boolean(string='Offered in the form', default=True,
                            help="Staff can pick it in the expense form (an account read from an accounting app "
                                 "starts unticked)")
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  help="Only expenses in this currency can be paid with it (empty: any)")


class MtbgExpenseSource(models.AbstractModel):
    _name = 'mtbg.expense.source'
    _description = 'An expense (shared fields)'

    date = fields.Date(required=True, default=fields.Date.context_today)
    name = fields.Char(string='Description')
    amount = fields.Monetary(required=True, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', required=True,
                                  default=lambda self: self.env.company.currency_id)
    category_id = fields.Many2one('mtbg.expense.category', string='Category', required=True, ondelete='restrict')
    method_id = fields.Many2one('mtbg.expense.method', string='Paid With', required=True, ondelete='restrict')
    vendor_id = fields.Many2one('res.partner', string='Vendor', ondelete='restrict')
    receipt_id = fields.Many2one('ir.attachment', string='Receipt', ondelete='set null')
    recorded_by_id = fields.Many2one('res.users', string='Recorded By', default=lambda self: self.env.user,
                                     readonly=True)
    # where a connector sent it (Zoho Connector: Zoho Books); without one: not sent
    expense_sync_state = fields.Selection(SYNC_STATES, string='Accounting', compute='_compute_expense_sync')
    expense_sync_error = fields.Char(string='Accounting Error', compute='_compute_expense_sync')
    expense_sync_url = fields.Char(string='Accounting Link', compute='_compute_expense_sync')

    def _compute_expense_sync(self):
        """A connector extends it (its state, its error, the expense's page there)."""
        for record in self:
            record.expense_sync_state = 'none'
            record.expense_sync_error = False
            record.expense_sync_url = False

    def action_mtbg_expense_open(self):
        """The expense where the connector sent it (a new tab)."""
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': self.expense_sync_url, 'target': 'new'} \
            if self.expense_sync_url else False

    def action_mtbg_expense_send(self):
        """Send again now (after an error): the connectors do it."""
        return True

    @api.model
    def _mtbg_expense_fields(self):
        """The fields whose change changes the expense where a connector sent it."""
        return set(EXPENSE_FIELDS)

    def _mtbg_expense_reference(self):
        """The expense's reference in another app (unique per model and record)."""
        self.ensure_one()
        what = '-'.join(self._name.split('.')[1:] or [self._name]).upper().replace('_', '-')  # no module prefix
        return f"ODOO-{what}-{self.id}"

    def _mtbg_expense_description(self):
        """One line saying what the expense was (the connectors send it)."""
        self.ensure_one()
        return " - ".join(p for p in (self.category_id.with_context(lang='en_US').name, self.name,
                                      f"at {self.vendor_id.name}" if self.vendor_id else '',
                                      f"recorded by {self.recorded_by_id.name}" if self.recorded_by_id else '') if p)

    def _mtbg_expense_changed(self, deleted=False):
        """Hook: these expenses were made or changed (``deleted``: are being deleted). The connectors extend it."""
        return True

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._mtbg_expense_receipt_link()
        records._mtbg_expense_changed()
        return records

    def write(self, vals):
        result = super().write(vals)
        if 'receipt_id' in vals:
            self._mtbg_expense_receipt_link()
        if self._mtbg_expense_fields() & set(vals):
            self._mtbg_expense_changed()
        return result

    def unlink(self):
        self._mtbg_expense_changed(deleted=True)
        return super().unlink()

    def _mtbg_expense_receipt_link(self):
        """The receipt's file belongs to its expense (its access follows the record)."""
        for record in self.filtered('receipt_id'):
            if record.receipt_id.res_model != record._name or record.receipt_id.res_id != record.id:
                record.receipt_id.sudo().write({'res_model': record._name, 'res_id': record.id})
