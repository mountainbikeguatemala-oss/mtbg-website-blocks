"""Google Photos (the Photos Library API) for the apps that keep albums there (e.g. the Tours' tour photos): every
Google Photos call lives here, in the connector; the app module declares its own app (code, scopes) through
google.connector._google_app_specs and calls ``env['google.photos']`` with that code.

What Google allows since 2025-03-31: an app creates albums and uploads into them (``photoslibrary.appendonly``),
and reads and changes only the albums and photos it created itself (``photoslibrary.readonly.appcreateddata``,
``photoslibrary.edit.appcreateddata``). Sharing through the API is gone: an administrator makes the share link in
Google Photos (Share › Create link) and pastes it in Odoo. The Google Cloud project needs the Photos Library API
enabled.

A media item's ``base_url`` expires after about 60 minutes: never keep one, fetch the bytes (``fetch_image``)
and keep a copy.

The app's spec: ``read_scopes`` READ_SCOPES, ``write_scopes`` WRITE_SCOPES. Errors are the connector's
``GoogleError`` (``auth``, ``retryable``, ``missing_scopes``); every call is in the sync log."""
import io
import mimetypes
import tempfile
from urllib.parse import quote, urlparse

from odoo import api, models

from .client import GoogleError

API = "https://photoslibrary.googleapis.com/v1"
READ_SCOPES = ["https://www.googleapis.com/auth/photoslibrary.readonly.appcreateddata"]
WRITE_SCOPES = ["https://www.googleapis.com/auth/photoslibrary.appendonly",
                "https://www.googleapis.com/auth/photoslibrary.edit.appcreateddata"]
SCOPE_PREFIX = "https://www.googleapis.com/auth/photoslibrary"
MAX_BYTES = 200 * 1024 * 1024      # Google's limit for a photo
VIDEO_MAX_BYTES = 2 * 1024 ** 3    # a video: at most 2 GB here (owner, 2026-11-14; Google takes up to 20 GB)
CHUNK = 8 * 1024 * 1024            # a file bigger than this goes up in chunks (resumable), one chunk in memory
BIG_CHUNK = 32 * 1024 * 1024       # the chunk of a file over BIG_FROM (fewer calls against the day's limit)
BIG_FROM = 256 * 1024 * 1024
BATCH = 50                         # mediaItems.batchCreate takes at most 50 items
PAGE = 100                         # mediaItems.search: at most 100 a page
TITLE_MAX = 500
DESCRIPTION_MAX = 1000
FILENAME_MAX = 255
UPLOAD_TIMEOUT = 300
RETRYABLE_CODES = {4, 8, 10, 13, 14}  # Google's status codes worth trying again (deadline, quota, aborted, internal,
#                                       unavailable)
IMAGE_HOSTS = ("googleusercontent.com",)


def uses_photos(scopes):
    """An app whose access is Google Photos' (its card and the APIs step say what Google Photos needs)."""
    return any(scope.startswith(SCOPE_PREFIX) for scope in (scopes or "").split())


def _album(data):
    return {"id": data.get("id"), "url": data.get("productUrl") or "", "title": data.get("title") or ""}


def _max_bytes(mimetype):
    return VIDEO_MAX_BYTES if (mimetype or "").startswith("video/") else MAX_BYTES


def _item(data):
    meta = data.get("mediaMetadata") or {}
    video = meta.get("video")
    kind = "video" if video is not None or (data.get("mimeType") or "").startswith("video/") else "photo"
    # (the Library API's video metadata has fps, camera and processing status; a duration only if Google adds it)
    duration = (video or {}).get("duration")
    return {"type": kind, "duration": duration or None,
            "video_status": (video or {}).get("status") or False if kind == "video" else False,
            "id": data.get("id"), "filename": data.get("filename") or "", "base_url": data.get("baseUrl") or "",
            "width": int(meta.get("width") or 0), "height": int(meta.get("height") or 0),
            "taken": meta.get("creationTime") or False, "mime": data.get("mimeType") or ""}


def _read_exact(stream, size):
    """``size`` bytes of ``stream`` (fewer only at its end)."""
    parts, left = [], size
    while left > 0:
        part = stream.read(left)
        if not part:
            break
        parts.append(part)
        left -= len(part)
    return b"".join(parts)


