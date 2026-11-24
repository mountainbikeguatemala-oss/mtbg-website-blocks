"""The Meta connector with a fake Meta: the setup (app, login, Pages), the Pages' state, the Instagram feed (WebP
copies, the newest kept, read without calling Meta), neutralize."""
import io
from unittest.mock import patch

from PIL import Image

from odoo.exceptions import UserError
from odoo.tests import HttpCase, TransactionCase, tagged

from ..models import graph


def jpeg(size=(2400, 1600)):
    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 30, 90)).save(buffer, "JPEG")
    return buffer.getvalue()


class FakeMeta:
    def __init__(self):
        self.posts = []
        self.downloads = 0

    def install(self, case):
        for name in ("app_info", "exchange_code", "long_lived", "me", "pages", "page_info", "media", "download",
                     "set_app_webhook", "debug_token", "subscribe_page", "instagram_account"):
            patcher = patch.object(graph, name, getattr(self, name))
            patcher.start()
            case.addCleanup(patcher.stop)

    def app_info(self, app_id, secret):
        return {"id": app_id, "name": "Odoo"}

    def exchange_code(self, *args):
        return "SHORT"

    def long_lived(self, *args):
        return "LONG", None

    def me(self, token):
        return {"id": "U1", "name": "Brendan"}

    def pages(self, token):
        return [{"id": "PAGE1", "name": "Example Tours", "access_token": "PT1",
                 "instagram_business_account": {"id": "IG1", "username": "exampletours"}}]

    def page_info(self, page_id, token):
        return {"id": page_id}

    def subscribe_page(self, *args, **kwargs):  # (an app, e.g. Communication Flows' Messenger, subscribes Pages)
        return {"success": True}

    grants = {"is_valid": True}

    def debug_token(self, *args):
        return self.grants

    def set_app_webhook(self, *args):
        return {"success": True}

    def media(self, ig_id, token, limit=24):
        return self.posts[:limit]

    def instagram_account(self, ig_id, token):
        return {"id": ig_id, "username": "exampletours", "name": "Example Tours", "followers_count": 12345,
                "media_count": 321, "profile_picture_url": "https://cdn/avatar.jpg"}

    def download(self, url):
        if url.startswith("https://cdn/avatar"):
            return jpeg((800, 800)), "image/jpeg"
        self.downloads += 1
        return jpeg(), "image/jpeg"


def post(i, kind="IMAGE"):
    item = {"id": "M%s" % i, "media_type": kind, "permalink": "https://www.instagram.com/p/%s/" % i,
            "caption": "Ride %s" % i, "timestamp": "2026-10-%02dT10:00:00+0000" % (1 + i % 25)}
    if kind == "VIDEO":
        item["thumbnail_url"] = "https://cdn/thumb%s.jpg" % i
    else:
        item["media_url"] = "https://cdn/%s.jpg" % i
    return item


class ConnectorCase(TransactionCase):

    def setUp(self):
        super().setUp()
        self.meta = FakeMeta()
        self.meta.install(self)

    def connect(self):
        app = self.env["meta.connector.app"].create({"app_id": "APP", "app_secret": "SECRET"})
        app.action_check_app()
        app.sudo().oauth_state = "S"
        self.env["meta.connector.app"]._oauth_done("S", code="C")
        app.action_save_pages()
        return app


