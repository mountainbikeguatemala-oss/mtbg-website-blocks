"""19.0.2.1.0 (owner 2026-11-18: one database, two websites, each its own Cloudflare zone): each website's purges and
page cache in its own zone; Set up Cloudflare's zone stays the default website's. Every Cloudflare call is mocked."""
from unittest.mock import MagicMock, patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.cloudflare_connector.models import connector, edge_cache

API = 'https://api.cloudflare.com/client/v4/zones/%s/purge_cache'


@tagged('post_install', '-at_install', 'mtbg')
class TestWebsiteZones(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ICP = cls.env['ir.config_parameter'].sudo()
        cls.Api = cls.env['cloudflare.api'].sudo()
        cls.Cache = cls.env['mtbg.edge.cache']
        cls.Log = cls.env['mtbg.edge.cache.log'].sudo()
        Website = cls.env['website'].sudo()
        cls.one = Website.get_current_website()
        cls.one.domain = 'https://www.example.com'
        cls.two = Website.create({'name': 'Zone Two', 'domain': 'https://www.example.org'})
        for key, value in {'zone_id': 'ZONE1', 'zone_name': 'example.com', 'api_token': 'TOKEN'}.items():
            cls.ICP.set_param(connector.P + key, value)
        cls.ICP.set_param(connector.P + 'zone_website_id', False)
        for key, value in {'edge_cache': 'True', 'edge_cache_paths': '/ /blog', 'edge_cache_ttl': '300'}.items():
            cls.ICP.set_param('mtbg_tours.' + key, value)

    def setUp(self):
        super().setUp()
        offline = patch.object(edge_cache.requests, 'post', side_effect=AssertionError("Cloudflare called"))
        offline.start()
        self.addCleanup(offline.stop)
        for module in (edge_cache, connector):
            sleep = patch.object(module.time, 'sleep')
            sleep.start()
            self.addCleanup(sleep.stop)
        self.Log.search([]).unlink()
        self.env['mtbg.edge.cache.warm'].sudo().search([]).unlink()

    def _cloudflare(self):
        answer = MagicMock(status_code=200)
        answer.json.return_value = {'success': True, 'errors': []}
        return patch.object(edge_cache.requests, 'post', return_value=answer)

    def _zones(self, post):
        """{zone: [the bodies sent to it]}."""
        out = {}
        for c in post.call_args_list:
            zone = c.args[0].split('/zones/')[1].split('/')[0]
            out.setdefault(zone, []).append(c.kwargs['json'])
        return out

    def test_each_website_its_zone(self):
        self.assertEqual(self.Api.zone(self.one), {'id': 'ZONE1', 'name': 'example.com'}, "Set up Cloudflare's")
        self.assertEqual(self.Api.zone(self.two)['id'], '', "another website: none until it has its own")
        self.two.write({'cloudflare_zone_name': 'example.org', 'cloudflare_zone_id': 'ZONE2'})
        self.assertEqual(self.Api.zone(self.two), {'id': 'ZONE2', 'name': 'example.org'})
        self.assertEqual(self.Api.zone(self.one)['id'], 'ZONE1', "the first website's unchanged")
        # (a website whose address is in Set up Cloudflare's zone: that zone)
        shop = self.env['website'].sudo().create({'name': 'Zone Shop', 'domain': 'shop.example.com'})
        self.assertEqual(self.Api.zone(shop)['id'], 'ZONE1')
        self.assertTrue(connector.in_zone('https://www.example.com/', 'example.com'))
        self.assertFalse(connector.in_zone('www.notexample.com', 'example.com'))

    def test_pages_kept_only_where_a_purge_reaches(self):
        self.assertTrue(self.Cache._mtbg_website_kept(self.one))
        self.assertFalse(self.Cache._mtbg_website_kept(self.two), "no zone: Cloudflare never keeps its pages")
        self.two.write({'cloudflare_zone_name': 'example.org', 'cloudflare_zone_id': 'ZONE2'})
        self.assertTrue(self.Cache._mtbg_website_kept(self.two))

    def test_purge_goes_to_each_websites_zone(self):
        self.two.write({'cloudflare_zone_name': 'example.org', 'cloudflare_zone_id': 'ZONE2'})
        with self._cloudflare() as post:
            self.assertTrue(self.Cache._mtbg_purge('test'))
        zones = self._zones(post)
        self.assertEqual(set(zones), {'ZONE1', 'ZONE2'})
        tags = {zone: [t for body in bodies for t in body.get('tags', [])] for zone, bodies in zones.items()}
        self.assertEqual(tags['ZONE1'], [edge_cache.site_tag('www.example.com')])
        self.assertEqual(tags['ZONE2'], [edge_cache.site_tag('www.example.org')])
        prefixes = [p for body in zones['ZONE2'] for p in body.get('prefixes', [])]
        self.assertTrue(prefixes and all(p.startswith('www.example.org/') for p in prefixes), "its own address")
        logs = self.Log.search([])
        self.assertEqual(set(logs.mapped('website_id').ids), {self.one.id, self.two.id}, "a row each")
        self.assertTrue(all(logs.mapped('ok')))

    def test_some_pages_and_everything(self):
        self.two.write({'cloudflare_zone_name': 'example.org', 'cloudflare_zone_id': 'ZONE2'})
        with self._cloudflare() as post:
            self.Cache._mtbg_purge('test', paths=['/blog'])
        self.assertEqual(set(self._zones(post)), {'ZONE1', 'ZONE2'})
        with self._cloudflare() as post:
            self.Cache._mtbg_purge('test', everything=True)
        self.assertEqual(self._zones(post), {'ZONE1': [{'purge_everything': True}],
                                             'ZONE2': [{'purge_everything': True}]})

    def test_a_website_without_zone_is_left_alone(self):
        with self._cloudflare() as post:
            self.assertTrue(self.Cache._mtbg_purge('test'))
        self.assertEqual(set(self._zones(post)), {'ZONE1'}, "only the website that has one")
        self.assertEqual(self.Log.search([]).mapped('website_id'), self.one)

    def test_refill_at_each_websites_address(self):
        self.two.write({'cloudflare_zone_name': 'example.org', 'cloudflare_zone_id': 'ZONE2'})
        self.ICP.set_param('mtbg_tours.edge_cache_warm_paths', '/')
        answer = MagicMock(status_code=200, headers={'cf-cache-status': 'MISS'})
        with patch.object(edge_cache.requests, 'get', return_value=answer) as get:
            self.Cache._mtbg_warm_night()
        asked = {c.args[0] for c in get.call_args_list}
        self.assertIn('https://www.example.com/', asked)
        self.assertIn('https://www.example.org/', asked)
        self.assertFalse(self.env['mtbg.edge.cache.warm'].sudo().search([]))

    def test_check_after_a_save_at_its_websites_address(self):
        self.two.write({'cloudflare_zone_name': 'example.org', 'cloudflare_zone_id': 'ZONE2'})
        self.Log.with_context(mtbg_edge_cache_website=self.two.id)._mtbg_add(
            False, 'test', '', scope='pages', check='waiting', check_paths='/', purged=1.0)
        answer = MagicMock(status_code=200, headers={'cf-cache-status': 'MISS'})
        with patch.object(edge_cache.requests, 'get', return_value=answer) as get:
            self.Log._mtbg_check_waiting()
        self.assertEqual(get.call_args.args[0], 'https://www.example.org/')
        self.assertEqual(self.Log.search([], limit=1).check, 'ok')

    def test_settings_page_per_website(self):
        settings = self.env['res.config.settings'].create({'website_id': self.two.id})
        self.assertIn('No zone for this website', settings.mtbg_edge_cache_connection)
        settings.write({'website_cloudflare_zone_name': 'example.org', 'website_cloudflare_zone_id': 'ZONE2'})
        with self._cloudflare():
            settings.execute()
        self.assertEqual((self.two.cloudflare_zone_name, self.two.cloudflare_zone_id), ('example.org', 'ZONE2'))
        settings = self.env['res.config.settings'].create({'website_id': self.two.id})
        self.assertIn("this website's own", settings.mtbg_edge_cache_connection)
        self.assertIn('example.com', self.env['res.config.settings'].create(
            {'website_id': self.one.id}).mtbg_edge_cache_connection)

    def test_migration_names_the_default_website(self):
        from odoo.modules.module import load_script
        from odoo.tools.misc import file_path
        migration = load_script(file_path('cloudflare_connector/migrations/19.0.2.1.0/post-migrate.py'),
                                'cloudflare_connector_zones_migration')
        self.one.sequence, self.two.sequence = 20, 10   # (the first website by order is not the zone's)
        migration.migrate(self.env.cr, '19.0.2.0.1')
        self.assertEqual(self.ICP.get_param(connector.P + 'zone_website_id'), str(self.one.id),
                         "the website whose address is in the zone")
        self.assertEqual(self.Api.zone(self.one)['id'], 'ZONE1')
        self.assertEqual(self.ICP.get_param(connector.P + 'zone_id'), 'ZONE1', "Settings › Cloudflare as it was")
        self.ICP.set_param(connector.P + 'zone_name', 'elsewhere.net')
        self.assertEqual(self.Api.zone(self.one)['id'], 'ZONE1', "named: kept whatever the zone's name")
        self.assertEqual(self.Api.zone(self.two)['id'], '')