class GooglePhotos(models.AbstractModel):
    _name = "google.photos"
    _description = "Google Photos (Google connector)"

    # ------------------------------------------------------------------
    # The app
    # ------------------------------------------------------------------
    @api.model
    def _gp_app(self, code):
        """The google.connector.app row of ``code`` (empty when no module declares it)."""
        return self.env["google.connector"]._google_app(code)

    @api.model
    def _gp_ready(self, app_code, write=False):
        """The app is on, its Google account granted its access (and writes are allowed, with ``write``)."""
        app = self._gp_app(app_code)
        return bool(app) and app.status == "ready" and (not write or app.writes_allowed)

    @api.model
    def _gp_client(self, app_code, write=False):
        return self.env["google.connector"].client(app_code, write=write)

    def _gp_log(self, app_code, operation, client):
        return self.env["google.connector"].sync_log(app_code, "Google Photos: %s" % operation,
                                                     account=client.account or None)

    # ------------------------------------------------------------------
    # Albums
    # ------------------------------------------------------------------
    @api.model
    def create_album(self, app_code, title):
        """A new album the app owns: {"id", "url" (Google's productUrl, for the administrator), "title"}."""
        title = (title or "").strip()[:TITLE_MAX]
        if not title:
            raise GoogleError(self.env._("A Google Photos album needs a title."))
        client = self._gp_client(app_code, write=True)
        with self._gp_log(app_code, "create album", client) as log:
            album = _album(client.post(API + "/albums", json={"album": {"title": title}}))
            log.add(created=1, note="%s (%s)" % (album["title"], album["id"]))
        return album

    @api.model
    def rename_album(self, app_code, album_id, title):
        """The album's new title (only an album the app created): {"id", "url", "title"}."""
        title = (title or "").strip()[:TITLE_MAX]
        if not album_id or not title:
            raise GoogleError(self.env._("Renaming a Google Photos album needs the album and a title."))
        client = self._gp_client(app_code, write=True)
        with self._gp_log(app_code, "rename album", client) as log:
            album = _album(client.patch(API + "/albums/%s" % quote(album_id, safe=""), params={"updateMask": "title"},
                                        json={"id": album_id, "title": title}))
            log.add(updated=1, note="%s (%s)" % (title, album_id))
        return album

    @api.model
    def album_info(self, app_code, album_id):
        """{"id", "title", "url", "count", "cover_base_url"} of an album the app created; ``count`` is photos and
        videos together (Google's album has only the total: a split needs list_album). (The cover's base URL
        expires within the hour: fetch it now, never keep it)."""
        client = self._gp_client(app_code)
        with self._gp_log(app_code, "album info", client) as log:
            data = client.get(API + "/albums/%s" % quote(album_id or "", safe=""))
            log.add(note=album_id)
        return dict(_album(data), count=int(data.get("mediaItemsCount") or 0),
                    cover_base_url=data.get("coverPhotoBaseUrl") or "")

    @api.model
    def list_album(self, app_code, album_id, limit=None):
        """The album's items, in Google's order (every page, up to ``limit``):
        [{"id", "filename", "base_url", "width", "height", "taken", "mime", "type" ("photo" | "video"),
        "duration" (None when Google gives none), "video_status" (a video's PROCESSING / READY / FAILED)}]."""
        client = self._gp_client(app_code)
        items, page = [], None
        with self._gp_log(app_code, "list album", client) as log:
            while limit is None or len(items) < limit:
                size = PAGE if limit is None else max(1, min(PAGE, limit - len(items)))
                body = {"albumId": album_id, "pageSize": size}
                if page:
                    body["pageToken"] = page
                data = client.post(API + "/mediaItems:search", json=body)
                items += [_item(item) for item in data.get("mediaItems") or []]
                page = data.get("nextPageToken")
                if not page:
                    break
            items = items if limit is None else items[:limit]
            log.add(note="%s: %d items" % (album_id, len(items)))
        return items

    # ------------------------------------------------------------------
    # Uploads
    # ------------------------------------------------------------------
    @api.model
    def upload(self, app_code, album_id, filename, data, mimetype, description=None):
        """One photo or video (bytes, or a file-like stream read a chunk at a time, never whole) into the album:
        {"id", "url"}. ``mimetype``: the caller's (guessed from the name only when empty); a video (video/*) at
        most 2 GB, a photo 200 MB. A GoogleError when Google refuses it (``retryable`` when worth trying again)."""
        client = self._gp_client(app_code, write=True)
        filename = (filename or "photo").strip()[:FILENAME_MAX] or "photo"
        mimetype = mimetype or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        with self._gp_log(app_code, "upload", client) as log:
            token = self._gp_upload_bytes(client, filename, data, mimetype)
            result = self._gp_batch_create(client, album_id, [
                {"upload_token": token, "filename": filename, "description": description}])[0]
            if result.get("error"):
                log.add(failed=1, note="%s: %s" % (filename, result["error"]))
                raise GoogleError(self.env._("Google Photos did not take %(file)s: %(error)s", file=filename,
                                             error=result["error"]), retryable=result.get("retryable", False))
            log.add(created=1, note=filename)
        return {"id": result["id"], "url": result["url"]}

    @api.model
    def batch_create(self, app_code, album_id, items):
        """Already uploaded photos (``items``: [{"upload_token", "filename", "description"}]) into the album, 50 a
        call. One result per item, in order: {"id", "url", "filename"}, or {"error", "retryable", "filename"} for
        an item Google refused (the others still go in)."""
        client = self._gp_client(app_code, write=True)
        with self._gp_log(app_code, "add to album", client) as log:
            results = self._gp_batch_create(client, album_id, items)
            failed = [r for r in results if r.get("error")]
            log.add(created=len(results) - len(failed), failed=len(failed),
                    note="\n".join("%s: %s" % (r["filename"], r["error"]) for r in failed))
        return results

    @api.model
    def _gp_upload_bytes(self, client, filename, data, mimetype):
        """Google's upload token for the bytes: one raw upload up to CHUNK, else a resumable one in chunks."""
        if isinstance(data, (bytes, bytearray, memoryview)):
            data = bytes(data)
            if not data:
                raise GoogleError(self.env._("%s is empty.", filename))
            if len(data) > _max_bytes(mimetype):
                raise self._gp_too_big(filename, mimetype)
            if len(data) <= CHUNK:
                return self._gp_raw_upload(client, data, mimetype)
            return self._gp_resumable(client, io.BytesIO(data), len(data), mimetype)
        stream, size, spool = data, None, None
        try:
            start = stream.tell()
            stream.seek(0, 2)
            size = stream.tell() - start
            stream.seek(start)
        except (AttributeError, OSError, ValueError):
            size = None
        if size is None:  # a stream that cannot seek: kept on disk past CHUNK to learn its size
            spool = tempfile.SpooledTemporaryFile(max_size=CHUNK)
            size = 0
            while True:
                part = stream.read(1024 * 1024)
                if not part:
                    break
                size += len(part)
                if size > _max_bytes(mimetype):
                    spool.close()
                    raise self._gp_too_big(filename, mimetype)
                spool.write(part)
            spool.seek(0)
            stream = spool
        try:
            if not size:
                raise GoogleError(self.env._("%s is empty.", filename))
            if size > _max_bytes(mimetype):
                raise self._gp_too_big(filename, mimetype)
            if size <= CHUNK:
                return self._gp_raw_upload(client, _read_exact(stream, size), mimetype)
            return self._gp_resumable(client, stream, size, mimetype)
        finally:
            if spool:
                spool.close()

    def _gp_too_big(self, filename, mimetype):
        return GoogleError(self.env._("%(file)s is over the %(limit)s limit.", file=filename,
                                      limit="2 GB" if _max_bytes(mimetype) == VIDEO_MAX_BYTES else "200 MB"),
                           status=413)

    @api.model
    def _gp_raw_upload(self, client, data, mimetype):
        token = client.post(API + "/uploads", data=data, raw=True, timeout=UPLOAD_TIMEOUT, headers={
            "Content-Type": "application/octet-stream", "X-Goog-Upload-Content-Type": mimetype,
            "X-Goog-Upload-Protocol": "raw"})
        return self._gp_token(token)

    @api.model
    def _gp_resumable(self, client, stream, size, mimetype):
        """Google's resumable upload: start (the size), then chunks at their offset, the last one finalizes. A
        chunk Google answers 5xx or 429 to is sent again by the client (same offset)."""
        started = client.post(API + "/uploads", data=b"", full=True, headers={
            "X-Goog-Upload-Command": "start", "X-Goog-Upload-Content-Type": mimetype,
            "X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Raw-Size": str(size)})
        url = started.headers.get("X-Goog-Upload-URL")
        if not url:
            raise GoogleError(self.env._("Google Photos did not start the upload."), retryable=True)
        granularity = int(started.headers.get("X-Goog-Upload-Chunk-Granularity") or 0) or 1
        wanted = BIG_CHUNK if size > BIG_FROM else CHUNK
        chunk = max(granularity, wanted // granularity * granularity)
        offset, token = 0, b""
        while offset < size:
            part = _read_exact(stream, min(chunk, size - offset))
            if not part:
                raise GoogleError(self.env._("The photo ended before its size (%(sent)s of %(size)s bytes).",
                                             sent=offset, size=size))
            last = offset + len(part) >= size
            token = client.post(url, data=part, raw=True, timeout=UPLOAD_TIMEOUT, headers={
                "X-Goog-Upload-Command": "upload, finalize" if last else "upload",
                "X-Goog-Upload-Offset": str(offset)})
            offset += len(part)
        return self._gp_token(token)

    def _gp_token(self, token):
        token = (token.decode() if isinstance(token, bytes) else str(token or "")).strip()
        if not token:
            raise GoogleError(self.env._("Google Photos gave no upload token."), retryable=True)
        return token

    @api.model
    def _gp_batch_create(self, client, album_id, items):
        results = []
        for start in range(0, len(items), BATCH):
            batch = items[start:start + BATCH]
            new_items = []
            for item in batch:
                new = {"simpleMediaItem": {"uploadToken": item["upload_token"],
                                           "fileName": (item.get("filename") or "")[:FILENAME_MAX]}}
                if item.get("description"):
                    new["description"] = item["description"][:DESCRIPTION_MAX]
                new_items.append(new)
            data = client.post(API + "/mediaItems:batchCreate", json={"albumId": album_id, "newMediaItems": new_items})
            answers = (data.get("newMediaItemResults") or []) if isinstance(data, dict) else []
            by_token = {answer.get("uploadToken"): answer for answer in answers if answer.get("uploadToken")}
            for index, item in enumerate(batch):
                answer = by_token.get(item["upload_token"]) or (answers[index] if index < len(answers) else {})
                status = answer.get("status") or {}
                code = int(status.get("code") or 0)
                media = answer.get("mediaItem") or {}
                if code or not media.get("id"):
                    results.append({"filename": item.get("filename") or "", "retryable": code in RETRYABLE_CODES,
                                    "error": status.get("message") or self.env._("Google Photos gave no photo back.")})
                else:
                    results.append({"filename": item.get("filename") or media.get("filename") or "",
                                    "id": media["id"], "url": media.get("productUrl") or ""})
        return results

    # ------------------------------------------------------------------
    # Pictures
    # ------------------------------------------------------------------
    @api.model
    def fetch_image(self, app_code, base_url, width=1200):
        """The picture of a media item's ``base_url`` at ``width`` pixels wide (bytes). Base URLs expire after
        about an hour: ask for a fresh one (list_album, album_info) and keep the bytes, never the URL."""
        parsed = urlparse(base_url or "")
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not any(host == h or host.endswith("." + h) for h in IMAGE_HOSTS):
            raise GoogleError(self.env._("Not a Google Photos picture address."))
        width = max(1, min(int(width or 1200), 16383))
        client = self._gp_client(app_code)
        with self._gp_log(app_code, "fetch picture", client) as log:
            data = client.get(base_url + "=w%d" % width, raw=True)
            log.add(note="%d bytes" % len(data or b""))
        return data
