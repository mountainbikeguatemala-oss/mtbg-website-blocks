"""The Contact Rules' own rules (announced like an extension's, off until switched on): the phone's country and US
state, duplicates by phone or email, the language from the country."""
import logging
import re

from odoo import api, models

_logger = logging.getLogger(__name__)

try:
    import phonenumbers
    from phonenumbers import geocoder
except ImportError:  # the rule then finds nothing
    phonenumbers = geocoder = None

# Spanish-speaking countries (Latin America, Spain, Equatorial Guinea)
SPANISH = {'AR', 'BO', 'CL', 'CO', 'CR', 'CU', 'DO', 'EC', 'ES', 'GQ', 'GT', 'HN', 'MX', 'NI', 'PA', 'PE', 'PR', 'PY',
           'SV', 'UY', 'VE'}


class MtbgCrmRule(models.Model):
    _inherit = 'mtbg.crm.rule'

    def _mtbg_crm_rule_sources(self):
        _ = self.env._
        specs = [
            {'code': 'phone_location', 'name': _("Country and state from the phone"), 'icon': 'fa-phone',
             'sequence': 10, 'model': 'res.partner', 'trigger': 'changed', 'fields': ['phone'],
             'description': _("A contact without a country (or a US / Canadian contact without a state) gets them "
                              "from the phone number's country code and area code. Only empty fields are filled."),
             'run': '_mtbg_crm_phone_location'},
            {'code': 'message_phone_location', 'name': _("Country and state from a message's number"),
             'icon': 'fa-commenting', 'sequence': 15, 'model': 'res.partner', 'trigger': 'received', 'once': False,
             'description': _("When a message comes in (WhatsApp, text, call) from a contact without a country (or a "
                              "US / Canadian contact without a state), the number it came from gives them. Only "
                              "empty fields are filled."),
             'run': '_mtbg_crm_phone_location'},
            {'code': 'duplicates', 'name': _("Possible duplicates by phone or email"), 'icon': 'fa-clone',
             'sequence': 20, 'model': 'res.partner', 'trigger': 'changed', 'fields': ['phone', 'email'],
             'once': False,
             'description': _("A contact with the same phone (last 8 digits) or the same email as another is "
                              "flagged on the Possible Duplicates list. Nothing is ever merged."),
             'actions': [{'kind': 'flag_duplicate', 'match_on': 'both'}]},
            {'code': 'lang_from_country', 'name': _("Spanish for Spanish-speaking countries"), 'icon': 'fa-language',
             'sequence': 40, 'model': 'res.partner', 'trigger': 'changed', 'fields': ['country_id'],
             'description': _("A contact from a Spanish-speaking country whose language is still English (the "
                              "default) gets Spanish, so messages go out in Spanish."),
             'run': '_mtbg_crm_lang_from_country'},
        ]
        # (0.2.0: "Enquiry not answered" moved to Communications, on the website form messages: Odoo's CRM retired)
        return super()._mtbg_crm_rule_sources() + specs

    # ------------------------------------------------------------------
    # The phone's country and state
    # ------------------------------------------------------------------
    @api.model
    def _mtbg_phone_location(self, phone):
        """(country, state) of a phone number, from its country code (and a US / Canadian area code)."""
        Country, State = self.env['res.country'], self.env['res.country.state']
        if not phonenumbers or not phone:
            return Country, State
        home = self.env.company.country_id.code or None
        try:
            number = phonenumbers.parse(phone, home)
        except phonenumbers.NumberParseException:
            return Country, State
        if not phonenumbers.is_valid_number(number):
            return Country, State
        region = phonenumbers.region_code_for_number(number)
        country = Country.search([('code', '=', region)], limit=1) if region else Country
        state = State
        if country and country.code in ('US', 'CA'):
            place = geocoder.description_for_number(number, 'en') or ''
            code = re.search(r',\s*([A-Z]{2})$', place)
            domain = [('country_id', '=', country.id)]
            state = State.search(domain + ([('code', '=', code.group(1))] if code else [('name', '=ilike', place)]),
                                 limit=1) if place else State
        return country, state

    def _mtbg_crm_phone_location(self, rule, records):
        phones = self.env.context.get('mtbg_crm_phones') or {}
        if not records:
            records = self.env['res.partner'].search(
                [('phone', '!=', False), '|', ('country_id', '=', False), '&', ('country_id.code', 'in', ('US', 'CA')),
                 ('state_id', '=', False)], limit=2000)
        changes = []
        for partner in records:
            phone = phones.get(partner.id) or phones.get(str(partner.id)) or partner.phone
            if not phone or (partner.country_id and (partner.state_id or partner.country_id.code not in ('US', 'CA'))):
                continue
            country, state = self._mtbg_phone_location(phone)
            values = {}
            if country and not partner.country_id:
                values['country_id'] = country.id
            if state and (not partner.country_id or partner.country_id == country) and not partner.state_id:
                values['state_id'] = state.id
            if values:
                changes.append({'record': partner, 'values': values})
        return changes

    # ------------------------------------------------------------------
    # The language from the country
    # ------------------------------------------------------------------
    def _mtbg_crm_lang_from_country(self, rule, records):
        spanish = next((code for code, _n in self.env['res.lang'].get_installed() if code.startswith('es')), None)
        if not spanish:
            return []
        if not records:
            records = self.env['res.partner'].search([('country_id.code', 'in', list(SPANISH)),
                                                      ('lang', '=', 'en_US')], limit=2000)
        return [{'record': p, 'values': {'lang': spanish}, 'fill_empty': False} for p in records
                if p.country_id.code in SPANISH and p.lang in (False, 'en_US')]
