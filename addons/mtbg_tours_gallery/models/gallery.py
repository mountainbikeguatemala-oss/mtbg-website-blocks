import re

from markupsafe import Markup

from odoo import api, models

from ..services.layout import layout

# a Tiled Gallery block's photos (its data-gallery): pictures chosen in the editor ("ids:12,14"), or a record's own
# gallery ("<kind>:<id>", a kind another module offers: _mtbg_gallery_sources / _mtbg_record_items)
SOURCE_IDS = re.compile(r'^ids:([\d,]*)$')
SOURCE_RECORD = re.compile(r'^([a-z][a-z0-9_]*):(\d+)$')
# the widest the page content gets (Bootstrap's container), for the tiles' "sizes"
CONTENT_PX = 1320


def _alt_of(att):
    """A picked picture's alt text from its file name: 'volcano-ride_2.webp' -> 'volcano ride 2'."""
    return re.sub(r'[-_]+', ' ', (att.name or '').rsplit('.', 1)[0]).strip()


def _sizes(share, screen):
    """The tile's width on screen, so the browser downloads a copy of the right size."""
    vw = max(1, round(share * 100))
    if screen == 'phone':
        return '%svw' % vw
    return '(min-width: 1400px) %spx, %svw' % (round(share * CONTENT_PX), vw)


class MtbgGallery(models.AbstractModel):
    _name = 'mtbg.gallery'
    _description = 'Tiled gallery'

    @api.model
    def _mtbg_photos(self, items):
        """Tiles' photos from [(attachment, caption, alt)], in order: pictures without a size are left out."""
        # (what the visitor may see was decided by the caller: _mtbg_source_items, the tour page)
        attachments = self.env['ir.attachment'].sudo().union(*[att.sudo() for att, _caption, _alt in items])
        attachments._mtbg_measure()
        copies = attachments._mtbg_copies()
        photos = []
        for att, caption, alt in items:
            att = att.sudo()
            if not att.mtbg_width or not att.mtbg_height:
                continue
            photos.append({
                'index': len(photos), 'attachment': att, 'ratio': att.mtbg_width / att.mtbg_height,
                'caption': caption or '', 'alt': alt or caption or '',
                'position': '%s%% %s%%' % (att.mtbg_focus_x, att.mtbg_focus_y),
                **att._mtbg_sources(copies),
            })
        return photos

    @api.model
    def _mtbg_render(self, items, name=''):
        """The tiles' HTML (desktop and phone rows) for [(attachment, caption, alt)]."""
        photos = self._mtbg_photos(items)
        if not photos:
            return Markup()
        screens = []
        for screen in ('desktop', 'phone'):
            rows = layout(photos, screen)
            for row in rows:
                for col in row['columns']:
                    col['sizes'] = _sizes(col['share'], screen)
            screens.append({'screen': screen, 'rows': rows})
        return self.env['ir.qweb']._render('mtbg_tours_gallery.tiles', {
            'screens': screens, 'count': len(photos), 'gallery_name': name,
        })

    @api.model
    def _mtbg_gallery_sources(self):
        """The records whose own gallery a block can show, besides pictures chosen in the editor: other modules add
        theirs (always ``super()`` plus theirs), each a dict:

        * ``kind``: the source's prefix in the block's data-gallery ("tour" -> "tour:12", "tour:page");
        * ``model``, ``domain``: the records offered in the block's searchable picker;
        * ``label`` (the choice: "A tour's gallery"), ``record_label`` ("Tour"), ``search_label`` ("Search a tour…");
        * ``add``: whether the block's "Add" puts pictures into that record's gallery (``_mtbg_record_add``), with
          ``add_label`` and ``help``.

        "<kind>:page" is the record of the page holding the block: the closest element with ``data-mtbg-<kind>``
        (its value, the record's id) or, while editing a record's HTML field, the closest ``data-oe-model``."""
        return []

    @api.model
    def _mtbg_record_items(self, kind, res_id):
        """[(attachment, caption, alt)] of a record's own gallery (``<kind>:<id>``), only what the visitor may see; a
        module offering a kind answers for it (``super()`` for the others). None: no module knows the kind."""
        return None

    @api.model
    def _mtbg_record_add(self, kind, res_id, attachments):
        """Pictures chosen in a block's media dialog, added to a record's gallery (a kind offered with ``add``); the
        number added. None: no module knows the kind."""
        return None

    @api.model
    def _mtbg_source_items(self, source):
        """[(attachment, caption, alt)] of a block's source; only what the visitor may see."""
        match = SOURCE_RECORD.match(source or '')
        if match and match.group(1) != 'ids':
            return self._mtbg_record_items(match.group(1), int(match.group(2))) or []
        match = SOURCE_IDS.match(source or '')
        if match:
            ids = [int(i) for i in match.group(1).split(',') if i]
            atts = self.env['ir.attachment'].sudo().browse(ids).exists()
            designer = self.env.user.has_group('website.group_website_designer')
            by_id = {att.id: att for att in atts if att.public or designer}
            return [(by_id[i], '', _alt_of(by_id[i])) for i in ids if i in by_id]
        return []
