from unittest.mock import patch

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install', 'mtbg')
class TestCachedPage(HttpCase):
    """Odoo refreshes a page it cached more than an hour ago and hands back the very response it keeps in its cache:
    what a request does to its page must never change that cached response (0.3.2: "/" answered 500 on every
    request after such a refresh, its cached body turned to bytes)."""

    def test_stale_cached_page_refreshed_then_served_again(self):
        view = self.env['ir.ui.view'].create({
            'name': 'Page speed cache test', 'type': 'qweb', 'key': 'mtbg_tours_page_speed.cache_test',
            'arch': '<t t-name="mtbg_tours_page_speed.cache_test"><t t-call="website.layout"><div id="wrap">'
                    '<img src="/web/image/1" loading="lazy"/><p>cache test</p></div></t></t>'})
        self.env['website.page'].create({'view_id': view.id, 'url': '/mtbg-page-speed-cache-test',
                                         'is_published': True, 'website_id': self.env.ref('website.default_website').id})
        Page = self.env.registry['website.page']
        # (every cached page older than its life: each request takes Odoo's refresh path, then a hit of it)
        with patch.object(Page, '_CACHE_DURATION', -1):
            for _ in range(3):
                response = self.url_open('/mtbg-page-speed-cache-test')
                self.assertEqual(response.status_code, 200)
                self.assertIn('rel="preload" as="image" fetchpriority="high" href="/web/image/1"', response.text)
        for _ in range(2):  # (then served from the cache as usual)
            response = self.url_open('/mtbg-page-speed-cache-test')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.text.count('rel="preload" as="image"'), 1)
