from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged



@tagged('post_install', '-at_install', 'mtbg')
class TestUserPrefs(TransactionCase):
    """Owner, 2026-11-09: the columns picked (and folds) kept per user on the server, the same on every browser."""

    def setUp(self):
        super().setUp()
        Users = self.env['res.users'].with_context(no_reset_password=True)
        self.ana = Users.create({'name': 'Ana Prefs', 'login': 'ana-prefs', 'group_ids': [(6, 0, [self.env.ref('base.group_user').id])]})
        self.ben = Users.create({'name': 'Ben Prefs', 'login': 'ben-prefs', 'group_ids': [(6, 0, [self.env.ref('base.group_user').id])]})
        self.Pref = self.env['mtbg.user.pref']

    def test_own_choices_only(self):
        key = 'list:mtbg.tour.booking,form,12,participant_ids,list'
        value = {'shown': ['height_cm', 'bike_option_id'], 'known': ['height_cm', 'bike_option_id', 'email']}
        self.assertTrue(self.Pref.with_user(self.ana).mtbg_set_pref(key, value))
        self.assertEqual(self.Pref.with_user(self.ana)._mtbg_prefs(), {key: value})
        self.assertEqual(self.Pref.with_user(self.ben)._mtbg_prefs(), {}, "another user's choices are theirs")
        # changed: one row still
        self.Pref.with_user(self.ana).mtbg_set_pref(key, {'shown': [], 'known': ['email']})
        self.assertEqual(self.Pref.sudo().search_count([('user_id', '=', self.ana.id)]), 1)
        self.Pref.with_user(self.ana).mtbg_set_pref('fold:invoice_preview', True)
        self.assertIs(self.Pref.with_user(self.ana)._mtbg_prefs()['fold:invoice_preview'], True)
        # forgotten
        self.Pref.with_user(self.ana).mtbg_set_pref(key, None)
        self.assertNotIn(key, self.Pref.with_user(self.ana)._mtbg_prefs())
        # a user can't read or write the rows directly
        with self.assertRaises(Exception):
            self.Pref.with_user(self.ben).search([])



@tagged('post_install', '-at_install', 'mtbg')
class TestUserPrefsSession(HttpCase):
    """Signed in again (another browser): the session brings the choices back."""

    def test_loaded_with_the_session(self):
        user = new_test_user(self.env, login='cara-prefs', password='cara-prefs-pw-1', groups='base.group_user')
        self.env['mtbg.user.pref'].with_user(user).mtbg_set_pref('fold:invoice_preview', True)
        self.authenticate('cara-prefs', 'cara-prefs-pw-1')
        info = self.make_jsonrpc_request('/web/session/get_session_info')
        self.assertEqual(info.get('mtbg_user_prefs'), {'fold:invoice_preview': True})
