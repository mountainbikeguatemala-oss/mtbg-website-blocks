"""One expense input form for the whole suite (owner, 2026-11-07: "you two should share the same input form for
expenses"): the Staff App's phone form and the back office's Add Expense (a departure, a unit, the Expenses page)
are one component, MtbgExpenseForm (static/src/expense_form), driven by this server side.

An extension brings a *target* (what an expense of it is, how it is saved) by inheriting ``mtbg.expense.form``:

* ``_mtbg_expense_targets()``: ``dict(super()._mtbg_expense_targets(), <target>={'model': '<its model>'})``
* ``_mtbg_ef_<target>_load(params)``: the form's schema (title, fields, values, receipt, readonly, can_delete)
* ``_mtbg_ef_<target>_save(params, values)``: ``{'id': ..., 'message': ...}``; a UserError's text is shown
* ``_mtbg_ef_<target>_delete(params, record_id)``
* ``_mtbg_ef_<target>_search(params, field, term)``: ``[{'value': id, 'label': str}]``

Every target's form has the same four standard fields (owner, 2026-11-08: "all expense entry forms should be the same
across all modules, they all need vendor and category as well as amount, date"): Date, Category, Vendor and Amount,
all required, the same labels and kinds, made by ``_mtbg_ef_standard()`` (``mtbg_load`` refuses a schema without
them). The vendor is a vendor contact (res.partner ``mtbg_is_vendor``), one list for the whole suite:
``_mtbg_ef_vendor_search()`` finds them, ``_mtbg_ef_vendor()`` turns the picked or typed one into the contact (made
when new, never a rider's or a customer's contact).

Field kinds: choice, select (with search), typeahead (with create), date, money (with a currency select), number,
text, textarea, check, info, tags (several options picked at once, as chips: the value a list of option values). A choice may carry ``'then': '<a select's name>'`` (owner, 2026-11-09: "put the Paid by
buttons in the paid with section. Click a button (mandatory) and then it displays the paid through options as a
popup"): that select is drawn under its buttons once one is tapped, its list opened right away (the phone's own
picker; one option left: taken).

As few fields at once as can be (owner, 2026-11-09: "no one is going to fill it out if there are 12+ fields"): the
one order's fields show, and any other field only when it must be filled in and isn't yet (a ``with`` field goes
with its own); the rest (the date already today, notes, a rate...) fold under "More details". ``'main': True`` /
``'more': True`` on a field overrides. A field's ``visible`` / ``required`` may be a condition ``{field: value | [values] |
{'not': [values]}}`` (every key holds).

The phone's sheet (owner, 2026-11-16): ``'top': True`` draws a field above the receipt (the type's big buttons, never
under the receipt's box); a choice's option with ``'minor': True`` is a small button (under More details on the phone),
never a big one, and ``'sets': {field: value}`` sets other fields with it (a type's button, its Category); a field with
``'fold': {condition}`` shows as one line with its value and "Change" while the condition holds (the Category the
button set); a select with ``'lock_single': True`` is read only when one option is left (its options' ``only``
conditions: the currency of the account it was paid through). The Staff App's forms (``params['app']``, or the
schema's ``'touch': True``) draw every field large, for fingers (48px tap targets, 16px text). Core holds no expense itself: the targets' own rules decide everything."""
import re
import unicodedata

from odoo import _, api, models
from odoo.exceptions import UserError

KINDS = {'choice', 'select', 'typeahead', 'date', 'money', 'number', 'text', 'textarea', 'check', 'info', 'tags'}
STANDARD = ('date', 'category_id', 'vendor_id', 'amount')
# every expense form's order (owner, 2026-11-09: "Order on the expense form (universal) 1. Departure, 2. Ammount,
# 3. Paid by, 4 Vendor 5. description"), then the Category, then the target's other fields in their own order. A field
# with ``'with': '<name>'`` stays right after that one (a staff member after Paid by, a fill-up's after the Category).
ORDER = ('departure_id', 'amount', 'paid_by', 'vendor_id', 'name', 'category_id')


def vendor_key(name):
    """A vendor's name to match on: no accents, case, punctuation or extra spaces."""
    text = unicodedata.normalize('NFKD', name or '')
    text = ''.join(c for c in text if not unicodedata.combining(c)).lower()
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', text).split())


