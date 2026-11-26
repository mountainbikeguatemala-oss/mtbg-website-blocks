"""The marketing engine (owner, 2026-11-22: "the marketing template preview should be GLOBAL"): a template's layers
filled and drawn, stickers waiting for a flag, a sticker turned, a photo shown whole, the website's values and logo,
the editor's live preview, a record drawn through a source, the preview address for a queue's card."""
import base64
import io

from PIL import Image

from odoo import api, models
from odoo.tests import HttpCase, TransactionCase, tagged

from ..models import overlay_render
from ..models.marketing_overlay import sample_photo


def png(colour, size=(400, 200)):
    buffer = io.BytesIO()
    Image.new("RGB", size, colour).save(buffer, "PNG")
    return buffer.getvalue()


@tagged("post_install", "-at_install")
class TestMarketingOverlay(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].create({"name": "Parts Test", "domain": "https://www.parts.example"})
        cls.overlay = cls.env["mtbg.marketing.overlay"].create({
            "name": "Engine test", "shape": "vertical", "website_id": cls.website.id, "scrim": "none",
            "layer_ids": [
                (0, 0, {"sequence": 1, "name": "New", "kind": "sticker", "show_if": False, "text_en": "New in",
                        "text_es": "Nuevo ingreso", "uppercase": True, "rotate": 8.0, "box_color": "#E0262B",
                        "x": 10, "y": 20, "align": "left"}),
                (0, 0, {"sequence": 2, "name": "Address", "kind": "text", "text_en": "{website_domain}",
                        "x": 50, "y": 90}),
                (0, 0, {"sequence": 3, "name": "Logo", "kind": "logo", "logo_source": "website", "x": 50, "y": 5}),
            ],
        })

    def test_website_values(self):
        values = self.overlay._mtbg_website_values()
        self.assertEqual(values["website_domain"], "parts.example")
        self.assertEqual(values["website_name"], "Parts Test")
        self.assertEqual(overlay_render.domain_text("https://www.example.com/"), "example.com")
        self.assertEqual(overlay_render.domain_text("shop.example.com"), "shop.example.com")
        layers = self.overlay._mtbg_layers(values, "es")
        self.assertEqual([l["kind"] for l in layers], ["text", "text", "logo"])
        self.assertEqual(layers[0]["text"], "NUEVO INGRESO", "a sticker in Spanish, in capitals")
        self.assertTrue(layers[0]["box"], "a sticker always has its badge")
        self.assertEqual(layers[1]["text"], "parts.example")

    def test_show_if_waits_for_the_flag(self):
        sticker = self.overlay.layer_ids.filtered(lambda l: l.kind == "sticker")
        Overlay = type(self.env["mtbg.marketing.overlay"])

        def sources(model):
            found = super(Overlay, model)._mtbg_overlay_sources()
            found["any"] = dict(found["any"], flags=[("last_one", "The last one")])
            return found
        self.patch(Overlay, "_mtbg_overlay_sources", api.model(sources))
        sticker.show_if = "last_one"
        self.assertNotIn("NEW IN", [l.get("text") for l in self.overlay._mtbg_layers({}, "en")])
        self.assertIn("NEW IN", [l.get("text") for l in self.overlay._mtbg_layers({"last_one": True}, "en")])

    def test_logo_from_the_website(self):
        self.website.logo = base64.b64encode(png((10, 200, 10)))
        logo = [l for l in self.overlay._mtbg_layers(self.overlay._mtbg_website_values(), "en")
                if l["kind"] == "logo"][0]
        self.assertEqual(Image.open(io.BytesIO(logo["image"])).getpixel((5, 5)), (10, 200, 10))

    def test_comic_burst_frame(self):
        """A sticker's Comic burst shape (owner 2026-11-26: "bicipaca kapaw framing"): a jagged star round the text,
        its border colour all round it, the text on its fill; spikes reach well past the rounded box."""
        badge = {"text": "NUEVO\nINGRESO", "size": 90, "max_lines": 2, "box": True, "box_color": "#FFD60A",
                 "box_opacity": 1, "box_padding": 10, "box_border": 12, "box_border_color": "#E0262B",
                 "color": "#111111", "x": 50, "y": 50}
        boxed = overlay_render.photo_canvas(None, "vertical")
        burst = overlay_render.photo_canvas(None, "vertical")
        overlay_render.draw_text(boxed, badge)
        drawn = overlay_render.draw_text(burst, dict(badge, box_shape="burst"))
        self.assertEqual(drawn["lines"], ["NUEVO", "INGRESO"])

        def count(canvas, colour):
            return sum(1 for p in canvas.getdata() if p[:3] == colour)
        self.assertGreater(count(burst, (255, 214, 10)), count(boxed, (255, 214, 10)), "the star is bigger")
        self.assertGreater(count(burst, (224, 38, 43)), 1000, "its red border round it")
        left, top, width, height = drawn["box"]
        self.assertEqual(burst.getpixel((int(left + width / 2), int(top - 40)))[:3], (255, 214, 10),
                         "yellow above the text, inside the star")

    def test_turned_sticker_and_photo_shown_whole(self):
        badge = {"text": "GANGA", "size": 90, "box": True, "box_color": "#FFD60A", "box_opacity": 1, "x": 50, "y": 50}
        flat_canvas = overlay_render.photo_canvas(None, "vertical")
        turned_canvas = overlay_render.photo_canvas(None, "vertical")
        flat = overlay_render.draw_text(flat_canvas, badge)
        turned = overlay_render.draw_text(turned_canvas, dict(badge, rotate=10))
        self.assertEqual(flat["lines"], turned["lines"])

        def yellow(canvas):
            return sum(1 for p in canvas.crop((240, 760, 840, 1160)).getdata() if p[:3] == (255, 214, 10))
        self.assertGreater(yellow(turned_canvas), 1000, "the badge is drawn about its centre")
        self.assertNotEqual(flat_canvas.tobytes(), turned_canvas.tobytes(), "turned")
        # a square photo on a story, whole in its box, on the background
        photo = png((0, 0, 255), (500, 500))
        image = Image.open(io.BytesIO(overlay_render.render(photo, "vertical", [], fit="contain", background="#FFFFFF",
                                                            box=(0, 20, 100, 60), fmt="PNG")))
        self.assertEqual(image.size, (1080, 1920))
        self.assertEqual(image.getpixel((540, 100)), (255, 255, 255), "background above the box")
        self.assertEqual(image.getpixel((540, 768)), (0, 0, 255), "the photo in its box")
        self.assertEqual(image.getpixel((20, 768)), (255, 255, 255), "the photo whole: background beside it")

    def test_live_preview_and_auto_fit(self):
        self.assertTrue(self.overlay.preview_image)
        preview = Image.open(io.BytesIO(base64.b64decode(self.overlay.preview_image)))
        self.assertEqual(preview.size, (360, 640))
        self.overlay.write({"fit": "auto", "background_color": "#FFFFFF", "contain_top": 30, "contain_bottom": 50})
        self.assertEqual(self.overlay._mtbg_fit({"vertical": True}), "cover")
        self.assertEqual(self.overlay._mtbg_fit({"vertical": False}), "contain")
        drawn = Image.open(io.BytesIO(self.overlay._mtbg_render(sample_photo("square"), {"vertical": False}, "en",
                                                                 fmt="PNG")))
        self.assertEqual(drawn.getpixel((540, 200)), (255, 255, 255))

    def test_record_through_a_source(self):
        Overlay = type(self.env["mtbg.marketing.overlay"])

        def values(model, record, lang, website=None, **options):
            return {"website_name": "never", "name": record.name, "is_new": options.get("phase") == "new"}

        def photo(model, record, **options):
            return png((0, 0, 255), (600, 600)), False
        self.patch(Overlay, "_mtbg_source_values", api.model(values))
        self.patch(Overlay, "_mtbg_source_photo", api.model(photo))
        self.overlay.layer_ids.filtered(lambda l: l.kind == "text").text_en = "{name} · {website_domain}"
        partner = self.env["res.partner"].create({"name": "Sample Record"})
        merged = self.overlay._mtbg_values_for(partner, "en", phase="new")
        self.assertEqual(merged["name"], "Sample Record")
        self.assertTrue(merged["is_new"])
        jpeg = self.overlay._mtbg_render_record(partner, "en", phase="new")
        self.assertEqual(Image.open(io.BytesIO(jpeg)).size, (1080, 1920))
        url = self.overlay._mtbg_preview_url(partner, phase="new")
        self.assertIn("/meta_connector/overlay/%s/preview/res.partner/%s?" % (self.overlay.id, partner.id), url)
        self.assertIn("phase=new", url)


@tagged("post_install", "-at_install")
class TestMarketingPreviewRoute(HttpCase):

    def test_preview_route_internal_only(self):
        overlay = self.env["mtbg.marketing.overlay"].create({"name": "Route", "shape": "square"})
        partner = self.env["res.partner"].create({"name": "Route Record"})
        url = "/meta_connector/overlay/%s/preview/res.partner/%s?width=200" % (overlay.id, partner.id)
        self.assertNotEqual(self.url_open(url, allow_redirects=False).status_code, 200, "logged in only")
        self.authenticate("admin", "admin")
        response = self.url_open(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "image/jpeg")
        self.assertEqual(Image.open(io.BytesIO(response.content)).size, (200, 200))
        self.assertEqual(self.url_open("/meta_connector/overlay/%s/preview/no.model/1" % overlay.id).status_code, 404)
