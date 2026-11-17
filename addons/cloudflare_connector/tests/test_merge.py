from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.cloudflare_connector.tools import page_cache_upgrades, retire

OLD = 'mtbg_test_retired_page_cache'


@tagged('post_install', '-at_install', 'mtbg')
class TestPageCacheMerge(TransactionCase):
    """19.0.2.0.0: the page cache's former extension retired into the connector, its records kept (never dropped or
    made twice), the module uninstallable; the upgrade steps an older database had not had run once."""

    def setUp(self):
        super().setUp()
        self.Module = self.env['ir.module.module'].sudo()
        self.old = self.Module.create({'name': OLD, 'state': 'installed', 'latest_version': '19.0.0.8.0'})
        self.cron = self.env.ref('cloudflare_connector.cron_edge_cache_purge')
        self.Data = self.env['ir.model.data'].sudo()
        # as on www: the old module's names on the records (here: the connector's own cron and a record of its own)
        self.Data.create({'module': OLD, 'name': 'cron_edge_cache_purge', 'model': 'ir.cron', 'res_id': self.cron.id,
                          'noupdate': True})
        self.param = self.env['ir.config_parameter'].sudo().create({'key': 'mtbg_test.retired', 'value': '1'})
        self.Data.create({'module': OLD, 'name': 'param_only_old', 'model': 'ir.config_parameter',
                          'res_id': self.param.id, 'noupdate': True})

    def _state(self):
        self.env.cr.execute("SELECT state FROM ir_module_module WHERE id = %s", [self.old.id])
        return self.env.cr.fetchone()[0]

    def test_retire_keeps_records(self):
        report = retire.retire_into(self.env.cr, OLD, 'cloudflare_connector')
        self.assertEqual(report['orphans'], [], "the shared name points at the same record")
        self.assertEqual(self.env.ref('cloudflare_connector.param_only_old'), self.param, "copied to the connector")
        self.assertEqual(self._state(), 'uninstallable')
        retire.retire_finish(self.env, OLD, 'cloudflare_connector')
        self.assertFalse(self.Data.search_count([('module', '=', OLD)]), "the old names gone")
        self.assertTrue(self.cron.exists() and self.param.exists(), "nothing dropped")
        self.assertEqual(self.Data.search_count([('module', '=', 'cloudflare_connector'),
                                                 ('name', '=', 'cron_edge_cache_purge')]), 1, "once")

    def test_finish_removes_a_copy(self):
        retire.retire_into(self.env.cr, OLD, 'cloudflare_connector')
        # its old folder loaded in the run made the cron again under its own name
        copy = self.cron.copy()
        self.Data.search([('module', '=', OLD), ('name', '=', 'cron_edge_cache_purge')]).res_id = copy.id
        retire.retire_finish(self.env, OLD, 'cloudflare_connector')
        self.assertFalse(copy.exists(), "the copy goes")
        self.assertTrue(self.cron.exists(), "the connector's stays")

    def test_finish_gives_template_keys_back(self):
        retire.retire_into(self.env.cr, OLD, 'cloudflare_connector')
        view = self.env.ref('cloudflare_connector.layout_cached_tag')
        key = view.key
        self.env.cr.execute("UPDATE ir_ui_view SET key = %s WHERE id = %s", ['%s.layout_cached_tag' % OLD, view.id])
        retire.retire_finish(self.env, OLD, 'cloudflare_connector')
        view.invalidate_recordset(['key'])
        self.assertEqual(view.key, key, "its old folder reloaded in the run: the key is the connector's again")

    def test_keep_retired(self):
        retire.retire_into(self.env.cr, OLD, 'cloudflare_connector')
        self.env.cr.execute("UPDATE ir_module_module SET state = 'uninstalled' WHERE id = %s", [self.old.id])
        retire.keep_retired(self.env, OLD, 'cloudflare_connector')
        self.assertEqual(self._state(), 'uninstallable', "never listed as installable again")
        self.assertFalse(self.Data.search_count([('module', '=', OLD)]), "its leftover names handed over")

    def test_installed_is_left_alone(self):
        retire.keep_retired(self.env, OLD, 'cloudflare_connector')
        self.assertEqual(self._state(), 'installed')

    def test_former_module_is_retired_here(self):
        """This database (the merge ran on it, or it never had the former module): never loadable."""
        self.env.cr.execute("SELECT state FROM ir_module_module WHERE name = %s", [retire.OLD])
        row = self.env.cr.fetchone()
        self.assertIn(row and row[0], (None, 'uninstallable'))
        self.assertFalse(self.Data.search_count([('module', '=', retire.OLD)]))

    def test_upgrade_steps_by_version(self):
        self.assertEqual(retire.old_version(self.env.cr, OLD), (0, 8, 0))
        with patch.object(page_cache_upgrades, 'STEPS', tuple(
                (since, lambda env, s=since: None) for since, _step in page_cache_upgrades.STEPS)):
            self.assertEqual(page_cache_upgrades.run_missing(self.env, (0, 8, 0)), [(0, 9, 0)], "0.9.0's only")
            self.assertEqual(page_cache_upgrades.run_missing(self.env, (0, 9, 0)), [], "www: none")
            self.assertEqual(page_cache_upgrades.run_missing(self.env, None), [], "never had it: none")
        night = self.env.ref('cloudflare_connector.cron_edge_cache_warm_home')
        night.code = 'model._mtbg_warm()'
        page_cache_upgrades.step_090(self.env)
        self.assertEqual(night.code, 'model._mtbg_warm_night()')
