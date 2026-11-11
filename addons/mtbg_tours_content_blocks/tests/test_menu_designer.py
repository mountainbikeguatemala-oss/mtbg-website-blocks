from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, TransactionCase, tagged


@tagged('post_install', '-at_install', 'mtbg')
class TestMenuDesigner(TransactionCase):
    """The admin's menus arranged in the designer: kept apart from the modules' menus (an update does not undo them)."""

    def setUp(self):
        super().setUp()
        self.Override = self.env['mtbg.menu.override']
        self.Menu = self.env['ir.ui.menu']
        self.operations = self.env.ref('website.menu_content')
        self.catalog = self.env.ref('website.menu_reporting')
        self.calendar = self.env.ref('website.menu_website_pages_list')
        self.root = self.env.ref('website.menu_website_configuration')
        self.Override.mtbg_designer_reset([])  # the modules' menus (a site may run a preset: Tours suite on DEV4)

    def menus(self):
        self.env.registry.clear_cache()
        return self.Menu.load_menus(False)

    def node(self, data, menu):
        return next(n for n in data['nodes'] if n['id'] == menu.id)

    def save(self, changes, deleted=None):
        data = self.Override.mtbg_designer_data()
        nodes = [dict(n, **changes.get(n['id'], {})) for n in data['nodes']]
        nodes += [n for key, n in changes.items() if isinstance(key, str)]
        return self.Override.mtbg_designer_save(nodes, deleted or [])

    def test_move_rename_hide_and_an_update(self):
        self.save({self.calendar.id: {'parent': self.catalog.id, 'name': 'Site Pages', 'sequence': 1}})
        menus = self.menus()
        self.assertIn(self.calendar.id, menus[self.catalog.id]['children'])
        self.assertNotIn(self.calendar.id, menus[self.operations.id]['children'])
        self.assertEqual(menus[self.calendar.id]['name'], 'Site Pages')
        self.assertEqual(menus[self.catalog.id]['children'][0], self.calendar.id, "first in its new place")
        # a module update writes the menu's XML again: the layout stays
        self.calendar.write({'parent_id': self.operations.id, 'name': 'Calendar', 'sequence': 5})
        menus = self.menus()
        self.assertIn(self.calendar.id, menus[self.catalog.id]['children'])
        self.assertEqual(menus[self.calendar.id]['name'], 'Site Pages')
        self.assertEqual(self.calendar.parent_id, self.operations, "the module's menu itself is never changed")
        # hidden: gone from the menu bar, with its children
        self.save({self.catalog.id: {'hidden': True}})
        menus = self.menus()
        self.assertNotIn(self.catalog.id, menus)
        self.assertNotIn(self.calendar.id, menus)
        # back as the module has it
        self.Override.mtbg_designer_reset([self.calendar.id])
        menus = self.menus()
        self.assertIn(self.calendar.id, menus[self.operations.id]['children'])
        self.assertEqual(menus[self.calendar.id]['name'], self.calendar.name)

    def test_remove_a_modules_menu(self):
        """Removed (owner, 2026-10-28: "remove an item from the menu not just hide it"): out of the menus with what is
        inside it, kept as removed (an update cannot bring it back), put back from the Removed list."""
        parent_of = lambda menus: next(key for key, menu in menus.items() if self.calendar.id in menu['children'])
        before = parent_of(self.menus())
        data = self.save({self.calendar.id: {'removed': True}})
        self.assertTrue(self.node(data, self.calendar)['removed'])
        self.assertNotIn(self.calendar.id, self.menus())
        self.calendar.write({'name': 'Calendar', 'sequence': 5})  # a module update
        self.assertNotIn(self.calendar.id, self.menus(), "still removed after an update")
        self.assertTrue(self.calendar.exists(), "the module's menu itself is kept")
        self.save({self.operations.id: {'removed': True}})
        self.assertNotIn(self.operations.id, self.menus())
        data = self.save({self.calendar.id: {'removed': False}, self.operations.id: {'removed': False}})
        self.assertFalse(self.node(data, self.calendar)['removed'])
        self.assertEqual(parent_of(self.menus()), before, "put back in its place")
        designer = self.env.ref('mtbg_tours_content_blocks.menu_mtbg_menu_designer')
        with self.assertRaises(UserError):
            self.save({designer.id: {'removed': True}})

    def test_folders_pages_groups_and_reset(self):
        action = self.env.ref('mtbg_tours_content_blocks.action_mtbg_menu_designer')
        data = self.save({
            'new-1': {'id': 'new-1', 'name': 'My Folder', 'parent': self.root.id, 'sequence': 1, 'hidden': False,
                      'group_ids': []},
            'new-2': {'id': 'new-2', 'name': 'Designer here', 'parent': 'new-1', 'sequence': 1, 'hidden': False,
                      'group_ids': [], 'action': 'ir.actions.client,%d' % action.id},
        })
        folder = self.Menu.search([('name', '=', 'My Folder'), ('mtbg_designer', '=', True)])
        page = self.Menu.search([('parent_id', '=', folder.id)])
        self.assertEqual((page.action, page.mtbg_designer), (action, True))
        menus = self.menus()
        self.assertIn(folder.id, menus[self.root.id]['children'])
        self.assertEqual(menus[page.id]['action_id'], action.id)
        self.assertTrue(any(p['in_menu'] for p in data['pages'] if p['action'] == 'ir.actions.client,%d' % action.id))
        # only for some groups: an internal user without it does not see it
        system = self.env.ref('base.group_system')
        self.save({folder.id: {'group_ids': [system.id]}})
        user = self.env['res.users'].create({'name': 'Menu User', 'login': 'zz_menu_user',
                                             'group_ids': [(6, 0, [self.env.ref('base.group_user').id])]})
        self.env.registry.clear_cache()
        self.assertNotIn(folder.id, self.Menu.with_user(user).load_menus(False))
        self.assertIn(folder.id, self.menus(), "the admin still sees it")
        # the designer cannot hide itself
        with self.assertRaises(UserError):
            self.save({self.env.ref('mtbg_tours_content_blocks.menu_mtbg_menu_designer').id: {'hidden': True}})
        # reset everything: the changes and the added menus go
        self.save({self.calendar.id: {'name': 'Renamed'}})
        self.Override.mtbg_designer_reset([])
        self.assertFalse(self.Override.search([]))
        self.assertFalse(self.Menu.search([('mtbg_designer', '=', True)]))
        # what a group sees: each group with the groups its members have
        groups = {g['id']: g for g in self.Override.mtbg_designer_data()['groups']}
        manager = self.env.ref('base.group_user')
        self.assertIn(manager.id, groups[manager.id]['member_of'])
        self.assertIn(self.env.ref('base.group_user').id, groups[manager.id]['member_of'], "the groups it implies")
        # administrators only
        with self.assertRaises(AccessError):
            self.Override.with_user(user).mtbg_designer_data()