@tagged("post_install", "-at_install")
class TestConnector(ConnectorCase):

    def test_setup_and_pages(self):
        app = self.connect()
        self.assertEqual(app.step, "posting" if self.env["meta.connector"]._meta_posting_wanted() else "done")
        page = self.env["meta.connector"]._meta_pages("instagram")
        self.assertEqual((page.page_id, page.ig_username, page._token(), page.state),
                         ("PAGE1", "exampletours", "PT1", "connected"))
        self.assertEqual(self.env["meta.connector"]._meta_pages("page"), page)
        self.assertIn("instagram_basic", self.env["meta.connector"]._meta_scopes())
        # a new login updates the same Page (apps point to it)
        app.action_reconnect()
        app.sudo().oauth_state = "S2"
        self.env["meta.connector.app"]._oauth_done("S2", code="C")
        self.assertEqual(self.env["meta.connector.page"].search([]), page)
        self.assertFalse(app.legacy_urls)
        self.assertTrue(app.webhook_url.endswith("/meta_connector/webhook"))

    def test_instagram_feed(self):
        self.connect()
        Media = self.env["meta.connector.media"]
        self.meta.posts = [post(i, "VIDEO" if i == 2 else "IMAGE") for i in range(30)]
        Media._cron_refresh()
        self.assertEqual(Media.search_count([]), 24, "the newest 24 are kept")
        first = Media.search([], limit=1)
        self.assertEqual(first.image_id.mimetype, "image/webp")
        with Image.open(io.BytesIO(first.image_id.raw)) as image:
            self.assertLessEqual(max(image.size), 1920)
        self.assertLessEqual(len(first.image_id.raw), 350 * 1024)
        with Image.open(io.BytesIO(first.tile_id.raw)) as tile:
            self.assertLessEqual(max(tile.size), 640)
        self.assertTrue(first.image_id.public)
        downloads = self.meta.downloads
        Media._cron_refresh()
        self.assertEqual(self.meta.downloads, downloads, "kept posts are not downloaded again")
        feed = Media._meta_feed(count=6)
        self.assertEqual((feed["username"], len(feed["items"])), ("exampletours", 6))
        self.assertEqual(feed["profile_url"], "https://www.instagram.com/exampletours/")
        # the header: name, counts and the profile photo, kept here as a small WebP
        self.assertEqual((feed["name"], feed["followers"], feed["posts"]), ("Example Tours", 12345, 321))
        page = self.env["meta.connector"]._meta_pages("instagram")
        self.assertEqual(page.ig_avatar_id.mimetype, "image/webp")
        self.assertTrue(page.ig_avatar_id.public)
        with Image.open(io.BytesIO(page.ig_avatar_id.raw)) as avatar:
            self.assertLessEqual(max(avatar.size), 320)
        self.assertTrue(feed["avatar"].startswith("/web/image/%s?unique=" % page.ig_avatar_id.id))
        avatar = page.ig_avatar_id
        Media._cron_refresh()
        self.assertEqual(page.ig_avatar_id, avatar, "the photo is refreshed in place")
        self.assertIn("VIDEO", {i["type"] for i in Media._meta_feed(count=24)["items"]})
        # an account no longer used: its posts go
        self.env["meta.connector.page"].search([]).use_instagram = False
        Media._cron_refresh()
        self.assertFalse(Media.search_count([]))

    def test_settings_switches(self):
        self.connect()
        Media = self.env["meta.connector.media"]
        self.meta.posts = [post(i) for i in range(3)]
        settings = self.env["res.config.settings"].create({})
        self.assertTrue(settings.meta_ig_feed, "on unless switched off")
        self.assertEqual(settings.meta_ig_status, "@exampletours: connected.")
        self.assertIn("connected", settings.meta_fb_status)
        settings.meta_ig_feed = False
        settings.set_values()
        self.assertFalse(self.env["meta.connector"]._meta_use("ig_feed"))
        self.assertFalse(self.env["res.config.settings"].create({}).meta_ig_feed)
        Media._cron_refresh()
        self.assertFalse(Media.search_count([]), "the Feed block switched off: Instagram is not read")
        self.assertEqual(Media._meta_feed()["items"], [])
        self.env["res.config.settings"].create({"meta_ig_feed": True}).set_values()
        Media._cron_refresh()
        self.assertEqual(len(Media._meta_feed()["items"]), 3)
        self.assertEqual(self.env["meta.connector"]._meta_set_uses({"ig_feed": True}), [], "no change, no call")

    def test_login_for_apps_and_whatsapp_block(self):
        """1.3.0: the login's permissions (and assets) kept; an app gets the login only with every permission it
        needs (and, asked so, a login that never expires); no WhatsApp app here: no WhatsApp block."""
        Connector = self.env["meta.connector"]
        self.meta.grants = {"is_valid": True, "scopes": ["pages_show_list", "whatsapp_business_messaging"],
                            "granular_scopes": [{"scope": "whatsapp_business_messaging", "target_ids": [111, "222"]},
                                                {"scope": "pages_show_list"}]}
        app = self.connect()
        self.assertEqual(app.granted_scopes, "pages_show_list,whatsapp_business_messaging")
        self.assertEqual(Connector._meta_targets("whatsapp_business_messaging"), ["111", "222"])
        self.assertEqual(Connector._meta_targets("pages_show_list"), [])
        self.assertEqual(Connector._meta_login(["whatsapp_business_messaging"], permanent=True), "LONG")
        self.assertFalse(Connector._meta_login(["whatsapp_business_management"]), "a permission it lacks")
        app.sudo().user_token_expires = "2026-12-23 17:27:25"
        self.assertFalse(Connector._meta_login(["whatsapp_business_messaging"], permanent=True), "a 60-day login")
        self.assertEqual(Connector._meta_login(["whatsapp_business_messaging"]), "LONG")
        # the daily check reads them again
        self.meta.grants = {"is_valid": True, "scopes": ["pages_show_list"]}
        app._cron_health()
        self.assertEqual(app.granted_scopes, "pages_show_list")
        self.assertFalse(app.granted_targets)
        if Connector._meta_whatsapp_status() is False:
            self.assertFalse(self.env["res.config.settings"].create({}).meta_wa_installed)
        self.assertTrue(Connector._meta_use("wa_login"), "on unless switched off")

    def test_neutralize(self):
        self.connect()
        self.env.flush_all()
        with open(__file__.replace("tests/test_connector.py", "data/neutralize.sql")) as sql:
            self.env.cr.execute(sql.read())
        self.env.invalidate_all()
        app = self.env["meta.connector.app"].search([])
        self.assertFalse(app.sudo().app_secret or app.sudo().user_token)
        self.assertFalse(self.env["meta.connector.page"].search([]).sudo().page_token)


