import phonenumbers

from odoo import fields, models


def mtbg_phone_region(phone, picked=None):
    """The country of a mobile number ("GT"): the one picked in a form's phone field when the number is one of that
    country's, else the number's own region (phonenumbers tells +1 US from Canada by the area code); None when not
    known."""
    try:
        number = phonenumbers.parse(phone or '', (picked or '').upper() or None)
    except phonenumbers.NumberParseException:
        return None
    picked = (picked or '').upper()
    if picked and phonenumbers.is_valid_number_for_region(number, picked):
        return picked
    region = phonenumbers.region_code_for_number(number)
    return region if region and region != '001' else None


def mtbg_dial_regions(phone):
    """The countries sharing a number's dial code, the main one first (+1: US, CA, the Caribbean...; +44: GB, GG, JE,
    IM; +7: RU, KZ); [] when it does not parse."""
    try:
        number = phonenumbers.parse(phone or '', None)
    except phonenumbers.NumberParseException:
        return []
    return list(phonenumbers.region_codes_for_country_code(number.country_code))


def mtbg_phone_open_country(phone, contact_country=None):
    """The country a phone picker opens on for a number on file (owner, 2026-10-28: a US contact's +1 number opened on
    a Caribbean flag): on a shared dial code, the contact's own country when it uses that code, else the number's
    region (the area code, e.g. 443 = US), else the code's main country (US for +1); None when it does not parse."""
    regions = mtbg_dial_regions(phone)
    if not regions:
        return None
    contact_country = (contact_country or '').upper()
    if contact_country in regions:
        return contact_country
    region = mtbg_phone_region(phone)
    return region if region in regions else regions[0]


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # the promotional texts consent (owner, 2026-10-28: carriers ask for marketing on its own checkbox, apart from the
    # texts about a booking): the marketing popup's box and the booking form's write it, with the exact wording shown
    mtbg_sms_marketing_opt_in = fields.Boolean(
        string='Promotional Texts Consent', help="Agreed to receive occasional promotional texts (new tours, dates, "
                                                 "offers): marketing audiences filter on it.")
    mtbg_sms_marketing_date = fields.Datetime(string='Promotions Consent Given On')
    mtbg_sms_marketing_text = fields.Text(string='Promotions Consent Wording',
                                          help="The wording the customer agreed to, as shown, in the language shown.")

    def _mtbg_fill_country(self, picked=None, phone=None):
        """A contact's country from the mobile a form gives (``phone``: as typed on the form, else the contact's):
        the country picked in the phone field's country picker (``picked``, "GT") is the one kept, even over another
        one (the latest they chose); without a pick, the number's own region fills an empty country only. A dial code
        several countries share (+1, +7, +44...) never replaces a country the contact has (owner, 2026-10-28)."""
        Country = self.env['res.country'].sudo()
        picked = (picked or '').upper()
        for partner in self:
            number = phone or partner.phone
            code = mtbg_phone_region(number, picked)
            if not code or partner.country_id.code == code:
                continue
            if partner.country_id and (code != picked or len(mtbg_dial_regions(number)) > 1):
                continue
            country = Country.search([('code', '=', code)], limit=1)
            if country:
                partner.sudo().country_id = country


# ---------------------------------------------------------------------- with or without Tours Core (Forms 0.5.0)
# Tours Core brings the contact rule (one contact per person, the most complete details win, each change in the
# contact's chatter: ``mtbg_contact_from``), one open lead per person (``mtbg_lead_for``) and the first-touch lead
# source (``_mtbg_set_lead_source``). Where it is installed Forms uses them; on a plain website the same calls do the
# simple thing (found by email or mobile, else made; a new lead; the form's source on the lead).
class ResPartnerForms(models.Model):
    _inherit = 'res.partner'

    def _mtbg_forms_contact(self, values, source):
        """The contact of a form: Core's contact rule where installed, else found by email or mobile, else made."""
        Partner = self.sudo()
        if hasattr(Partner, 'mtbg_contact_from'):
            return Partner.mtbg_contact_from(values, source)
        email, phone = (values.get('email') or '').strip().lower(), values.get('phone') or ''
        partner = Partner.browse()
        if email:
            partner = Partner.search([('email', '=ilike', email)], limit=1)
        if not partner and phone:
            partner = Partner.search(['|', ('phone', '=', phone), ('phone_sanitized', '=', phone)], limit=1) \
                if 'phone_sanitized' in Partner._fields else Partner.search([('phone', '=', phone)], limit=1)
        if partner:
            partner.write({k: v for k, v in values.items() if v and not partner[k] and k in partner._fields})
            return partner
        return Partner.create(dict({k: v for k, v in values.items() if v and k in Partner._fields},
                                   name=values.get('name') or email or phone))

    def _mtbg_forms_set_source(self, source):
        """The form's lead source (a utm.source): the contacts' first touch where Core is installed. Returns it."""
        if hasattr(self, '_mtbg_set_lead_source'):
            return self._mtbg_set_lead_source(source)
        return self.env['utm.source']._mtbg_forms_source(source)


class UtmSource(models.Model):
    _inherit = 'utm.source'

    def _mtbg_forms_source(self, value):
        """A utm.source by record or name (Core's lead sources where installed; else found by name, else made)."""
        if hasattr(self, '_mtbg_lead_source'):
            return self._mtbg_lead_source(value)
        if isinstance(value, models.BaseModel):
            return value.sudo()[:1]
        name = ' '.join(str(value or '').split())
        if not name:
            return self.browse()
        return self.sudo().search([('name', '=', name)], limit=1) or self.sudo().create({'name': name})


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    def _mtbg_forms_lead(self, partner, values):
        """The lead of a form: the person's one open lead where Core is installed, else a new lead."""
        Lead = self.sudo()
        if hasattr(Lead, 'mtbg_lead_for'):
            return Lead.mtbg_lead_for(partner, values)
        return Lead.create(dict(values, partner_id=partner.id) if partner else values)
