"""Lighter screen copies of the photos (page speed 0.4.0, owner's search plan 2026-11-03: "resized hero copies
re-encoded at about WebP q70"): the 'resize: <px>' WebP copies Odoo's editor, the migration and the gallery make are
made again at quality 70 from their original (the copy itself when its original is gone) and kept only when at least
a tenth lighter. The same picture, the same address (/web/image/<id>), the same size on screen.

The job also makes the phone and tablet copies (800 and 1280 px, q70) of the sections' background photos that have
none (0.4.1: the editor makes them only when a picture is resized in it, so a cover like Contact us's came whole to
phones), then empties Cloudflare's cache once (Edge Cache, where installed) so the pages take them.

A job does it a few at a time (a minute apart: www's workers stay free for visitors), once per copy (it remembers the
last one done), and then every night for the copies made since.
"""
import io
import logging
import re
from datetime import timedelta

import PIL.WebPImagePlugin  # noqa: F401  Odoo registers only a few formats with PIL: WebP must be loaded to save it
from PIL import Image

from odoo import api, fields, models
from odoo.tools.sql import column_exists

_logger = logging.getLogger(__name__)

QUALITY = 70
MIN_SIZE = 40 * 1024        # lighter copies are left as they are
GAIN = 0.9                  # kept when at most 90 % of the copy's weight
BATCH = 30
LAST = 'mtbg_page_speed.lightened_last_id'   # (not mtbg_tours.*: that would empty Cloudflare's cache each batch)
RESIZE = re.compile(r'^resize: (\d+)$')
SCREENS = (800, 1280)       # the phone and tablet copies (ir_http.SCREENS)
DESKTOP_WIDTH = 1920        # the computers' copy (ir_http.DESKTOP, 0.7.1)
DESKTOP_FROM = 1600         # made for photos at least this wide
DESKTOP_GAIN = 0.8          # kept when at most 80 % of the photo
CHECKED = 'mtbg_page_speed.copies_checked_v2'   # the big photos looked at (0.7.1: each once, again for the 1920 copy)
BACKGROUND_BATCH = 10
# a section's background photo in what is stored (views, blog posts, content blocks; their JSON escapes quotes)
BACKGROUND_REF = re.compile(r'background-image:\s*url\((?:&#34;|&quot;|&#39;|&apos;|\\?["\'])?/web/image/(\d+)')
BACKGROUND_SOURCES = (('ir_ui_view', 'arch_db'), ('blog_post', 'content'), ('mtbg_tours_content_block', 'body'))


