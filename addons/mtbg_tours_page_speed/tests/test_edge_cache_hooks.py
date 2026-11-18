from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


class _EdgeCacheHooks(TransactionCase):
    """Cloudflare Connector's page cache (another repository, optional): where it is installed, this
    extension's declarations reach it. Its edits only noted (``_mtbg_changed`` mocked): never Cloudflare."""

    def setUp(self):
        super().setUp()
        if 'mtbg.edge.cache' not in self.env:
            self.skipTest("Cloudflare Page Cache is not installed")
        self.env['ir.config_parameter'].sudo().set_param('mtbg_tours.edge_cache', 'True')
        changed = patch.object(type(self.env['mtbg.edge.cache']), '_mtbg_changed', autospec=True)
        self.calls = changed.start()
        self.addCleanup(changed.stop)

    def _purges(self, key):
        self.calls.reset_mock()
        self.env['ir.config_parameter'].sudo().set_param(key, 'edge %s' % key)
        return self.calls.called


@tagged('post_install', '-at_install', 'mtbg')
class TestPageSpeedEdgeCache(_EdgeCacheHooks):

    def test_page_parameters(self):
        """0.9.2: the lean page switches purge; not every mtbg_tours.* (www, 2026-11-17: a sync stamp emptied every page)."""
        for key in ('mtbg_tours.page_speed_lean', 'mtbg_tours.page_speed_first_screen'):
            self.assertTrue(self._purges(key), key)
        for key in ('mtbg_page_speed.lightened_last_id', 'mtbg_tours.zoho_books_vendors_synced'):
            self.assertFalse(self._purges(key), key)
