"""staff_clock (19.0.0.2.5): soft (offered only where another extension answers res.users._site_link_staff_clock),
the clock-in state for a login; the caller side's helper; the way to the linked site in one health call."""
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.site_link_connector.models.site_link import SiteLinkError


@tagged('post_install', '-at_install')
class TestSiteLinkStaffClock(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.link_user = new_test_user(cls.env, 'slc_clock_link', groups='base.group_user,'
                                      'site_link_connector.group_site_link_remote')
        cls.plain_user = new_test_user(cls.env, 'slc_clock_plain', groups='base.group_user')
        cls.guide = new_test_user(cls.env, 'slc_clock_guide@example.com', groups='base.group_user')
        cls.portal = new_test_user(cls.env, 'slc_clock_portal@example.com', groups='base.group_portal')
        cls.Api = cls.env['site.link.api'].with_user(cls.link_user)
        cls.Users = type(cls.env['res.users'])
        cls.env['site.link'].search([]).active = False  # (a copy of a real site has its own links)

    def hook(self, answer):
        asked = []

        def clock(self_, user):
            asked.append(user)
            return answer(user) if callable(answer) else answer
        return patch.object(self.Users, '_site_link_staff_clock', create=True, new=clock), asked

    def test_soft(self):
        offered = hasattr(self.Users, '_site_link_staff_clock')
        self.assertEqual('staff_clock' in self.Api.health()['methods'], offered)
        patcher, _asked = self.hook({'clocked_in': False})
        with patcher:
            self.assertIn('staff_clock', self.Api.health()['methods'], "a hook: offered")

    def test_answer(self):
        patcher, asked = self.hook(lambda user: {'clocked_in': user == self.guide, 'since': '2026-11-19 14:02:00'})
        with patcher:
            self.assertEqual(self.Api.staff_clock(' SLC_CLOCK_GUIDE@example.com '),
                             {'clocked_in': True, 'since': '2026-11-19 14:02:00'})
            self.assertEqual(asked[-1], self.guide, "the login, case does not matter")
            self.assertEqual(self.Api.staff_clock('nobody@example.com'), {'clocked_in': False, 'since': None})
            self.assertEqual(self.Api.staff_clock(self.portal.login), {'clocked_in': False, 'since': None},
                             "a portal login: never asked")
            self.assertEqual(asked[-1], self.guide)
            with self.assertRaises(UserError):
                self.Api.staff_clock('')
            with self.assertRaises(AccessError):
                self.env['site.link.api'].with_user(self.plain_user).staff_clock(self.guide.login)

        def broken(self_, user):
            raise ValueError("boom")
        with patch.object(self.Users, '_site_link_staff_clock', create=True, new=broken):
            self.assertEqual(self.Api.staff_clock(self.guide.login), {'clocked_in': False, 'since': None},
                             "another extension's hook never breaks the answer")

    def test_no_hook(self):
        if hasattr(self.Users, '_site_link_staff_clock'):
            self.skipTest("another extension answers the staff clock on this database")
        with self.assertRaises(UserError):
            self.Api.staff_clock(self.guide.login)

    def test_caller_helper(self):
        Site = type(self.env['site.link'])
        self.assertIsNone(self.env['site.link']._site_link_staff_clock('a@example.com', 'no_such_role'))
        self.env['site.link'].create({'name': 'Tours', 'base_url': 'https://staff.example.com', 'api_key': 'K',
                                      'role': 'staff_source'})
        with patch.object(Site, '_site_link_call', return_value={'clocked_in': True, 'since': '2026-11-19 14:02:00'}) \
                as call:
            self.assertEqual(self.env['site.link']._site_link_staff_clock('a@example.com'),
                             {'clocked_in': True, 'since': '2026-11-19 14:02:00'})
        self.assertEqual(call.call_args.args[2:], ('staff_clock',))
        self.assertEqual(call.call_args.kwargs, {'login': 'a@example.com'})
        with patch.object(Site, '_site_link_call', side_effect=SiteLinkError("down")):
            self.assertIsNone(self.env['site.link']._site_link_staff_clock('a@example.com'))

    def test_sso_start_one_health_call(self):
        """The shop app's Tour switch: the linked site's path and its methods from one health answer."""
        Site = type(self.env['site.link'])
        self.env['site.link'].create({'name': 'Tours', 'base_url': 'https://staff.example.com', 'api_key': 'K',
                                      'role': 'staff_source'})
        health = {'protocol': 1, 'methods': ['health', 'sso_ticket'], 'paths': {'staff_app': '/odoo/x'}}
        with patch.object(Site, '_site_link_health', return_value=health) as call:
            self.assertEqual(self.env['site.link']._site_link_sso_start_url('staff_app'),
                             '/site_link/sso/start?return=https%3A%2F%2Fstaff.example.com%2Fodoo%2Fx&fallback=1')
        self.assertEqual(call.call_count, 1)
