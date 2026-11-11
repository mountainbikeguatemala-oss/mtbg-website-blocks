"""The customer fields every form on the site shares (booking form, website chat, pre-tour form).

One way to ask, one way to check: the browser checks with ``@mtbg_tours_forms/fields`` and the server checks the
same things here (``mtbg.form.fields``). Site rule 9: we ask once; forms start from what the visitor or the client
already gave us.
"""
import json
import re

import phonenumbers
from markupsafe import Markup
from phonenumbers import PhoneMetadata

from odoo import api, models, tools
from odoo.http import request

from .partner import mtbg_phone_open_country

# the mobile field opens on the visitor's country (Cloudflare / geo IP), else this one
DEFAULT_PHONE_COUNTRY = 'US'
EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')


def _flag(code):
    """The country's flag as an emoji (regional indicator letters) for the picker's options."""
    return ''.join(chr(0x1F1E6 + ord(c) - ord('A')) for c in code.upper())


def mtbg_normalize_phone(phone, country_code=None):
    """'+50255550000' (or '5555 0000' with country 'GT') -> '+502 5555 0000' when it is a possible number for its
    country, else False."""
    try:
        number = phonenumbers.parse(phone or '', (country_code or '').upper() or None)
    except phonenumbers.NumberParseException:
        return False
    if not phonenumbers.is_possible_number(number):
        return False
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.INTERNATIONAL)


def _request_country_code():
    """The visitor's country: Cloudflare's header on the live site, else Odoo's geo IP."""
    if not request:
        return ''
    code = (request.httprequest.headers.get('CF-IPCountry') or '').upper()
    if len(code) == 2 and code not in ('XX', 'T1'):
        return code
    geo = getattr(request, 'geoip', None) or {}
    code = (geo.get('country_code') if hasattr(geo, 'get') else getattr(geo, 'country_code', None)) or ''
    return code.upper()


class ResCountry(models.Model):
    _inherit = 'res.country'

    @tools.ormcache('self.env.lang')
    def _mtbg_phone_countries(self):
        """(code, name, dial code, mobile number lengths) of every country phonenumbers knows, by name."""
        result = []
        for country in self.sudo().search([]):
            meta = PhoneMetadata.metadata_for_region(country.code.upper())
            if not meta:
                continue
            lengths = [n for n in (meta.mobile.possible_length if meta.mobile else ()) if n > 0] \
                or [n for n in meta.general_desc.possible_length if n > 0]
            if lengths:
                result.append((country.code.upper(), country.name, str(meta.country_code), tuple(sorted(lengths))))
        return tuple(sorted(result, key=lambda c: c[1]))

    def mtbg_phone_picker(self):
        """Options of the mobile field's country code picker and the one it opens on."""
        countries = self._mtbg_phone_countries()
        known = {c[0] for c in countries}
        code = _request_country_code()
        default = code if code in known else DEFAULT_PHONE_COUNTRY
        return {
            'default': default,
            'countries': [{'code': c, 'name': n, 'dial': d, 'lengths': ','.join(map(str, lens)), 'flag': _flag(c),
                           'img': f'/base/static/img/country_flags/{c.lower()}.png'} for c, n, d, lens in countries],
        }

    @tools.ormcache('self.env.lang')
    def mtbg_phone_countries_json(self):
        """The picker's countries once for the whole page, filled into each picker when it is first used
        (views/templates.xml phone_list): [[code, name, dial code, lengths, flag], ...] by name."""
        rows = [[c, n, d, ','.join(map(str, lens)), _flag(c)] for c, n, d, lens in self._mtbg_phone_countries()]
        return Markup(json.dumps(rows, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/'))

    def mtbg_phone_open(self, phone, contact_country=None, default=None):
        """The country a picker opens on for a number on file ("+1 443…"): on a dial code several countries share,
        the contact's own country, else the area code's, else the code's main one (``mtbg_phone_open_country``);
        ``default`` (the visitor's) for anything else."""
        code = mtbg_phone_open_country(phone, contact_country) if str(phone or '').strip().startswith('+') else None
        known = {c[0] for c in self._mtbg_phone_countries()}
        return code if code in known else default or DEFAULT_PHONE_COUNTRY


class MtbgFormFields(models.AbstractModel):
    """Server-side checks of the shared fields: ``_mtbg_check(kind, text)`` -> (value, error message)."""
    _name = 'mtbg.form.fields'
    _description = 'MTBG form fields'

    @api.model
    def _mtbg_check(self, kind, text, country_code=None):
        _ = self.env._
        text = (text or '').strip()
        if kind == 'name':
            name = re.sub(r'\s+', ' ', text)
            return (name[:120], None) if len(name) >= 2 else (None, _("Please enter your name"))
        if kind == 'email':
            email = text.lower()
            return (email, None) if EMAIL_RE.match(email) else (None, _("Please enter a valid email"))
        if kind == 'phone':
            if not text.startswith(('+', '00')) and not country_code:
                return None, _("Please add your country code: it starts with + (e.g. +1 for the US and Canada, "
                               "+502 for Guatemala, +44 for the UK).")
            number = mtbg_normalize_phone(re.sub(r'^00', '+', text), country_code)
            return (number, None) if number else (None, _("Please enter a valid mobile number"))
        return text, None
