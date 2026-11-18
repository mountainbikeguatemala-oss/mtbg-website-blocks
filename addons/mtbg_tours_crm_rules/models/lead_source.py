"""Source channel (owner, 2026-11-08: "there should be a universal 'source channel' leads and clients"; 2026-11-18:
the same pipeline on every site): Odoo's own UTM sources, on the contact. Moved here from Tours Core 0.8 (0.4.0):
the field, its seed list and the method that sets it keep their names.

First touch only: a contact keeps the source they first came from; a later form, chat or sale never changes it.
Anything that brings a contact in calls ``partner._mtbg_set_lead_source(source)``, where ``source`` is a key of the
source list (``utm.source._mtbg_lead_source_keys()``: "whatsapp", "facebook", "instagram", "webchat", "phone",
"email", "referral", "newsletter", "website_sale", "other", and an extension's own, e.g. Tours' "website_booking"), an
XML id, a utm.source, or a name (found, else made, e.g. the Forms' "Web form: <form name>"). The Communication Flow
Designer calls it with its channel's key when a message comes in live (``omni.conversation._cfd_lead_source_key``:
WhatsApp, the mailboxes and Gmail as Email, the website chat as Webchat...), a soft check on its side.
"""
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

MODULE = 'mtbg_tours_crm_rules'
# key: (name, an existing XML id to use (Odoo's own UTM data) or None: ours, mtbg_tours_crm_rules.lead_source_<key>)
LEAD_SOURCES = {
    'whatsapp': ('WhatsApp', None),
    'facebook': ('Facebook', 'utm.utm_source_facebook'),
    'instagram': ('Instagram', None),
    'webchat': ('Webchat', None),
    'phone': ('Phone / Google Voice', None),
    'email': ('Email', None),
    'referral': ('Referral', 'utm.utm_source_referral'),
    'newsletter': ('Newsletter', 'utm.utm_source_newsletter'),
    # a sale on the website (a shop's checkout): its buyer (owner, 2026-11-18)
    'website_sale': ('Website sale', None),
    'other': ('Other', None),
}
# the channels of the Communication Flow Designer -> a source key (the history's backfill, when CFD is older than its
# own mapping ``omni.conversation._cfd_lead_source_key``)
CFD_CHANNELS = {'whatsapp': 'whatsapp', 'messenger': 'facebook', 'facebook': 'facebook', 'instagram': 'instagram',
                'livechat': 'webchat', 'google_voice': 'phone', 'sms': 'phone', 'call': 'phone', 'email': 'email',
                'gmail': 'email'}


class UtmSource(models.Model):
    _inherit = 'utm.source'

    mtbg_contact_count = fields.Integer(compute='_compute_mtbg_contact_count', string='Contacts')

    def _compute_mtbg_contact_count(self):
        counts = dict(self.env['res.partner'].sudo()._read_group(
            [('mtbg_lead_source_id', 'in', self.ids)], ['mtbg_lead_source_id'], ['__count']))
        for source in self:
            source.mtbg_contact_count = counts.get(source, 0)

    @api.model
    def _mtbg_lead_source_keys(self):
        """{key: (name, XML id)}: the source list. The XML id is Odoo's own (utm.*) or ours; None: ours here,
        ``mtbg_tours_crm_rules.lead_source_<key>``. An extension adds its own keys (super() + theirs, with its own
        XML ids, e.g. Tours Core's ``mtbg_tours_core.lead_source_website_booking``)."""
        return {key: (name, xmlid or f'{MODULE}.lead_source_{key}') for key, (name, xmlid) in LEAD_SOURCES.items()}

    @api.model
    def _mtbg_seed_lead_sources(self):
        """The lead sources (data): each key's source, found by its name or made, with its XML id. Re-run safe."""
        Data = self.env['ir.model.data'].sudo()
        for key, (name, xmlid) in self._mtbg_lead_source_keys().items():
            if self.env.ref(xmlid, raise_if_not_found=False):
                continue
            module, xml_name = xmlid.split('.', 1)
            if module == 'utm':  # Odoo's own record, gone: ours instead
                module, xml_name = MODULE, f'lead_source_{key}'
                if self.env.ref(f'{module}.{xml_name}', raise_if_not_found=False):
                    continue
            source = self.sudo().search([('name', '=ilike', name)], limit=1) or self.sudo().create({'name': name})
            Data.create({'module': module, 'name': xml_name, 'model': self._name, 'res_id': source.id,
                         'noupdate': True})

    def action_mtbg_fill_sources(self):
        """The Source Channels page's "Fill missing sources from history" (managers): the same as on update."""
        counts = self.env['res.partner']._mtbg_fill_sources_from_history()
        total = sum(counts.values())
        message = self.env._("%(total)s contacts got their source channel: %(detail)s", total=total,
                             detail=', '.join(f"{name} {count}" for name, count in sorted(counts.items()))) if total \
            else self.env._("No contact without a source channel has any history to take it from.")
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'message': message, 'type': 'success' if total else 'info', 'sticky': bool(total)}}

    @api.model
    def _mtbg_lead_source(self, value):
        """The utm.source for a key, an XML id, a record or a name (found by name, else made); empty for nothing."""
        if isinstance(value, models.BaseModel):
            return value.sudo()[:1]
        value = ' '.join(str(value or '').split())
        if not value:
            return self.browse()
        keys = self._mtbg_lead_source_keys()
        if value in keys:
            name, xmlid = keys[value]
            found = self.env.ref(xmlid, raise_if_not_found=False) \
                or self.env.ref(f'{MODULE}.lead_source_{value}', raise_if_not_found=False)
            if found:
                return found.sudo()
            value = name
        elif '.' in value and ' ' not in value:
            found = self.env.ref(value, raise_if_not_found=False)
            if found and found._name == self._name:
                return found.sudo()
        return self.sudo().search([('name', '=ilike', value)], limit=1) or self.sudo().create({'name': value[:120]})


