import io
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.google_connector.models import client as client_module
from odoo.addons.google_connector.models import photos as photos_module
from odoo.addons.google_connector.models.client import GoogleError
from odoo.addons.google_connector.models.connector import GoogleConnector
from odoo.addons.google_connector.models.photos import API, READ_SCOPES, WRITE_SCOPES

from .test_connector import Response

SPECS = {"testphotos": {"label": "Test Photos", "module": False, "read_scopes": READ_SCOPES,
                        "write_scopes": WRITE_SCOPES}}


class Recording(io.BytesIO):
    """A seekable file that remembers how much each read asked for."""

    def __init__(self, data):
        super().__init__(data)
        self.reads = []

    def read(self, size=-1):
        self.reads.append(size)
        return super().read(size)


class Huge:
    """A seekable stream that says it is ``size`` bytes long (nothing is read before the size check)."""

    def __init__(self, size):
        self.size, self.pos = size, 0

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos = self.size if whence == 2 else offset

    def read(self, size=-1):
        raise AssertionError("read before the size check")


class Unseekable:
    """A stream that cannot seek (e.g. a request body)."""

    def __init__(self, data):
        self._stream = io.BytesIO(data)

    def read(self, size=-1):
        return self._stream.read(min(size, 1000) if size and size > 0 else size)


