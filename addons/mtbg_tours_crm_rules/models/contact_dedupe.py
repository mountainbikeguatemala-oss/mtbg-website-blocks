"""De-duplicate a contact (owner, 2026-11-21: "In this settings menu for a contact we would never have a use for
duplicate let's remove that and add the option to "de-duplicate"").

* **No Duplicate** on a contact: the contact's form and list lose Odoo's Duplicate (the gear menu, the list's Actions
  menu), on every contact form and list (``duplicate="0"`` set when the view loads). Other models keep theirs.
* **De-duplicate** in the contact's gear menu (a server action, ``action_mtbg_dedupe``): the likely duplicates of
  this contact, among the active contacts of the same kind (a person with persons, a company with companies), never
  its own company or its people:

  - the same email (case aside),
  - the same phone (its digits, with or without the country code: the last 8 digits),
  - the same name, case and a trailing " (copy)" / " (copia)" aside (Odoo's Duplicate made those).

  They open in Odoo's own merge dialog (Contacts' Merge), the most complete one proposed as the contact kept; a person
  checks and clicks Merge Contacts: nothing is merged without that click. None found: a notice says so.
* **The contact kept** follows the contact rule (owner, 2026-10-29): the fuller details win (the key details filled,
  a full name over "G G", a phone with its country code); on a tie the stronger source (with Tours: where each detail
  came from, booking / payment > pre-tour > contact form > newsletter > live chat), then the one with the most linked
  records (bookings, invoices, messages...), then the oldest. A "(copy)" never wins over its original by default.
* **The merge** (Odoo's): every link to the merged contacts moves to the one kept (bookings, invoices, messages and
  chatter, followers, activities, attachments; also the links kept as a model and an id: message logs, external ids,
  short links). Never blanks out: the kept contact's details stay, the empty ones filled from the others, and each
  detail filled is written in its chatter ("Phone: (none) → +502 5555 1234, from Ellie Pritchard (copy)").
"""
import re

from markupsafe import Markup, escape

from odoo import api, models
from odoo.tools import email_normalize

try:  # with Tours: the contact rule's source ranks (Core); without it, every source counts the same
    from odoo.addons.mtbg_tours_core.models.contact_rule import CONTACT_SOURCES, UNKNOWN_RANK
except ImportError:  # pragma: no cover - a site without Tours
    CONTACT_SOURCES, UNKNOWN_RANK = {}, 0

# Odoo's Duplicate names the copy "<name> (copy)" (in Spanish "(copia)"), once or more
COPY_SUFFIX = re.compile(r'(\s*\((copy|copia)\))+\s*$', re.IGNORECASE)
COPY_SUFFIX_SQL = r'(\s*\((copy|copia)\))+\s*$'
PHONE_DIGITS = 8  # the same phone: the same last 8 digits (with or without the country code)
MERGE_MAX = 3  # Odoo's merge takes 3 contacts at a time
# the details that make a contact complete (rule 2: fuller wins), when the site has them
KEY_FIELDS = ('email', 'phone', 'mobile', 'street', 'city', 'zip', 'state_id', 'country_id', 'vat', 'function',
              'website', 'image_1920', 'parent_id', 'lang', 'comment')
# matched by: strongest first (the order of the contacts proposed)
REASONS = ('email', 'phone', 'name')


def _base_name(name):
    return ' '.join(COPY_SUFFIX.sub('', name or '').split()).casefold()


def _is_copy(name):
    return bool(COPY_SUFFIX.search(name or ''))


def _phone_tail(value):
    digits = ''.join(ch for ch in str(value or '') if ch.isdigit())
    return digits[-PHONE_DIGITS:] if len(digits) >= PHONE_DIGITS else ''


