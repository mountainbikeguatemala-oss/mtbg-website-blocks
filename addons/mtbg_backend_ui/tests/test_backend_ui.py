from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.mtbg_backend_ui.models.board import time_stage


@tagged('post_install', '-at_install', 'mtbg')
class TestBackendUi(TransactionCase):
    """The admin look on its own: what any model with boards, a side bar or a card gets, and who may change them."""

    def test_board_columns_any_model(self):
        columns = [c['key'] for c in self.env['mtbg.board.mixin']._mtbg_board_columns()]
        self.assertEqual(columns[:2], ['mtbg_time_stage', 'mtbg_missing_ids'], "the two columns every board can use")

    def test_time_stages(self):
        from datetime import date
        today = date(2026, 11, 11)
        self.assertEqual(time_stage(date(2027, 2, 1), False, today), 'm2')
        self.assertEqual(time_stage(date(2026, 11, 12), False, today), 'h24')
        self.assertEqual(time_stage(date(2026, 11, 10), date(2026, 11, 12), today), 'on')
        self.assertEqual(time_stage(date(2026, 1, 1), False, today), 'past')

    def test_missing_tags_created_once(self):
        Tag = self.env['mtbg.missing.tag']
        items = [{'key': 'guide', 'label': 'A guide', 'level': 'warning'}]
        first = Tag._mtbg_tags(items)
        self.assertEqual(Tag._mtbg_tags(items), first, "a thing missing is made once")
        self.assertEqual(first.color, '#f0b429')

    def test_who_may_change(self):
        """An internal user may not; an administrator may, unless a suite sets its own managers (Tours Core)."""
        admin = new_test_user(self.env, login='bui_admin', groups='base.group_system')
        user = new_test_user(self.env, login='bui_user', groups='base.group_user')
        self.assertFalse(user._mtbg_ui_manager())
        self.assertFalse(self.env['mtbg.board.mixin'].with_user(user).mtbg_board_settings()['can_edit'])
        if 'mtbg_tours_core' not in self.env.registry._init_modules:
            self.assertTrue(admin._mtbg_ui_manager(), "on its own: administrators")
        self.assertEqual(self.env['mtbg.board.mixin'].with_user(admin).mtbg_board_settings()['can_edit'],
                         admin._mtbg_ui_manager())

    def test_settings_switches_and_texts(self):
        """The settings pages read the switches as yes / no and the long texts as text."""
        Settings = self.env['res.config.settings']
        values = Settings.default_get(list(Settings._fields))
        for name in Settings._mtbg_switch_parameters():
            self.assertIsInstance(values.get(name), bool, name)
        for name in Settings._mtbg_text_parameters():
            self.assertIn(name, Settings._fields, name)
