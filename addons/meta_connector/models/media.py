"""The Instagram feed: the newest posts of each Instagram account this site uses, kept here as WebP copies (the site's
image rule: at most 1920 px and about 350 KB, plus a 640 px tile), refreshed by a cron. The website block reads
them (``_meta_feed``), never Instagram: a page view makes no call to Meta."""
import io
import logging
from datetime import datetime

from PIL import Image, WebPImagePlugin  # noqa: F401 (Odoo loads only a few image plugins: WebP's saver)

from odoo import api, fields, models

from . import graph

_logger = logging.getLogger(__name__)

KEEP = 24  # posts kept per account
FULL_SIZE, FULL_BYTES = 1920, 350 * 1024
TILE_SIZE, TILE_BYTES = 640, 90 * 1024
AVATAR_SIZE, AVATAR_BYTES = 320, 40 * 1024


def webp(data, size, max_bytes):
    """``data`` (any image) as WebP: at most ``size`` px wide and high, about ``max_bytes`` (quality lowered as
    needed)."""
    image = Image.open(io.BytesIO(data))
    image = image.convert("RGBA" if image.mode in ("RGBA", "LA", "P") and "transparency" in image.info else "RGB")
    image.thumbnail((size, size), Image.LANCZOS)
    out = b""
    for quality in (82, 74, 66, 58, 50, 42):
        buffer = io.BytesIO()
        image.save(buffer, "WEBP", quality=quality, method=6)
        out = buffer.getvalue()
        if len(out) <= max_bytes:
            break
    return out


def posted_at(value):
    """Instagram's "2026-10-22T18:01:02+0000" -> naive UTC."""
    try:
        return datetime.strptime(str(value)[:19], "%Y-%m-%dT%H:%M:%S")
    except (TypeError, ValueError):
        return fields.Datetime.now()