class ResPartnerDedupe(models.Model):
    _inherit = 'res.partner'

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        """No Duplicate on a contact (owner, 2026-11-21): off on every contact form and list."""
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type in ('form', 'list'):
            arch.set('duplicate', '0')
        return arch, view

    # -- finding them --------------------------------------------------------------------------------------------

    def _mtbg_dedupe_phone_tails(self):
        self.ensure_one()
        return {t for t in (_phone_tail(self[f]) for f in ('phone', 'mobile') if f in self._fields) if t}

    def _mtbg_dedupe_find(self):
        """{partner: reason} of this contact's likely duplicates (reason: 'email', 'phone' or 'name', the strongest
        one), the active contacts of the same kind, never its own company or its people."""
        self.ensure_one()
        self.env['res.partner'].flush_model()
        cr = self.env.cr
        found = {}

        def add(ids, reason):
            for pid in ids:
                found.setdefault(pid, reason)

        email = email_normalize(self.email or '')
        if email:
            cr.execute("SELECT id FROM res_partner WHERE email_normalized = %s AND id != %s", (email, self.id))
            add([r[0] for r in cr.fetchall()], 'email')
        tails = self._mtbg_dedupe_phone_tails()
        if tails:
            columns = [f for f in ('phone', 'mobile') if f in self._fields and self._fields[f].store]
            where = ' OR '.join(
                "right(regexp_replace(coalesce(%s, ''), '\\D', '', 'g'), %d) = ANY(%%s)" % (c, PHONE_DIGITS)
                for c in columns)
            cr.execute("SELECT id FROM res_partner WHERE id != %%s AND (%s)" % where,
                       [self.id] + [list(tails)] * len(columns))
            add([r[0] for r in cr.fetchall()], 'phone')
        base = _base_name(self.name)
        if len(base) > 1:
            cr.execute(r"""SELECT id FROM res_partner WHERE id != %s
                           AND lower(regexp_replace(regexp_replace(coalesce(name, ''), %s, '', 'i'), '\s+', ' ', 'g'))
                               = %s""", (self.id, COPY_SUFFIX_SQL, base))
            add([r[0] for r in cr.fetchall()], 'name')
        if not found:
            return {}
        family = self.parent_id | self.child_ids
        others = self.with_context(active_test=True).search([
            ('id', 'in', list(found)), ('is_company', '=', self.is_company), ('id', 'not in', family.ids),
            ('parent_id', '!=', self.id)])
        # the same name only: two people of one name with two different emails are two people (unless a copy)
        others = others.filtered(lambda p: found[p.id] != 'name' or _is_copy(p.name) or _is_copy(self.name)
                                 or not (p.email_normalized and self.email_normalized)
                                 or p.email_normalized == self.email_normalized)
        return {p: found[p.id] for p in others}

    # -- which one to keep ---------------------------------------------------------------------------------------

    def _mtbg_dedupe_links(self):
        """{partner id: how many records link to it} (bookings, invoices, messages...): every stored many2one to a
        contact, its chatter's messages too."""
        counts = dict.fromkeys(self.ids, 0)
        if not self:
            return counts
        fields_ = self.env['ir.model.fields'].sudo().search([
            ('ttype', '=', 'many2one'), ('relation', '=', 'res.partner'), ('store', '=', True)])
        for field in fields_:
            Model = self.env.get(field.model)
            if Model is None or Model._abstract or Model._transient or not Model._auto \
                    or field.model == 'res.partner' or field.name not in Model._fields \
                    or not Model._fields[field.name].store:
                continue
            groups = Model.sudo().with_context(active_test=False)._read_group(
                [(field.name, 'in', self.ids)], [field.name], ['__count'])
            for partner, count in groups:
                counts[partner.id] += count
        groups = self.env['mail.message'].sudo()._read_group(
            [('model', '=', 'res.partner'), ('res_id', 'in', self.ids)], ['res_id'], ['__count'])
        for res_id, count in groups:
            counts[res_id] = counts.get(res_id, 0) + count
        return counts

    def _mtbg_dedupe_fullness(self):
        """How complete the contact is (rule 2): its key details filled, then its name's letters and words."""
        self.ensure_one()
        filled = sum(1 for f in KEY_FIELDS if f in self._fields and self[f])
        words = [w for w in (self.name or '').split() if len(w.strip('.')) > 1]
        name = COPY_SUFFIX.sub('', self.name or '')
        return filled, len(words), sum(1 for c in name if c.isalpha())

    def _mtbg_dedupe_rank(self):
        """The strongest source its details came from (rule 3, with Tours' contact rule)."""
        self.ensure_one()
        if 'mtbg_contact_sources' not in self._fields or not CONTACT_SOURCES:
            return 0
        sources = self.mtbg_contact_sources or {}
        return max([CONTACT_SOURCES.get(s, 0) for s in sources.values()] or [UNKNOWN_RANK])

    def _mtbg_dedupe_keeper(self):
        """The contact to keep among these: not a "(copy)", the fullest, the strongest source, the most linked, the
        oldest."""
        if len(self) < 2:
            return self
        links = self._mtbg_dedupe_links()
        return max(self, key=lambda p: (not _is_copy(p.name), p._mtbg_dedupe_fullness(), p._mtbg_dedupe_rank(),
                                        links.get(p.id, 0), -p.id))

    # -- the gear menu's De-duplicate ----------------------------------------------------------------------------

    def action_mtbg_dedupe(self):
        """De-duplicate (the contact's gear menu): Odoo's merge dialog with this contact and its likely duplicates,
        the most complete proposed as the one kept; nothing merged until a person clicks Merge. None: a notice."""
        self.ensure_one()
        found = self._mtbg_dedupe_find()
        if not found:
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
                'type': 'info', 'sticky': False, 'title': self.env._("De-duplicate"),
                'message': self.env._("No duplicates found for %s", self.display_name)}}
        order = sorted(found, key=lambda p: (REASONS.index(found[p]), p.id))
        partners = self | self.browse([p.id for p in order[:MERGE_MAX - 1]])
        keeper = partners._mtbg_dedupe_keeper()
        wizard = self.env['base.partner.merge.automatic.wizard'].with_context(active_ids=[], active_model=False) \
            .create({'partner_ids': [(6, 0, partners.ids)], 'dst_partner_id': keeper.id, 'state': 'selection'})
        return {'type': 'ir.actions.act_window', 'res_model': wizard._name, 'res_id': wizard.id, 'view_mode': 'form',
                'views': [(False, 'form')], 'target': 'new',
                'name': self.env._("De-duplicate %s", self.display_name)}


