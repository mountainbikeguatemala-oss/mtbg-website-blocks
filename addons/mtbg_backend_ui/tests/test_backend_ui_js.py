from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install', 'mtbg')
class TestBackendUiLoads(HttpCase):
    """The admin starts with the admin look's scripts (every import found), light and dark."""

    def test_admin_loads(self):
        self.browser_js('/odoo', "console.log('test successful')", "odoo.isReady", login='admin')

    def test_admin_loads_dark(self):
        self.browser_js('/odoo', "console.log('test successful')", "odoo.isReady", login='admin',
                        cookies={'color_scheme': 'dark'})


@tagged('post_install', '-at_install', 'mtbg')
class TestCalendarZoomJs(HttpCase):
    """Every calendar's Day / Week view zooms sideways: the hoot tests of static/tests/calendar_zoom.test.js."""

    def test_calendar_zoom_hoot(self):
        # Odoo's unit test page loads every installed module's scripts first; Tours Booking 0.x's participant lists
        # stop it there (a field widget looked up before the fields load), so these run on a database without it.
        if self.env['ir.module.module'].search_count([('name', '=', 'mtbg_tours_booking'), ('state', '=', 'installed')]):
            self.skipTest("the unit test page does not load with mtbg_tours_booking installed")
        self.browser_js('/web/tests?headless&loglevel=2&preset=desktop&timeout=15000&filter=mtbg_calendar_zoom',
                        "", "", login='admin', timeout=600, success_signal="[HOOT] Test suite succeeded")