@tagged('post_install', '-at_install', 'mtbg')
class TestMenuPresets(TransactionCase):
    """Presets: the built-in layouts, one's own saved, applied for everyone."""

    def setUp(self):
        super().setUp()
        self.Preset = self.env['mtbg.menu.preset']
        self.Menu = self.env['ir.ui.menu']
        self.tours = self.env.ref('website.menu_website_configuration')

    def menus(self):
        self.env.registry.clear_cache()
        return self.Menu.load_menus(False)

    def test_builtin_presets(self):
        """Odoo default first; it takes every change away."""
        self.assertEqual(self.Preset.mtbg_presets()[0]['key'], 'odoo')
        self.env['mtbg.menu.override'].mtbg_designer_save([dict(n, **({'name': 'Renamed'} if n['id'] == self.tours.id
                                                                       else {}))
                                                          for n in self.env['mtbg.menu.override'].mtbg_designer_data()['nodes']])
        self.assertTrue(self.env['mtbg.menu.override'].search([]))
        self.Preset.mtbg_preset_apply('odoo')
        self.assertFalse(self.env['mtbg.menu.override'].search([]), "Odoo default: no change")

    def test_a_layout_that_hides_and_moves_apps(self):
        """The top-level menus everywhere follow the layout: the website's menu looks each one up in load_menus
        (2026-10-26: a hidden app made every website page fail for signed-in users)."""
        apps = self.env.ref('base.menu_management', raise_if_not_found=False)
        layout = [{'xmlid': 'website.menu_website_configuration', 'sequence': 1}]
        if apps:
            layout.append({'xmlid': 'base.menu_management', 'hidden': True})
        preset = self.Preset.create({'name': 'Website first', 'layout': layout})
        self.Preset.mtbg_preset_apply('saved:%d' % preset.id)
        menus = self.menus()
        self.assertEqual(menus['root']['children'][0], self.tours.id, "Website first")
        self.env.registry.clear_cache()
        roots = self.Menu.get_user_roots()
        self.assertEqual(roots.ids, menus['root']['children'])
        if apps:
            self.assertNotIn(apps, roots, "a hidden app is no top-level menu")
        self.assertIn(self.env.ref('mtbg_tours_content_blocks.menu_mtbg_menu_designer').id, menus, "the designer stays")
        self.Menu.with_context(force_action=True).load_menus_root()  # the website's: no KeyError

    def test_saved_preset(self):
        Override = self.env['mtbg.menu.override']
        catalog = self.env.ref('website.menu_reporting')
        data = Override.mtbg_designer_data()
        nodes = [dict(n, **({'name': 'Our Reports', 'sequence': 1} if n['id'] == catalog.id else {})) for n in data['nodes']]
        designer = self.env.ref('mtbg_tours_content_blocks.action_mtbg_menu_designer')
        nodes.append({'id': 'new-1', 'name': 'Shortcuts', 'parent': self.tours.id, 'sequence': 2, 'hidden': False,
                      'group_ids': []})
        nodes.append({'id': 'new-2', 'name': 'Designer', 'parent': 'new-1', 'sequence': 1, 'hidden': False,
                      'group_ids': [], 'action': 'ir.actions.client,%d' % designer.id})  # an empty folder is not shown
        Override.mtbg_designer_save(nodes, [])
        presets = self.Preset.mtbg_preset_save('Our layout')
        saved = next(p for p in presets if p['name'] == 'Our layout')
        self.Preset.mtbg_preset_apply('odoo')
        self.assertFalse(self.Menu.search([('name', '=', 'Shortcuts')]))
        self.Preset.mtbg_preset_apply(saved['key'])
        menus = self.menus()
        self.assertEqual(menus[catalog.id]['name'], 'Our Reports')
        folder = self.Menu.search([('name', '=', 'Shortcuts'), ('mtbg_designer', '=', True)])
        self.assertIn(folder.id, menus[self.tours.id]['children'], "its added folders come back too")
        self.assertNotIn('Our layout', [p['name'] for p in self.Preset.mtbg_preset_delete(saved['key'])])

    def test_pages_by_xml_id_and_what_a_site_lacks(self):
        """A preset made on one site works on another: its added pages found by their action's XML id (the ids
        differ), a page or folder this site does not have left out, not made an app of its own (0.5.17)."""
        designer = self.env.ref('mtbg_tours_content_blocks.action_mtbg_menu_designer')
        layout = [
            {'added': 'k:folder', 'name': 'Shortcuts', 'parent': 'website.menu_website_configuration', 'sequence': 1},
            {'added': 'k:page', 'name': 'Arrange', 'parent': 'k:folder', 'sequence': 1,
             'action_xmlid': 'mtbg_tours_content_blocks.action_mtbg_menu_designer', 'action': 'ir.actions.client,999999'},
            {'added': 'k:gone', 'name': 'Gone page', 'parent': 'k:folder', 'sequence': 2,
             'action_xmlid': 'no_such_module.action_x', 'action': 'ir.actions.act_window,999999'},
            {'added': 'k:orphan', 'name': 'Orphan', 'parent': 'no_such_module.menu_x', 'sequence': 3},
            {'xmlid': 'k:folder', 'hidden': False},
            {'xmlid': 'no_such_module.menu_y', 'hidden': True},
        ]
        preset = self.Preset.create({'name': 'From www', 'layout': layout})
        self.Preset.mtbg_preset_apply('saved:%d' % preset.id)
        page = self.Menu.search([('mtbg_designer', '=', True), ('name', '=', 'Arrange')])
        self.assertEqual(page.action, designer, "by its XML id, not the other site's id")
        self.assertFalse(self.Menu.search([('mtbg_designer', '=', True), ('name', 'in', ['Gone page', 'Orphan'])]))

    def test_other_modules_bring_presets(self):
        """Another module's presets, without depending on this one: any model's ``_mtbg_menu_presets()`` (e.g. Tours
        Core's layouts); listed and applied like the built-in ones, their names in every language of the site."""
        from unittest.mock import patch
        from odoo.addons.mtbg_tours_content_blocks.models import menu_designer
        layout = [{'added': 'x:today', 'name': menu_designer._lt("Today"),
                   'parent': 'website.menu_website_configuration', 'sequence': 1},
                  {'xmlid': 'website.menu_website_website_settings', 'parent': 'x:today', 'sequence': 1}]
        extra = {'key': 'x_test', 'name': menu_designer._lt("Today"), 'description': 'Test', 'layout': layout}
        patcher = patch.object(type(self.env['res.partner']), '_mtbg_menu_presets', lambda self: [extra], create=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.assertIn('x_test', [p['key'] for p in self.Preset.mtbg_presets()])
        self.Preset.mtbg_preset_apply('x_test')
        folder = self.Menu.search([('mtbg_designer', '=', True), ('name', '=', 'Today')])
        self.assertEqual(len(folder), 1)
        self.assertIn(self.env.ref('website.menu_website_website_settings').id, self.menus()[folder.id]['children'])


@tagged('post_install', '-at_install', 'mtbg')
class TestMenuDesignerPage(HttpCase):
    """The designer page: the menus' tree and the admin pages on the right."""

    def test_website_with_a_layout(self):
        """A layout that hides and moves apps: the website's pages still open for a signed-in user (a smoke test:
        the KeyError itself is caught by TestMenuPresets, through the website's load_menus_root)."""
        if 'website' not in self.env:
            self.skipTest("no website")
        layout = [{'xmlid': 'website.menu_website_configuration', 'sequence': 1},
                  {'xmlid': 'base.menu_management', 'hidden': True}]
        preset = self.env['mtbg.menu.preset'].create({'name': 'Website first', 'layout': layout})
        self.env['mtbg.menu.preset'].mtbg_preset_apply('saved:%d' % preset.id)
        # an administrator: sees every app, the hidden ones too in the database (as on DEV4)
        self.env['res.users'].create({'name': 'Website Staff', 'login': 'zz_site_staff', 'password': 'zz_site_staff_pw1',
                                      'group_ids': [(6, 0, [self.env.ref('base.group_system').id,
                                                            self.env.ref('base.group_erp_manager').id])]})
        self.authenticate('zz_site_staff', 'zz_site_staff_pw1')  # signed in: the page lists the apps
        response = self.url_open('/')
        self.assertIn('o_frontend_to_backend_apps_menu', response.text, "rendered for a signed-in user")
        self.assertEqual(response.status_code, 200, response.text[:500] if response.status_code != 200 else '')

    def test_page_renders(self):
        """The outline (owner, 2026-10-29: no drag and drop): ← → ↑ ↓ and ⋯ on every row, nothing to drag; the keys
        move a picked row (Shift+Tab: out of its folder)."""
        code = """
            const deadline = Date.now() + 20000;
            let step = 0;
            (function check() {
                const rows = [...document.querySelectorAll('.mtbg_md_outline .mtbg_md_row')];
                const outs = document.querySelectorAll('.mtbg_md_outline .mtbg_md_row .fa-arrow-left').length;
                const ins = document.querySelectorAll('.mtbg_md_outline .mtbg_md_row .fa-arrow-right').length;
                const draggable = document.querySelectorAll('[draggable="true"]').length;
                const chips = document.querySelectorAll('.mtbg_md_bar .mtbg_md_chip').length;
                const tops = document.querySelectorAll('.mtbg_md_outline > .mtbg_md_item').length;
                if (step === 0 && rows.length > 3 && outs === rows.length && ins === rows.length && !draggable && chips > 0) {
                    // open the first app, pick its first menu, Shift+Tab: an app of its own
                    step = 1;
                    window.__tops = tops;
                    document.querySelector('.mtbg_md_outline > .mtbg_md_item .mtbg_md_caret').click();
                } else if (step === 1 && document.querySelector('.mtbg_md_outline > .mtbg_md_item ul .mtbg_md_row')) {
                    step = 2;
                    const row = document.querySelector('.mtbg_md_outline > .mtbg_md_item ul .mtbg_md_row');
                    row.click();
                    row.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true }));
                } else if (step === 2 && tops === window.__tops + 1 && document.querySelector('.mtbg_md_dirty')) {
                    console.log('test successful');
                    return;
                }
                if (Date.now() > deadline) {
                    console.error('step ' + step + ' rows: ' + rows.length + ' outs: ' + outs + ' ins: ' + ins + ' draggable: ' + draggable + ' chips: ' + chips + ' tops: ' + tops);
                } else {
                    setTimeout(check, 300);
                }
            })();
        """
        self.browser_js('/odoo/menu-designer', code, ready="document.readyState === 'complete'", login='admin', timeout=90)
