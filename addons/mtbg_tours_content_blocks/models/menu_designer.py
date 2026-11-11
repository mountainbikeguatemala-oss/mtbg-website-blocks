"""The backend menu designer (owner, 2026-10-26): the admin's menus arranged for everyone (since 0.5.17 with buttons
and keys, no drag and drop: owner, 2026-10-29). Moved here from Tours Core in 0.11.0 (owner, 2026-11-11: a plain Odoo
website installs it without Tours); its menu is under Website › Configuration.

Odoo's own menus come from the modules' XML, which every module update writes again (name, parent, sequence,
groups): so they are never edited. What the owner changes on one of them is an override (``mtbg.menu.override``,
kept by the menu's XML id) applied when the menus are sent to the browser (``ir.ui.menu.load_menus``): a module update
cannot undo it. The folders and pages the owner adds are menus of their own (``mtbg_designer``): no module has them,
no update touches them. Reset: one menu, or everything (the overrides and the added menus go).

Hiding a menu, or keeping it for some groups, only changes the menu bar: what a page lets one do stays the modules'
access rules."""
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.http import request
from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__)

DESIGNER_MENU = 'mtbg_tours_content_blocks.menu_mtbg_menu_designer'
ACTION_MODELS = ('ir.actions.act_window', 'ir.actions.client')


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    mtbg_designer = fields.Boolean(string='Added in the Menu Designer', readonly=True, copy=False,
                                   help="A folder or page added in the menu designer (no module has it).")

    def load_menus(self, debug):
        """Odoo's menus with the designer's layout: renamed, moved, reordered, hidden, kept for some groups."""
        menus = super().load_menus(debug)
        overrides = self.env['mtbg.menu.override'].sudo()._mtbg_active()
        if not overrides:
            return menus
        menus = {key: dict(value, children=list(value.get('children') or [])) for key, value in menus.items()}
        self._mtbg_add_folders(menus)
        return self.env['mtbg.menu.override']._mtbg_apply(menus, overrides)

    @api.model
    def get_user_roots(self):
        """The apps as the designer arranged them (hidden ones out, moved and added ones in, in their order): what
        the top-level menus are everywhere (the website's menu among others looks each one up in load_menus)."""
        roots = super().get_user_roots()
        if not self.env['mtbg.menu.override'].sudo()._mtbg_active():
            return roots
        debug = request.session.debug if request and request.session else False
        return self.browse(self.load_menus(debug)['root']['children'])

    def _mtbg_add_folders(self, menus):
        """The designer's folders Odoo left out (no menu of their own in them: their menus are moved in by the
        layout), back in their place: the layout fills them, an empty one goes again."""
        folders = self.sudo().search([('mtbg_designer', '=', True), ('action', '=', False),
                                      ('id', 'not in', [key for key in menus if key != 'root'])], order='parent_path')
        for folder in folders:
            parent = folder.parent_id.id or False
            if parent and parent not in menus:
                continue
            menus[folder.id] = {'id': folder.id, 'name': folder.name, 'app_id': menus[parent]['app_id'] if parent else folder.id,
                                'action_model': False, 'action_id': False, 'action_path': False, 'web_icon': False,
                                'web_icon_data': False, 'web_icon_data_mimetype': False, 'xmlid': '', 'children': []}
            menus[parent or 'root']['children'].append(folder.id)

    def _mtbg_ancestor_ids(self):
        """The menu's parents up to its app, as the designer placed them."""
        self.ensure_one()
        rows = {row.menu_id.id: row for row in self.env['mtbg.menu.override'].sudo()._mtbg_active()}
        ids, current, seen = [], self, set()
        while current and current.id not in seen:
            seen.add(current.id)
            row = rows.get(current.id)
            parent = self.browse() if row and row.to_top else (row.parent_id if row and row.parent_id
                                                                 else current.parent_id)
            if parent:
                ids.append(parent.id)
            current = parent
        return ids


