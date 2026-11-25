from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestPrinterBluefyJs(HttpCase):
    """iPhone / iPad printing through Bluefy: the hoot tests of static/tests/printer_bluefy.test.js (the driver's
    Web Bluetooth fallbacks, the iOS detection, the "open this page in Bluefy" note)."""

    def test_printer_bluefy_hoot(self):
        # Odoo's unit test page loads every installed module's scripts first; Tours Booking 0.x stops it there
        if self.env["ir.module.module"].search_count([("name", "=", "mtbg_tours_booking"), ("state", "=", "installed")]):
            self.skipTest("the unit test page does not load with mtbg_tours_booking installed")
        self.browser_js("/web/tests?headless&loglevel=2&preset=desktop&timeout=15000&filter=printer_connector_bluefy",
                        "", "", login="admin", timeout=600, success_signal="[HOOT] Test suite succeeded")