@tagged("post_install", "-at_install")
class TestFeedRoute(HttpCase):

    def test_feed_route_is_public_and_calls_no_meta(self):
        app = self.env["meta.connector.app"].create({"app_id": "APP"})
        page = self.env["meta.connector.page"].create({"app_id": app.id, "page_id": "P", "ig_id": "IG",
                                                       "ig_username": "exampletours", "use_instagram": True})
        attachment = self.env["ir.attachment"].create({"name": "t.webp", "raw": b"x", "public": True})
        self.env["meta.connector.media"].create({"page_id": page.id, "media_id": "M1", "tile_id": attachment.id,
                                                 "permalink": "https://www.instagram.com/p/1/"})
        with patch.object(graph, "_call", side_effect=AssertionError("no call to Meta on a page view")):
            result = self.make_jsonrpc_request("/meta_connector/instagram/feed", {"count": 6})
        self.assertEqual(result["items"][0]["url"], "https://www.instagram.com/p/1/")


@tagged("post_install", "-at_install")
class TestSendBody(TransactionCase):
    """What graph.send posts to Meta (_call mocked: nothing leaves)."""

    def post(self, **kwargs):
        calls = []
        with patch.object(graph, "_call", side_effect=lambda *a, **kw: calls.append(kw) or {"message_id": "m1"}):
            self.assertEqual(graph.send("PAGE", "TOKEN", "USER", **kwargs), "m1")
        return calls[0]

    def test_quote_inside_message_by_default(self):
        call = self.post(text="Hi", reply_to="m_IN")
        self.assertNotIn("reply_to", call["data"])
        self.assertEqual(graph.json.loads(call["data"]["message"]), {"text": "Hi", "reply_to": {"mid": "m_IN"}})

    def test_quote_next_to_message(self):
        call = self.post(text="Hi", reply_to="m_IN", reply_to_top=True)
        self.assertEqual(graph.json.loads(call["data"]["reply_to"]), {"mid": "m_IN"})
        self.assertEqual(graph.json.loads(call["data"]["message"]), {"text": "Hi"})
        call = self.post(file={"name": "a.jpg", "mimetype": "image/jpeg", "data": b"x"}, reply_to="m_IN",
                         reply_to_top=True)
        self.assertEqual(graph.json.loads(call["data"]["reply_to"]), {"mid": "m_IN"})
        self.assertEqual(graph.json.loads(call["data"]["message"])["attachment"]["type"], "image")
        self.assertIn("filedata", call["files"])
        self.assertNotIn("reply_to", self.post(text="Hi", reply_to_top=True)["data"])


