"""The contact pipeline (owner, 2026-11-18: "the shop set up the same way as the tours site, with webchat and leads
pipeline as part of the customer record"): one contact list, segmented by a contact type and a stage, on any site.
Moved here from Tours Communications 0.8 (0.4.0); the fields keep their names, Tours adds its tour stages.

* **Contact type**: Lead or Client for the customer side (owner, 2026-11-08: "Only paying customers and their guests
  are considered clients"), Staff, Vendor or Internal for the people who are not customers (no stage, no client
  journeys). Every new contact starts a Lead (a WhatsApp number that writes in, a sender made a contact from the
  inbox, a website buyer) and becomes a Client, for good, when they pay. A type chosen by a person is kept.
* **Stage**: a lead is New (no contact yet), Lead (they reached us: a source channel), Negotiation (0.5.0: a quote
  was made for them, or set by hand) or Lost (by hand); a client is Customer. An extension adds its own stages and computes them (Tours: Past client, Repeat client, from the
  bookings), with ``selection_add`` and ``_compute_mtbg_stage`` / ``_mtbg_stage_depends``.
* **The hook for paying customers**: ``partner._mtbg_mark_customer(source=None)``: a sale paid (a website sale, a
  shop's quote paid) makes its contact a client (stage Customer), ``source`` its source channel when it has none
  yet (e.g. ``'website_sale'``). Nothing is sent: no flow watches the type.
* **The hook for quotes** (0.5.0): ``partner._mtbg_mark_negotiation()``: a quote made for a New or Lead contact moves
  them to Negotiation; never backwards (a customer stays a customer, a lost lead stays lost). Soft-checked too.
* **Classification**: the sure types every day (suppliers vendors, ourselves internal; never over a type set by
  hand), so no client journey reaches a supplier or our own inbox; all contacts once on install.
"""
from odoo import api, fields, models

CONTACT_TYPES = [
    ('lead', 'Lead'),
    ('client', 'Client'),
    ('staff', 'Staff / guide'),
    ('vendor', 'Vendor / supplier'),
    ('internal', 'Internal / test'),
]
STAGES = [
    ('new', 'No contact yet'),
    ('lead', 'Lead'),
    ('negotiation', 'Negotiation'),
    ('customer', 'Customer'),
    ('lost', 'Lost / not a fit'),
]
# the customer side: leads and clients (stages, journeys, the pipeline)
CUSTOMER_TYPES = ('lead', 'client')
STAGE_COLORS = {'new': '#9aa0a6', 'lead': '#f1c232', 'negotiation': '#f08c2e', 'customer': '#6cc66c', 'lost': '#e5534b'}
# a lead's stages that a person can pick (a contacts screen): the rest come from what they bought
HAND_STAGES = ('new', 'lead', 'negotiation', 'customer', 'lost')
# our own addresses: the company's mailboxes are not clients. Their domains come from the company (its email, its
# website) and the setting mtbg_tours.own_email_domains (more, comma separated): never a business name in the code
OWN_DOMAINS_PARAM = 'mtbg_tours.own_email_domains'
# mail providers anyone can use: never a business's own domain
PUBLIC_MAIL_DOMAINS = ('gmail.com', 'googlemail.com', 'hotmail.com', 'outlook.com', 'live.com', 'msn.com', 'yahoo.com',
                       'icloud.com', 'me.com', 'mac.com', 'aol.com', 'proton.me', 'protonmail.com', 'gmx.com',
                       'gmx.net', 'mail.com', 'zoho.com', 'yandex.com')


