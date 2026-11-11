from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


class _EdgeCacheHooks(TransactionCase):
    """Cloudflare Page Cache (another repository, optional): where it is installed, this extension's declarations
    reach it. Its edits only noted (``_mtbg_changed`` mocked): never Cloudflare."""

    def setUp(self):
        super().setUp()
        if 'mtbg.edge.cache' not in self.env:
            self.skipTest("Cloudflare Page Cache is not installed")
        self.env['ir.config_parameter'].sudo().set_param('mtbg_tours.edge_cache', 'True')
        changed = patch.object(type(self.env['mtbg.edge.cache']), '_mtbg_changed', autospec=True)
        self.calls = changed.start()
        self.addCleanup(changed.stop)

    def _declared(self, key):
        from odoo.addons.mtbg_tours_edge_cache.models import live_values
        return live_values.declared(self.env, key)

    def _watched(self, model):
        from odoo.addons.mtbg_tours_edge_cache.models import sources
        return sources.sources(self.env).get(model, 'not watched')

@tagged('post_install', '-at_install', 'mtbg')
class TestContentBlocksEdgeCache(_EdgeCacheHooks):

    def test_blocks_and_templates_watched(self):
        self.assertIsNone(self._watched('mtbg.tours.content.block'))
        self.assertIsNone(self._watched('mtbg.page.template.line'))
        self.assertIn('line_ids', self._watched('mtbg.page.template'))
        self.assertNotIn('draft_layout', self._watched('mtbg.page.template'), "the editor's unsaved preview")

    def test_content_block_edit_purges(self):
        block = self.env['mtbg.tours.content.block'].sudo().search([], limit=1)
        if not block:
            self.skipTest('no content block here')
        self.calls.reset_mock()
        block.write({'name': block.name})
        self.assertTrue(self.calls.called)