class MtbgMenuOverride(models.Model):
    _name = 'mtbg.menu.override'
    _description = 'Menu designer: a change to one of the modules\' menus'

    menu_id = fields.Many2one('ir.ui.menu', required=True, ondelete='cascade', index=True)
    menu_xmlid = fields.Char(string='Menu XML ID', readonly=True,
                             help="The menu's XML id: the change finds its menu again after a module is reinstalled.")
    parent_id = fields.Many2one('ir.ui.menu', string='Moved Into', ondelete='set null')
    to_top = fields.Boolean(string='Moved to the Top', help="An app of its own (the top level).")
    sequence = fields.Integer()
    has_sequence = fields.Boolean()
    name = fields.Char(translate=True, help="Its name in the menu bar (empty: the module's).")
    hidden = fields.Boolean()
    # removed (owner, 2026-10-28: "a way to remove an item from the menu not just hide it"): out of the menus and out
    # of the designer's lists (its Removed list, to put it back); a module's menu cannot be deleted (each update would
    # bring it back), so it is kept out instead
    removed = fields.Boolean()
    group_ids = fields.Many2many('res.groups', string='Only For',
                                 help="Shown only to these groups (empty: as the module says). Menus only: access "
                                      "stays as the modules define it.")

    _menu_unique = models.Constraint('UNIQUE(menu_id)', "One change per menu.")

    # ------------------------------------------------------------------ applying the layout
    @api.model
    def _mtbg_active(self):
        rows = self.search([])
        missing = rows.filtered(lambda r: not r.menu_id and r.menu_xmlid)
        for row in missing:  # a module reinstalled: its menu came back with another id
            menu = self.env.ref(row.menu_xmlid, raise_if_not_found=False)
            if menu:
                row.menu_id = menu
        return rows.filtered('menu_id')

    @api.model
    def _mtbg_apply(self, menus, overrides):
        """``menus``: load_menus' {id: menu} (a copy). The overrides: names, places, order, hidden, groups."""
        by_menu = {row.menu_id.id: row for row in overrides}
        user_groups = set(self.env.user._get_group_ids())
        is_admin = self.env.user.has_group('base.group_system')
        protected = set()
        designer = self.env.ref(DESIGNER_MENU, raise_if_not_found=False)
        if designer and is_admin:  # the designer stays reachable for who designs
            protected = set(designer._mtbg_ancestor_ids()) | {designer.id}
        parents = {}
        for key, menu in menus.items():
            for child in menu.get('children') or []:
                parents[child] = menu['id'] if key != 'root' else False
        # names
        for menu_id, row in by_menu.items():
            if menu_id in menus and row.name:
                menus[menu_id]['name'] = row.name
        # places
        for menu_id, row in by_menu.items():
            if menu_id not in menus or not (row.parent_id or row.to_top):
                continue
            target = False if row.to_top else row.parent_id.id
            if target and (target not in menus or target == menu_id or self._mtbg_is_inside(menus, target, menu_id)):
                continue  # its new place is not shown to this user (or would loop): it stays where it was
            old = parents.get(menu_id, False)
            old_key = old if old else 'root'
            if menu_id in menus[old_key]['children']:
                menus[old_key]['children'].remove(menu_id)
            menus[target or 'root']['children'].append(menu_id)
            parents[menu_id] = target
        # order
        sequences = {menu.id: menu.sequence for menu in self.env['ir.ui.menu'].sudo().browse(
            [key for key in menus if key != 'root']).exists()}
        for menu_id, row in by_menu.items():
            if row.has_sequence:
                sequences[menu_id] = row.sequence
        for menu in menus.values():
            menu['children'].sort(key=lambda child: (sequences.get(child, 0), child))
        # hidden, groups
        gone = set()
        for menu_id, row in by_menu.items():
            if menu_id in protected:
                continue
            if row.hidden or row.removed or (row.group_ids and not user_groups & set(row.group_ids.ids)):
                gone |= self._mtbg_subtree(menus, menu_id)
        for menu in menus.values():
            menu['children'] = [child for child in menu['children'] if child not in gone]
        for menu_id in gone:
            menus.pop(menu_id, None)
        # a menu with no page of its own and nothing left in it (all moved out): not shown, as Odoo does
        while True:
            empty = {key for key, menu in menus.items()
                     if key != 'root' and not menu.get('action_id') and not menu.get('children')}
            if not empty:
                break
            for menu in menus.values():
                menu['children'] = [child for child in menu['children'] if child not in empty]
            for key in empty:
                menus.pop(key, None)
        # apps: each menu's top level
        for app in menus['root']['children']:
            for menu_id in self._mtbg_subtree(menus, app):
                if menu_id in menus:
                    menus[menu_id]['app_id'] = app
        return menus

    @api.model
    def _mtbg_subtree(self, menus, menu_id):
        ids, todo = set(), [menu_id]
        while todo:
            current = todo.pop()
            if current in ids or current not in menus:
                continue
            ids.add(current)
            todo += menus[current].get('children') or []
        return ids

    @api.model
    def _mtbg_is_inside(self, menus, target, menu_id):
        return target in self._mtbg_subtree(menus, menu_id)

    # ------------------------------------------------------------------ the designer page
    @api.model
    def _mtbg_check(self):
        if not self.env.su and not self.env.user.has_group('base.group_system'):  # (su: an install hook)
            raise AccessError(_("Only administrators can change the menus."))

    @api.model
    def mtbg_designer_data(self):
        """Every menu (as the designer shows it: the layout applied, hidden ones too), every admin page, the groups."""
        self._mtbg_check()
        Menu = self.env['ir.ui.menu'].sudo().with_context(active_test=True)
        menus = Menu.search([])
        xmlids = menus._get_menuitems_xmlids()
        rows = {row.menu_id.id: row for row in self._mtbg_active()}
        designer = self.env.ref(DESIGNER_MENU, raise_if_not_found=False)
        protected = set(designer._mtbg_ancestor_ids()) | {designer.id} if designer else set()
        nodes = []
        for menu in menus:
            row = rows.get(menu.id)
            parent = menu.parent_id.id
            if row and row.to_top:
                parent = False
            elif row and row.parent_id:
                parent = row.parent_id.id
            action = menu.action
            nodes.append({
                'id': menu.id, 'name': (row.name if row and row.name else menu.name), 'module_name': menu.name,
                'xmlid': xmlids.get(menu.id, ''), 'parent': parent or False, 'module_parent': menu.parent_id.id or False,
                'sequence': row.sequence if row and row.has_sequence else menu.sequence,
                'hidden': bool(row and row.hidden), 'removed': bool(row and row.removed),
                'group_ids': row.group_ids.ids if row else [],
                'module_group_ids': menu.group_ids.ids, 'designer': menu.mtbg_designer,
                'action': '%s,%s' % (action._name, action.id) if action else False,
                'action_name': action.name if action else '', 'protected': menu.id in protected,
                'changed': bool(row),
            })
        in_menu = {node['action'] for node in nodes if node['action']}
        pages = []
        data = self.env['ir.model.data'].sudo().search_read(
            [('model', 'in', ACTION_MODELS)], ['model', 'res_id', 'module'])
        modules = {(d['model'], d['res_id']): d['module'] for d in data}
        names = {m.name: m.shortdesc for m in self.env['ir.module.module'].sudo().search([('state', '=', 'installed')])}
        for model in ACTION_MODELS:
            for action in self.env[model].sudo().search([]):
                key = '%s,%s' % (model, action.id)
                module = modules.get((model, action.id), '')
                pages.append({'action': key, 'name': action.name or '', 'kind': 'page' if model.endswith('window') else 'tool',
                              'group_ids': action.group_ids.ids if 'group_ids' in action._fields else [],
                              'model': getattr(action, 'res_model', '') or getattr(action, 'tag', '') or '',
                              'module': module, 'module_name': names.get(module, module), 'in_menu': key in in_menu})
        # each group with the groups its members have (the ones it implies): to check what a group sees
        groups = [{'id': g.id, 'name': g.full_name, 'member_of': (g | g.all_implied_ids).ids}
                  for g in self.env['res.groups'].sudo().search([], order='full_name')]
        return {'nodes': nodes, 'pages': sorted(pages, key=lambda p: (p['module_name'] or '~', p['name'])),
                'groups': groups}

    @api.model
    def mtbg_designer_save(self, nodes, deleted=None):
        """The layout as the designer shows it: [{id (an int, or "new-1"), parent, sequence, name, hidden, removed (a
        module's menu), group_ids, action (a new page: "ir.actions.act_window,12")}]; ``deleted``: added menus to
        remove."""
        self._mtbg_check()
        Menu = self.env['ir.ui.menu'].sudo()
        new_ids = {}
        # the added folders and pages first (their children may be added ones too)
        for node in nodes:
            if isinstance(node['id'], str):
                action = node.get('action') or False
                new_ids[node['id']] = Menu.create({'name': node.get('name') or _("New folder"), 'mtbg_designer': True,
                                                   'action': action, 'sequence': node.get('sequence') or 10}).id
        resolve = lambda value: new_ids.get(value, value) if value else False
        for node in nodes:
            menu = Menu.browse(resolve(node['id'])).exists()
            if not menu:
                continue
            parent, sequence = resolve(node.get('parent')), int(node.get('sequence') or 0)
            name, hidden = (node.get('name') or '').strip(), bool(node.get('hidden'))
            removed = bool(node.get('removed')) and not menu.mtbg_designer  # an added menu is deleted instead
            groups = [int(g) for g in node.get('group_ids') or []]
            row = self.search([('menu_id', '=', menu.id)])
            if menu.mtbg_designer:  # ours: its place and name written as they are; hidden and groups as for the others
                menu.write({'parent_id': parent, 'sequence': sequence, 'name': name or menu.name})
                if hidden or groups:
                    vals = {'hidden': hidden, 'group_ids': [(6, 0, groups)]}
                    row.write(vals) if row else self.create(dict(vals, menu_id=menu.id))
                else:
                    row.unlink()
                continue
            if menu.id in (self.env.ref(DESIGNER_MENU, raise_if_not_found=False) or Menu).ids and (hidden or removed):
                raise UserError(_("The Menu Designer itself cannot be hidden."))
            vals = {
                'parent_id': parent if parent != (menu.parent_id.id or False) and parent else False,
                'to_top': not parent and bool(menu.parent_id),
                'has_sequence': sequence != menu.sequence, 'sequence': sequence,
                'name': name if name and name != menu.name else False,
                'hidden': hidden, 'removed': removed, 'group_ids': [(6, 0, groups)],
            }
            if not (vals['parent_id'] or vals['to_top'] or vals['has_sequence'] or vals['name'] or hidden or removed
                    or groups):
                row.unlink()  # as the module says: no change kept
                continue
            xmlid = menu._get_menuitems_xmlids().get(menu.id, '')
            if row:
                row.write(vals)
            else:
                self.create(dict(vals, menu_id=menu.id, menu_xmlid=xmlid or False))
        for menu_id in deleted or []:
            menu = Menu.browse(int(menu_id)).exists()
            if menu and menu.mtbg_designer:
                self.search([('parent_id', 'child_of', menu.id)]).write({'parent_id': False, 'to_top': False})
                (Menu.search([('id', 'child_of', menu.id), ('mtbg_designer', '=', True)])).unlink()
        self.env.registry.clear_cache()
        return self.mtbg_designer_data()

    @api.model
    def mtbg_designer_reset(self, menu_ids=None):
        """Back to the modules' menus: one or some menus (their changes), or everything (``menu_ids`` empty: the
        changes and the added menus)."""
        self._mtbg_check()
        if menu_ids:
            self.search([('menu_id', 'in', [int(m) for m in menu_ids])]).unlink()
        else:
            self.search([]).unlink()
            self.env['ir.ui.menu'].sudo().search([('mtbg_designer', '=', True)]).unlink()
        self.env.registry.clear_cache()
        return self.mtbg_designer_data()


