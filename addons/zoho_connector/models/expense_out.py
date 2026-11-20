"""Expenses recorded in Odoo, sent to Zoho Books (0.3.0, owner 2026-11-20: the shop site's used purchases, "thats
where we record the cost and thats where we create the expense all in one go"; the standing rule: every expense made
in Odoo is in Zoho Books, never kept here only).

Any model with the shared expense mixin (Admin Look's ``mtbg.expense.source``: date, category, paid with, vendor,
amount, receipt) is sent by itself, once its save is committed:

* booked on its category's Zoho Books account, paid through its payment method's account (Expense Categories and
  Expense Payment Methods: **Sync from Zoho Books** reads Zoho's expense accounts and its bank, cash and card accounts
  into those lists, unticked, for a manager to offer in the form),
* its vendor contact as the Zoho Books vendor (found by name, else made), its receipt attached,
* in its own currency, at Zoho Books' rate when that is not Zoho's base currency,
* described with what it is and who recorded it, its reference (``ODOO-<MODEL>-<id>``) the marker a retry finds it by.

A change updates it; a deletion deletes it. A category or method without an account, or Zoho refusing it: the error
shows on the record (Zoho Books: Error, with the reason) and the hourly run tries again; Writes allowed off: it waits.
"""
import hashlib
import json
import logging

from odoo import _, api, fields, models
from odoo.tools.translate import LazyTranslate
from odoo.exceptions import UserError

from ..services.client import Zoho, ZohoError, ZohoWriteBlocked

_logger = logging.getLogger(__name__)
_lt = LazyTranslate(__name__)

KIND = 'expense_out'
EXPENSE_TYPES = ('expense', 'cost_of_goods_sold', 'other_expense')
PAID_THROUGH_TYPES = ('bank', 'cash', 'credit_card', 'payment_clearing')


def _pages(books, path, key, params):
    rows, page = [], 1
    while page <= 20:
        body = books.request('GET', path, params=dict(params, page=page, per_page=200))
        rows += body.get(key) or []
        if not (body.get('page_context') or {}).get('has_more_page'):
            break
        page += 1
    return rows


def _books_for_sync(env):
    books = Zoho(env, 'books')
    if not books.enabled:
        raise UserError(_("Switch Zoho Books on first (Settings › Zoho)."))
    return books


class MtbgZohoSubextensionExpenses(models.AbstractModel):
    """This connector's own card in Settings › Zoho (0.3.2): Zoho Books On and Writes allowed on a site without the
    Tours' Zoho cards (the shop site), the run now, the two lists."""
    _inherit = 'mtbg.zoho.subextension'

    @api.model
    def _mtbg_card_defaults(self):
        return super()._mtbg_card_defaults() + [{
            'key': 'expenses_out', 'module': False, 'owner': 'zoho_connector', 'app': 'books', 'sequence': 15,
            'title': _lt("Zoho Books: expenses recorded in Odoo"),
            'summary': _lt("Expenses recorded in Odoo (e.g. the shop's used purchases) go to Zoho Books with their "
                           "receipt: each category's account, each payment method's paid through account."),
            'sync': 'mtbg.expense.source:_mtbg_zoho_sync_expenses',
            'links': [{'title': _lt("Expense Categories"), 'action': 'mtbg_backend_ui.action_mtbg_expense_category'},
                      {'title': _lt("Expense Payment Methods"),
                       'action': 'mtbg_backend_ui.action_mtbg_expense_method'}],
        }]