class MetaConnectorMedia(models.Model):
    _name = "meta.connector.media"
    _description = "Instagram Post (cached)"
    _order = "posted_at desc, id desc"

    page_id = fields.Many2one("meta.connector.page", required=True, ondelete="cascade", index=True)
    media_id = fields.Char(required=True, index=True)
    media_type = fields.Selection([("IMAGE", "Photo"), ("VIDEO", "Video"), ("CAROUSEL_ALBUM", "Album")],
                                  default="IMAGE")
    permalink = fields.Char()
    caption = fields.Text()
    posted_at = fields.Datetime(index=True)
    image_id = fields.Many2one("ir.attachment", string="Image", ondelete="set null")
    tile_id = fields.Many2one("ir.attachment", string="Tile", ondelete="set null")

    _media_unique = models.Constraint("UNIQUE(page_id, media_id)", "This post is already kept.")


    @staticmethod
    def _image_url(item):
        """The post's picture: a photo itself, a video's cover, an album's first picture."""
        if item.get("media_type") == "VIDEO":
            return item.get("thumbnail_url")
        if item.get("media_type") == "CAROUSEL_ALBUM":
            for child in (item.get("children") or {}).get("data") or []:
                url = child.get("thumbnail_url") if child.get("media_type") == "VIDEO" else child.get("media_url")
                if url:
                    return url
        return item.get("media_url") or item.get("thumbnail_url")

    def _attach(self, name, data):
        return self.env["ir.attachment"].sudo().create({
            "name": name, "raw": data, "mimetype": "image/webp", "public": True,
            "res_model": self._name, "res_id": self.id})

    @api.model
    def _refresh_profile(self, page):
        """The account's name, follower and post counts, and its profile photo (a WebP copy, for the header)."""
        info = graph.instagram_account(page.ig_id, page._token())
        values = {"ig_name": info.get("name") or False, "ig_followers": info.get("followers_count") or 0,
                  "ig_posts": info.get("media_count") or 0}
        if info.get("username"):
            values["ig_username"] = info["username"]
        if info.get("profile_picture_url"):
            try:
                data, _type = graph.download(info["profile_picture_url"])
                avatar = webp(data, AVATAR_SIZE, AVATAR_BYTES)
            except (graph.GraphError, OSError, ValueError) as error:
                _logger.warning("Meta: Instagram photo of @%s not kept: %s", page.ig_username, error)
            else:
                if page.ig_avatar_id:
                    page.ig_avatar_id.sudo().raw = avatar
                else:
                    values["ig_avatar_id"] = self.env["ir.attachment"].sudo().create({
                        "name": "instagram-%s.webp" % page.ig_id, "raw": avatar, "mimetype": "image/webp",
                        "public": True, "res_model": page._name, "res_id": page.id}).id
        page.sudo().write(values)

    @api.model
    def _refresh_page(self, page):
        """The newest posts of ``page``'s Instagram account: new ones kept (as WebP), the others' captions updated,
        the oldest beyond KEEP removed. Returns how many are new."""
        items = graph.media(page.ig_id, page._token(), limit=KEEP)
        kept = {media.media_id: media for media in self.sudo().search([("page_id", "=", page.id)])}
        created = 0
        for item in items:
            values = {"media_type": item.get("media_type") if item.get("media_type") in ("IMAGE", "VIDEO", "CAROUSEL_ALBUM")
                      else "IMAGE", "permalink": item.get("permalink"), "caption": item.get("caption") or False,
                      "posted_at": posted_at(item.get("timestamp"))}
            media = kept.get(item["id"])
            if media:
                media.write(values)
                continue
            url = self._image_url(item)
            if not url:
                continue
            try:
                data, _type = graph.download(url)
                full, tile = webp(data, FULL_SIZE, FULL_BYTES), webp(data, TILE_SIZE, TILE_BYTES)
            except (graph.GraphError, OSError, ValueError) as error:
                _logger.warning("Meta: Instagram post %s not kept: %s", item.get("id"), error)
                continue
            media = self.sudo().create(dict(values, page_id=page.id, media_id=item["id"]))
            media.write({"image_id": media._attach("instagram-%s.webp" % item["id"], full).id,
                         "tile_id": media._attach("instagram-%s-tile.webp" % item["id"], tile).id})
            created += 1
        self.sudo().search([("page_id", "=", page.id)])[KEEP:].unlink()
        return created

    @api.model
    def _cron_refresh(self):
        """Every hour: the feed of each Instagram account this site uses (when the Feed block is switched on)."""
        if not self.env["meta.connector"]._meta_use("ig_feed"):
            return
        for page in self.env["meta.connector"]._meta_pages("instagram"):
            try:
                self._refresh_profile(page)
            except graph.GraphError as error:
                _logger.warning("Meta: Instagram profile of @%s not refreshed: %s", page.ig_username, error)
            try:
                self._refresh_page(page)
            except graph.GraphError as error:
                _logger.warning("Meta: Instagram feed of @%s not refreshed: %s", page.ig_username, error)
                continue
        # accounts no longer used: their posts go
        self.sudo().search([("page_id", "not in", self.env["meta.connector"]._meta_pages("instagram").ids)]).unlink()

    @api.model
    def _meta_feed(self, count=6, username=None):
        """What the website block shows: the account (the one named, else the first used) and its newest posts."""
        pages = self.env["meta.connector"]._meta_pages("instagram")
        if not self.env["meta.connector"]._meta_use("ig_feed"):
            pages = pages.browse()
        page = pages.filtered(lambda p: p.ig_username == username)[:1] if username else pages[:1]
        if not page:
            return {"username": "", "profile_url": "", "name": "", "followers": 0, "posts": 0, "avatar": "",
                    "items": []}
        posts = self.sudo().search([("page_id", "=", page.id), ("tile_id", "!=", False)], limit=max(1, min(int(count), KEEP)))
        return {
            "username": page.ig_username or "",
            "profile_url": "https://www.instagram.com/%s/" % page.ig_username if page.ig_username else "",
            "name": page.ig_name or "",
            "followers": page.ig_followers,
            "posts": page.ig_posts,
            "avatar": "/web/image/%s?unique=%s" % (page.ig_avatar_id.id, (page.ig_avatar_id.checksum or "")[:8])
                      if page.ig_avatar_id else "",
            "items": [{"id": post.id, "tile": "/web/image/%s" % post.tile_id.id,
                       "full": "/web/image/%s" % post.image_id.id if post.image_id else "",
                       "url": post.permalink or "", "type": post.media_type,
                       "caption": (post.caption or "")[:200]} for post in posts],
        }