class MtbgExpenseForm(models.AbstractModel):
    _name = 'mtbg.expense.form'
    _description = 'Expense input form (shared)'

    @api.model
    def _mtbg_expense_targets(self):
        """{target: {'model': ...}}: what the form can record; each extension adds its own."""
        return {}

    @api.model
    def _mtbg_ef_method(self, target, verb):
        if target not in self._mtbg_expense_targets():
            raise UserError(_("Nothing records expenses of this kind here (%s).", target))
        return getattr(self, f'_mtbg_ef_{target}_{verb}')

    @api.model
    def mtbg_load(self, target, params=None):
        schema = self._mtbg_ef_method(target, 'load')(dict(params or {}))
        for field in schema.get('fields', []):
            if field.get('kind') not in KINDS:
                raise UserError(_("Unknown kind of field in the expense form: %s", field.get('kind')))
        names = {field.get('name') for field in schema.get('fields', [])}
        missing = [name for name in STANDARD if name not in names]
        if missing:  # every expense form has them (owner, 2026-11-08)
            raise UserError(_("This expense form lacks its standard fields: %s", ", ".join(missing)))
        schema['fields'] = self._mtbg_ef_ordered(schema.get('fields', []))
        schema.setdefault('values', {})
        schema.setdefault('receipt', {})
        schema.setdefault('readonly', False)
        schema.setdefault('can_delete', False)
        return dict(schema, target=target)

    @api.model
    def _mtbg_ef_ordered(self, form_fields):
        """The fields in the one order (ORDER, then the rest as the target gave them), each ``with`` field right after
        its own (in the target's order)."""
        names = {f.get('name') for f in form_fields}
        attached = {}
        for field in form_fields:
            anchor = field.get('with')
            if anchor and anchor in names and anchor != field.get('name'):
                attached.setdefault(anchor, []).append(field)
        lead = sorted((f for f in form_fields if f.get('name') in ORDER and f not in sum(attached.values(), [])),
                      key=lambda f: ORDER.index(f['name']))
        rest = [f for f in form_fields if f not in lead and not any(f in group for group in attached.values())]
        ordered, seen = [], set()

        def place(field):
            if id(field) in seen:
                return
            seen.add(id(field))
            ordered.append(field)
            for follower in attached.get(field.get('name'), []):
                place(follower)
        for field in lead + rest:
            place(field)
        for field in form_fields:  # a ``with`` whose anchor is itself attached in a loop: never lost
            place(field)
        for field in ordered:  # the one order's fields always show; the form folds others (see the JS)
            if field.get('name') in ORDER:
                field.setdefault('lead', True)
        return ordered

    @api.model
    def mtbg_save(self, target, params, values):
        return self._mtbg_ef_method(target, 'save')(dict(params or {}), dict(values or {}))

    @api.model
    def mtbg_delete(self, target, params, record_id):
        return self._mtbg_ef_method(target, 'delete')(dict(params or {}), int(record_id))

    @api.model
    def mtbg_search(self, target, params, field, term=''):
        return self._mtbg_ef_method(target, 'search')(dict(params or {}), field, (term or '').strip())

    # ------------------------------------------------------------------ the standard fields
    @api.model
    def _mtbg_ef_standard(self, categories, currencies=None, date_max=None, amount_label=None):
        """Date, Category, Vendor, Amount (and its currency when ``currencies`` are offered): every form's own, in this
        order, all required. ``categories``: [{'value', 'label'}] (the target's). The amount's value key is ``amount``
        and its currency's ``currency_id``."""
        date = {'name': 'date', 'kind': 'date', 'label': _("Date"), 'required': True}
        if date_max:
            date['max'] = date_max
        fields_ = [
            date,
            {'name': 'category_id', 'kind': 'select', 'label': _("Category"), 'required': True, 'options': categories},
            {'name': 'vendor_id', 'kind': 'typeahead', 'label': _("Vendor"), 'required': True, 'create': True,
             'placeholder': _("Pick a vendor or add a new one")},
            {'name': 'amount', 'kind': 'money', 'label': amount_label or _("Amount"), 'required': True,
             'currency_field': 'currency_id'},
        ]
        if currencies is not None:
            fields_.append({'name': 'currency_id', 'kind': 'select', 'label': _("Currency"), 'required': True,
                            'options': [{'value': c.id, 'label': c.name} for c in currencies]})
        return fields_

    @api.model
    def _mtbg_ef_vendor_value(self, partner):
        """A vendor contact as the form shows it."""
        return {'value': partner.id, 'label': partner.name} if partner else False

    @api.model
    def _mtbg_ef_vendor_search(self, term, recent=None, limit=8):
        """The vendor picker: vendor contacts matching what is typed (the name's start first), else ``recent`` ones."""
        Partner = self.env['res.partner'].sudo()
        if term:
            vendors = [('mtbg_is_vendor', '=', True), ('parent_id', '=', False)]  # the businesses, not their people
            found = Partner.search(vendors + [('name', '=ilike', term + '%')], limit=limit, order='name')
            found |= Partner.search(vendors + [('name', 'ilike', term), ('id', 'not in', found.ids)],
                                    limit=max(0, limit - len(found)), order='name')
        else:
            found = (recent or Partner).filtered(lambda p: p.active and p.mtbg_is_vendor)[:limit]
        return [{'value': p.id, 'label': p.name} for p in found]

    @api.model
    def _mtbg_ef_vendor(self, value, required=True):
        """The vendor contact picked (``{'value': id}``) or typed (``{'label': name}``): an existing vendor contact of
        that name (any spelling), else a new one (a company, a vendor). Never a rider's or a customer's contact."""
        Partner = self.env['res.partner'].sudo()
        value = value if isinstance(value, dict) else {'value': value} if isinstance(value, int) else {'label': value}
        partner = Partner.browse(int(value.get('value') or 0)).exists()
        if partner and partner.mtbg_is_vendor and not partner.parent_id:
            return partner
        name = ' '.join((value.get('label') or (partner.name if partner else '') or '').split())[:120]
        key = vendor_key(name)
        if not key:
            if required:
                raise UserError(_("Pick the vendor, or add it"))
            return Partner
        same = Partner.with_context(active_test=False).search(
            [('mtbg_is_vendor', '=', True), ('parent_id', '=', False)]).filtered(
            lambda p: vendor_key(p.name) == key)
        if same:
            return same.sorted(lambda p: (not p.active, p.id))[:1]
        return Partner.create({'name': name, 'is_company': True, 'mtbg_is_vendor': True})

    @api.model
    def _mtbg_action(self, target, params=None, title=None):
        """The back office's Add Expense / an expense opened: the form in a dialog (a button returns this)."""
        return {'type': 'ir.actions.client', 'tag': 'mtbg_expense_form', 'target': 'new',
                'name': title or _("Add Expense"), 'params': {'target': target, 'params': dict(params or {})}}