class MtbgExpenseCategoryZoho(models.Model):
    _inherit = 'mtbg.expense.category'

    zoho_account_id = fields.Char(string='Zoho Books Account ID', index=True, copy=False,
                                  help="The Zoho Books expense account this category is booked on")
    zoho_account_name = fields.Char(string='Zoho Books Account', readonly=True, copy=False)

    def action_mtbg_zoho_sync(self):
        """Zoho Books' expense accounts into the categories: a new account a new category (not offered yet); a known
        one keeps its name here, its Zoho name is updated."""
        books = _books_for_sync(self.env)
        try:
            chart = _pages(books, 'chartofaccounts', 'chartofaccounts', {'filter_by': 'AccountType.Active'})
        except ZohoError as error:
            raise UserError(_("Zoho Books: %s", error)) from error
        Category = self.sudo().with_context(active_test=False)
        known = {c.zoho_account_id: c for c in Category.search([('zoho_account_id', '!=', False)])}
        added = 0
        for row in chart:
            account_id, name = str(row.get('account_id') or ''), row.get('account_name') or ''
            if not account_id or row.get('account_type') not in EXPENSE_TYPES:
                continue
            if account_id in known:
                known[account_id].zoho_account_name = name
                continue
            Category.create({'name': name or account_id, 'zoho_account_id': account_id, 'zoho_account_name': name,
                             'in_app': False})
            added += 1
        return _notify(_("Zoho Books: %(added)s new categories (tick the ones staff may pick).", added=added))


class MtbgExpenseMethodZoho(models.Model):
    _inherit = 'mtbg.expense.method'

    zoho_paid_through_id = fields.Char(string='Zoho Books Paid Through ID', index=True, copy=False,
                                       help="The Zoho Books account the money left from (the cash's, the card's, "
                                            "the bank's)")
    zoho_paid_through_name = fields.Char(string='Zoho Books Paid Through', readonly=True, copy=False)

    def action_mtbg_zoho_sync(self):
        """Zoho Books' bank, cash and card accounts into the payment methods (new ones not offered yet)."""
        books = _books_for_sync(self.env)
        try:
            banks = _pages(books, 'bankaccounts', 'bankaccounts', {'filter_by': 'Status.Active'})
        except ZohoError as error:
            raise UserError(_("Zoho Books: %s", error)) from error
        Method = self.sudo().with_context(active_test=False)
        Currency = self.env['res.currency'].sudo().with_context(active_test=False)
        known = {m.zoho_paid_through_id: m for m in Method.search([('zoho_paid_through_id', '!=', False)])}
        added = 0
        for row in banks:
            account_id, name = str(row.get('account_id') or ''), row.get('account_name') or ''
            if not account_id or row.get('account_type') not in PAID_THROUGH_TYPES or not row.get('is_active', True):
                continue
            if account_id in known:
                known[account_id].zoho_paid_through_name = name
                continue
            currency = Currency.search([('name', '=', row.get('currency_code') or '')], limit=1)
            Method.create({'name': name or account_id, 'zoho_paid_through_id': account_id,
                           'zoho_paid_through_name': name, 'currency_id': currency.id or False, 'in_app': False})
            added += 1
        return _notify(_("Zoho Books: %(added)s new payment methods (tick the ones staff may pick).", added=added))


def _notify(message):
    return {'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'message': message, 'type': 'success', 'next': {'type': 'ir.actions.client',
                                                                        'tag': 'soft_reload'}}}