@tagged("post_install", "-at_install")
class TestPostingSwitch(TransactionCase):
    """Posting on in Settings asks for the posting permissions, with or without an app that posts."""

    def test_switch_asks_for_posting_permissions(self):
        from ..models import graph
        Connector = self.env["meta.connector"]
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("meta_connector.posting", "1")
        self.assertTrue(Connector._meta_posting_wanted())
        self.assertTrue(set(graph.POSTING_SCOPES) <= set(Connector._meta_scopes()))
        ICP.set_param("meta_connector.posting", "0")
        if "mtbg.marketing.item" not in self.env:
            self.assertFalse(Connector._meta_posting_wanted())
            self.assertNotIn("pages_manage_posts", Connector._meta_scopes())

    def test_story_posts(self):
        """A story (owner, 2026-11-11: "publish instagram / facebook stories"): Instagram's container is a STORIES one
        with no caption; the Page's photo goes up unpublished, then as a photo story; a story has no address."""
        from ..models import graph
        calls = []

        def fake_call(method, path, token, params=None, data=None, **kw):
            if method == "GET":  # the container's status: ready
                return {"id": "77", "status_code": "FINISHED"}
            calls.append((path.split("/")[-1], dict(data or {})))
            return {"id": "77", "post_id": "123_77", "success": True}

        with patch.object(graph, "_call", fake_call):
            graph.ig_publish("ig1", "tok", "https://x.test/s.png", "never shown", story=True)
            graph.page_photo_story("123", "tok", "https://x.test/s.png")
        self.assertEqual(calls[0], ("media", {"image_url": "https://x.test/s.png", "media_type": "STORIES"}))
        self.assertEqual(calls[1][0], "media_publish")
        self.assertEqual(calls[2], ("photos", {"url": "https://x.test/s.png", "published": "false"}))
        self.assertEqual(calls[3], ("photo_stories", {"photo_id": "77"}))
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("meta_connector.posting", "1")
        Connector = self.env["meta.connector"]
        app = Connector._meta_app() or self.env["meta.connector.app"].sudo().create({"name": "Test"})
        app.write({"active": True, "granted_scopes": "pages_show_list,pages_manage_posts"})
        self.env["meta.connector.page"].sudo().create({"app_id": app.id, "page_id": "123", "use_page": True,
                                                        "page_token": "test-token", "name": "Example Page"})
        with patch.object(graph, "page_photo_story", lambda *a: {"post_id": "123_77"}), \
                patch.object(graph, "permalink", lambda *a: "https://fb.test/never"):
            self.assertEqual(Connector._meta_post("facebook", "", "https://x.test/s.png", story=True),
                             {"id": "123_77", "url": ""})


