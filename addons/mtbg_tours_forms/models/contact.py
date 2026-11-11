"""The contact forms (the contact page, the popup, the tour page's sidebar): one form, one way in.

A message sent from any of them finds the client by email or phone, or makes a new contact, its details by Core's
contact rule (the most complete wins, each change in the contact's chatter); keeps the SMS / WhatsApp opt-ins with
their wording; and adds the message to the person's one open CRM lead (Core's ``mtbg_lead_for``). A visitor we already know is not asked for
their details again (site rule 9): the form shows them masked and the server uses the contact it knows.
"""
import logging

from lxml import html

from odoo import api, fields, models
from odoo.http import request

from .fields import mtbg_normalize_phone

_logger = logging.getLogger(__name__)

# the messaging terms (owner, 2026-10-28): two global texts, edited in every language on Tours Core's settings page
# (through Booking Form) and read wherever they are shown (models/texts.py); after each, the links sentence (template text with real links)
TERMS_BOOKING = 'mtbg_tours.messaging_terms_booking'        # booking texts: shown by the booking form only
TERMS_PROMOTIONS = 'mtbg_tours.messaging_terms_promotions'  # promotional texts: the newsletter popup only
# the defaults until the owner's wording is saved: the company's name and email filled in (no business name in the code)
CONSENT_TEXT = (
    "By checking this box you agree to receive text messages from %(company)s in reply to your enquiry and about "
    "your booking. Message frequency varies. Message and data rates may apply. Consent is not a condition of purchase. "
    "Reply STOP to opt out, HELP for help or contact %(email)s.")
MARKETING_TEXT = (
    "Send me occasional promotional texts from %(company)s about new tours, dates and offers (up to 4 per month). "
    "Message and data rates may apply. Reply STOP to opt out. Consent is not a condition of purchase.")


def consent_values(env):
    """The company's name and email, in the default messaging terms."""
    company = env.company
    return {'company': company.name or '', 'email': company.email or ''}
TEXTING_BOXES = ('sms_optin', 'whatsapp_optin', 'sms_marketing_optin')


def _texting_opted(values):
    """Any texting box ticked (each needs the mobile number)."""
    return any(values.get(box) for box in TEXTING_BOXES)


def _whatsapp_opt_in(partner):
    """The WhatsApp opt-in on the contact (Tours Core's field, where installed; the old WhatsApp connector's too where it
    is installed)."""
    vals = {'mtbg_whatsapp_opt_in': True} if 'mtbg_whatsapp_opt_in' in partner._fields else {}
    if 'wa_is_opted_in' in partner._fields:
        vals['wa_is_opted_in'] = True
    return vals


def _mask_phone(phone):
    digits = ''.join(c for c in phone or '' if c.isdigit())
    return '•••• %s' % digits[-4:] if len(digits) >= 4 else ''


def _mask_email(email):
    if not email or '@' not in email:
        return ''
    name, domain = email.split('@', 1)
    return '%s•••@%s' % (name[:1], domain)