class ResPartnerPipeline(models.Model):
    _inherit = 'res.partner'

    mtbg_contact_type = fields.Selection(CONTACT_TYPES, string='Contact type', default='lead', required=True,
                                         index=True, tracking=True,
                                         help="Lead: not paid yet. Client: a paying customer (set when they first "
                                              "pay, never undone automatically). Leads and clients have a stage and "
                                              "get the client journeys; staff, vendors and internal contacts do not.")
    mtbg_contact_type_manual = fields.Boolean(
        string='Type set by hand', copy=False,
        help="The contact type was chosen by a person: the automatic classification never changes it.")
    mtbg_is_lead = fields.Boolean(
        string='Is a Lead', compute='_compute_mtbg_is_lead', store=True, index=True,
        help="The contact is a lead (not paid yet): pages and view items switch on it without knowing contact types.")
    mtbg_stage = fields.Selection(STAGES, string='Stage', compute='_compute_mtbg_stage', store=True, index=True,
                                  tracking=True, group_expand='_group_expand_mtbg_stage',
                                  help="Where the contact is in their journey with us: a lead's from their first "
                                       "contact, a client's from what they bought")
    mtbg_lost = fields.Boolean(string='Lost / not a fit', tracking=True,
                               help="Set by hand: not going to buy. Paying makes them a customer again.")
    mtbg_negotiation = fields.Boolean(
        string='Negotiation', tracking=True, copy=False,
        help="A quote was made for this lead (set when a quote is made, or by hand): stage Negotiation until they "
             "pay (Customer) or are lost.")
    # the pipeline's fields shown on the contact's page by another extension (Tours Core's contact page): this
    # extension's own then hide
    mtbg_pipeline_elsewhere = fields.Boolean(compute='_compute_mtbg_pipeline_elsewhere')

    def _compute_mtbg_pipeline_elsewhere(self):
        self.mtbg_pipeline_elsewhere = False

    def write(self, vals):
        if 'mtbg_contact_type' in vals and not self.env.context.get('mtbg_auto_type'):
            vals = dict(vals, mtbg_contact_type_manual=True)  # chosen by a person: kept
        return super().write(vals)

    @api.depends('mtbg_contact_type')
    def _compute_mtbg_is_lead(self):
        for partner in self:
            partner.mtbg_is_lead = partner.mtbg_contact_type == 'lead'

    @api.model
    def _group_expand_mtbg_stage(self, stages, domain):
        """Every stage a column, in order; a board filtered on stages (e.g. the Leads pipeline) shows those only."""
        keys = [key for key, _label in self._fields['mtbg_stage']._description_selection(self.env)]
        for leaf in domain or []:
            if isinstance(leaf, (list, tuple)) and len(leaf) == 3 and leaf[0] == 'mtbg_stage' and leaf[1] in ('in', '='):
                allowed = set(leaf[2] if isinstance(leaf[2], (list, tuple)) else [leaf[2]])
                keys = [key for key in keys if key in allowed]
        return keys

    def _mtbg_stage_depends(self):
        """What the stage is computed from (an extension adds its own: super() + theirs)."""
        return ['mtbg_contact_type', 'mtbg_lost', 'mtbg_negotiation', 'mtbg_lead_source_id']

    def _mtbg_contacted_us(self):
        """They reached us: a source channel (their first message, a form, a sale...)."""
        self.ensure_one()
        return bool(self.mtbg_lead_source_id)

    @api.depends(lambda self: self._mtbg_stage_depends())
    def _compute_mtbg_stage(self):
        for partner in self:
            if partner.mtbg_contact_type not in CUSTOMER_TYPES:
                partner.mtbg_stage = False
            elif partner.mtbg_contact_type == 'client':
                partner.mtbg_stage = 'customer'
            elif partner.mtbg_lost:
                partner.mtbg_stage = 'lost'
            elif partner.mtbg_negotiation:
                partner.mtbg_stage = 'negotiation'
            elif partner._mtbg_contacted_us():
                partner.mtbg_stage = 'lead'
            else:
                partner.mtbg_stage = 'new'

    # ------------------------------------------------------------------ Lead -> Client
    def _mtbg_has_paid(self):
        """They paid us (an extension adds its own: super() or theirs, e.g. Tours' paid bookings). Here, when the
        apps are there: a customer invoice paid (or partly), or a website order confirmed (a website confirms its
        orders when they are paid)."""
        self.ensure_one()
        partner = self.sudo().commercial_partner_id
        env = self.env(su=True)
        if 'account.move' in env and env['account.move'].search_count([
                ('commercial_partner_id', '=', partner.id), ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
                ('payment_state', 'in', ('paid', 'in_payment', 'partial'))], limit=1):
            return True
        if 'sale.order' not in env or 'website_id' not in env['sale.order']._fields:
            return False
        return bool(env['sale.order'].search_count(
            [('partner_id', 'child_of', partner.id), ('state', '=', 'sale'), ('website_id', '!=', False)], limit=1))

    def _mtbg_has_history(self):
        """Something on record says who they are (a payment, a conversation...): the classification is sure."""
        self.ensure_one()
        return self._mtbg_contacted_us() or self._mtbg_has_paid()

    def _mtbg_become_clients(self):
        """Leads that paid (``_mtbg_has_paid``) become clients, for good. Only leads, never a type set by hand;
        nothing is sent (no flow watches the type). Returns the contacts that changed."""
        leads = self.sudo().filtered(lambda p: p.mtbg_contact_type == 'lead' and not p.mtbg_contact_type_manual)
        clients = leads.filtered(lambda p: p._mtbg_has_paid())
        if clients:
            clients.with_context(mtbg_auto_type=True).write({'mtbg_contact_type': 'client'})
        return clients

    def _mtbg_mark_customer(self, source=None):
        """The hook for a sale paid (a website sale, a quote paid in the shop; owner, 2026-11-18: "New website sales
        create contacts with stage - customer"): these contacts are paying customers. A lead becomes a client
        (stage Customer), for good; a type set by hand, staff, vendors and internal contacts are left as they are.
        ``source``: their source channel when they have none yet (first touch; a key such as ``'website_sale'``, an
        XML id, a utm.source or a name). Nothing is sent. Returns the contacts that became clients.

        Other extensions call it with a soft check: ``if hasattr(partner, '_mtbg_mark_customer'):``."""
        partners = self.sudo().exists()
        if source:
            partners.filtered(lambda p: p.mtbg_contact_type in CUSTOMER_TYPES)._mtbg_set_lead_source(source)
        clients = partners.filtered(lambda p: p.mtbg_contact_type == 'lead' and not p.mtbg_contact_type_manual)
        if clients:
            clients.with_context(mtbg_auto_type=True).write({'mtbg_contact_type': 'client', 'mtbg_lost': False,
                                                            'mtbg_negotiation': False})
        return clients

    def _mtbg_mark_negotiation(self):
        """The hook for a quote made (0.5.0, owner 2026-11-19: a shop's quote for a lead): New and Lead contacts move to
        Negotiation. Never backwards: customers (any client stage), lost leads, staff, vendors and internal contacts
        are left as they are. Nothing is sent. Returns the contacts that moved.

        Other extensions call it with a soft check: ``if hasattr(partner, '_mtbg_mark_negotiation'):``."""
        partners = self.sudo().exists().filtered(
            lambda p: p.mtbg_contact_type == 'lead' and not p.mtbg_lost and not p.mtbg_negotiation
            and p.mtbg_stage in ('new', 'lead'))
        if partners:
            partners.write({'mtbg_negotiation': True})
        return partners

    def _mtbg_set_stage(self, stage):
        """A stage picked by a person (a contacts screen's stage menu or board; 0.5.0): New / Lead (back to an open
        lead), Negotiation, Customer (a client), Lost. Customer and the stages of a lead change the contact type, as
        a person choosing it (kept by the automatic classification). Stages computed from bookings or sales (e.g.
        Tours' Past client) cannot be picked. Returns False for a stage that cannot."""
        if stage not in HAND_STAGES:
            return False
        for partner in self:
            vals = {}
            if stage == 'customer':
                if partner.mtbg_contact_type != 'client':
                    vals['mtbg_contact_type'] = 'client'
                vals.update(mtbg_lost=False, mtbg_negotiation=False)
            else:
                if partner.mtbg_contact_type not in CUSTOMER_TYPES or partner.mtbg_contact_type == 'client':
                    vals['mtbg_contact_type'] = 'lead'
                vals.update(mtbg_lost=stage == 'lost', mtbg_negotiation=stage == 'negotiation')
            changed = {key: value for key, value in vals.items() if partner[key] != value}
            if changed:
                partner.write(changed)
        return True

    # ------------------------------------------------------------------ classification
    @api.model
    def _mtbg_domain_of(self, text):
        """The domain in an email address or a web address ('' if none)."""
        text = (text or '').strip().lower()
        if '@' in text:
            text = text.rsplit('@', 1)[1]
        text = text.split('//', 1)[-1].split('/', 1)[0].split(':', 1)[0].removeprefix('www.').strip('.> ')
        return text if '.' in text else ''

    @api.model
    def _mtbg_own_email_domains(self):
        """Our own email domains: the company's email and website domains, plus the setting's."""
        company = self.env.company
        found = {self._mtbg_domain_of(text) for text in (company.email, company.website)} - {''}
        extra = self.env['ir.config_parameter'].sudo().get_param(OWN_DOMAINS_PARAM) or ''
        found |= {d.strip().lower().removeprefix('@') for d in extra.split(',') if d.strip()}
        return sorted(found)

    @api.model
    def _mtbg_is_supplier(self, partner):
        """A company we buy from (vendor bills), never one we sell to (an extension adds its own)."""
        company = partner.commercial_partner_id
        return bool('supplier_rank' in company._fields and company.supplier_rank > 0
                    and not ('customer_rank' in company._fields and company.customer_rank > 0))

    @api.model
    def _mtbg_guess_contact_type(self, partner):
        """(type, sure?) for one contact, from what we know about them (an extension adds its own)."""
        email = (partner.email or '').lower()
        if partner == self.env.company.partner_id or partner.user_ids.filtered(lambda u: not u.share) \
                or partner in self.env['res.company'].sudo().search([]).partner_id:
            return 'internal', True
        if email.endswith(tuple('@' + d for d in self._mtbg_own_email_domains())):
            return 'internal', True
        if self._mtbg_is_supplier(partner):
            return 'vendor', True
        return ('client' if partner._mtbg_has_paid() else 'lead'), partner._mtbg_has_history()

    @api.model
    def mtbg_classify_contacts(self, only_unset=False):
        """Set every contact's type (never one set by hand); returns the contacts to check by hand (no history,
        odd names)."""
        partners = self.sudo().with_context(active_test=True).search(
            [('type', '=', 'contact'), ('mtbg_contact_type_manual', '=', False)])
        to_check = self.browse()
        for partner in partners:
            contact_type, sure = self._mtbg_guess_contact_type(partner)
            if partner.mtbg_contact_type != contact_type:
                partner.with_context(mtbg_auto_type=True).mtbg_contact_type = contact_type
            name = (partner.name or '').strip()
            if not sure or not name or name.replace(' ', '').isdigit():
                to_check |= partner
        return to_check

    @api.model
    def _mtbg_cron_classify_suppliers(self):
        """Every day: the sure guesses of the contact type (a supplier becomes a vendor, ourselves internal; an
        extension adds its own, e.g. Tours' staff), never over a type set by hand, so no client journey reaches a
        supplier or our own inbox. Returns how many contacts changed."""
        partners = self.sudo().with_context(active_test=True).search(
            [('mtbg_contact_type_manual', '=', False), ('type', '=', 'contact')])
        changed = 0
        for partner in partners:
            contact_type, sure = self._mtbg_guess_contact_type(partner)
            if sure and contact_type in ('vendor', 'staff', 'internal') and partner.mtbg_contact_type != contact_type:
                partner.with_context(mtbg_auto_type=True).mtbg_contact_type = contact_type
                changed += 1
        return changed

    @api.model
    def _mtbg_classify_on_install(self):
        """A site that gets the pipeline (a new install, or this version on a site without Tours): every contact
        has the default type (Lead) until now: their types from what is on record (ourselves, suppliers, those who
        paid), then the source channels from history. Nothing is sent."""
        self.mtbg_classify_contacts()
        return self._mtbg_fill_sources_from_history()