def remake(raw, width, original=None):
    """The copy at ``width`` px as WebP q70, from ``original`` (bytes) when given, else from the copy ``raw``."""
    image = Image.open(io.BytesIO(original or raw))
    image.load()
    if getattr(image, 'is_animated', False):
        return None
    if image.mode not in ('RGB', 'RGBA'):
        image = image.convert('RGBA' if 'A' in image.getbands() else 'RGB')
    if original and image.width > width:
        image = image.resize((width, max(1, round(image.height * width / image.width))), Image.LANCZOS)
    out = io.BytesIO()
    image.save(out, 'WEBP', quality=QUALITY, method=6)
    return out.getvalue()


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    @api.model
    def _mtbg_background_ids(self):
        """The attachments used as a section's background photo in what is stored."""
        cr, ids = self.env.cr, set()
        for table, column in BACKGROUND_SOURCES:
            if not column_exists(cr, table, column):
                continue
            cr.execute(f'SELECT "{column}"::text FROM "{table}" WHERE "{column}"::text LIKE %s', ['%background-image%'])
            for (text,) in cr.fetchall():
                ids.update(int(found) for found in BACKGROUND_REF.findall(text or ''))
        # the tour pages' backgrounds (Website 0.10.28: written as the picture's own /web/image address)
        ids.update(self.sudo().search([('res_field', '=', 'page_background_image'), ('public', '=', True)]).ids)
        return ids

    @api.model
    def _mtbg_hero_ids(self):
        """The photos a page shows big: the sections' backgrounds and the tour pages' main photo (their cover)."""
        ids = self._mtbg_background_ids()
        if 'mtbg.tour' in self.env:
            Tour = self.env['mtbg.tour'].sudo()
            for tour in Tour.search([('is_published', '=', True)]):
                cover = tour.get_cover_attachment() if hasattr(tour, 'get_cover_attachment') else None
                if cover:
                    ids.add(cover.id)
        return ids

    @api.model
    def _mtbg_background_copies(self, limit=BACKGROUND_BATCH):
        """The screen copies the big photos lack (``limit`` photos a run): phone 800 and tablet 1280 px when the photo
        is wider, and (0.7.1) a computer copy, 1920 px or the photo's own width when 1600 px or more, kept only when at
        most 80 % of the photo. Each photo is looked at once (CHECKED): a photo too small for a copy never comes back.
        One Cloudflare purge when copies were made. Returns (photos done, copies made, photos left)."""
        Attachment = self.sudo()
        ICP = self.env['ir.config_parameter'].sudo()
        checked = {int(i) for i in (ICP.get_param(CHECKED) or '').split(',') if i.strip().isdigit()}
        photos = Attachment.browse(sorted(self._mtbg_hero_ids() - checked)).exists().filtered(
            # (not our own screen copies; an editor-made picture (cropped, optimized) is one the page shows: kept)
            lambda a: a.public and (a.mimetype or '').startswith('image/') and a.mimetype != 'image/svg+xml'
            and not RESIZE.match(a.description or ''))
        if not photos:
            return 0, 0, 0
        widths = {}
        for copy in Attachment.search([('res_model', '=', 'ir.attachment'), ('res_id', 'in', photos.ids),
                                       ('description', '=like', 'resize: %'), ('mimetype', '=', 'image/webp')]):
            found = RESIZE.match(copy.description or '')
            if found:
                widths.setdefault(copy.res_id, set()).add(int(found.group(1)))
        made = 0
        batch = photos[:limit]
        for photo in batch:
            checked.add(photo.id)
            try:
                image = Image.open(io.BytesIO(photo.raw))
                image.load()
                if getattr(image, 'is_animated', False):
                    continue
                if image.mode not in ('RGB', 'RGBA'):
                    image = image.convert('RGBA' if 'A' in image.getbands() else 'RGB')
            except Exception as e:  # noqa: BLE001 - a picture Pillow cannot read: left as it is
                _logger.info("Page speed: photo %s left as it is (%s)", photo.id, e)
                continue
            have = widths.get(photo.id, set())
            wanted = [(w, 1.0) for w in SCREENS if w < image.width and w not in have]
            desk = min(DESKTOP_WIDTH, image.width)
            if image.width >= DESKTOP_FROM and not any(w >= desk for w in have if w > max(SCREENS)):
                wanted.append((desk, DESKTOP_GAIN))
            for width, gain in wanted:
                copy = image if width >= image.width else image.resize(
                    (width, max(1, round(image.height * width / image.width))), Image.LANCZOS)
                out = io.BytesIO()
                copy.save(out, 'WEBP', quality=QUALITY, method=6)
                if len(out.getvalue()) > (photo.file_size or 0) * gain or len(out.getvalue()) >= (photo.file_size or 0):
                    continue  # (never heavier than the photo; a computer copy only when clearly lighter)
                vals = {'name': photo.name, 'description': 'resize: %s' % width, 'raw': out.getvalue(),
                        'mimetype': 'image/webp', 'res_model': 'ir.attachment', 'res_id': photo.id, 'public': True}
                if 'original_id' in Attachment._fields:
                    vals['original_id'] = photo.id  # (an optimized copy for Odoo: hidden in the media library)
                if 'mtbg_width' in Attachment._fields:
                    vals.update(mtbg_width=copy.width, mtbg_height=copy.height)
                Attachment.create(vals)
                made += 1
        ICP.set_param(CHECKED, ','.join(str(i) for i in sorted(checked)))
        if made:
            _logger.info("Page speed: %s screen copies made for %s big photos", made, len(batch))
            if 'mtbg.edge.cache' in self.env:
                self.env['mtbg.edge.cache']._mtbg_changed()  # (the pages take them: one purge, as for an edit)
        return len(batch), made, max(0, len(photos) - len(batch))

    @api.model
    def _mtbg_lighten_copies(self, limit=BATCH):
        """The next ``limit`` copies made lighter; asks for the next batch in a minute while there are more.
        Returns (looked at, made lighter, KB saved)."""
        _done, _made, left = self._mtbg_background_copies()
        ICP = self.env['ir.config_parameter'].sudo()
        last = int(ICP.get_param(LAST) or 0)
        Attachment = self.sudo()
        # (0.4.2: a copy need not be public itself: the sized address of a public photo (/web/image/<id>/1280x1280,
        # the tour pages' cover) is answered with it (Website's ir.binary); the photo must be public)
        copies = Attachment.search([
            ('id', '>', last), ('description', '=like', 'resize: %'), ('mimetype', '=', 'image/webp'),
            ('file_size', '>', MIN_SIZE)], order='id', limit=limit)
        originals = {a.id: a for a in Attachment.browse(
            list({c.res_id for c in copies if c.res_model == 'ir.attachment' and c.res_id})).exists()}
        lighter = saved = 0
        for copy in copies:
            found = RESIZE.match(copy.description or '')
            photo = originals.get(copy.res_id) if copy.res_model == 'ir.attachment' else None
            if not copy.public and not (photo and photo.public):
                continue  # (a private picture's copy: left alone)
            original = (copy.original_id if 'original_id' in copy._fields else Attachment) or photo or Attachment
            try:
                source = original.raw if original and (original.mimetype or '').startswith('image/') and \
                    original.mimetype != 'image/svg+xml' else None
                new = remake(copy.raw, int(found.group(1)), source) if found else None
            except Exception as e:  # noqa: BLE001 - a picture Pillow cannot read: left as it is
                _logger.info("Page speed: copy %s left as it is (%s)", copy.id, e)
                new = None
            if new and len(new) <= copy.file_size * GAIN:
                saved += copy.file_size - len(new)
                copy.raw = new
                lighter += 1
        if copies:
            ICP.set_param(LAST, str(copies[-1].id))
            _logger.info("Page speed: %s screen copies looked at, %s made lighter (%s KB less)", len(copies), lighter,
                         saved // 1024)
        if len(copies) == limit or left:
            cron = self.env.ref('mtbg_tours_page_speed.cron_lighten_copies', raise_if_not_found=False)
            if cron:
                cron._trigger(at=fields.Datetime.now() + timedelta(minutes=1))
        return len(copies), lighter, saved // 1024
