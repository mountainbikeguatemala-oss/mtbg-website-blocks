"""0.9.0 (owner, 2026-11-17): the speed log's dashboard (a big chart, last night against the week before, the worst
pages) and every row's page title; the rows on their own page."""
from datetime import date, timedelta
from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

from odoo.addons.mtbg_tours_page_speed.models import speed_log

BASE = 'https://speed.example.com'
LAST = date(2026, 11, 16)


def seed(env, nights=30, pages=20):
    """Nights of rows: page n slower as n grows; the slowest phone page 'tours/ride-19' slow every night."""
    rows = []
    for night in range(nights):
        day = LAST - timedelta(days=night)
        for n in range(pages):
            for strategy in ('mobile', 'desktop'):
                # (tenths: the log keeps one decimal)
                lcp = round((1.0 + n * 0.3 + night * 0.1) * (1 if strategy == 'mobile' else 0.5), 1)
                slow = lcp > speed_log.LIMITS[strategy]
                rows.append({
                    'run_date': day, 'url': f'{BASE}/tours/ride-{n}', 'strategy': strategy, 'state': 'done',
                    'page_title': f'Ride {n}', 'score': max(5, 100 - n * 4 - night % 3), 'lcp': lcp, 'fcp': 0.9,
                    'tbt': 100 + n, 'cls': 0.01, 'ttfb': 200 + n, 'weight_kb': 900 + n, 'slow': slow,
                    'flagged': slow and night < nights - 1, 'lcp_ttfb': 200, 'lcp_load_delay': 100,
                    'lcp_load_time': 300, 'lcp_render_delay': 400 + n * 50})
    env['mtbg.page.speed.log'].sudo().create(rows)


