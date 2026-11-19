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
