"""Both ways (19.0.0.2.4): health's named paths, the linked site's addresses, the way back's single sign-on group on
the site that sends the employee list (calls mocked)."""
from unittest.mock import patch

from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.site_link_connector.models.site_link import SiteLinkError

SSO = 'site_link_connector.group_site_link_sso'


@tagged('post_install', '-at_install')
class TestSiteLinkPartnerUrl(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.link_user = new_test_user(cls.env, 'slc_paths_link', groups='base.group_user,'
                                      'site_link_connector.group_site_link_remote')
        cls.Site = cls.env['site.link']
        cls.staff = cls.Site.create({'name': 'Tours', 'base_url': 'https://staff.example.com/', 'api_key': 'K',
                                     'role': 'staff_source'})

    def health(self, **extra):
        return patch.object(type(self.Site), '_site_link_health',
                            return_value={'protocol': 1, 'methods': ['health', 'sso_ticket'], **extra})

    def test_health_paths(self):
        Api = self.env['site.link.api'].with_user(self.link_user)
        health = Api.health()
        self.assertIs(health['sso_return'], True)
        Users = type(self.env['res.users'])
        if not hasattr(Users, '_site_link_paths'):
            self.assertEqual(health['paths'], {}, "nobody names a path: none")
        with patch.object(Users, '_site_link_paths', create=True, new=lambda self: {
                'staff_app': '/odoo/action-x?staff_mode=tour', 'evil': 'https://evil.example.com/', 'n': 3,
                'two': '//evil.example.com'}):
            self.assertEqual(Api.health()['paths'], {'staff_app': '/odoo/action-x?staff_mode=tour'})

        def broken(self):
            raise ValueError("boom")
        with patch.object(Users, '_site_link_paths', create=True, new=broken):
            self.assertEqual(Api.health()['paths'], {}, "another extension's hook never breaks the health check")

    def test_partner_url(self):
        with self.health(paths={'staff_app': '/odoo/action-x?staff_mode=tour', 'bad': 'https://evil.example.com'}):
            self.assertEqual(self.Site._site_link_partner_paths('staff_source'),
                             {'staff_app': '/odoo/action-x?staff_mode=tour'})
            self.assertEqual(self.Site._site_link_partner_url('staff_app', 'staff_source'),
                             'https://staff.example.com/odoo/action-x?staff_mode=tour')
            self.assertEqual(self.Site._site_link_partner_url('/odoo', 'staff_source'), 'https://staff.example.com/odoo')
            self.assertEqual(self.Site._site_link_partner_url('', 'staff_source'), 'https://staff.example.com/')
            self.assertIsNone(self.Site._site_link_partner_url('bad', 'staff_source'))
            self.assertIsNone(self.Site._site_link_partner_url('nope', 'staff_source'))
            self.assertIsNone(self.Site._site_link_partner_url('//evil.example.com/x', 'staff_source'))
            self.assertIsNone(self.Site._site_link_partner_url('/odoo', 'inventory_source'), "no such site")
            start = self.Site._site_link_sso_start_url('staff_app', 'staff_source')
        self.assertEqual(start, '/site_link/sso/start?return=https%3A%2F%2Fstaff.example.com%2Fodoo%2Faction-x'
                                '%3Fstaff_mode%3Dtour&fallback=1')
        # the other site gives no tickets (older version, unreachable): its plain address
        with patch.object(type(self.Site), '_site_link_health', side_effect=SiteLinkError("down")):
            self.assertEqual(self.Site._site_link_partner_paths('staff_source'), {})
            self.assertEqual(self.Site._site_link_sso_start_url('/odoo', 'staff_source'),
                             'https://staff.example.com/odoo')
        with self.health(methods=['health']):
            self.assertEqual(self.Site._site_link_sso_start_url('/odoo', 'staff_source'),
                             'https://staff.example.com/odoo')
        self.staff.api_key = False
        with self.health():
            self.assertEqual(self.Site._site_link_sso_start_url('/odoo', 'staff_source'),
                             'https://staff.example.com/odoo', "no key: no ticket can be asked")

    def test_sso_url_return_path(self):
        with patch.object(type(self.Site), '_site_link_call',
                          return_value={'url': '/site_link/sso/abc', 'expires_in': 60}):
            self.assertEqual(self.Site._site_link_sso_url('a@example.com', 'staff_source', return_path='/odoo/x?y=1'),
                             'https://staff.example.com/site_link/sso/abc?return=%2Fodoo%2Fx%3Fy%3D1'
                             '&redirect=%2Fodoo%2Fx%3Fy%3D1')
            self.assertEqual(self.Site._site_link_sso_url('a@example.com', 'staff_source',
                                                          return_path='https://evil.example.com/'),
                             'https://staff.example.com/site_link/sso/abc', "only a path")

    def test_sso_back_group(self):
        """The site that sends the employee list: shop access gives its own single sign-on group (the way back)."""
        sso = self.env.ref(SSO)
        seller = new_test_user(self.env, 'slc.back.seller@example.com', groups='base.group_user')
        guide = new_test_user(self.env, 'slc.back.guide@example.com', groups=f'base.group_user,{SSO}')
        owner = new_test_user(self.env, 'slc.back.owner@example.com', groups='base.group_system')
        portal = new_test_user(self.env, 'slc.back.portal@example.com', groups='base.group_portal')
        other = new_test_user(self.env, 'slc.back.other@example.com', groups=f'base.group_user,{SSO}')
        admin = self.env.ref('base.user_admin')
        rows = [{'login': 'SLC.Back.Seller@example.com', 'active': True, 'shop_access': True},
                {'login': guide.login, 'active': True, 'shop_access': False},
                {'login': owner.login, 'active': True, 'shop_access': True},
                {'login': portal.login, 'active': True, 'shop_access': True},
                {'login': other.login, 'active': True, 'shop_access': None},
                {'login': admin.login, 'active': True, 'shop_access': True},
                {'login': 'nobody@example.com', 'active': True, 'shop_access': True}]
        changed = self.staff._site_link_sync_sso_back(rows)
        self.assertEqual(sorted(changed), sorted([seller.login, guide.login]))
        self.assertIn(sso, seller.group_ids)
        self.assertNotIn(sso, guide.group_ids)
        for user in (owner, portal, admin):
            self.assertNotIn(sso, user.group_ids, user.login)
        self.assertIn(sso, other.group_ids, "null leaves it")
        log = self.env['site.link.log'].search([('kind', '=', 'sso'), ('method', '=', 'user_sync'),
                                                ('message', 'ilike', seller.login)])
        self.assertEqual(len(log), 1)
        self.assertEqual(self.staff._site_link_sync_sso_back(rows), [], "nothing more to change")
        # archived there (active false): the way back closes
        self.assertEqual(self.staff._site_link_sync_sso_back([{'login': seller.login, 'active': False,
                                                               'shop_access': True}]), [seller.login])
        self.assertNotIn(sso, seller.group_ids)

    def test_sync_users_runs_it(self):
        """Sync employees: the way back's group first, also when the other site offers no user_sync."""
        seller = new_test_user(self.env, 'slc.back.sync@example.com', groups='base.group_user')
        self.staff.sync_users = True
        Site = type(self.Site)
        with patch.object(Site, '_site_link_sync_users_list', return_value=[
                {'login': seller.login, 'name': 'S', 'email': None, 'active': True, 'shop_access': True}]), \
                patch.object(Site, '_site_link_offers', return_value=False):
            self.assertIsNone(self.staff._site_link_sync_users())
        self.assertIn(self.env.ref(SSO), seller.group_ids)
