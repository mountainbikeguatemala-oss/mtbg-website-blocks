from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestLabelLayout(TransactionCase):

    def test_print_layout(self):
        layout = self.env["bsx.label.layout"].get_print_layout()
        self.assertEqual(layout["tape_mm"], 12.0)
        self.assertEqual(layout["barcode_max_mm"], 40.0)
        self.assertIn("price_position", layout)

    def test_ranges(self):
        Layout = self.env["bsx.label.layout"]
        with self.assertRaises(ValidationError):
            Layout.create({"name": "Too high", "tape_mm": 15})
        with self.assertRaises(ValidationError):
            Layout.create({"name": "Too dark", "darkness": 40})

    def test_takes_over_shop_records(self):
        """The install hook re-owns the shop core's records (nothing to do on a site without them)."""
        data = self.env["ir.model.data"].search([("name", "=", "label_layout_default"),
                                                 ("model", "=", "bsx.label.layout")])
        self.assertEqual(data.mapped("module"), ["printer_connector"])

    def test_layout_by_use_and_font(self):
        Layout = self.env["bsx.label.layout"]
        general = Layout.get_print_layout()
        self.assertEqual(general["usage"], "general")
        self.assertEqual(Layout.get_print_layout("no_such_use")["id"], general["id"], "no layout of its own: general")
        # an Odoo font: its files from the site itself
        mono = Layout.create({"name": "Mono", "font": "fira_mono", "sequence": 1})
        spec = Layout.get_print_layout()["font_spec"]
        self.assertEqual(spec["family"], "Fira Mono")
        self.assertTrue(all(f["url"].startswith("/web/static/fonts/") for f in spec["faces"]))
        # "My own font" without a file: the device's font, said
        mono.font = "custom"
        self.assertTrue(Layout.get_print_layout()["font_spec"].get("missing"))
        mono.font_file = "AAAA"
        self.assertIn("/web/content/bsx.label.layout/", Layout.get_print_layout()["font_spec"]["faces"][0]["url"])
        self.assertIn("roboto", Layout.get_font_specs())
        with self.assertRaises(ValidationError):
            mono.logo_rotation = 120
