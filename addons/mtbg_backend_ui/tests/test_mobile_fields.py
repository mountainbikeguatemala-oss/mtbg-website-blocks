from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install', 'mtbg')
class TestMobileFieldsPhone(HttpCase):
    """A phone (390px): a form in a dialog has finger-sized fields (44px+ high, 16px+ text) and buttons, light and
    dark; not inside the Staff App."""
    browser_size = '390x844'
    touch_enabled = True

    def test_mobile_fields_phone(self):
        self.start_tour('/odoo', 'mtbg_backend_ui_mobile_fields', login='admin')

    def test_mobile_fields_phone_dark(self):
        self.start_tour('/odoo', 'mtbg_backend_ui_mobile_fields', login='admin', cookies={'color_scheme': 'dark'})


@tagged('post_install', '-at_install', 'mtbg')
class TestMobileFieldsDesktop(HttpCase):
    """A desktop (1366px): the same dialog keeps Odoo's field size."""

    def test_mobile_fields_desktop(self):
        self.start_tour('/odoo', 'mtbg_backend_ui_mobile_fields', login='admin')