@tagged("post_install", "-at_install")
class TestPostingTargets(TransactionCase):
    """Several Pages (owner, 2026-11-18: a second website gets its own social channels): ``target`` posts on a chosen
    Page or its Instagram account; without one, the default; the migration makes the Page used until now the
    default. Meta is replaced: nothing is posted."""

    def setUp(self):
        super().setUp()
        self.env["ir.config_parameter"].sudo().set_param("meta_connector.posting", "1")
        Connector = self.env["meta.connector"]
        self.app = Connector._meta_app() or self.env["meta.connector.app"].sudo().create({"name": "Test"})
        self.app.write({"active": True, "granted_scopes": "pages_manage_posts,instagram_content_publish"})
        Page = self.env["meta.connector.page"].sudo()
        Page.search([]).unlink()
        self.a = Page.create({"app_id": self.app.id, "page_id": "A1", "name": "A Page", "page_token": "TA",
                              "ig_id": "IGA", "use_page": True, "use_instagram": True})
        self.b = Page.create({"app_id": self.app.id, "page_id": "B1", "name": "B Page", "page_token": "TB",
                              "ig_id": "IGB", "use_page": True, "use_instagram": True})
        self.calls = []
        calls = self.calls
        for name, kind in (("page_photo_post", "fb"), ("ig_publish", "ig")):
            def fake(target_id, token, image_url, caption=None, story=False, kind=kind):
                calls.append((kind, target_id, token))
                return {"id": "%s_1" % target_id}
            patcher = patch.object(graph, name, fake)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(graph, "permalink", lambda *a: "https://fb.test/p")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_target_and_default(self):
        Connector = self.env["meta.connector"]
        # no default ticked: the first ticked, as before (the Pages' order)
        Connector._meta_post("facebook", "Hi", "https://x.test/a.jpg")
        Connector._meta_post("instagram", "Hi", "https://x.test/a.jpg")
        self.assertEqual(self.calls, [("fb", "A1", "TA"), ("ig", "IGA", "TA")])
        # a target: that Page, or its Instagram account (a record or its id)
        Connector._meta_post("facebook", "Hi", "https://x.test/a.jpg", target=self.b)
        Connector._meta_post("instagram", "Hi", "https://x.test/a.jpg", target=self.b.id)
        self.assertEqual(self.calls[2:], [("fb", "B1", "TB"), ("ig", "IGB", "TB")])
        # the default: one per network, the last ticked wins
        self.a.post_default_page = True
        self.b.post_default_page = True
        self.assertFalse(self.a.post_default_page)
        self.assertEqual(Connector._meta_post_target("facebook"), self.b)
        self.assertEqual(Connector._meta_post_target("instagram"), self.a)
        # a target not ticked for the network: refused, nothing posted
        self.b.use_instagram = False
        before = len(self.calls)
        with self.assertRaises(UserError):
            Connector._meta_post("instagram", "Hi", "https://x.test/a.jpg", target=self.b)
        self.assertEqual(len(self.calls), before)
        # its default unticked: back to the first ticked
        self.b.use_page = False
        self.assertEqual(Connector._meta_post_target("facebook"), self.a)

    def test_migration_makes_the_used_page_default(self):
        import importlib.util
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "migrations", "19.0.1.6.0", "post-migrate.py")
        spec = importlib.util.spec_from_file_location("meta_connector_post_migrate_1_6_0", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        self.a.use_instagram = False
        migration.migrate(self.env.cr, "19.0.1.5.0")
        self.env.invalidate_all()
        self.assertTrue(self.a.post_default_page)
        self.assertFalse(self.a.post_default_instagram)
        self.assertTrue(self.b.post_default_instagram)
        self.assertFalse(self.b.post_default_page)


class _Response:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def json(self):
        return self.payload


@tagged("post_install", "-at_install")
class TestInstagramContainerWait(TransactionCase):
    """Instagram (www 2026-11-22: stories failed with "The media with ... cannot be found"): the container is
    published only once Meta says FINISHED (GET /{container}?fields=status_code), polled every few seconds for at
    most a minute. ``requests`` is replaced: nothing reaches Meta; the clock is a fake one, nothing waits."""

    def run_publish(self, statuses, publish=None, story=True, timeout=60.0):
        """ig_publish with Meta answering the status polls with ``statuses`` (the last one repeats) and
        media_publish with ``publish`` (a list of answers, default one success). The calls made, the result."""
        calls, statuses, publish = [], list(statuses), list(publish or [({"id": "IGPOST"}, 200)])
        now = [0.0]

        def fake_request(method, url, params=None, data=None, **kw):
            path = url.replace(graph.BASE, "")
            calls.append((method, path, dict(params or {}), dict(data or {})))
            if method == "POST" and path.endswith("/media"):
                return _Response({"id": "CONT1"})
            if method == "GET" and path == "/CONT1":
                status = statuses.pop(0) if len(statuses) > 1 else statuses[0]
                return _Response(status)
            if method == "POST" and path.endswith("/media_publish"):
                payload, code = publish.pop(0) if len(publish) > 1 else publish[0]
                return _Response(payload, code)
            raise AssertionError("unexpected call %s %s" % (method, path))

        def fake_sleep(seconds):
            now[0] += seconds

        with patch.object(graph.requests, "request", fake_request), \
                patch.object(graph.time, "sleep", fake_sleep), \
                patch.object(graph.time, "monotonic", lambda: now[0]):
            try:
                result = graph.ig_publish("IG1", "tok", "https://x.test/s.jpg", "", story=story, timeout=timeout)
            except graph.GraphError as error:
                result = error
        return calls, result, now[0]

    def kinds(self, calls):
        return [("status" if method == "GET" else path.split("/")[-1]) for method, path, _p, _d in calls]

    def test_ready_on_first_poll(self):
        calls, result, waited = self.run_publish([{"status_code": "FINISHED", "id": "CONT1"}])
        self.assertEqual(result, {"id": "IGPOST"})
        self.assertEqual(self.kinds(calls), ["media", "status", "media_publish"])
        self.assertEqual(calls[1][2]["fields"], "status_code,status")
        self.assertEqual(calls[2][3], {"creation_id": "CONT1"})
        self.assertEqual(waited, 0)

    def test_ready_after_in_progress(self):
        calls, result, waited = self.run_publish(
            [{"status_code": "IN_PROGRESS"}, {"status_code": "IN_PROGRESS"}, {"status_code": "FINISHED"}],
            story=False)
        self.assertEqual(result, {"id": "IGPOST"})
        self.assertEqual(self.kinds(calls), ["media", "status", "status", "status", "media_publish"])
        self.assertEqual(waited, 6.0)
        self.assertNotIn("media_type", calls[0][3])  # a feed picture, with its caption

    def test_error_status(self):
        calls, result, _waited = self.run_publish(
            [{"status_code": "IN_PROGRESS"}, {"status_code": "ERROR", "status": "Error: unsupported image"}])
        self.assertIsInstance(result, graph.GraphError)
        self.assertIn("ERROR", str(result))
        self.assertIn("unsupported image", str(result))
        self.assertNotIn("media_publish", self.kinds(calls))
        _c, result, _w = self.run_publish([{"status_code": "EXPIRED"}])
        self.assertIn("EXPIRED", str(result))

    def test_timeout(self):
        calls, result, waited = self.run_publish([{"status_code": "IN_PROGRESS"}])
        self.assertIsInstance(result, graph.GraphError)
        self.assertIn("still preparing", str(result))
        self.assertNotIn("media_publish", self.kinds(calls))
        self.assertLessEqual(waited, 60)
        self.assertGreaterEqual(self.kinds(calls).count("status"), 15)

    def test_publish_retries_cannot_be_found(self):
        """FINISHED, yet media_publish answers "cannot be found" a moment: tried again; another error raises."""
        missing = ({"error": {"message": "The media with 18577644565074925 cannot be found", "code": 100}}, 400)
        calls, result, _w = self.run_publish([{"status_code": "FINISHED"}], publish=[missing, ({"id": "P2"}, 200)])
        self.assertEqual(result, {"id": "P2"})
        self.assertEqual(self.kinds(calls).count("media_publish"), 2)
        other = ({"error": {"message": "Invalid parameter", "code": 100}}, 400)
        calls, result, _w = self.run_publish([{"status_code": "FINISHED"}], publish=[other])
        self.assertIsInstance(result, graph.GraphError)
        self.assertEqual(self.kinds(calls).count("media_publish"), 1)