@tagged("post_install", "-at_install")
class TestGooglePhotos(TransactionCase):

    def setUp(self):
        super().setUp()
        patcher = patch.object(GoogleConnector, "_google_app_specs", lambda self: dict(SPECS))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.G = self.env["google.connector"]
        self.P = self.env["google.photos"]
        self.G._google_set_credentials(client_id="cid", client_secret="secret")
        self.G._google_sync_apps()
        self.app = self.P._gp_app("testphotos")
        self.app.write({"on": True, "writes_allowed": True})
        self.account = self.env["google.connector.account"].create({
            "name": "ops@example.com", "email": "ops@example.com", "state": "connected", "refresh_token": "r",
            "access_token": "a", "token_expiry": 9999999999,
            "granted_scopes": " ".join(["openid"] + READ_SCOPES + WRITE_SCOPES)})
        self.calls = []
        self.answers = []
        self.request = patch.object(client_module.requests, "request", side_effect=self._fake_request)
        self.request.start()
        self.addCleanup(self.request.stop)

    def _fake_request(self, method, url, **kwargs):
        data = kwargs.get("data")
        self.calls.append({"method": method, "url": url, "params": kwargs.get("params"), "json": kwargs.get("json"),
                           "data": data, "headers": kwargs.get("headers") or {}})
        answer = self.answers.pop(0)
        return answer(method, url, kwargs) if callable(answer) else answer

    def _logs(self, operation):
        return self.env["google.connector.log"].search([("app_code", "=", "testphotos"),
                                                        ("operation", "=", "Google Photos: %s" % operation)])

    def test_ready_and_the_card_says_what_google_allows(self):
        self.assertTrue(self.P._gp_ready("testphotos"))
        self.assertTrue(self.P._gp_ready("testphotos", write=True))
        self.assertIn("Photos Library API", self.app.description)
        self.assertIn("only the albums and photos it created", self.app.description)
        self.app.writes_allowed = False
        self.assertFalse(self.P._gp_ready("testphotos", write=True))
        self.assertFalse(self.P._gp_ready("unknown"))
        wizard = self.env["google.connector.setup"].create({"project_id": "p1"})
        self.assertIn("apis/library/photoslibrary.googleapis.com?project=p1", wizard.apis_html)
        self.assertIn("only the albums and photos it created", wizard.apis_html)
        for scope in READ_SCOPES:
            self.assertIn(scope, wizard.scope_strings)

    def test_missing_scopes(self):
        self.account.granted_scopes = " ".join(["openid"] + READ_SCOPES)
        self.app.invalidate_recordset(["status"])
        self.assertFalse(self.P._gp_ready("testphotos"))
        with self.assertRaises(GoogleError) as refused:
            self.P.create_album("testphotos", "Day 1")
        self.assertTrue(refused.exception.auth)
        self.assertEqual(set(refused.exception.missing_scopes), set(WRITE_SCOPES))
        self.assertFalse(self.calls, "nothing asked of Google")
        self.answers = [Response(200, {"id": "A1", "title": "Day 1", "mediaItemsCount": "3"})]
        self.assertEqual(self.P.album_info("testphotos", "A1")["count"], 3, "reading needs the read access only")
        self.app.writes_allowed = False
        with self.assertRaises(GoogleError):
            self.P.upload("testphotos", "A1", "a.jpg", b"x", "image/jpeg")

    def test_create_and_rename_album(self):
        self.answers = [Response(200, {"id": "A1", "title": "Day 1", "productUrl": "https://photos.google.com/lr/a1",
                                       "isWriteable": True})]
        album = self.P.create_album("testphotos", "  Day 1  ")
        self.assertEqual(album, {"id": "A1", "url": "https://photos.google.com/lr/a1", "title": "Day 1"})
        self.assertEqual((self.calls[0]["method"], self.calls[0]["url"]), ("POST", API + "/albums"))
        self.assertEqual(self.calls[0]["json"], {"album": {"title": "Day 1"}})
        self.assertEqual(self.calls[0]["headers"]["Authorization"], "Bearer a")
        self.assertEqual(self._logs("create album").state, "done")
        self.answers = [Response(200, {"id": "A1", "title": "Day 1 · Ruta", "productUrl": "https://photos.google.com/lr/a1"})]
        renamed = self.P.rename_album("testphotos", "A1", "Day 1 · Ruta")
        self.assertEqual(renamed["title"], "Day 1 · Ruta")
        self.assertEqual((self.calls[1]["method"], self.calls[1]["url"]), ("PATCH", API + "/albums/A1"))
        self.assertEqual(self.calls[1]["params"], {"updateMask": "title"})
        self.assertEqual(self.calls[1]["json"], {"id": "A1", "title": "Day 1 · Ruta"})
        with self.assertRaises(GoogleError):
            self.P.create_album("testphotos", " ")

    def test_upload_raw(self):
        self.answers = [Response(200, content=b"TOKEN1"),
                        Response(200, {"newMediaItemResults": [{"uploadToken": "TOKEN1", "status": {"message": "Success"},
                                                                "mediaItem": {"id": "M1", "productUrl": "https://p/m1"}}]})]
        result = self.P.upload("testphotos", "A1", "a.jpg", b"JPEGDATA", "image/jpeg", description="Uploaded by Ana")
        self.assertEqual(result, {"id": "M1", "url": "https://p/m1"})
        upload, create = self.calls
        self.assertEqual(upload["url"], API + "/uploads")
        self.assertEqual(upload["data"], b"JPEGDATA")
        self.assertEqual(upload["headers"]["X-Goog-Upload-Protocol"], "raw")
        self.assertEqual(upload["headers"]["X-Goog-Upload-Content-Type"], "image/jpeg")
        self.assertEqual(create["url"], API + "/mediaItems:batchCreate")
        self.assertEqual(create["json"], {"albumId": "A1", "newMediaItems": [
            {"description": "Uploaded by Ana", "simpleMediaItem": {"uploadToken": "TOKEN1", "fileName": "a.jpg"}}]})
        self.assertEqual(self._logs("upload").created, 1)

    def test_upload_resumable_from_a_stream(self):
        """A big file goes up in chunks at their offset; a chunk Google answers 503 to is sent again."""
        self.patch(photos_module, "CHUNK", 10)
        data = bytes(range(20))

        self.answers = [Response(200, headers={"X-Goog-Upload-URL": "https://up.example/s1",
                                               "X-Goog-Upload-Chunk-Granularity": "4"}),
                        Response(200), Response(503, {"error": {"message": "busy"}}), Response(200),
                        Response(200, content=b"TOKEN2"),
                        Response(200, {"newMediaItemResults": [{"uploadToken": "TOKEN2", "status": {"code": 0},
                                                                "mediaItem": {"id": "M2", "productUrl": "https://p/m2"}}]})]
        result = self.P.upload("testphotos", "A1", "big.jpg", Unseekable(data), None)
        self.assertEqual(result["id"], "M2")
        start = self.calls[0]
        self.assertEqual(start["headers"]["X-Goog-Upload-Command"], "start")
        self.assertEqual(start["headers"]["X-Goog-Upload-Raw-Size"], "20")
        self.assertEqual(start["headers"]["X-Goog-Upload-Content-Type"], "image/jpeg", "guessed from the name")
        chunks = self.calls[1:5]
        self.assertTrue(all(c["url"] == "https://up.example/s1" for c in chunks))
        self.assertEqual([c["headers"]["X-Goog-Upload-Offset"] for c in chunks], ["0", "8", "8", "16"],
                         "8-byte chunks (the granularity), the refused one again")
        self.assertEqual([c["headers"]["X-Goog-Upload-Command"] for c in chunks],
                         ["upload", "upload", "upload", "upload, finalize"])
        self.assertEqual(chunks[0]["data"] + chunks[2]["data"] + chunks[3]["data"], data)

    def test_upload_limits(self):
        self.patch(photos_module, "MAX_BYTES", 5)
        with self.assertRaises(GoogleError) as big:
            self.P.upload("testphotos", "A1", "a.jpg", b"123456", "image/jpeg")
        self.assertEqual(big.exception.status, 413)
        with self.assertRaises(GoogleError):
            self.P.upload("testphotos", "A1", "a.jpg", io.BytesIO(b"123456"), "image/jpeg")
        with self.assertRaises(GoogleError):
            self.P.upload("testphotos", "A1", "a.jpg", Unseekable(b"123456"), "image/jpeg")
        with self.assertRaises(GoogleError):
            self.P.upload("testphotos", "A1", "a.jpg", b"", "image/jpeg")
        self.assertFalse(self.calls)

    def test_upload_refused_by_batch_create(self):
        self.answers = [Response(200, content=b"T"),
                        Response(200, {"newMediaItemResults": [{"uploadToken": "T", "status": {
                            "code": 13, "message": "Internal error"}}]})]
        try:  # (assertRaises would roll the failed log back)
            self.P.upload("testphotos", "A1", "a.jpg", b"x", "image/jpeg")
            raised = None
        except GoogleError as error:
            raised = error
        self.assertTrue(raised and raised.retryable)
        self.assertIn("Internal error", str(raised))
        log = self._logs("upload")
        self.assertEqual((log.state, log.failed), ("failed", 1))

    def test_batch_create_partial_failure(self):
        items = [{"upload_token": "T%d" % i, "filename": "p%d.jpg" % i} for i in range(52)]

        def answer(method, url, kwargs):
            results = []
            for new in kwargs["json"]["newMediaItems"]:
                token = new["simpleMediaItem"]["uploadToken"]
                if token == "T1":
                    results.append({"uploadToken": token, "status": {"code": 3, "message": "Bad file"}})
                else:
                    results.append({"uploadToken": token, "status": {"message": "Success"},
                                    "mediaItem": {"id": "M" + token, "productUrl": "https://p/" + token}})
            return Response(207 if any(r["status"].get("code") for r in results) else 200,
                            {"newMediaItemResults": list(reversed(results))})
        self.answers = [answer, answer]
        results = self.P.batch_create("testphotos", "A1", items)
        self.assertEqual([len(c["json"]["newMediaItems"]) for c in self.calls], [50, 2], "50 a call")
        self.assertEqual(len(results), 52)
        self.assertEqual(results[0], {"filename": "p0.jpg", "id": "MT0", "url": "https://p/T0"}, "in order")
        self.assertEqual(results[1], {"filename": "p1.jpg", "retryable": False, "error": "Bad file"})
        self.assertEqual(results[51]["id"], "MT51")
        log = self._logs("add to album")
        self.assertEqual((log.state, log.created, log.failed), ("done", 51, 1))
        self.assertIn("p1.jpg: Bad file", log.note)

    def test_album_info_list_pages_and_fetch(self):
        self.answers = [Response(200, {"id": "A1", "title": "Day 1", "productUrl": "https://photos.google.com/lr/a1",
                                       "mediaItemsCount": "120",
                                       "coverPhotoBaseUrl": "https://lh3.googleusercontent.com/lr/cover"})]
        self.assertEqual(self.P.album_info("testphotos", "A1"), {
            "id": "A1", "title": "Day 1", "url": "https://photos.google.com/lr/a1", "count": 120,
            "cover_base_url": "https://lh3.googleusercontent.com/lr/cover"})
        self.assertEqual((self.calls[0]["method"], self.calls[0]["url"]), ("GET", API + "/albums/A1"))

        def item(n):
            return {"id": "M%d" % n, "filename": "p%d.jpg" % n, "mimeType": "image/jpeg",
                    "baseUrl": "https://lh3.googleusercontent.com/lr/m%d" % n,
                    "mediaMetadata": {"width": "4000", "height": "3000", "creationTime": "2026-11-14T10:00:00Z"}}
        self.answers = [Response(200, {"mediaItems": [item(n) for n in range(100)], "nextPageToken": "P2"}),
                        Response(200, {"mediaItems": [item(n) for n in range(100, 120)]})]
        items = self.P.list_album("testphotos", "A1")
        self.assertEqual(len(items), 120)
        self.assertEqual(items[0], {"id": "M0", "filename": "p0.jpg", "base_url": "https://lh3.googleusercontent.com/lr/m0",
                                    "width": 4000, "height": 3000, "taken": "2026-11-14T10:00:00Z", "mime": "image/jpeg",
                                    "type": "photo", "duration": None, "video_status": False})
        self.assertEqual(self.calls[1]["url"], API + "/mediaItems:search")
        self.assertEqual(self.calls[1]["json"], {"albumId": "A1", "pageSize": 100})
        self.assertEqual(self.calls[2]["json"], {"albumId": "A1", "pageSize": 100, "pageToken": "P2"})
        self.answers = [Response(200, {"mediaItems": [item(n) for n in range(3)], "nextPageToken": "P2"})]
        self.assertEqual(len(self.P.list_album("testphotos", "A1", limit=3)), 3)
        self.assertEqual(self.calls[3]["json"]["pageSize"], 3)
        self.assertEqual(len(self.calls), 4, "the limit reached: no next page")
        self.answers = [Response(200, content=b"\xff\xd8JPEG")]
        self.assertEqual(self.P.fetch_image("testphotos", "https://lh3.googleusercontent.com/lr/cover"), b"\xff\xd8JPEG")
        self.assertEqual(self.calls[4]["url"], "https://lh3.googleusercontent.com/lr/cover=w1200")
        self.answers = [Response(200, content=b"J")]
        self.P.fetch_image("testphotos", "https://lh3.googleusercontent.com/lr/cover", width=400)
        self.assertEqual(self.calls[5]["url"], "https://lh3.googleusercontent.com/lr/cover=w400")
        with self.assertRaises(GoogleError, msg="the token goes to Google only"):
            self.P.fetch_image("testphotos", "https://evil.example/lr/cover")
        self.assertEqual(len(self.calls), 6)

    def test_token_refresh_and_errors(self):
        """An expired token is refreshed; a 401 refreshes once and tries again; Google's refusal is a GoogleError."""
        self.account.write({"access_token": False, "token_expiry": 0})
        self.answers = [Response(401, {"error": "expired"}),
                        Response(200, {"id": "A9", "title": "T", "productUrl": "https://photos.google.com/lr/a9"})]
        tokens = [Response(200, {"access_token": "new1", "expires_in": 3600}),
                  Response(200, {"access_token": "new2", "expires_in": 3600})]
        with patch.object(client_module.requests, "post", side_effect=lambda *a, **k: tokens.pop(0)):
            self.assertEqual(self.P.create_album("testphotos", "T")["id"], "A9")
        self.assertEqual([c["headers"]["Authorization"] for c in self.calls], ["Bearer new1", "Bearer new2"])
        self.answers = [Response(403, {"error": {"message": "Photos Library API has not been used in project"}})]
        try:
            self.P.album_info("testphotos", "A9")
            raised = None
        except GoogleError as error:
            raised = error
        self.assertEqual(raised.status, 403)
        self.assertFalse(raised.retryable)
        self.assertEqual(self._logs("album info").state, "failed")
        with patch.object(client_module.requests, "post", return_value=Response(400, {"error": "invalid_grant"})):
            self.account.write({"access_token": False, "token_expiry": 0})
            try:
                self.P.album_info("testphotos", "A9")
                raised = None
            except GoogleError as error:
                raised = error
        self.assertTrue(raised.auth, "the sign-in is gone: connect again")
        self.assertEqual(self.account.state, "error")

    def test_video_upload_in_chunks(self):
        """A video goes up with Google's resumable protocol, read a chunk at a time (never whole), with the
        caller's mimetype; a big file uses the bigger chunk."""
        self.patch(photos_module, "CHUNK", 8)
        self.patch(photos_module, "BIG_CHUNK", 16)
        self.patch(photos_module, "BIG_FROM", 30)
        data = bytes(range(40))
        stream = Recording(data)
        self.answers = [Response(200, headers={"X-Goog-Upload-URL": "https://up.example/v1"}),
                        Response(200), Response(200), Response(200, content=b"VTOKEN"),
                        Response(200, {"newMediaItemResults": [{"uploadToken": "VTOKEN", "status": {"message": "OK"},
                                                                "mediaItem": {"id": "V1", "productUrl": "https://p/v1"}}]})]
        result = self.P.upload("testphotos", "A1", "ride.mov", stream, "video/quicktime")
        self.assertEqual(result, {"id": "V1", "url": "https://p/v1"})
        start, *chunks, create = self.calls
        self.assertEqual(start["headers"]["X-Goog-Upload-Protocol"], "resumable")
        self.assertEqual(start["headers"]["X-Goog-Upload-Content-Type"], "video/quicktime", "the caller's mimetype")
        self.assertEqual(start["headers"]["X-Goog-Upload-Raw-Size"], "40")
        self.assertEqual([len(c["data"]) for c in chunks], [16, 16, 8], "the big chunk (over BIG_FROM)")
        self.assertEqual([c["headers"]["X-Goog-Upload-Offset"] for c in chunks], ["0", "16", "32"])
        self.assertEqual(chunks[-1]["headers"]["X-Goog-Upload-Command"], "upload, finalize")
        self.assertEqual(b"".join(c["data"] for c in chunks), data)
        self.assertTrue(stream.reads and all(0 < size <= 16 for size in stream.reads), "never read whole")
        self.assertEqual(create["json"]["newMediaItems"][0]["simpleMediaItem"]["fileName"], "ride.mov")

    def test_video_and_photo_limits(self):
        """A video at most 2 GB, a photo 200 MB: refused before anything is read or sent."""
        with self.assertRaises(GoogleError) as video:
            self.P.upload("testphotos", "A1", "long.mp4", Huge(2 * 1024 ** 3 + 1), "video/mp4")
        self.assertEqual(video.exception.status, 413)
        self.assertIn("2 GB", str(video.exception))
        with self.assertRaises(GoogleError) as photo:
            self.P.upload("testphotos", "A1", "huge.jpg", Huge(300 * 1024 * 1024), "image/jpeg")
        self.assertIn("200 MB", str(photo.exception))
        self.assertFalse(self.calls)
        self.assertEqual(photos_module._max_bytes("video/mp4"), 2 * 1024 ** 3)

    def test_video_metadata_in_the_list(self):
        self.answers = [Response(200, {"mediaItems": [
            {"id": "V1", "filename": "ride.mp4", "mimeType": "video/mp4",
             "baseUrl": "https://lh3.googleusercontent.com/lr/v1",
             "mediaMetadata": {"width": "1920", "height": "1080", "creationTime": "2026-11-14T11:00:00Z",
                               "video": {"fps": 29.97, "status": "READY", "duration": "12.5s"}}},
            {"id": "V2", "filename": "new.mp4", "mimeType": "video/mp4", "baseUrl": "https://lh3.googleusercontent.com/lr/v2",
             "mediaMetadata": {"video": {"status": "PROCESSING"}}},
            {"id": "P1", "filename": "a.jpg", "mimeType": "image/jpeg", "baseUrl": "https://lh3.googleusercontent.com/lr/p1",
             "mediaMetadata": {"photo": {}}}]})]
        video, processing, photo = self.P.list_album("testphotos", "A1")
        self.assertEqual((video["type"], video["duration"], video["video_status"], video["width"]),
                         ("video", "12.5s", "READY", 1920))
        self.assertEqual((processing["type"], processing["duration"], processing["video_status"]),
                         ("video", None, "PROCESSING"))
        self.assertEqual((photo["type"], photo["duration"], photo["video_status"]), ("photo", None, False))