class ResPartnerLeadSource(models.Model):
    _inherit = 'res.partner'

    mtbg_lead_source_id = fields.Many2one('utm.source', string='Source Channel', index=True, ondelete='set null',
                                          tracking=True,
                                          help="The channel they first came through (WhatsApp, email, the website "
                                               "chat, a web form, a website sale…): set once, by the first contact, "
                                               "kept as they become a client")

    # ------------------------------------------------------------------ the history (owner, 2026-11-08)
    def _mtbg_source_evidence(self):
        """Where these contacts (without a source channel) first came from, from what is on record: [{partner_id,
        date, source (a key, XML id, record or name), brought_by?}]. Each extension adds its own (super() + theirs).
        Here: their first message received in the Communication Flow Designer (any channel, history and imports
        too), when it is installed, mapped by its own channel -> source (the same as live)."""
        evidence = []
        Message = self.env.get('omni.message')
        if Message is None or not self:
            return evidence
        Message = Message.sudo().with_context(active_test=False)
        date_field = 'sent_at' if 'sent_at' in Message._fields else 'create_date'
        first = {}
        for message in Message.search([('conversation_id.partner_id', 'in', self.ids), ('direction', '=', 'in')],
                                      order=f'{date_field}, id'):
            conversation = message.conversation_id
            partner = conversation.partner_id
            if partner.id in first:
                continue
            key = conversation._cfd_lead_source_key() if hasattr(conversation, '_cfd_lead_source_key') \
                else CFD_CHANNELS.get(conversation.channel or '', '')
            date = message[date_field] or message.create_date
            if key and date:
                first[partner.id] = {'partner_id': partner.id, 'date': date, 'source': key}
        return evidence + list(first.values())

    @api.model
    def _mtbg_fill_sources_from_history(self):
        """The contacts without a source channel (never a vendor's or one of ours): the earliest evidence of each
        (_mtbg_source_evidence), first touch (a channel already set is never replaced). Returns {source name: count}."""
        partners = self.sudo().with_context(active_test=False).search(
            [('mtbg_lead_source_id', '=', False), ('mtbg_contact_type', '!=', 'vendor'), ('user_ids', '=', False)])
        if not partners:
            return {}
        earliest = {}
        for item in partners._mtbg_source_evidence():
            if not item.get('date') or not item.get('source'):
                continue
            current = earliest.get(item['partner_id'])
            if current is None or item['date'] < current['date']:
                earliest[item['partner_id']] = item
        counts = {}
        Source = self.env['utm.source']
        for partner_id, item in earliest.items():
            partner = self.sudo().browse(partner_id)
            source = Source._mtbg_lead_source(item['source'])
            if item.get('brought_by') and 'mtbg_brought_by_id' in partner._fields and not partner.mtbg_brought_by_id:
                partner.mtbg_brought_by_id = item['brought_by']
            if source and partner._mtbg_set_lead_source(source) and partner.mtbg_lead_source_id == source:
                counts[source.name] = counts.get(source.name, 0) + 1
        _logger.info("Source channels filled from history: %s", counts)
        return counts

    def _mtbg_set_lead_source(self, source, replace=None):
        """First touch: the contacts without a lead source get ``source`` (a key of the source list, an XML id, a
        record or a name). ``replace``: a source that may be replaced too (the same touch, better known: an
        incomplete booking once paid). Returns the source."""
        Source = self.env['utm.source']
        source = Source._mtbg_lead_source(source)
        if not source:
            return source
        replace = Source._mtbg_lead_source(replace) if replace else Source
        for partner in self.sudo():
            if not partner.mtbg_lead_source_id or (replace and partner.mtbg_lead_source_id == replace):
                if partner.mtbg_lead_source_id != source:
                    partner.mtbg_lead_source_id = source
        return source
