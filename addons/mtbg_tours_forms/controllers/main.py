import json

from odoo import http
from odoo.http import request


class MtbgFormFields(http.Controller):

    @http.route('/mtbg_forms/phone_picker', type='jsonrpc', auth='public', website=True, sitemap=False, readonly=True)
    def phone_picker(self):
        """The mobile field's countries (dial code, number lengths) and the one it opens on (the visitor's)."""
        return request.env['res.country'].mtbg_phone_picker()

    @http.route(['/contact-us'], type='http', auth='public', website=True, sitemap=True)
    def contact_page(self, **kw):
        """The contact page (the same form opens as a popup and sits under the booking form on tour pages)."""
        return request.render('mtbg_tours_forms.contact_page', {})

    @http.route(['/chat'], type='http', auth='public', website=True, sitemap=False)
    def chat_page(self, **kw):
        """A chat-only page for links in emails (the owner): the logo, and the website chat opens by itself (the contact
        form when no chat is available)."""
        return request.render('mtbg_tours_forms.chat_page', {})

    @http.route('/mtbg_forms/contact/known', type='jsonrpc', auth='public', website=True, sitemap=False)
    def contact_known(self):
        return request.env['mtbg.form.fields'].sudo().mtbg_contact_known()

    @http.route('/mtbg_forms/contact', type='jsonrpc', auth='public', website=True, sitemap=False)
    def contact_submit(self, values=None, website_hp=None):
        if website_hp:  # the hidden field filled in: a bot
            return {'ok': True}
        return request.env['mtbg.form.fields'].sudo().mtbg_contact_submit(values or {})

    @http.route('/mtbg_forms/block', type='jsonrpc', auth='public', website=True, sitemap=False)
    def form_block(self, key=None, variant=None, **kw):
        """A Form block (website editor > Contact & Forms > Form): the website form it shows, drawn now, so a change
        in the Form Designer shows on every page with it ('' when the form is gone or not a website form)."""
        Form = request.env['mtbg.form'].sudo()
        if key not in [f['key'] for f in Form.mtbg_block_forms()]:
            return {'html': ''}
        # a variant the form has (its own look, e.g. 'menu' inside the phone menu), else the page one
        form = Form.search([('key', '=', key)], limit=1)
        allowed = [v.strip() for v in (form.variants or 'page').split(',') if v.strip()]
        html = request.env['ir.qweb']._render('mtbg_tours_forms.form', {
            'form_key': key, 'variant': variant if variant in allowed else 'page', 'request': request})
        return {'html': str(html)}

    @http.route('/mtbg_forms/submit/<string:key>', type='jsonrpc', auth='public', website=True, sitemap=False)
    def form_submit(self, key, values=None, website_hp=None):
        """A Form Designer form sent from the website: checked by its blocks and rules, then its handler."""
        if website_hp:  # the hidden field filled in: a bot
            return {'ok': True}
        values = values or {}
        if key == 'contact':
            return request.env['mtbg.form.fields'].sudo().mtbg_contact_submit(values)
        form = request.env['mtbg.form'].sudo().mtbg_get(key)
        if not form:
            raise request.not_found()
        return form.mtbg_submit(values, {'variant': values.get('source') or 'page', 'lang': request.env.lang,
                                         'tour': bool(values.get('tour_id'))})

    @http.route('/mtbg_forms/designer/preview', type='http', auth='user', website=True, sitemap=False)
    def form_designer_preview(self, form=None, variant='page', known=None, tour=None, facts=None, all=None, sample=None,
                              walk=None, popup=None, **kw):
        """The Form Designer's preview: the saved form on a page of the website (the designer puts its unsaved
        blocks in, form.js); ``sample``: a made-up answer in every field, ``walk``: one step at a time (the full
        preview)."""
        if not request.env['mtbg.form'].has_access('write'):  # who may change the forms (website designers; Tours managers too)
            raise request.not_found()
        record = request.env['mtbg.form'].sudo().browse(int(form)).exists() if (form or '').isdigit() else None
        if not record:
            raise request.not_found()
        tour_record = request.env['mtbg.form']._mtbg_subject(tour)
        try:
            facts = json.loads(facts or '{}')
        except ValueError:
            facts = {}
        designer = request.env['mtbg.form.designer']
        view = record.mtbg_view(variant, tour_record or None, known=known == '1', preview=True,
                                ctx=designer._mtbg_preview_facts(record, facts), show_all=all == '1',
                                sample=sample == '1', walk=walk == '1')
        template, values = record._mtbg_designer_preview(view, variant)
        # a popup form previewed as its popup: the designer's unsaved popup settings (pictures, overlay, logo, bar)
        if variant == 'popup' and popup:
            try:
                popup = json.loads(popup)
            except ValueError:
                popup = None
            if isinstance(popup, dict) and popup.get('on'):
                from ..models.form import clean_popup
                settings = clean_popup(popup)
                values.update(popup_settings=settings, popup_bar_text=str(popup.get('bar_text') or '')[:300],
                              popup_walk=walk == '1',
                              popup_images=settings['images'] or request.env['mtbg.form.fields'].sudo().mtbg_popup_backgrounds())
        response = request.render(template, values)
        response.headers['Cache-Control'] = 'no-store'
        return response

    @http.route('/mtbg_forms/newsletter', type='jsonrpc', auth='public', website=True, sitemap=False)
    def newsletter_submit(self, values=None, website_hp=None):
        if website_hp:
            return {'ok': True}
        return request.env['mtbg.form.fields'].sudo().mtbg_newsletter_submit(values or {})
