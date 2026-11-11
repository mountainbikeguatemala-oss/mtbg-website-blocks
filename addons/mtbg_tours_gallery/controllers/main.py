from odoo import http
from odoo.http import request


class MtbgGalleryController(http.Controller):

    @http.route('/mtbg_tours_gallery/render', type='jsonrpc', auth='public', website=True)
    def render(self, gallery=None, page_model=None, page_id=None):
        """A Tiled Gallery block's tiles, from what it shows (``<kind>:<id>``, ``ids:<attachment ids>``; ``<kind>:page``
        with the record whose HTML field holds the block, while it is edited)."""
        Gallery = request.env['mtbg.gallery']
        gallery = gallery or ''
        kind, _sep, rest = gallery.partition(':')
        if rest == 'page':
            source = next((s for s in Gallery._mtbg_gallery_sources() if s['kind'] == kind), None)
            gallery = f'{kind}:{int(page_id)}' if source and page_model == source['model'] and page_id else ''
        items = Gallery._mtbg_source_items(gallery)
        return {'html': str(Gallery._mtbg_render(items)), 'count': len(items)}

    @http.route('/mtbg_tours_gallery/sources', type='jsonrpc', auth='user', website=True)
    def sources(self):
        """The record galleries a block can show (the block options' choices), in the editor's language."""
        return request.env['mtbg.gallery']._mtbg_gallery_sources()

    @http.route('/mtbg_tours_gallery/record_add', type='jsonrpc', auth='user', website=True)
    def record_add(self, kind, res_id, attachment_ids):
        """Pictures chosen in a block's media dialog, added at the end of a record's gallery (e.g. a tour's)."""
        pictures = request.env['ir.attachment'].browse([int(i) for i in attachment_ids]).exists()
        pictures.check_access('read')
        pictures = pictures.filtered(lambda a: (a.mimetype or '').startswith('image/'))
        added = request.env['mtbg.gallery']._mtbg_record_add(kind, int(res_id), pictures)
        return {'added': added or 0}