# ---------------------------------------------------------------------- presets
# a layout by XML ids, so it works on any site with those apps: [{xmlid, sequence, top (an app of its own), parent
# (another menu's XML id), name, hidden, removed}] and the menus a preset adds: [{added (its key), name, parent,
# sequence, action_xmlid (its page, by XML id: the same on every site)}]; a menu a site does not have is left out, and
# so is an added page whose page or folder the site does not have.
#
# **Other modules' presets** (no dependency on this module): a model of theirs with a method ``_mtbg_menu_presets()``
# returning [{key, name, description, layout}] (names: ``_lt``) is asked for them (e.g. Tours Core's layouts).
PRESETS_METHOD = '_mtbg_menu_presets'

BUILTIN_PRESETS = [
    {'key': 'odoo', 'name': _lt("Odoo default"),
     'description': _lt("The menus as the modules define them (the same as Reset everything)."), 'layout': []},
]


class MtbgMenuPreset(models.Model):
    _name = 'mtbg.menu.preset'
    _description = 'Menu designer: a saved layout'
    _order = 'name, id'

    name = fields.Char(required=True)
    description = fields.Char()
    layout = fields.Json(required=True, default=list)

    @api.model
    def _mtbg_check(self):
        self.env['mtbg.menu.override']._mtbg_check()

    @api.model
    def _mtbg_builtin_presets(self):
        """The presets that come with the modules: [{key, name, description, layout}] (names: ``_lt``): this module's,
        then every model's ``_mtbg_menu_presets()`` (see above; a key already given is not given again). Extensions of
        this module can also add theirs here (``super() + [...]``)."""
        presets, keys = list(BUILTIN_PRESETS), {p['key'] for p in BUILTIN_PRESETS}
        for name in sorted(self.env.registry):
            if not callable(getattr(type(self.env[name]), PRESETS_METHOD, None)):
                continue
            for preset in getattr(self.env[name], PRESETS_METHOD)() or []:
                if preset.get('key') and preset['key'] not in keys:
                    keys.add(preset['key'])
                    presets.append(preset)
        return presets

    @api.model
    def mtbg_presets(self):
        """The built-in presets and the ones saved here."""
        self._mtbg_check()
        presets = [{'key': p['key'], 'name': self._mtbg_text(p['name']), 'description': self._mtbg_text(p['description']),
                    'builtin': True} for p in self._mtbg_builtin_presets()]
        presets += [{'key': 'saved:%d' % p.id, 'name': p.name, 'description': p.description or '', 'builtin': False}
                    for p in self.sudo().search([])]
        return presets

    @api.model
    def _mtbg_current_layout(self):
        """The layout now: the changes to the modules' menus, and the folders and pages added here."""
        Menu = self.env['ir.ui.menu'].sudo()
        xmlids = Menu.search([])._get_menuitems_xmlids()
        ref = lambda menu: xmlids.get(menu.id) or ('added:%d' % menu.id if menu else False)
        layout = []
        for menu in Menu.search([('mtbg_designer', '=', True)], order='parent_path'):
            action = menu.action
            layout.append({'added': 'added:%d' % menu.id, 'name': menu.name, 'parent': ref(menu.parent_id),
                           'sequence': menu.sequence,
                           'action': '%s,%s' % (action._name, action.id) if action else False})
        for row in self.env['mtbg.menu.override'].sudo()._mtbg_active():
            entry = {'xmlid': ref(row.menu_id)}
            if row.to_top:
                entry['top'] = True
            elif row.parent_id:
                entry['parent'] = ref(row.parent_id)
            if row.has_sequence:
                entry['sequence'] = row.sequence
            if row.name:
                entry['name'] = row.name
            if row.hidden:
                entry['hidden'] = True
            if row.removed:
                entry['removed'] = True
            layout.append(entry)
        return layout

    @api.model
    def mtbg_preset_save(self, name, description=''):
        """The layout now, kept under ``name``."""
        self._mtbg_check()
        name = (name or '').strip()
        if not name:
            raise UserError(_("Give the preset a name."))
        self.sudo().create({'name': name, 'description': (description or '').strip() or False,
                            'layout': self._mtbg_current_layout()})
        return self.mtbg_presets()

    @api.model
    def mtbg_preset_delete(self, key):
        self._mtbg_check()
        if str(key).startswith('saved:'):
            self.sudo().browse(int(key.split(':')[1])).exists().unlink()
        return self.mtbg_presets()

    @api.model
    def mtbg_preset_apply(self, key):
        """The preset's layout instead of the one now (the changes and the added menus first go)."""
        self._mtbg_check()
        if str(key).startswith('saved:'):
            preset = self.sudo().browse(int(key.split(':')[1])).exists()
            if not preset:
                raise UserError(_("This preset is gone."))
            layout = preset.layout or []
        else:
            layout = next((p['layout'] for p in self._mtbg_builtin_presets() if p['key'] == key), None)
            if layout is None:
                raise UserError(_("Unknown preset."))
        Override = self.env['mtbg.menu.override']
        Override.mtbg_designer_reset([])
        Menu = self.env['ir.ui.menu'].sudo()
        added = {}

        def menu_of(value):
            if not value:
                return Menu
            if value in added:
                return added[value]
            return self.env.ref(value, raise_if_not_found=False) if '.' in value else Menu

        for entry in [e for e in layout if e.get('added')]:  # parents before children (saved in that order)
            parent = menu_of(entry.get('parent'))
            if entry.get('parent') and not parent:
                continue  # its folder is not on this site: left out (not made an app of its own)
            action = self._mtbg_preset_action(entry)
            if action is None:
                continue  # a page this site does not have
            added[entry['added']] = menu = Menu.create({
                'name': self._mtbg_text(entry.get('name')) or _("New folder"), 'mtbg_designer': True,
                'parent_id': parent.id or False, 'sequence': entry.get('sequence') or 10, 'action': action})
            self._mtbg_name_translations(menu, entry.get('name'))
        rows, names = {}, {}
        for entry in [e for e in layout if e.get('xmlid')]:
            menu = menu_of(entry['xmlid'])
            if not menu or menu._name != 'ir.ui.menu':
                continue  # a menu this site does not have
            vals = rows.setdefault(menu.id, {'menu_id': menu.id, 'menu_xmlid': entry['xmlid'] if '.' in entry['xmlid'] else False})
            if entry.get('top'):
                vals['to_top'] = True
            elif entry.get('parent'):
                parent = menu_of(entry['parent'])
                if parent and parent._name == 'ir.ui.menu' and parent != menu:
                    vals['parent_id'] = parent.id
            if 'sequence' in entry:
                vals.update(has_sequence=True, sequence=int(entry['sequence']))
            if entry.get('name'):
                vals['name'] = self._mtbg_text(entry['name'])
                names[menu.id] = entry['name']
            if menu != self.env.ref(DESIGNER_MENU, raise_if_not_found=False):
                if entry.get('hidden'):
                    vals['hidden'] = True
                if entry.get('removed'):
                    vals['removed'] = True
        for row in Override.sudo().create(list(rows.values())):
            self._mtbg_name_translations(row, names.get(row.menu_id.id))
        self.env.registry.clear_cache()
        return Override.mtbg_designer_data()

    @api.model
    def _mtbg_preset_action(self, entry):
        """An added menu's page: by its XML id (the same on every site), else the action saved here; False: a folder;
        None: a page this site does not have."""
        if not (entry.get('action_xmlid') or entry.get('action')):
            return False
        if entry.get('action_xmlid'):
            action = self.env.ref(entry['action_xmlid'], raise_if_not_found=False)
            if action and action._name in ACTION_MODELS:
                return '%s,%s' % (action._name, action.id)
        model, _sep, res_id = (entry.get('action') or '').partition(',')
        if model in ACTION_MODELS and res_id.isdigit() and self.env[model].sudo().browse(int(res_id)).exists():
            return entry['action']
        return None

    @api.model
    def _mtbg_text(self, text):
        """A preset's text in the user's language (built-in ones are ``_lt``; saved ones plain text)."""
        return text if isinstance(text, str) or not text else self.env._(text)

    @api.model
    def _mtbg_name_translations(self, record, name):
        """A built-in preset's menu name in every language of the site (EN + ES), not only the one applying it."""
        if not name or isinstance(name, str):
            return
        langs = [code for code, _label in self.env['res.lang'].get_installed()]
        record.with_context(lang='en_US').name = name._translate('en_US')
        record.update_field_translations('name', {lang: name._translate(lang) for lang in langs})
