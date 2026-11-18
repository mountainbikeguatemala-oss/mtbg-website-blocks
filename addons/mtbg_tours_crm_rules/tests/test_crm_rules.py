from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCrmRules(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Rule = cls.env['mtbg.crm.rule']
        cls.Rule._mtbg_sync_sources()
        cls.Partner = cls.env['res.partner']
        cls.gt = cls.env.ref('base.gt')
        cls.us = cls.env.ref('base.us')

    def _rule(self, code):
        return self.Rule.search([('code', '=', code)])

    def test_builtins_synced_and_off(self):
        for code in ('phone_location', 'message_phone_location', 'duplicates', 'lang_from_country'):
            rule = self._rule(code)
            self.assertTrue(rule, code)
            self.assertFalse(rule.enabled)
            self.assertEqual(rule.state, 'off')
        self.Rule._mtbg_sync_sources()  # again: nothing new
        self.assertEqual(self.Rule.search_count([('code', '=', 'duplicates')]), 1)

    def test_custom_rule_tag_and_undo(self):
        partner_model = self.env['ir.model']._get('res.partner')
        field = self.env['ir.model.fields']._get
        rule = self.Rule.create({
            'name': 'Tag new contacts', 'model_id': partner_model.id, 'trigger': 'changed',
            'trigger_field_ids': [(6, 0, field('res.partner', 'country_id').ids)],
            'action_ids': [(0, 0, {'kind': 'add_tag', 'value': 'Local'}),
                           (0, 0, {'kind': 'set_field', 'field_id': field('res.partner', 'city').id,
                                   'value': 'Antigua', 'fill_empty': True})],
        })
        partner = self.Partner.create({'name': 'Ana', 'country_id': self.gt.id})
        self.assertFalse(partner.category_id, "off: nothing happens")
        # the dry run changes nothing but lists the changes
        run = rule._mtbg_run(partner, 'dry', dry=True)
        self.assertEqual(run.matched, 1)
        self.assertEqual(set(run.change_ids.mapped('kind')), {'tag_add', 'field'})
        self.assertFalse(partner.category_id)
        rule.enabled = True
        self.assertTrue(rule.automation_id.active)
        other = self.Partner.create({'name': 'Bob', 'country_id': self.gt.id})
        self.assertEqual(other.category_id.mapped('name'), ['Local'])
        self.assertEqual(other.city, 'Antigua')
        # fill-empty: a city already there stays
        kept = self.Partner.create({'name': 'Dee', 'country_id': self.gt.id, 'city': 'Xela'})
        self.assertEqual(kept.city, 'Xela')
        changes = self.env['mtbg.crm.rule.change'].search([('rule_id', '=', rule.id), ('res_id', '=', other.id),
                                                          ('dry_run', '=', False)])
        changes.action_mtbg_undo()
        self.assertFalse(other.category_id)
        self.assertFalse(other.city)
        rule.enabled = False
        self.assertFalse(rule.automation_id.active)

    def test_duplicates_flagged_never_merged(self):
        rule = self._rule('duplicates')
        rule.enabled = True
        first = self.Partner.create({'name': 'Eve One', 'email': 'eve@example.com', 'phone': '+502 5555 1234'})
        second = self.Partner.create({'name': 'Eve Two', 'email': 'EVE@example.com'})
        third = self.Partner.create({'name': 'Eve Three', 'phone': '5555-1234'})
        flags = self.env['mtbg.crm.duplicate'].search([('res_model', '=', 'res.partner'),
                                                       ('res_id', 'in', (first | second | third).ids)])
        self.assertEqual(set(flags.mapped('reason')), {'email', 'phone'})
        self.assertTrue(first.exists() and second.exists() and third.exists())

    def test_phone_location_fills_empty_only(self):
        rule = self._rule('phone_location')
        rule.enabled = True
        partner = self.Partner.create({'name': 'Fay', 'phone': '+1 415 555 0100'})
        self.assertEqual(partner.country_id, self.us)
        self.assertEqual(partner.state_id.code, 'CA')
        mine = self.Partner.create({'name': 'Gus', 'phone': '+1 415 555 0101', 'country_id': self.gt.id})
        self.assertEqual(mine.country_id, self.gt, "a country already there stays")

    def test_lang_from_country(self):
        if not any(code.startswith('es') for code, _n in self.env['res.lang'].get_installed()):
            self.env['res.lang']._activate_lang('es_ES')
        rule = self._rule('lang_from_country')
        rule.enabled = True
        partner = self.Partner.create({'name': 'Hal', 'lang': 'en_US'})
        partner.country_id = self.gt
        self.assertTrue(partner.lang.startswith('es'))
        us = self.Partner.create({'name': 'Ivy', 'lang': 'en_US', 'country_id': self.us.id})
        self.assertEqual(us.lang, 'en_US')

    def test_unanswered_enquiry_moved(self):
        """0.2.0: "Enquiry not answered" is no longer this extension's (Communications has it, on the website form
        messages; Odoo's CRM retired)."""
        specs = self.Rule._mtbg_source_specs()
        spec = specs.get('enquiry_unanswered')
        if spec:
            self.assertEqual(spec['model'], 'res.partner')
            self.assertNotEqual(spec['source'], 'mtbg.crm.rule')

    def test_message_received_fills_country(self):
        rule = self._rule('message_phone_location')
        self.assertEqual(rule.trigger, 'received')
        partner = self.Partner.create({'name': 'Jo'})  # no phone, no country
        self.Rule._mtbg_message_received(partner, '+1 212 555 0100', 'whatsapp')
        self.Rule._cron_mtbg_received()
        self.assertFalse(partner.country_id, "off: nothing happens")
        rule.enabled = True
        self.Rule._mtbg_message_received(partner, '+1 212 555 0100', 'whatsapp')
        self.Rule._cron_mtbg_received()
        self.assertEqual(partner.country_id, self.us)
        self.assertEqual(partner.state_id.code, 'NY')
        self.assertFalse(self.env['mtbg.crm.rule.inbox'].search([('done', '=', False)]))

    def test_page_endpoints(self):
        data = self.Rule.mtbg_get_crm_rules()
        models = {g['model'] for g in data['groups']}
        self.assertIn('res.partner', models)
        rule = self._rule('lang_from_country')
        self.Rule.mtbg_save_crm_rule(rule.id, {'days': 3})
        self.assertEqual(rule.days, 3)
        dry = self.Rule.mtbg_crm_dry_run(rule.id)
        self.assertIn('changes', dry)
        self.assertFalse(self.env['mtbg.crm.rule.run'].search([('dry_run', '=', True)]), "a page dry run leaves no run")
        self.assertIn('changes', self.Rule.mtbg_get_crm_changes())

    def test_list_side_bar(self):
        """The Contact Rules list's side bar (Core 0.5.13 groups a many2one or selection): by status, when, records."""
        sections = {s['key']: s for s in self.Rule.mtbg_sidebar([])['sections']}
        records = sections['model']['nodes']
        partner = self.env['ir.model']._get('res.partner')
        node = next(n for n in records if n['domain'] == [('model_id', '=', partner.id)])
        self.assertEqual(node['count'], self.Rule.search_count([('model_id', '=', partner.id)]))
        self.assertEqual(node['label'], partner.display_name)

    def test_own_page_and_menu(self):
        """0.3.0: no Tours needed: its own page and menu (hidden where the Alert Feed puts them in the Tours menus)."""
        action = self.env.ref('mtbg_tours_crm_rules.action_crm_rules_page')
        self.assertEqual(action.tag, 'mtbg_crm_rules_page')
        root = self.env.ref('mtbg_tours_crm_rules.menu_crm_root')
        # 0.4.0: the Contacts pipeline and the Source Channels too
        self.assertEqual(root.child_id, self.env.ref('mtbg_tours_crm_rules.menu_crm_rules_page')
                         | self.env.ref('mtbg_tours_crm_rules.menu_crm_duplicates')
                         | self.env.ref('mtbg_tours_crm_rules.menu_crm_pipeline')
                         | self.env.ref('mtbg_tours_crm_rules.menu_crm_lead_sources'))
        manifest = self.env['ir.module.module'].get_module_info('mtbg_tours_crm_rules')
        self.assertFalse([dep for dep in manifest['depends'] if dep.startswith('mtbg_tours')])
        hidden = self.env['ir.ui.menu']._load_menus_blacklist()
        if 'mtbg.alert.feed' in self.env:
            self.assertIn(root.id, hidden, "with Tours its own menu is not shown")
        else:
            self.assertNotIn(root.id, hidden)