class MtbgExpenseSourceZoho(models.AbstractModel):
    _inherit = 'mtbg.expense.source'

    def _compute_expense_sync(self):
        super()._compute_expense_sync()
        Ref = self.env['mtbg.zoho.ref'].sudo()
        for record in self:
            ref = Ref._mtbg_find(record, 'books', KIND) if record.id else Ref
            if not ref:
                continue
            record.expense_sync_state = ref.state
            record.expense_sync_error = ref.error or False if ref.state in ('error', 'waiting') else False
            record.expense_sync_url = ref.zoho_url or False if ref.state == 'done' else False

    def action_mtbg_expense_send(self):
        """Send to Zoho Books now (after an error too)."""
        super().action_mtbg_expense_send()
        books = Zoho(self.env, 'books')
        if not books.enabled:
            raise UserError(_("Switch Zoho Books on first (Settings › Zoho)."))
        Ref = self.env['mtbg.zoho.ref'].sudo()
        cache = {}
        for record in self:
            record._mtbg_zoho_send(books, Ref._mtbg_set(record, 'books', KIND, state='waiting'), cache)
        return True

    # ------------------------------------------------------------------ queued, sent once committed
    def _mtbg_expense_changed(self, deleted=False):
        result = super()._mtbg_expense_changed(deleted=deleted)
        Ref = self.env['mtbg.zoho.ref'].sudo()
        for record in self:
            ref = Ref._mtbg_find(record, 'books', KIND)
            if deleted and not (ref and ref.zoho_id):
                if ref:
                    ref.write({'state': 'skipped', 'error': _("Deleted in Odoo before it was sent.")})
                continue
            # a deletion keeps its reference waiting: the run deletes the Zoho Books expense
            Ref._mtbg_set(record, 'books', KIND, state='waiting', error=False)
        cron = self.env.ref('zoho_connector.cron_zoho_expense_out', raise_if_not_found=False)
        if cron and self:
            cron.sudo()._trigger()
        return result

    @api.model
    def _mtbg_zoho_expense_models(self):
        """The models whose records are expenses (they have the mixin)."""
        return [name for name, model in self.env.registry.items()
                if not model._abstract and not model._transient
                and self.env.registry['mtbg.expense.source'] in model.__mro__]

    @api.model
    def _mtbg_zoho_sync_expenses(self, limit=50):
        """Cron (triggered after each save, and every hour for the retries)."""
        books = Zoho(self.env, 'books')
        if not books.enabled:
            return False
        Ref = self.env['mtbg.zoho.ref'].sudo()
        cache = {}
        self.env['res.partner']._mtbg_zoho_push_vendors(books, cache)
        models_ = self._mtbg_zoho_expense_models()
        todo = Ref.search([('system', '=', 'books'), ('kind', '=', KIND), ('res_model', 'in', models_),
                           ('state', 'in', ('waiting', 'error'))], order='id', limit=limit * 2)
        todo = (todo.filtered(lambda r: r.state == 'waiting') | todo._mtbg_retry_due())[:limit]
        for ref in todo:
            record = self.env[ref.res_model].sudo().browse(ref.res_id).exists()
            if record:
                record._mtbg_zoho_send(books, ref, cache)
            else:
                self._mtbg_zoho_deleted(books, ref)
        return True

    @api.model
    def _mtbg_zoho_deleted(self, books, ref):
        if not ref._mtbg_lock():
            return
        if not ref.zoho_id:
            ref.write({'state': 'skipped', 'error': _("Deleted in Odoo before it was sent.")})
            return
        try:
            with self.env.cr.savepoint():
                books.request('DELETE', f'expenses/{ref.zoho_id}')
                ref.write({'state': 'skipped',
                           'error': _("Deleted in Odoo: its Zoho Books expense %s was deleted.", ref.zoho_id)})
        except ZohoWriteBlocked:
            ref.write({'error': _("Waiting for Zoho Books “Writes allowed”.")})
        except ZohoError as error:
            ref.write({'state': 'error', 'error': str(error)[:500]})

    # ------------------------------------------------------------------ one expense
    def _mtbg_zoho_marker(self):
        return f"({self._mtbg_expense_reference()})"

    def _mtbg_zoho_rate(self, books, currency_code, day, cache):
        """Zoho Books' rate for the currency on that day, or None when it is Zoho's base currency."""
        if 'currencies' not in cache:
            cache['currencies'] = books.request('GET', 'settings/currencies').get('currencies') or []
        row = next((c for c in cache['currencies'] if c.get('currency_code') == currency_code), None)
        if not row:
            raise ZohoError(f"Zoho Books has no currency {currency_code}")
        if row.get('is_base_currency'):
            return str(row['currency_id']), None
        body = books.request('GET', f"settings/currencies/{row['currency_id']}/exchangerates",
                             params={'from_date': str(day), 'sort_column': 'effective_date'})
        rates = [r for r in body.get('exchange_rates') or [] if (r.get('effective_date') or '') <= str(day)]
        rates = rates or body.get('exchange_rates') or []
        if rates:
            return str(row['currency_id']), float(max(rates, key=lambda r: r.get('effective_date') or '')['rate'])
        # no rate typed in Zoho Books: Odoo's (Zoho's rate is base units per one of this currency)
        base = self.env['res.currency'].sudo().search(
            [('name', '=', next((c.get('currency_code') for c in cache['currencies'] if c.get('is_base_currency')),
                                ''))], limit=1)
        if not base:
            raise ZohoError(f"Zoho Books has no exchange rate for {currency_code} on {day}")
        return str(row['currency_id']), self.currency_id._convert(1.0, base, self.env.company, day, round=False)

    def _mtbg_zoho_payload(self, books, cache):
        """The expense's Zoho Books body, or a str saying what it waits for."""
        self.ensure_one()
        record = self.sudo()
        if not record.category_id.zoho_account_id:
            return _("The category %s has no Zoho Books account (Expense Categories).", record.category_id.name or '-')
        if not record.method_id.zoho_paid_through_id:
            return _("The payment method %s has no Zoho Books account (Expense Payment Methods).",
                     record.method_id.name or '-')
        body = {
            'account_id': record.category_id.zoho_account_id,
            'paid_through_account_id': record.method_id.zoho_paid_through_id,
            'date': fields.Date.to_string(record.date),
            'amount': record.currency_id.round(record.amount),
            'is_billable': False,
            'reference_number': record._mtbg_expense_reference()[:50],
            'description': f"{record._mtbg_expense_description()} {record._mtbg_zoho_marker()}"[:500],
        }
        currency_id, rate = record._mtbg_zoho_rate(books, record.currency_id.name, record.date, cache)
        body['currency_id'] = currency_id
        if rate:
            body['exchange_rate'] = rate
        if record.vendor_id:
            vendor_id = record.vendor_id._mtbg_zoho_vendor_ensure(books, cache.setdefault('vendors', {}))
            if vendor_id:
                body['vendor_id'] = vendor_id
        return body

    def _mtbg_zoho_find(self, books):
        """The expense a send made before (a retry after a timeout): its marker in the description."""
        marker = self._mtbg_zoho_marker()
        found = books.request('GET', 'expenses', params={'description_contains': marker, 'filter_by': 'Status.All'})
        return next((e for e in found.get('expenses') or [] if marker in (e.get('description') or '')), None)

    def _mtbg_zoho_send(self, books, ref, cache):
        self.ensure_one()
        Ref = self.env['mtbg.zoho.ref'].sudo()
        record = self.sudo()
        if not ref._mtbg_lock():
            return False
        try:
            with self.env.cr.savepoint():
                payload = record._mtbg_zoho_payload(books, cache)
                if isinstance(payload, str):
                    Ref._mtbg_set(record, 'books', KIND, state='error', error=payload)
                    return False
                receipt = record.receipt_id
                stamp = hashlib.sha1((json.dumps(payload, sort_keys=True, default=str)
                                      + (receipt.checksum or '')).encode()).hexdigest()
                if ref.zoho_id and ref.fingerprint == stamp:
                    Ref._mtbg_set(record, 'books', KIND, state='done')
                    return False
                expense_id = ref.zoho_id
                if not expense_id:
                    found = record._mtbg_zoho_find(books)
                    expense_id = str(found['expense_id']) if found else False
                if expense_id:
                    books.request('PUT', f'expenses/{expense_id}', json=payload, record=record)
                else:
                    expense_id = str(books.request('POST', 'expenses', json=payload,
                                                   record=record)['expense']['expense_id'])
                if receipt and receipt.raw:
                    books.request('POST', f'expenses/{expense_id}/receipt', record=record,
                                  files={'receipt': (receipt.name or 'receipt', receipt.raw,
                                                     receipt.mimetype or 'image/jpeg')})
                Ref._mtbg_set(record, 'books', KIND, state='done', zoho_id=expense_id, fingerprint=stamp)
                return True
        except ZohoWriteBlocked:
            Ref._mtbg_set(record, 'books', KIND, state='waiting',
                          error=_("Waiting for Zoho Books “Writes allowed”."))
        except (ZohoError, KeyError, ValueError) as error:
            _logger.warning("Zoho Books expense %s,%s failed: %s", record._name, record.id, error)
            Ref._mtbg_set(record, 'books', KIND, state='error', error=str(error)[:500])
        return False