class MergePartnerDedupe(models.TransientModel):
    _inherit = 'base.partner.merge.automatic.wizard'

    def _update_reference_fields(self, src_partners, dst_partner):
        """Odoo's links by model and id, plus every other one kept that way (a model field and an id): message logs,
        external ids, short links, possible duplicate flags."""
        super()._update_reference_fields(src_partners, dst_partner)
        merged = (src_partners | dst_partner).ids
        if 'mtbg.crm.duplicate' in self.env:  # the flags between the merged contacts: settled now
            self.env['mtbg.crm.duplicate'].sudo().search([
                ('res_model', '=', 'res.partner'), ('res_id', 'in', merged), ('other_id', 'in', merged)]).unlink()
        for model_name, field_name, model_field in self._mtbg_reference_pairs():
            self._mtbg_move_references(model_name, field_name, model_field, src_partners, dst_partner)

    @api.model
    def _mtbg_reference_pairs(self):
        """[(model, id field, model field)]: the stored Many2oneReference fields, and an integer ``res_id`` beside a
        ``res_model`` (Odoo's own handled already)."""
        handled = {'ir.attachment', 'mail.followers', 'mail.activity', 'mail.message', 'ir.model.data'}
        pairs = []
        for model_name in self.env.registry:
            Model = self.env[model_name]
            if model_name in handled or Model._abstract or Model._transient or not Model._auto:
                continue
            for name, field in Model._fields.items():
                if not field.store:
                    continue
                if field.type == 'many2one_reference':
                    model_field = field.model_field
                elif name == 'res_id' and field.type == 'integer':
                    model_field = 'res_model'
                else:
                    continue
                kept = Model._fields.get(model_field)
                if kept is not None and kept.store and kept.type in ('char', 'selection'):
                    pairs.append((model_name, name, model_field))
        return pairs

    def _mtbg_move_references(self, model_name, field_name, model_field, src_partners, dst_partner):
        Model = self.env[model_name].sudo().with_context(active_test=False)
        records = Model.search([(model_field, '=', 'res.partner'), (field_name, 'in', src_partners.ids)])
        if not records:
            return
        try:
            with self.env.cr.savepoint():
                records.write({field_name: dst_partner.id})
                records.env.flush_all()
        except Exception:  # noqa: BLE001 - a unique key: the kept contact has its own already (as Odoo's)
            records.unlink()

    def _update_values(self, src_partners, dst_partner):
        """Never blank out (Odoo's own: the kept contact's details stay, the empty ones filled): each detail filled
        from a merged contact written in the kept one's chatter (the contact rule's rule 5)."""
        Partner = dst_partner.sudo()
        watched = [name for name, field in Partner._fields.items()
                   if field.copy and field.compute is None and field.type not in ('many2many', 'one2many')
                   and field.type not in ('binary', 'html', 'json', 'properties', 'reference')
                   and name not in ('id', 'parent_id') and not name.startswith('mtbg_contact_sources')]
        before = {name: Partner[name] for name in watched}
        result = super()._update_values(src_partners, dst_partner)
        lines = []
        for name in watched:
            old, new = before[name], Partner[name]
            if old == new or not new:
                continue
            giver = next((p for p in reversed(src_partners) if p[name]), src_partners[:1])
            field = Partner._fields[name]
            lines.append(Markup('%s: %s → %s, %s') % (
                field._description_string(self.env), self._mtbg_shown(field, old), self._mtbg_shown(field, new),
                self.env._("from %s", giver.display_name)))
        if lines:
            dst_partner.message_post(body=Markup('%s<br/>') % escape(self.env._("Details taken from the merged contacts:"))
                                     + Markup('<br/>').join(lines), subtype_xmlid='mail.mt_note')
        return result

    def _mtbg_shown(self, field, value):
        if not value:
            return self.env._("(none)")
        if field.type == 'many2one':
            return value.display_name
        if field.type == 'selection':
            return dict(field._description_selection(self.env)).get(value, value)
        if field.type == 'boolean':
            return self.env._("Yes")
        return str(value)
