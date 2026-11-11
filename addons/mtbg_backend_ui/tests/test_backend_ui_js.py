from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install', 'mtbg')
class TestBackendUiLoads(HttpCase):
    """The admin starts with the admin look's scripts (every import found), light and dark."""

    def test_admin_loads(self):
        self.browser_js('/odoo', "console.log('test successful')", "odoo.isReady", login='admin')

    def test_admin_loads_dark(self):
        self.browser_js('/odoo', "console.log('test successful')", "odoo.isReady", login='admin',
                        cookies={'color_scheme': 'dark'})
