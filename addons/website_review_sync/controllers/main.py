import re

from odoo import http
from odoo.http import request


class ReviewSync(http.Controller):

    def _use_lang(self, lang):
        """The page's language (sent by the blocks), when the website has it: the cards' translations."""
        if lang and lang in dict(request.env['res.lang'].get_installed()):
            request.update_context(lang=lang)

    @http.route('/review_sync/google/callback', type='http', auth='user', sitemap=False)
    def google_callback(self, code=None, state=None, error=None, **kw):
        """Google sign-in comes back here: keep the refresh token, add the account's locations."""
        if not request.env.user.has_group('base.group_system'):
            raise request.not_found()
        account = request.env['review.account'].browse(int(state or 0)).exists()
        if not account:
            raise request.not_found()
        if code and not error:
            try:
                account._google_finish_connect(code)
            except Exception as exc:  # noqa: BLE001 - shown on the account
                account.sudo().note = str(exc)
        else:
            account.sudo().note = error or 'Google sign-in cancelled'
        return request.redirect(f'/odoo/action-website_review_sync.action_review_account/{account.id}')

    @http.route('/review_sync/wall', type='jsonrpc', auth='public', website=True, sitemap=False)
    def wall(self, platform=None, source_id=None, min_rating=1, with_photos=False, language=None, sort='newest',
             offset=0, limit=12, lang=None, **kw):
        """A page of the Reviews wall (limit=0: the filters' choices and the rating badges)."""
        self._use_lang(lang)
        return request.env['review.review'].wall_reviews(
            platform=platform or None, source_id=source_id or None, min_rating=min_rating, with_photos=bool(with_photos),
            language=language or None, sort=sort, offset=offset, limit=limit, website=request.website)

    @http.route('/review_sync/slider', type='jsonrpc', auth='public', website=True, sitemap=False)
    def slider(self, platform=None, source_id=None, min_rating=4, limit=12, scope=None, main_object=None, sort=None,
               lang=None, **kw):
        """Reviews of a Reviews block (the block's options), published ones only. ``scope='page'``: the reviews
        of the page's record (``main_object``, e.g. "mtbg.tour(5,)"), resolved by modules extending
        ``review.review._slider_domain``."""
        self._use_lang(lang)
        record = None
        if scope == 'page' and main_object:
            m = re.fullmatch(r'([\w.]+)\((\d+),?\)', main_object)
            if m and m.group(1) in request.env:
                record = request.env[m.group(1)].sudo().browse(int(m.group(2))).exists() or None
        return request.env['review.review'].slider_reviews(
            platform=platform or None, source_id=source_id or None, min_rating=min_rating, limit=limit,
            lang=request.env.lang, website=request.website, page_record=record, scope=scope, sort=sort)

    @http.route('/review_sync/preset', type='jsonrpc', auth='public', website=True, sitemap=False)
    def preset(self, key=None, lang=None, **kw):
        """A Reviews block linked to a preset (``data-preset``): its HTML, drawn from the preset ('' when gone)."""
        self._use_lang(lang)
        return {'html': request.env['review.preset'].render_block(key)}

    @http.route('/review_sync/preset/preview', type='http', auth='user', website=True, sitemap=False)
    def preset_preview(self, preset=None, **kw):
        """The Reviews page's preview: a page with the preset's block (the page puts its unsaved changes in place)."""
        if not request.env.user.has_group('website.group_website_designer'):
            raise request.not_found()
        record = request.env['review.preset'].browse(int(preset)).exists() if (preset or '').isdigit() else None
        response = request.render('website_review_sync.preset_preview', {
            'block': record._render_saved() if record else ''})
        response.headers['Cache-Control'] = 'no-store'
        return response
