"""One employee list: user_sync on the site that receives it, and the sending side (hook, button, soon after a
change; calls mocked)."""
from unittest.mock import patch

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged

SSO = 'site_link_connector.group_site_link_sso'


@tagged('post_install', '-at_install')
class TestSiteLinkUserSync(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.link_user = new_test_user(cls.env, 'slc_sync_link', groups='base.group_user,'
                                      'site_link_connector.group_site_link_remote')
        cls.Api = cls.env['site.link.api'].with_user(cls.link_user)
        cls.shop_group = cls.env['res.groups'].create({'name': 'SLC shop app'})
        cls.staff_site = cls.env['site.link'].create({
            'name': 'Staff site', 'base_url': 'https://staff.example.com', 'api_key': 'K', 'role': 'staff_source',
            'shop_group_ids': [(6, 0, cls.shop_group.ids)]})
        cls.existing = new_test_user(cls.env, 'Emp.Both@Example.com', groups='base.group_user', name='Old Name',
                                     email='old@example.com')
        cls.sso = cls.env.ref(SSO)

    def sync(self, *users):
        return self.Api.user_sync(list(users))

    def test_match_by_login_and_update(self):
        answer = self.sync({'login': 'emp.both@example.com', 'name': 'New Name', 'email': 'emp.both@example.com',
                            'active': True, 'shop_access': True})
        self.assertEqual(answer, [{'login': 'emp.both@example.com', 'user_id': self.existing.id, 'created': False,
                                   'updated': True}])
        self.assertEqual((self.existing.name, self.existing.email), ('New Name', 'emp.both@example.com'))
        self.assertIn(self.sso, self.existing.group_ids)
        self.assertIn(self.shop_group, self.existing.group_ids)
        # the same again: nothing to change
        again = self.sync({'login': 'EMP.BOTH@example.com', 'name': 'New Name', 'email': 'emp.both@example.com',
                           'active': True, 'shop_access': True})
        self.assertFalse(again[0]['updated'])
        # null shop access leaves the groups, False takes them away
        self.sync({'login': 'emp.both@example.com', 'name': 'New Name', 'email': 'emp.both@example.com',
                   'shop_access': None})
        self.assertIn(self.shop_group, self.existing.group_ids)
        self.sync({'login': 'emp.both@example.com', 'name': 'New Name', 'email': 'emp.both@example.com',
                   'shop_access': False})
        self.assertNotIn(self.shop_group, self.existing.group_ids)
        self.assertNotIn(self.sso, self.existing.group_ids)
        self.assertIn(self.env.ref('base.group_user'), self.existing.group_ids)
        self.assertTrue(self.env['site.link.log'].search([('kind', '=', 'served'), ('method', '=', 'user_sync')]))

    def test_create_without_password(self):
        mails_before = self.env['mail.mail'].search_count([])
        answer = self.sync({'login': 'new.emp@example.com', 'name': 'New Emp', 'email': 'new.emp@example.com',
                            'active': True, 'shop_access': True},
                           {'login': 'gone.emp@example.com', 'name': 'Gone', 'active': False})
        self.assertTrue(answer[0]['created'])
        user = self.env['res.users'].browse(answer[0]['user_id'])
        self.assertEqual((user.login, user.name, user.email), ('new.emp@example.com', 'New Emp', 'new.emp@example.com'))
        self.assertTrue(user._is_internal())
        self.assertFalse(user.share)
        self.assertIn(self.shop_group, user.group_ids)
        self.env.cr.execute("SELECT password FROM res_users WHERE id = %s", (user.id,))
        self.assertFalse(self.env.cr.fetchone()[0], "no password: the user signs in by single sign-on")
        self.assertEqual(self.env['mail.mail'].search_count([]), mails_before, "no invitation or other email")
        # an archived employee is not made
        self.assertEqual(answer[1], {'login': 'gone.emp@example.com', 'user_id': None, 'created': False,
                                     'updated': False})
        self.assertFalse(self.env['res.users'].with_context(active_test=False).search(
            [('login', '=', 'gone.emp@example.com')]))

    def test_deactivate_and_back(self):
        self.sync({'login': 'emp.both@example.com', 'name': 'Old Name', 'email': 'old@example.com', 'active': False})
        self.assertFalse(self.existing.active)
        self.sync({'login': 'emp.both@example.com', 'name': 'Old Name', 'email': 'old@example.com', 'active': True})
        self.assertTrue(self.existing.active)

    def test_protected_users_untouched(self):
        root, admin = self.env.ref('base.user_root'), self.env.ref('base.user_admin')
        before = [(u.name, u.email, u.active, u.group_ids) for u in (root, admin, self.link_user)]
        answer = self.sync(*[{'login': u.login, 'name': 'Changed', 'email': 'x@example.com', 'active': False,
                              'shop_access': True} for u in (root, admin, self.link_user)])
        self.assertEqual([a['user_id'] for a in answer], [root.id, admin.id, self.link_user.id])
        self.assertFalse(any(a['created'] or a['updated'] for a in answer))
        self.assertEqual([(u.name, u.email, u.active, u.group_ids) for u in (root, admin, self.link_user)], before)

    def test_portal_user_untouched(self):
        portal = new_test_user(self.env, 'slc.portal.sync@example.com', groups='base.group_portal')
        answer = self.sync({'login': portal.login, 'name': 'Staff?', 'shop_access': True})
        self.assertFalse(answer[0]['updated'])
        self.assertTrue(portal.share)
        self.assertNotIn(self.sso, portal.group_ids)

    def test_caller_needs_the_group(self):
        plain = new_test_user(self.env, 'slc_sync_plain', groups='base.group_user')
        with self.assertRaises(AccessError):
            self.env['site.link.api'].with_user(plain).user_sync([])

    # ------------------------------------------------------------------ the sending side

    def test_hook_list(self):
        users = self.staff_site._site_link_sync_users_list()
        logins = [u['login'] for u in users]
        self.assertIn(self.existing.login, logins)
        for xmlid in ('base.user_root', 'base.user_admin', 'base.default_user', 'base.public_user'):
            user = self.env.ref(xmlid, raise_if_not_found=False)
            if user:
                self.assertNotIn(user.login, logins)
        self.assertTrue(all(u['shop_access'] is None for u in users))
        self.assertEqual(set(users[0]), {'login', 'name', 'email', 'active', 'shop_access'})

    def test_sync_button_soft_check(self):
        Site = type(self.env['site.link'])
        site = self.env['site.link'].create({'name': 'Shop', 'base_url': 'https://shop.example.com', 'api_key': 'K',
                                             'role': 'inventory_source', 'sync_users': True})
        with patch.object(Site, '_site_link_call', return_value={'protocol': 1, 'methods': ['health']}) as call:
            action = site.action_sync_users()
        self.assertEqual(call.call_count, 1, "only the health check: no user_sync there, skipped")
        self.assertEqual(action['params']['type'], 'warning')
        self.assertIn('Skipped', site.last_sync_message)

        def answer(site_, model, method, *ids, **kw):
            if method == 'health':
                return {'protocol': 1, 'methods': ['health', 'user_sync']}
            return [{'login': u['login'], 'user_id': 1, 'created': True, 'updated': False} for u in kw['users']]
        with patch.object(Site, '_site_link_call', side_effect=answer) as call:
            action = site.action_sync_users()
        self.assertEqual(action['params']['type'], 'success')
        self.assertEqual(call.call_args.args[2], 'user_sync')
        self.assertEqual(call.call_args.kwargs['users'], site._site_link_sync_users_list())
        self.assertIn('employees sent', site.last_sync_message)

    def test_user_change_runs_sync_soon(self):
        cron = self.env.ref('site_link_connector.cron_site_link_user_sync')
        Trigger = self.env['ir.cron.trigger']
        count = Trigger.search_count([('cron_id', '=', cron.id)])
        self.existing.name = 'No site sends employees'
        self.assertEqual(Trigger.search_count([('cron_id', '=', cron.id)]), count)
        self.staff_site.sync_users = True
        self.existing.name = 'Changed'
        self.assertEqual(Trigger.search_count([('cron_id', '=', cron.id)]), count + 1)
        new_test_user(self.env, 'slc.new.staff@example.com', groups='base.group_user')
        self.existing.active = False
        self.assertGreater(Trigger.search_count([("cron_id", "=", cron.id)]), count + 1)

    def test_administrators_skipped(self):
        """A user with Settings or Access Rights rights (not only ids 1 and 2) is never changed by the list."""
        owner = new_test_user(self.env, 'slc.owner.sync@example.com', groups='base.group_system', name='Owner')
        rights = new_test_user(self.env, 'slc.rights.sync@example.com', groups='base.group_erp_manager', name='Rights')
        before = [(u.name, u.email, u.active, u.group_ids) for u in (owner, rights)]
        answer = self.sync(*[{'login': u.login.upper(), 'name': 'Taken over', 'email': 'evil@example.com',
                              'active': False, 'shop_access': True} for u in (owner, rights)])
        self.assertEqual([a['user_id'] for a in answer], [owner.id, rights.id])
        self.assertTrue(all('administrator' in a['skipped'] and not a['updated'] for a in answer))
        self.assertEqual([(u.name, u.email, u.active, u.group_ids) for u in (owner, rights)], before)
        self.assertNotIn(self.sso, owner.group_ids)

    def test_shop_groups_never_admin(self):
        implying = self.env['res.groups'].create({'name': 'SLC implies settings',
                                                  'implied_ids': [(4, self.env.ref('base.group_system').id)]})
        for group in (self.env.ref('base.group_system'), self.env.ref('base.group_erp_manager'), implying):
            with self.subTest(group=group.name), self.assertRaises(ValidationError):
                self.staff_site.write({'shop_group_ids': [(4, group.id)]})
        with self.assertRaises(ValidationError):
            self.env['site.link'].create({'name': 'X', 'base_url': 'https://x.example.com',
                                          'shop_group_ids': [(6, 0, implying.ids)]})
        self.staff_site.write({'shop_group_ids': [(4, self.env['res.groups'].create({'name': 'SLC ok'}).id)]})
