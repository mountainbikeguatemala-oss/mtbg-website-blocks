from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request


class MtbgWebsiteCards(http.Controller):

    @http.route('/mtbg/cards/render', type='jsonrpc', auth='public', website=True, sitemap=False, readonly=True)
    def cards_render(self, source, design_id=0, filters=None, limit=6, columns=3, lang=None):
        """The Cards block: its source's records (its filters, how many) as cards in its design, in the page's
        language."""
        Design = request.env['mtbg.website.card.design']
        langs = {code for code, _name in request.env['res.lang'].get_installed()}
        if lang in langs:
            Design = Design.with_context(lang=lang)
        if source not in Design._mtbg_card_sources():
            return {'html': ''}
        design = Design._mtbg_design_for(source, design_id)
        if not design:
            return {'html': ''}
        limit = max(1, min(int(limit or 6), 48))
        records = Design.sudo()._mtbg_card_records(source, Design.mtbg_parse_filters(filters), limit)
        return {'html': design.with_context(lang=Design.env.lang).mtbg_render(records, columns=int(columns or 3))}

    @http.route('/mtbg/cards/preview/<int:design_id>', type='http', auth='user', website=True, sitemap=False)
    def cards_preview(self, design_id, dark=None, hover=None, **kw):
        """The Card Designer's preview: the design (its unsaved settings) with its source's sample records."""
        if not request.env.user.has_group('website.group_website_designer'):
            raise NotFound()
        design = request.env['mtbg.website.card.design'].browse(design_id).exists()
        if not design:
            raise NotFound()
        samples = design._mtbg_card_samples(design.source)
        cards_html = design.mtbg_render(samples, draft=True) if samples else ''
        response = request.render('mtbg_website_cards.designer_preview', {
            'cards_html': cards_html, 'dark': dark == '1', 'hover': hover == '1'})
        response.headers['Cache-Control'] = 'no-store'
        return response
