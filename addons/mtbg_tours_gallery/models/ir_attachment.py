import io
import logging

from PIL import Image
import PIL.WebPImagePlugin  # noqa: F401  Odoo registers only a few formats with PIL: WebP must be loaded to save it

from odoo import fields, models

_logger = logging.getLogger(__name__)

# the screen-sized copies of a WebP picture (Odoo does not resize WebP on the fly); the migration makes the same
COPY_WIDTHS = (480, 800, 1280)
COPY_QUALITY = 80


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    mtbg_width = fields.Integer("Picture width", readonly=True)
    mtbg_height = fields.Integer("Picture height", readonly=True)
    mtbg_focus_x = fields.Integer("Focus point (across)", default=50,
                                  help="Where the subject is, in % from the left: a cropped tile keeps it in frame")
    mtbg_focus_y = fields.Integer("Focus point (down)", default=50,
                                  help="Where the subject is, in % from the top: a cropped tile keeps it in frame")

    def write(self, vals):
        if {'raw', 'datas'} & set(vals) and 'mtbg_width' not in vals:
            # a new file: measured again when next shown
            vals = dict(vals, mtbg_width=0, mtbg_height=0)
        return super().write(vals)

    def _mtbg_open(self):
        try:
            return Image.open(io.BytesIO(self.raw or b''))
        except Exception:  # noqa: BLE001  not a picture PIL can read
            return None

    def _mtbg_measure(self):
        """The pictures' sizes, read once from the files (only their headers) and kept."""
        for att in self.filtered(lambda a: not a.mtbg_width and (a.mimetype or '').startswith('image/')):
            image = att.sudo()._mtbg_open()
            if image:
                att.sudo().write({'mtbg_width': image.width, 'mtbg_height': image.height})
        return self

    def _mtbg_copies(self):
        """{original id: {width: copy}}, the 'resize: <px>' copies Odoo and the migration make of WebP pictures."""
        copies = {att.id: {} for att in self}
        if not self:
            return copies
        found = self.sudo().search([('res_model', '=', 'ir.attachment'), ('res_id', 'in', self.ids),
                                    ('description', '=like', 'resize: %'), ('mimetype', '=', 'image/webp')])
        found._mtbg_measure()
        for copy in found:
            copies[copy.res_id][copy.mtbg_width] = copy
        return copies

    def _mtbg_make_copies(self):
        """Screen-sized WebP copies of WebP pictures that have none yet (new uploads; the migration made its own)."""
        made = self.browse()
        webp = self.filtered(lambda a: a.mimetype == 'image/webp')
        existing = webp._mtbg_copies()
        for att in webp:
            if existing[att.id]:
                continue
            image = att.sudo()._mtbg_open()
            if not image:
                continue
            image.load()
            for width in COPY_WIDTHS:
                if width >= image.width:
                    break
                copy = image.resize((width, round(image.height * width / image.width)), Image.LANCZOS)
                buf = io.BytesIO()
                copy.save(buf, 'WEBP', quality=COPY_QUALITY)
                made |= self.sudo().create({
                    'name': att.name, 'description': 'resize: %s' % width, 'raw': buf.getvalue(),
                    # original_id: an optimized copy for Odoo, so the media library hides it (outside debug mode)
                    'mimetype': 'image/webp', 'res_model': 'ir.attachment', 'res_id': att.id, 'public': att.public,
                    'original_id': att.id,
                    'mtbg_width': copy.width, 'mtbg_height': copy.height,
                })
        if made:
            _logger.info("MTBG gallery: made %s WebP copies", len(made))
        return made

    def _mtbg_sources(self, copies=None):
        """{'src': a mid-size copy, 'full': the original, 'srcset': every size with its width} of a picture."""
        self.ensure_one()
        url = '/web/image/%s' % self.id
        sizes = []
        if self.mimetype == 'image/webp':
            copies = (copies if copies is not None else self._mtbg_copies()).get(self.id, {})
            sizes = [('/web/image/%s' % copy.id, width) for width, copy in sorted(copies.items())]
        elif self.mtbg_width:
            # JPEG and PNG: Odoo resizes on the fly (width x 0 keeps the shape)
            sizes = [('%s/%sx0' % (url, width), width) for width in COPY_WIDTHS if width < self.mtbg_width]
        if self.mtbg_width:
            sizes.append((url, self.mtbg_width))
        mid = next((src for src, width in sizes if width >= 800), url)
        return {
            'src': mid, 'full': url,
            'srcset': ', '.join('%s %sw' % (src, width) for src, width in sizes) if len(sizes) > 1 else '',
        }
