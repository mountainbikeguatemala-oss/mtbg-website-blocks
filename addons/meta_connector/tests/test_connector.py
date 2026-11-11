"""The Meta connector with a fake Meta: the setup (app, login, Pages), the Pages' state, the Instagram feed (WebP
copies, the newest kept, read without calling Meta), neutralize."""
import io
from unittest.mock import patch

from PIL import Image

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
