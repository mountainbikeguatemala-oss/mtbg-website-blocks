from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request


class MtbgContentBlockPage(http.Controller):

    @http.route('/mtbg/block/<int:block_id>', type='http', auth='user', website=True, sitemap=False)
    def block_page(self, block_id, preview=None, theme=None, **kw):
        """A reusable block on its own, in the website layout, so the full website builder edits its content
        (backgrounds, carousels, every block's options) and saves it to the block. Not a public page.

        ``preview=1``: the Reusable Blocks page's preview (the block alone, on a light or a dark tour page:
        ``theme=dark``)."""
        if not request.env.user.has_group('website.group_website_restricted_editor'):
            raise NotFound()
        block = request.env['mtbg.tours.content.block'].browse(block_id).exists()
        if not block:
            raise NotFound()
        response = request.render('mtbg_tours_content_blocks.block_page', {
            'block': block, 'main_object': block, 'preview': preview == '1', 'dark': theme == 'dark'})
        if preview == '1':
            response.headers['Cache-Control'] = 'no-store'
        return response