@tagged('post_install', '-at_install', 'mtbg')
class TestSpeedDashboard(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Log = self.env['mtbg.page.speed.log']
        self.Log.search([]).unlink()

    def test_empty(self):
        data = self.Log.mtbg_speed_dashboard(30)
        self.assertFalse(data['last'])
        self.assertEqual(data['worst'], {})

    def test_averages_per_night_and_screen(self):
        seed(self.env, nights=10, pages=4)
        self.Log.create({'run_date': LAST, 'url': BASE + '/x', 'strategy': 'mobile', 'state': 'error'})
        data = self.Log.mtbg_speed_dashboard(7)
        self.assertEqual(data['last'], '2026-11-16')
        self.assertEqual(len(data['dates']), 7, "the last 7 nights only")
        self.assertEqual(data['dates'][-1], '2026-11-16')
        # last night, phone: LCPs 1.0, 1.3, 1.6, 1.9 -> 1.45 (the error row left out)
        self.assertAlmostEqual(data['series']['mobile']['lcp'][-1], 1.45, delta=0.006)
        self.assertAlmostEqual(data['series']['mobile']['lcp'][0], 2.05, delta=0.006, msg="6 nights before")
        self.assertLess(data['series']['desktop']['lcp'][-1], 0.8)
        self.assertEqual(data['series']['mobile']['ttfb'][-1], 202)
        self.assertEqual(set(data['series']['mobile']), set(speed_log.STATS))
        self.assertEqual(data['marks']['lcp'], speed_log.LIMITS)

    def test_kpis_last_night_against_the_week(self):
        seed(self.env, nights=10, pages=4)
        self.Log.create({'run_date': LAST, 'url': BASE + '/x', 'strategy': 'mobile', 'state': 'error'})
        kpis = self.Log.mtbg_speed_dashboard(30)['kpis']['mobile']
        self.assertEqual(kpis['last']['error'], 1)
        self.assertEqual(kpis['week']['error'], 0)
        # the 7 nights before: LCP 1.45 + 0.1 * night, nights 1..7 -> 1.85
        self.assertAlmostEqual(kpis['week']['lcp'], 1.85, delta=0.006)
        self.assertLess(kpis['last']['lcp'], kpis['week']['lcp'])
        self.assertEqual(kpis['last']['over'], 0)

    def test_worst_pages(self):
        seed(self.env)
        data = self.Log.mtbg_speed_dashboard(30)
        worst = data['worst']['mobile']
        self.assertEqual(len(worst), speed_log.WORST)
        self.assertEqual([p['path'] for p in worst], [f'/tours/ride-{n}' for n in (19, 18, 17, 16, 15)])
        first = worst[0]
        self.assertEqual(first['title'], 'Ride 19')
        self.assertEqual(first['night'], '2026-11-16')
        self.assertEqual(first['lcp'], 6.7)
        # (0.9.1: 1.95 s of breakdown for a 6.7 s LCP: it doesn't explain it, said instead of its biggest part)
        self.assertEqual((first['cause'], first['cause_ms']), ("The breakdown doesn't explain the time", 0))
        explained = [p for p in worst if p['cause_ms']]
        for page in explained:
            self.assertIn(page['cause'], ('render delay', 'load time', 'load delay', 'server answer'))
        self.assertEqual(first['slow_nights'], 30, "slow every night of the 30")
        self.assertTrue(first['flagged'])
        # (7 nights: the slow nights counted in the range only)
        self.assertEqual(self.Log.mtbg_speed_dashboard(7)['worst']['mobile'][0]['slow_nights'], 7)
        self.assertIn(first['url'], data['pages'])
        self.assertEqual(len(data['pages'][first['url']]['mobile']['lcp']), 30)
        self.assertEqual(data['worst']['desktop'][0]['path'], '/tours/ride-19')

    def test_cause_when_the_breakdown_does_not_explain_the_lcp(self):
        """0.9.1 (www, 2026-11-17: a 9.6 s phone LCP whose card said "render delay 1.3 s", its element the logo)."""
        common = {'run_date': LAST, 'strategy': 'mobile', 'state': 'done', 'score': 60, 'lcp_ttfb': 15,
                  'lcp_load_delay': 0, 'lcp_load_time': 0}
        self.Log.create([
            dict(common, url=BASE + '/tours/logo', lcp=9.6, lcp_render_delay=1277,
                 lcp_selector='div.d-flex > a.navbar-brand > span > img.img'),
            dict(common, url=BASE + '/tours/card', lcp=8.0, lcp_render_delay=900,
                 lcp_element='<img class="mtbg-card__img" loading="lazy" src="/web/image/1">'),
            dict(common, url=BASE + '/tours/background', lcp=7.0, lcp_render_delay=800,
                 lcp_selector='body > div#wrapwrap > main > div#wrap'),
            dict(common, url=BASE + '/tours/explained', lcp=2.4, lcp_render_delay=1500, lcp_load_time=600),
        ])
        worst = {p['path']: p for p in self.Log.mtbg_speed_dashboard(7)['worst']['mobile']}
        self.assertEqual((worst['/tours/logo']['cause'], worst['/tours/logo']['cause_ms']),
                         ("LCP element: header logo; the breakdown doesn't explain the time", 0))
        self.assertEqual(worst['/tours/card']['cause'],
                         "LCP element: img.mtbg-card__img; the breakdown doesn't explain the time")
        self.assertEqual(worst['/tours/background']['cause'],
                         "LCP element: page background; the breakdown doesn't explain the time")
        self.assertEqual((worst['/tours/explained']['cause'], worst['/tours/explained']['cause_ms']),
                         ('render delay', 1500), "2.1 s of 2.4 s: its biggest part, as before")
        es = self.Log.with_context(lang='es_ES')
        if self.env['res.lang']._lang_get('es_ES'):
            self.assertEqual(es._mtbg_element_label('a.navbar-brand > img'), 'logo del encabezado')

    def test_admins_only(self):
        user = new_test_user(self.env, login='speed_dash_user', groups='base.group_user')
        with self.assertRaises(AccessError):
            self.Log.with_user(user).mtbg_speed_dashboard(30)

    def test_menus(self):
        dashboard = self.env.ref('mtbg_tours_page_speed.menu_speed_log')
        self.assertEqual(dashboard.action, self.env.ref('mtbg_tours_page_speed.action_speed_log_dashboard'))
        rows = self.env.ref('mtbg_tours_page_speed.menu_speed_log_rows')
        self.assertEqual(rows.action, self.env.ref('mtbg_tours_page_speed.action_speed_log'))
        self.assertEqual(rows.name, 'Speed log: all nights')
        arch = self.env.ref('mtbg_tours_page_speed.speed_log_list').arch
        self.assertLess(arch.index('page_title'), arch.index('name="url"'), "the title, then the page")


@tagged('post_install', '-at_install', 'mtbg')
class TestPageTitles(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Log = self.env['mtbg.page.speed.log'].sudo()
        self.Log.search([]).unlink()
        self.website = self.env['website'].get_current_website()

    def test_clean_title(self):
        clean = self.Log._mtbg_clean_title
        self.assertEqual(clean('Volcano Ride | Some Site', 'Some Site'), 'Volcano Ride')
        self.assertEqual(clean('  Volcano &amp; Lake\n Ride - Some Site ', 'Some Site'), 'Volcano & Lake Ride')
        self.assertEqual(clean('A | B', 'Other'), 'A | B', "only the site's own name left out")

    def test_website_page_name_else_its_title(self):
        page = self.env['website.page'].create({'name': 'Speed Test Page', 'url': '/speed-test-page', 'type': 'qweb',
                                                'arch': '<div/>', 'key': 'website.speed_test_page',
                                                'website_id': self.website.id})
        fetched = []

        def fetch(_self, url):
            fetched.append(url)
            return f'Ride Title | {self.website.name}'
        with patch.object(type(self.Log), '_mtbg_fetch_title', autospec=True, side_effect=fetch):
            titles = self.Log._mtbg_titles([BASE + page.url, BASE + '/tours/ride'])
        self.assertEqual(titles, {BASE + page.url: 'Speed Test Page', BASE + '/tours/ride': 'Ride Title'})
        self.assertEqual(fetched, [BASE + '/tours/ride'], "the page's HTML only when no website page is it")

    def test_fetch_title_reads_the_head(self):
        class Answer:
            status_code, encoding = 200, 'utf-8'

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def iter_content(self, size):
                yield b'<html><head><meta charset="utf-8"><title>Lago &amp; Volc\xc3\xa1n</title>'
                raise AssertionError("read on after the title")
        with patch.object(speed_log.requests, 'get', return_value=Answer()):
            self.assertEqual(self.Log._mtbg_fetch_title(BASE + '/'), 'Lago &amp; Volcán')
        with patch.object(speed_log.requests, 'get', side_effect=speed_log.requests.ConnectionError()):
            self.assertEqual(self.Log._mtbg_fetch_title(BASE + '/'), '')

    def test_backfill(self):
        """The rows logged before 0.9.0: the title their page had another night, else their page's own."""
        old = self.Log.create([{'run_date': LAST - timedelta(days=d), 'url': BASE + path, 'strategy': 'mobile',
                                'state': 'done'} for d in range(3) for path in ('/a', '/b')])
        self.Log.create({'run_date': LAST + timedelta(days=1), 'url': BASE + '/a', 'strategy': 'mobile',
                         'page_title': 'Page A'})
        with patch.object(type(self.Log), '_mtbg_fetch_title', autospec=True, return_value='Page B'):
            self.assertEqual(self.Log._mtbg_fill_titles(), 2)
        self.assertEqual(set(old.filtered(lambda r: r.url.endswith('/a')).mapped('page_title')), {'Page A'})
        self.assertEqual(set(old.filtered(lambda r: r.url.endswith('/b')).mapped('page_title')), {'Page B'})
        # (the update's own pass fetches nothing: a page without a known title waits for the job)
        self.Log.create({'run_date': LAST, 'url': BASE + '/c', 'strategy': 'mobile'})
        with patch.object(type(self.Log), '_mtbg_fetch_title', autospec=True) as fetch:
            self.assertEqual(self.Log._mtbg_fill_titles(fetch=False), 0)
        self.assertFalse(fetch.called)

    def test_night_rows_get_their_title(self):
        if 'google.connector' not in self.env:
            self.skipTest('no Google connector here')
        self.env['ir.config_parameter'].sudo().set_param(speed_log.PARAM_ON, 'True')
        Connector = type(self.env['google.connector'])
        with patch.object(Connector, '_google_pagespeed_ready', autospec=True, return_value=True), \
                patch.object(Connector, '_google_pagespeed_run', autospec=True, side_effect=Exception('Google error 403')), \
                patch.object(type(self.Log), '_mtbg_pages', autospec=True, return_value=['/tours/ride']), \
                patch.object(type(self.Log), '_mtbg_websites', autospec=True,
                             return_value=self.env['website'].sudo().get_current_website()), \
                patch.object(type(self.Log), '_mtbg_fetch_title', autospec=True, return_value='The Ride'):
            self.Log._mtbg_speed_run()
        self.assertEqual(self.Log.search([]).mapped('page_title'), ['The Ride', 'The Ride'])
        self.assertEqual(self.Log.search([], limit=1).path, '/tours/ride')


@tagged('post_install', '-at_install', 'mtbg')
class TestSpeedDashboardTour(HttpCase):

    def setUp(self):
        super().setUp()
        self.env['mtbg.page.speed.log'].search([]).unlink()
        seed(self.env)

    def test_dashboard_light(self):
        self.start_tour('/odoo/action-mtbg_tours_page_speed.action_speed_log_dashboard', 'mtbg_speed_log_dashboard',
                        login='admin')

    def test_dashboard_dark(self):
        self.start_tour('/odoo/action-mtbg_tours_page_speed.action_speed_log_dashboard',
                        'mtbg_speed_log_dashboard_dark', login='admin')


@tagged('post_install', '-at_install', 'mtbg')
class TestSpeedDashboardPhone(HttpCase):
    """Owner, 2026-11-17: "make this whole page mobile compatible"."""
    browser_size = '390x844'
    touch_enabled = True

    def setUp(self):
        super().setUp()
        self.env['mtbg.page.speed.log'].search([]).unlink()
        seed(self.env)

    def test_dashboard_phone(self):
        self.start_tour('/odoo/action-mtbg_tours_page_speed.action_speed_log_dashboard',
                        'mtbg_speed_log_dashboard_phone', login='admin')

    def test_rows_open_as_cards_on_phones(self):
        action = self.env.ref('mtbg_tours_page_speed.action_speed_log')
        self.assertEqual(action.mobile_view_mode, 'kanban')
        self.assertIn('kanban', action.view_mode.split(','))