class MtbgFormFields(models.AbstractModel):
    _inherit = 'mtbg.form.fields'

    @api.model
    def _mtbg_known_contact(self):
        """The client this browser belongs to (a known website visitor), or an empty record."""
        if not request:
            return self.env['res.partner']
        user = request.env.user
        if not user._is_public() and user.partner_id:
            partner = user.partner_id
        else:
            visitor = self.env['website.visitor'].sudo()._get_visitor_from_request()
            partner = visitor.partner_id if visitor else self.env['res.partner']
        partner = partner.sudo()
        if 'mtbg_contact_type' in partner._fields and partner.mtbg_contact_type not in ('lead', 'client'):
            return self.env['res.partner']  # staff trying the form: ask everything
        return partner

    @api.model
    def mtbg_contact_known(self):
        """What the form shows for a known visitor: their first name and masked phone / email (never in full: a
        forwarded link must not show someone else's details)."""
        partner = self._mtbg_known_contact()
        if not partner:
            return {}
        return {'first_name': (partner.name or '').split(' ')[0], 'phone': _mask_phone(partner.phone),
                'email': _mask_email(partner.email), 'newsletter': bool(partner.mtbg_newsletter)}

    @api.model
    def mtbg_contact_submit(self, values, ctx=None):
        """Check and record a contact form (the Form Designer's "contact" form: its blocks and rules). Returns
        {'ok': True} or {'ok': False, 'errors': {field: message}}."""
        values = values or {}
        ctx = dict(ctx or {}, variant=values.get('source') or 'page', tour=bool(values.get('tour_id')),
                   lang=self.env.lang)
        return self.env['mtbg.form'].mtbg_get('contact').mtbg_submit(values, ctx)

    @api.model
    def _mtbg_consent_text(self, kind='enquiry'):
        """The wording a texting consent keeps, in the reader's language. 'marketing': the newsletter popup's box as
        the visitor read it (texting_consent rendered: the promotional terms and the links sentence, as plain text);
        'enquiry' (only the old newsletter form still sends SMS / WhatsApp ticks): the booking texts terms."""
        if kind != 'marketing':
            return terms_text(self.env, TERMS_BOOKING)
        try:
            body = html.fromstring(str(self.env['ir.qweb']._render('mtbg_tours_forms.texting_consent', {
                'texting_shown': True, 'texting_marketing': True, 'texting_terms': terms_text(self.env, TERMS_PROMOTIONS)})))
            text = ' '.join(' '.join(body.find_class(css)[0].text_content().split())
                            for css in ('mtbg-contact-form__marketing-text', 'mtbg-contact-form__marketing-links'))
        except Exception:  # noqa: BLE001 — never lose an opt-in over its wording
            text = ''
        return text or terms_text(self.env, TERMS_PROMOTIONS)

    @api.model
    def _mtbg_opt_in_values(self, partner, values):
        """What the ticked texting boxes write on the contact: each its flag, date and the wording shown."""
        now = fields.Datetime.now()
        vals = {}
        if values.get('sms_optin') and 'mtbg_sms_opt_in' in partner._fields:
            vals['mtbg_sms_opt_in'] = True
        if values.get('whatsapp_optin'):
            vals.update(_whatsapp_opt_in(partner))
        if vals and 'mtbg_messaging_consent' in partner._fields:
            vals.update(mtbg_messaging_consent=True, mtbg_messaging_consent_date=now,
                        mtbg_messaging_consent_text=self._mtbg_consent_text())
        if values.get('sms_marketing_optin') and 'mtbg_sms_marketing_opt_in' in partner._fields:
            vals.update(mtbg_sms_marketing_opt_in=True, mtbg_sms_marketing_date=now,
                        mtbg_sms_marketing_text=self._mtbg_consent_text('marketing'))
        return vals

    @api.model
    def _mtbg_set_opt_ins(self, partner, values):
        """The SMS / WhatsApp / promotions opt-ins ticked, with the consent's wording and date."""
        opt_ins = self._mtbg_opt_in_values(partner, values)
        if opt_ins:
            partner.sudo().write(opt_ins)

    @api.model
    def _mtbg_find_or_create_contact(self, clean, source='contact'):
        """The person by email or phone, else a new contact, their details by Core's contact rule (owner,
        2026-10-29: the most complete wins, every change in the contact's chatter): ``source`` is the form's kind
        (contact, question, newsletter)."""
        values = {'name': clean.get('name'), 'email': clean.get('email') or False,
                  'phone': mtbg_normalize_phone(clean['phone']) if clean.get('phone') else False}
        if request and request.lang:
            values['lang'] = request.lang.code
        return self.env['res.partner']._mtbg_forms_contact(values, source)

    @api.model
    def _mtbg_link_visitor(self, partner):
        """The browser's website visitor joins the contact (CFD website visitors 1.1.0; soft: nothing without it,
        never failing the submit). Contact details stay with Core's contact rule."""
        Visitor = self.env['website.visitor'].sudo() if 'website.visitor' in self.env else None
        if partner and Visitor is not None and hasattr(Visitor, '_cfd_link_request'):
            try:
                with self.env.cr.savepoint():
                    Visitor._cfd_link_request(partner, 'form')
            except Exception:  # noqa: BLE001 - the submit never fails on the visitor's link
                _logger.warning("Website visitor link failed for %s", partner.id, exc_info=True)

    @api.model
    def mtbg_popup_backgrounds(self):
        """The contact popup's background pictures, one per opening, in turn: the URLs in the
        ``mtbg_tours.contact_popup_images`` setting (comma separated), else (Booking Form) the covers of a few published
        tours."""
        return [u.strip() for u in (self.env['ir.config_parameter'].sudo().get_param(
            'mtbg_tours.contact_popup_images') or '').split(',') if u.strip()]

    @api.model
    def mtbg_newsletter_submit(self, values):
        """The newsletter popup (Zoho's "Newsletter2025" form): the contact (phone first, then email), subscribed,
        tagged "Newsletter", with their language and opt-ins. Returns {'ok'} or {'ok': False, 'errors'}."""
        values = values or {}
        check = self._mtbg_check
        errors, clean = {}, {}
        partner = self._mtbg_known_contact() if values.get('use_known') else self.env['res.partner']
        if not partner:
            name = (values.get('name') or '').strip() or ' '.join(
                filter(None, [(values.get('first_name') or '').strip(), (values.get('last_name') or '').strip()]))
            for key, kind, text in [('name', 'name', name), ('email', 'email', values.get('email'))]:
                value, error = check(kind, text)
                if error:
                    errors[key] = error
                else:
                    clean[key] = value
            if values.get('phone'):
                value, error = check('phone', values.get('phone'))
                if error:
                    errors['phone'] = error
                else:
                    clean['phone'] = value
        opted = _texting_opted(values)
        if opted and not (clean.get('phone') or partner.phone):
            errors['phone'] = self.env._("Please enter your mobile number for SMS / WhatsApp updates")
        if (values.get('sms_optin') or values.get('whatsapp_optin')) and not values.get('terms'):
            errors['terms'] = self.env._("Please agree to receive text messages")
        if errors:
            return {'ok': False, 'errors': errors}
        if not partner:
            partner = self._mtbg_find_or_create_contact(dict(clean, phone=clean.get('phone') or ''), 'newsletter')
        partner._mtbg_fill_country(values.get('phone_country'), clean.get('phone'))  # the country picked with the mobile (the latest they chose)
        self._mtbg_subscribe_newsletter(partner, values)
        partner._mtbg_forms_set_source('newsletter')  # first touch only (Core, where installed)
        self._mtbg_link_visitor(partner)
        self.env['crm.lead']._mtbg_forms_lead(partner, {
            'name': self.env._("Newsletter signup: %s", partner.name), 'type': 'lead', 'partner_id': partner.id,
            'contact_name': partner.name, 'email_from': partner.email, 'phone': partner.phone,
            'description': self.env._("Signed up for the newsletter (website popup)."), 'referred': 'Newsletter Form',
        })
        return {'ok': True, 'first_name': (partner.name or '').split(' ')[0]}

    @api.model
    def _mtbg_subscribe_newsletter(self, partner, values):
        """Subscribe ``partner`` to the newsletter: flagged, tagged "Newsletter", their language and opt-ins (the
        newsletter popup, and every form whose "Signs up for the newsletter" is on)."""
        lang = {'en': 'en_US', 'es': 'es_ES'}.get(values.get('language'))
        update = {'mtbg_newsletter': True, 'mtbg_newsletter_date': fields.Datetime.now()}
        if lang and self.env['res.lang']._lang_get(lang):
            update['lang'] = lang
        tag = self.env['res.partner.category'].sudo().search([('name', '=', 'Newsletter')], limit=1) or \
            self.env['res.partner.category'].sudo().create({'name': 'Newsletter'})
        update['category_id'] = [(4, tag.id)]
        update.update(self._mtbg_opt_in_values(partner, values))
        partner.sudo().write(update)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _mtbg_source_evidence(self):
        """Their source channel from history (Core): a lead a website form made for them (before Source Channel
        existed: "Website message", "Question about …", "Newsletter signup"), its form's source. A lead keeps where it
        came from (``referred``), not its form: the contact forms by variant, the newsletter form for a signup."""
        evidence = super()._mtbg_source_evidence()
        Form = self.env['mtbg.form'].sudo().with_context(active_test=False)
        forms = Form.search([], order='sequence, id')
        newsletter = forms.filtered('newsletter')[:1]
        menu = forms.filtered(lambda f: not f.newsletter and (f.variants or '').split(',') == ['menu'])[:1]
        contact = forms.filtered(lambda f: f.key == 'contact')[:1] or forms.filtered(
            lambda f: not f.newsletter and 'page' in (f.variants or ''))[:1]
        by_referred = {'Newsletter Form': newsletter, 'phone menu': menu or contact, 'contact page': contact,
                       'contact popup': contact, 'tour page': contact, 'website': contact}
        Lead = self.env['crm.lead'].sudo().with_context(active_test=False)
        for lead in Lead.search([('partner_id', 'in', self.ids), ('source_id', '=', False),
                                 ('referred', 'in', list(by_referred))], order='create_date, id'):
            form = by_referred.get(lead.referred)
            if form:
                evidence.append({'partner_id': lead.partner_id.id, 'date': lead.create_date,
                                 'source': form._mtbg_lead_source()})
        return evidence

    mtbg_newsletter = fields.Boolean(string='Newsletter', help="Signed up for the newsletter")
    mtbg_newsletter_date = fields.Datetime(string='Newsletter since')


def terms_defaults(env):
    """{key: default(lang)}: the messaging terms' built-in texts (the owner's wording for the Twilio toll-free
    verification is saved over them). Tours registers them as editable text settings (Booking Form)."""
    def lang_env(lang):
        return env(context=dict(env.context, lang=lang))
    values = consent_values(env)
    return {
        TERMS_BOOKING: lambda lang: lang_env(lang)._(
            "By checking this box you agree to receive text messages from %(company)s in reply to your enquiry "
            "and about your booking. Message frequency varies. Message and data rates may apply. Consent is not a "
            "condition of purchase. Reply STOP to opt out, HELP for help or contact %(email)s.", **values),
        TERMS_PROMOTIONS: lambda lang: lang_env(lang)._(
            "Send me occasional promotional texts from %(company)s about new tours, dates and offers (up to 4 "
            "per month). Message and data rates may apply. Reply STOP to opt out. Consent is not a condition of "
            "purchase.", **values),
    }


def terms_text(env, key, lang=None):
    """A messaging terms text in the reader's language: the site's saved wording, else the built-in one."""
    return env['ir.config_parameter'].mtbg_get_text(key, lang, terms_defaults(env).get(key))
