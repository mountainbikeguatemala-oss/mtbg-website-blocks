from unittest.mock import MagicMock, patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.mtbg_tours_page_speed.models import ir_http, speed_log


def _answer(lcp_ms, score=0.82):
    return {'lighthouseResult': {
        'categories': {'performance': {'score': score}},
        'audits': {
            'largest-contentful-paint': {'numericValue': lcp_ms}, 'first-contentful-paint': {'numericValue': 900},
            'total-blocking-time': {'numericValue': 120.4}, 'cumulative-layout-shift': {'numericValue': 0.012},
            'speed-index': {'numericValue': 2100}, 'server-response-time': {'numericValue': 110},
            'total-byte-weight': {'numericValue': 2048 * 1024},
            'largest-contentful-paint-element': {'details': {'items': [{'items': [{'node': {'type': 'node',
                'snippet': '<img class="mtbg-tour-cover" src="/web/image/2662/1280x1280">'}}]}]}},
        }}}


class _Google:
    """The Google connector, measuring (a soft dependency: patched on its model when it is installed)."""

    def _google(self, ready=True, answers=None, error=None):
        Connector = type(self.env['google.connector'])
        ready_p = patch.object(Connector, '_google_pagespeed_ready', autospec=True, return_value=ready)
        run_p = patch.object(Connector, '_google_pagespeed_run', autospec=True,
                             side_effect=error if error else (lambda _self, url, strategy='mobile': answers.pop(0)))
        ready_p.start()
        run = run_p.start()
        self.addCleanup(ready_p.stop)
        self.addCleanup(run_p.stop)
        return run


@tagged('post_install', '-at_install', 'mtbg')
class TestSpeedLog(_Google, TransactionCase):
    """0.7.0 (owner: "we should do it from our own www server"), 0.7.4: through the Google connector."""

    def setUp(self):
        super().setUp()
        if 'google.connector' not in self.env:
            self.skipTest('no Google connector here')
        self.Log = self.env['mtbg.page.speed.log']
        self.ICP = self.env['ir.config_parameter'].sudo()
        self.Log.search([]).unlink()
        self.ICP.set_param(speed_log.PARAM_ON, 'True')
        # (0.10.0: one website measured here, at the site's address; several: TestSpeedLogWebsites)
        one = patch.object(type(self.Log), '_mtbg_websites', autospec=True,
                           return_value=self.env['website'].sudo().get_current_website())
        one.start()
        self.addCleanup(one.stop)

    def test_off_or_google_not_ready_does_nothing(self):
        run = self._google(ready=False, answers=[])
        self.assertEqual(self.Log._mtbg_speed_run(), 0)
        self.assertIn('switch on PageSpeed', self.Log._mtbg_google()[1])
        self.ICP.set_param(speed_log.PARAM_ON, 'False')
        self.assertEqual(self.Log._mtbg_speed_run(), 0)
        self.assertFalse(run.called)
        self.assertFalse(self.Log.search_count([]))

    def test_night_rows_then_batches(self):
        pages = ['/', '/es', '/tours/a-ride', '/tours/b-ride']
        # (0.8.0: phone pages under the limit here: a slow one is measured three times, test_slow_phone_median)
        run = self._google(answers=[_answer(3200), _answer(1900), _answer(2600), _answer(2000)] * 3)
        with patch.object(type(self.Log), '_mtbg_pages', autospec=True, return_value=pages):
            done = self.Log._mtbg_speed_run()
        rows = self.Log.search([])
        self.assertEqual(len(rows), 8, "every page, phone and computer")
        self.assertEqual(done, speed_log.BATCH)
        self.assertEqual(run.call_args.args[2], rows.sorted('id')[3].strategy)
        first = rows.filtered(lambda r: r.state == 'done').sorted('id')[0]
        self.assertEqual((first.score, first.lcp, first.tbt, first.ttfb, first.weight_kb), (82, 3.2, 120, 110, 2048))
        self.assertIn('mtbg-tour-cover', first.lcp_element)
        with patch.object(type(self.Log), '_mtbg_pages', autospec=True, return_value=pages):
            self.Log._mtbg_speed_run()
            self.Log._mtbg_speed_run()
        self.assertEqual(self.Log.search_count([]), 8)
        self.assertFalse(self.Log.search_count([('state', '=', 'pending')]))

    def test_limits(self):
        self.assertTrue(self.Log._mtbg_values(_answer(4100), 'mobile')['flagged'])
        self.assertFalse(self.Log._mtbg_values(_answer(3900), 'mobile')['flagged'])
        self.assertTrue(self.Log._mtbg_values(_answer(2600), 'desktop')['flagged'])
        self.assertFalse(self.Log._mtbg_values({}, 'desktop')['flagged'], "an empty answer: nothing flagged")

    def _due(self):
        """The retries and extra runs due now (as later in the night)."""
        self.Log.search([('next_try', '!=', False)]).write({'next_try': '2000-01-01 00:00:00'})

    def test_lighthouse_could_not_measure(self):
        """0.7.6 (www, Nov 8: six pages logged with score 0 and no LCP): Lighthouse's runtime error or a missing
        score is "Not measured" with Google's reason, never a measured 0. 0.8.0: only after two more tries later in
        the night."""
        broken = _answer(0, score=None)
        broken['lighthouseResult']['runtimeError'] = {
            'code': 'NO_LCP', 'message': 'The page did not display content that qualifies as a Largest Contentful Paint.'}
        self._google(answers=[broken, _answer(0, score=None), _answer(3000), _answer(1000),
                              _answer(0, score=None), broken, broken, _answer(0, score=None)])
        with patch.object(type(self.Log), '_mtbg_pages', autospec=True, return_value=['/', '/es']):
            self.Log._mtbg_speed_run()
            rows = self.Log.search([], order='id')
            self.assertEqual(rows.mapped('state'), ['pending', 'pending', 'done', 'done'], "tried again later")
            self.assertEqual(rows[:2].mapped('tries'), [1, 1])
            self.assertTrue(all(rows[:2].mapped('next_try')))
            self.assertIn('Largest Contentful Paint', rows[0].message, "the reason stays visible meanwhile")
            self.assertEqual(self.Log._mtbg_speed_run(), 0, "not before their time")
            for _n in range(2):
                self._due()
                self.Log._mtbg_speed_run()
        self.assertEqual(rows.mapped('state')[:2], ['error', 'error'], "three tries: Not measured")
        self.assertEqual(rows[:2].mapped('tries'), [3, 3])
        self.assertIn('Largest Contentful Paint', rows[0].message, "the last try's reason")
        self.assertIn('no performance score', rows[1].message)
        self.assertFalse(rows[0].flagged or rows[1].flagged or rows[0].slow)
        self.assertEqual(rows[2].score, 82)

    def test_retry_then_measured(self):
        """0.8.0: FAILED_DOCUMENT_REQUEST once, measured on the retry."""
        failed = _answer(0, score=None)
        failed['lighthouseResult']['runtimeError'] = {'code': 'FAILED_DOCUMENT_REQUEST', 'message': 'Lighthouse was '
                                                      'unable to reliably load the page you requested.'}
        self._google(answers=[failed, _answer(1200), _answer(2100)])
        with patch.object(type(self.Log), '_mtbg_pages', autospec=True, return_value=['/']):
            self.Log._mtbg_speed_run()
            self._due()
            self.Log._mtbg_speed_run()
        phone = self.Log.search([('strategy', '=', 'mobile')])
        self.assertEqual((phone.state, phone.lcp, phone.message), ('done', 2.1, False))

    def test_slow_phone_median(self):
        """0.8.0: a phone page slow on its first run is measured twice more, the median run kept, each run's LCP
        visible; a computer page once."""
        self._google(answers=[_answer(10100, score=0.5), _answer(3100), _answer(3200, score=0.9),
                              _answer(4600, score=0.7)])
        with patch.object(type(self.Log), '_mtbg_pages', autospec=True, return_value=['/']):
            self.Log._mtbg_speed_run()
            phone = self.Log.search([('strategy', '=', 'mobile')])
            self.assertEqual(phone.state, 'pending', "two more runs to come")
            self.assertEqual(self.Log.search([('strategy', '=', 'desktop')]).state, 'done')
            for _n in range(2):
                self._due()
                self.Log._mtbg_speed_run()
        self.assertEqual(phone.state, 'done')
        self.assertEqual(phone.lcp, 4.6, "the median of 10.1, 3.2 and 4.6")
        self.assertEqual(phone.score, 70, "the median run's own values")
        self.assertEqual(phone.lcp_runs, '10.1, 3.2, 4.6')
        self.assertTrue(phone.slow)
        self.assertFalse(phone.flagged, "slow one night only")

    def test_two_nights_in_a_row(self):
        """0.8.0: "Over the limit" only when the page was slow the night before too."""
        Log = self.Log.sudo()
        url = self.Log._mtbg_base() + '/tours/a-ride'
        Log.create({'run_date': '2026-11-14', 'url': url, 'strategy': 'desktop', 'state': 'done', 'slow': True})
        fast = Log.create({'run_date': '2026-11-15', 'url': url, 'strategy': 'desktop', 'state': 'done'})
        tonight = Log.create({'run_date': '2026-11-16', 'url': url, 'strategy': 'desktop'})
        tonight.runs_data = '[%s]' % __import__('json').dumps(self.Log._mtbg_values(_answer(3000), 'desktop'))
        tonight._mtbg_finish()
        self.assertTrue(tonight.slow)
        self.assertFalse(tonight.flagged, "the night before was fast")
        fast.slow = True
        tonight._mtbg_finish()
        self.assertTrue(tonight.flagged, "two slow nights in a row")
        sections = self.Log._mtbg_sidebar_sections([('strategy', '=', 'mobile')])
        nodes = {n['key']: n['count'] for s in sections if s['key'] == 'speed' for n in s['nodes']}
        self.assertEqual(nodes['desktop'], 3, "Computer counted with the Phone filter on (0.8.0)")
        self.assertEqual(nodes['mobile'], 0)

    def test_night_window(self):
        """0.8.0: the night ends: a page still to retry is Not measured, a slow phone page keeps its runs."""
        self._google(answers=[_answer(0, score=None), _answer(1000), _answer(6000), _answer(1000)])
        with patch.object(type(self.Log), '_mtbg_pages', autospec=True, return_value=['/', '/es']):
            self.Log._mtbg_speed_run()
            rows = self.Log.search([], order='id')
            self.env.cr.execute("UPDATE mtbg_page_speed_log SET create_date = create_date - interval '5 hours'")
            self.Log.invalidate_model(['create_date'])
            self.assertEqual(self.Log._mtbg_speed_run(), 0)
        self.assertEqual(rows.mapped('state'), ['error', 'done', 'done', 'done'])
        self.assertEqual((rows[2].lcp, rows[2].lcp_runs), (6.0, False), "one run kept")

    def test_google_refuses(self):
        self._google(error=Exception("Google error 403: PageSpeed Insights API has not been used in project 1"))
        with patch.object(type(self.Log), '_mtbg_pages', autospec=True, return_value=['/']):
            self.Log._mtbg_speed_run()
        self.assertEqual(set(self.Log.search([]).mapped('state')), {'error'})
        self.assertIn('has not been used', self.Log.search([], limit=1).message)

    def test_pages_from_the_sitemap(self):
        pages = self.Log._mtbg_pages()
        self.assertEqual(pages[0], '/')
        self.assertTrue(all(p == '/' or p.count('/') <= 2 for p in pages))

    def test_no_key_of_its_own(self):
        self.assertFalse(hasattr(speed_log, 'PARAM_KEY'), "Page Speed keeps no Google key (0.7.4)")


@tagged('post_install', '-at_install', 'mtbg')
class TestLazyBackgrounds(TransactionCase):
    """0.7.0: the sections' backgrounds after the first screen load when near (www homepage: ~10 photos, 3.5 MB,
    fetched with the first one, its LCP 0.7 -> 1.8-4.2 s)."""

    def test_later_backgrounds_wait(self):
        page = (b'<html><head></head><body><div id="wrap">'
                b'<section style="background-image: url(&#39;/web/image/1&#39;);">hero</section>'
                b'<section style="background-image: url(/web/image/2)">2</section>'
                b'<style>.x{background-image: url(/web/image/9)}</style>'
                b'<section class="s_cover" style="background-image: url(&quot;/web/image/3&quot;)">3</section>'
                b'<div class="carousel"><div class="carousel-item" style="background-image: url(/web/image/4)">4</div>'
                b'</div></div></body></html>')
        out = ir_http.speed_up(page)
        self.assertIn(b'<section style="background-image: url(&#39;/web/image/1&#39;);">', out, "the first: as is")
        self.assertIn(b'rel="preload"', out, "and preloaded")
        self.assertIn(b'<section style="background-image: url(/web/image/2)">', out, "the first screen: as is")
        self.assertIn(b'<section data-mtbg-lazy-bg="" class="s_cover"', out)
        self.assertIn(b'<div data-mtbg-lazy-bg="" class="carousel-item"', out)
        self.assertIn(b'<style>.x{background-image: url(/web/image/9)}</style>', out, "a stylesheet: untouched")
        self.assertIn(ir_http.LAZY_RULE, out)
        self.assertIn(b'data-mtbg-lazy-bg-js', out)
        self.assertEqual(ir_http.speed_up(out), out, "once")

    def test_backgrounds_after_the_first_photo_wait(self):
        """0.7.10: a tour page's description sections (far below its cover) waited for nothing: the first two
        backgrounds were eager by rank, and shared slow 4G with the cover (a tour page: 125 KB beside its 91 KB)."""
        page = (b'<html><head></head><body><main><div id="wrap" style="background-image: url(/web/image/7)">'
                b'<img src="data:image/gif;base64,R0lGOD" alt=""/>'
                b'<img class="mtbg-tour-cover" src="/web/image/5"/>'
                b'<section style="background-image: url(&#39;/web/image/1&#39;);">far below</section>'
                b'</div></main></body></html>')
        out = ir_http.speed_up(page)
        self.assertIn(b'<div id="wrap" style="background-image: url(/web/image/7)">', out,
                      "the page's own background, before the cover: at once")
        self.assertIn(b'<section data-mtbg-lazy-bg="" style=', out, "after the first photo: when near, even the first")
        self.assertIn(ir_http.LAZY_RULE, out)
        self.assertIn(b'<link rel="preload" as="image" media="(min-width: 992px)" href="/web/image/7"/>', out,
                      "the page background (0.9.1: computers only, never urgent beside the cover)")
        self.assertIn(b'<link rel="preload" as="image" fetchpriority="high" href="/web/image/5"/>', out,
                      "and the cover too: the phone's largest picture, behind the page background")
        self.assertIn(b'<img fetchpriority="high" class="mtbg-tour-cover" src="/web/image/5"/>', out)

    def test_video_player_when_near(self):
        """0.7.10: Odoo built a video's player at once, wherever the video was (a tour page: 1.3 MB of YouTube's
        scripts during Google's phone test); the page carries Odoo's iframe, loading="lazy"."""
        src = b'//www.youtube-nocookie.com/embed/2wY5jTMC28M?rel=0&amp;autoplay=1&amp;mute=1'
        page = (b'<html><head></head><body><main><img src="/web/image/5"/>'
                b'<div class="media_iframe_video my-3" data-oe-expression="' + src + b'"></div>'
                b'<div class="media_iframe_video" data-oe-expression="//evil.example/x"></div>'
                b'<div class="media_iframe_video" data-oe-expression="' + src + b'"><iframe src="x"></iframe></div>'
                b'</main></body></html>')
        out = ir_http.speed_up(page)
        self.assertIn(b'<div class="media_iframe_video my-3" data-oe-expression="' + src + b'">'
                      b'<div class="css_editable_mode_display"></div><div class="media_iframe_video_size"></div>'
                      b'<iframe frameborder="0" allowfullscreen="allowfullscreen" referrerpolicy="strict-origin-when-'
                      b'cross-origin" loading="lazy" src="' + src + b'"></iframe></div>', out)
        self.assertEqual(out.count(b'<iframe'), 2, "not another site's address, not a block that has its player")
        self.assertEqual(ir_http.speed_up(out).count(b'<iframe'), 2, "once")
        approval = page.replace(b'my-3"', b'my-3" data-need-cookies-approval="true"')
        self.assertEqual(ir_http.speed_up(approval).count(b'<iframe'), 1, "the cookies approval: Odoo's own way")
        self.assertEqual(ir_http.video_domain(b'https://www.youtube.com/embed/x'), b'youtube.com')
        self.assertIsNone(ir_http.video_domain(b'javascript:alert(1)'))

    def test_few_backgrounds_untouched(self):
        page = (b'<html><head></head><body><div id="wrap"><section style="background-image: url(/web/image/1)">1'
                b'</section><section style="background-image: url(/web/image/2)">2</section></div></body></html>')
        out = ir_http.speed_up(page)
        self.assertNotIn(b'data-mtbg-lazy-bg', out)


@tagged('post_install', '-at_install', 'mtbg')
class TestSetupWizard(_Google, TransactionCase):
    """The guided Set up (0.7.4: through the Google connector): steps, Test (one measurement through the connector,
    nothing saved), Save writes only the speed log's switch."""

    def setUp(self):
        super().setUp()
        if 'google.connector' not in self.env:
            self.skipTest('no Google connector here')
        self.ICP = self.env['ir.config_parameter'].sudo()
        self.ICP.set_param(speed_log.PARAM_ON, 'False')
        self.Setup = self.env['mtbg.page.speed.log.setup']

    def _others(self):
        return {p.key: p.value for p in self.ICP.search([('key', '!=', speed_log.PARAM_ON)])}

    def test_steps(self):
        self._google(ready=False, answers=[])
        wizard = self.Setup.create({})
        self.assertEqual(wizard.step, 'api')
        for step in ('app', 'test', 'on'):
            action = wizard.with_context(mtbg_step=step).action_go()
            self.assertEqual((wizard.step, action['res_id'], action['target']), (step, wizard.id, 'new'))
        self.assertIn('pages under /tours', wizard.pages_note)
        self.assertFalse(wizard.google_ok)
        self.assertTrue(wizard.has_connector)
        self.assertEqual(wizard.action_open_google().get('res_model'), 'google.connector.setup')

    def test_test_ok_saves_nothing(self):
        before = self._others()
        run = self._google(answers=[_answer(2300, score=0.91)])
        wizard = self.Setup.create({})
        wizard.action_test()
        self.assertTrue(run.call_args.args[1].endswith('/'))
        self.assertEqual(run.call_args.args[2], 'mobile')
        self.assertTrue(wizard.test_ok)
        self.assertIn('score 91', wizard.test_result)
        self.assertEqual(self._others(), before, "a test saves nothing")

    def test_test_refusals_in_plain_words(self):
        wizard = self.Setup.create({})
        for message, words in (
                ('Google error 400: API key not valid. Please pass a valid API key.', 'not valid'),
                ('Google error 403: PageSpeed Insights API has not been used in project 123 before or it is '
                 'disabled.', 'Enable'),
                ('Google error 403: Requests from referer <empty> are blocked.', 'Application restrictions'),
                ("Google error 429: Quota exceeded for quota metric 'Queries'", 'used up')):
            run_p = patch.object(type(self.env['google.connector']), '_google_pagespeed_run', autospec=True,
                                 side_effect=Exception(message))
            ready_p = patch.object(type(self.env['google.connector']), '_google_pagespeed_ready', autospec=True,
                                   return_value=True)
            with run_p, ready_p:
                wizard.action_test()
            self.assertFalse(wizard.test_ok, message)
            self.assertIn(words, wizard.test_result, message)
        self._google(ready=False, answers=[])
        wizard.action_test()
        self.assertIn('switch on PageSpeed', wizard.test_result, "not connected: what to do")

    def test_save_writes_only_its_switch(self):
        self._google(answers=[])
        self.ICP.set_param('mtbg_tours.edge_cache_canary', 'keep')
        self.ICP.set_param('mtbg_tours.zoho_canary', 'keep')
        before = self._others()
        self.Setup.create({'on': True, 'step': 'on'}).action_save()
        self.assertEqual(self.ICP.get_param(speed_log.PARAM_ON), 'True')
        self.assertEqual(self._others(), before)

    def test_admins_only(self):
        from odoo.exceptions import AccessError
        from odoo.tests import new_test_user
        user = new_test_user(self.env, login='speed_designer', groups='website.group_website_designer')
        with self.assertRaises(AccessError):
            self.env['mtbg.page.speed.log'].with_user(user).action_mtbg_setup()


@tagged('post_install', '-at_install', 'mtbg')
class TestKeyMoved(TransactionCase):
    """0.7.4's update: Page Speed's own key becomes the connector's server key (when it has none), then goes."""

    def _migrate(self):
        import importlib.util
        import os
        from odoo.modules.module import get_module_path
        path = os.path.join(get_module_path('mtbg_tours_page_speed'), 'migrations', '19.0.0.7.4', 'post-migrate.py')
        spec = importlib.util.spec_from_file_location('mtbg_page_speed_074', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.migrate(self.env.cr, '19.0.0.7.3')

    def test_moved_then_gone(self):
        if 'google.connector' not in self.env:
            self.skipTest('no Google connector here')
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('google_connector.server_key', False)
        ICP.set_param(speed_log.OLD_PARAM_KEY, 'OLD-KEY')
        self._migrate()
        self.assertEqual(ICP.get_param('google_connector.server_key'), 'OLD-KEY')
        self.assertFalse(ICP.get_param(speed_log.OLD_PARAM_KEY))
        ICP.set_param(speed_log.OLD_PARAM_KEY, 'OTHER-KEY')
        self._migrate()
        self.assertEqual(ICP.get_param('google_connector.server_key'), 'OLD-KEY', "the connector's key stays")
        self.assertFalse(ICP.get_param(speed_log.OLD_PARAM_KEY))


@tagged('post_install', '-at_install', 'mtbg')
class TestPageSpeedSettings(TransactionCase):
    """Page Speed's own settings page (owner: "the setup link should be in a central page-speed review settings
    area"): its Save writes only Page Speed's own switch."""

    def test_save_writes_only_page_speed(self):
        from odoo.addons.mtbg_tours_page_speed.models import lean
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('mtbg_tours.edge_cache_canary', 'keep')
        ICP.set_param('mtbg_tours.zoho_canary', 'keep')
        ICP.set_param(lean.PARAM, 'False')
        own = [lean.PARAM, lean.FIRST_SCREEN_PARAM]  # (0.7.7: and the first screen's switch)
        before = {p.key: p.value for p in ICP.search([('key', 'not in', own)])}
        page = self.env['mtbg.page.speed.settings'].create({})
        self.assertFalse(page.lean, "opens with what is saved")
        page.lean = True
        page.action_save()
        self.assertEqual(ICP.get_param(lean.PARAM), 'True')
        self.assertEqual({p.key: p.value for p in ICP.search([('key', 'not in', own)])}, before,
                         "nothing else written")
        self.assertTrue(self.env['ir.asset'].search_count([('bundle', '=', lean.BUNDLE)]), "its removals follow")

    def test_state_and_buttons(self):
        page = self.env['mtbg.page.speed.settings'].create({})
        self.assertGreaterEqual(page.copies_made, 0)
        self.assertEqual(page.action_setup()['res_model'], 'mtbg.page.speed.log.setup')
        self.assertEqual(page.action_open_log()['res_model'], 'mtbg.page.speed.log')
        self.assertEqual(page.action_run_copies()['tag'], 'display_notification')
        self.assertEqual(self.env['mtbg.page.speed.log']._mtbg_settings_xmlid(),
                         'mtbg_tours_page_speed.action_page_speed_settings')
        sections = self.env['mtbg.page.speed.log']._mtbg_sidebar_sections([])
        self.assertIn('flagged', [n['key'] for s in sections for n in s['nodes']])

    def test_admins_only(self):
        from odoo.exceptions import AccessError
        from odoo.tests import new_test_user
        user = new_test_user(self.env, login='speed_page_designer', groups='website.group_website_designer')
        with self.assertRaises(AccessError):
            self.env['mtbg.page.speed.settings'].with_user(user).create({}).action_save()


@tagged('post_install', '-at_install', 'mtbg')
class TestNightSchedule(_Google, TransactionCase):
    """0.7.5 (owner: "it should follow the global time zone"): 02:30 in the business's time zone, never moved by an
    update; Measure now."""

    def setUp(self):
        super().setUp()
        self.Log = self.env['mtbg.page.speed.log']
        self.ICP = self.env['ir.config_parameter'].sudo()
        self.cron = self.env.ref('mtbg_tours_page_speed.cron_speed_log')

    def test_next_night_in_the_business_time_zone(self):
        from datetime import datetime
        self.ICP.set_param(speed_log.TZ_PARAM, 'America/Guatemala')  # UTC-6
        # 20:00 in Guatemala (02:00 UTC next day): tonight's 02:30 = 08:30 UTC the next day
        self.assertEqual(self.Log._mtbg_next_night(datetime(2026, 11, 9, 2, 0)), datetime(2026, 11, 9, 8, 30))
        # 01:00 in Guatemala: 02:30 the same night
        self.assertEqual(self.Log._mtbg_next_night(datetime(2026, 11, 9, 7, 0)), datetime(2026, 11, 9, 8, 30))
        # 03:00 in Guatemala: the next night
        self.assertEqual(self.Log._mtbg_next_night(datetime(2026, 11, 9, 9, 0)), datetime(2026, 11, 10, 8, 30))
        self.ICP.set_param(speed_log.TZ_PARAM, 'Europe/Madrid')  # UTC+1 in November
        self.assertEqual(self.Log._mtbg_next_night(datetime(2026, 11, 9, 9, 0)), datetime(2026, 11, 10, 1, 30))

    def test_time_zone_change_moves_the_night(self):
        import pytz
        self.ICP.set_param(speed_log.TZ_PARAM, 'America/Guatemala')
        self.Log._mtbg_schedule_night()
        self.ICP.set_param(speed_log.TZ_PARAM, 'Asia/Tokyo')
        local = pytz.utc.localize(self.cron.nextcall).astimezone(pytz.timezone('Asia/Tokyo'))
        self.assertEqual((local.hour, local.minute), (2, 30))

    def test_job_kept_by_updates(self):
        data = self.env['ir.model.data'].search([('module', '=', 'mtbg_tours_page_speed'), ('name', '=', 'cron_speed_log')])
        self.assertTrue(data.noupdate, "an update never rewrites its time")

    def test_measure_now(self):
        page = self.env['mtbg.page.speed.settings'].create({})
        self.ICP.set_param(speed_log.PARAM_ON, 'False')
        self.assertEqual(page.action_measure_now()['params']['type'], 'warning', "off: says so")
        if 'google.connector' not in self.env:
            return
        self.ICP.set_param(speed_log.PARAM_ON, 'True')
        self._google(ready=True, answers=[])
        with patch.object(type(self.cron), '_trigger', autospec=True) as trigger:
            self.assertEqual(page.action_measure_now()['params']['type'], 'info')
        self.assertTrue(trigger.called, "measuring starts")
        self.assertTrue(page.next_night)



@tagged('post_install', '-at_install', 'mtbg')
class TestLcpElement(TransactionCase):
    """0.7.8: the LCP element read from Lighthouse 13's answer (lcp-breakdown-insight) as well as the older one."""

    def test_breakdown(self):
        """0.8.0: the LCP breakdown and the element's selector, from Lighthouse 13 and from older answers."""
        Log = self.env['mtbg.page.speed.log']
        new = {'lcp-breakdown-insight': {'details': {'type': 'list', 'items': [
            {'type': 'table', 'items': [{'subpart': 'timeToFirstByte', 'label': 'Time to first byte', 'duration': 10.4},
                                        {'subpart': 'resourceLoadDelay', 'duration': 120},
                                        {'subpart': 'resourceLoadDuration', 'duration': 180.2},
                                        {'subpart': 'elementRenderDelay', 'duration': 1130}]},
            {'type': 'node', 'selector': 'div.container > img.mtbg-tour-cover', 'snippet': '<img class="mtbg-tour-cover">'}]}}}
        self.assertEqual(Log._mtbg_lcp_breakdown(new), {'lcp_ttfb': 10, 'lcp_load_delay': 120, 'lcp_load_time': 180,
                                                        'lcp_render_delay': 1130})
        values = Log._mtbg_values({'lighthouseResult': {'audits': new}}, 'mobile')
        self.assertEqual(values['lcp_selector'], 'div.container > img.mtbg-tour-cover')
        self.assertEqual(values['lcp_element'], '<img class="mtbg-tour-cover">')
        old = {'largest-contentful-paint-element': {'details': {'type': 'list', 'items': [
            {'type': 'table', 'items': [{'node': {'type': 'node', 'selector': 'h1.t', 'snippet': '<h1 class="t">'}}]},
            {'type': 'table', 'items': [{'phase': 'TTFB', 'timing': 600}, {'phase': 'Load Delay', 'timing': 0},
                                        {'phase': 'Load Time', 'timing': 0}, {'phase': 'Render Delay', 'timing': 900}]}]}}}
        self.assertEqual(Log._mtbg_lcp_breakdown(old), {'lcp_ttfb': 600, 'lcp_load_delay': 0, 'lcp_load_time': 0,
                                                        'lcp_render_delay': 900})
        self.assertEqual(Log._mtbg_lcp_node(old, 'selector'), 'h1.t')
        self.assertEqual(Log._mtbg_lcp_breakdown({}), {'lcp_ttfb': 0, 'lcp_load_delay': 0, 'lcp_load_time': 0,
                                                       'lcp_render_delay': 0})

    def test_list_opens_on_both_screens(self):
        """0.8.0: the Speed log opens without the Phone filter (it hid the Computer rows)."""
        action = self.env.ref('mtbg_tours_page_speed.action_speed_log')
        self.assertNotIn('search_default_phone', action.context or '')
        self.assertIn('form', action.view_mode)

    def test_lighthouse_13_and_older(self):
        Log = self.env['mtbg.page.speed.log']
        new = {'lcp-breakdown-insight': {'details': {'type': 'list', 'items': [
            {'type': 'table', 'items': [{'subpart': 'timeToFirstByte', 'duration': 110}]},
            {'type': 'node', 'selector': 'div > img.mtbg-tour-cover', 'nodeLabel': 'Tour',
             'snippet': '<img class="mtbg-tour-cover" src="/web/image/2688/800x800">'}]}}}
        self.assertIn('/web/image/2688/800x800', Log._mtbg_lcp_node(new))
        old = {'largest-contentful-paint-element': {'details': {'type': 'list', 'items': [{'type': 'table', 'items': [
            {'node': {'type': 'node', 'snippet': '<h1 class="mtbg-title">'}}]}]}}}
        self.assertEqual(Log._mtbg_lcp_node(old), '<h1 class="mtbg-title">')
        selector_only = {'lcp-breakdown-insight': {'details': {'items': [{'type': 'node', 'selector': 'section.s_cover'}]}}}
        self.assertEqual(Log._mtbg_lcp_node(selector_only), 'section.s_cover')
        self.assertEqual(Log._mtbg_lcp_node({}), '')
        self.assertEqual(Log._mtbg_values({'lighthouseResult': {'audits': new}}, 'mobile')['lcp_element'][:4], '<img')


@tagged('post_install', '-at_install', 'mtbg')
class TestSpeedLogWebsites(_Google, TransactionCase):
    """0.10.0 (owner 2026-11-18, the shop site's two websites): each website measured on its own, its rows its own,
    the dashboard one website at a time."""

    def setUp(self):
        super().setUp()
        if 'google.connector' not in self.env:
            self.skipTest('no Google connector here')
        self.Log = self.env['mtbg.page.speed.log']
        self.Log.search([]).unlink()
        self.env['ir.config_parameter'].sudo().set_param(speed_log.PARAM_ON, 'True')
        Website = self.env['website'].sudo()
        self.one = Website.create({'name': 'Speed One', 'domain': 'https://one.example.com'})
        self.two = Website.create({'name': 'Speed Two', 'domain': 'two.example.org'})
        self.sites = self.one | self.two

    def test_each_website_its_own_rows(self):
        self._google(answers=[_answer(2000)] * 8)
        with patch.object(type(self.Log), '_mtbg_websites', autospec=True, return_value=self.sites), \
                patch.object(type(self.Log), '_mtbg_pages', autospec=True, return_value=['/', '/es']):
            self.Log._mtbg_speed_run()
            self.Log._mtbg_speed_run()
            self.Log._mtbg_speed_run()  # (a second night's run the same day makes no rows again)
        rows = self.Log.search([])
        self.assertEqual(len(rows), 8, "two pages, phone and computer, on each website")
        self.assertEqual(set(rows.filtered(lambda r: r.website_id == self.one).mapped('url')),
                         {'https://one.example.com/', 'https://one.example.com/es'})
        self.assertEqual(set(rows.filtered(lambda r: r.website_id == self.two).mapped('url')),
                         {'https://two.example.org/', 'https://two.example.org/es'})
        self.assertFalse(rows.filtered(lambda r: r.state == 'pending'))

        board = self.Log.mtbg_speed_dashboard(website_id=self.two.id)
        self.assertEqual(board['website_id'], self.two.id)
        self.assertEqual({w['id'] for w in board['websites']}, set(self.sites.ids))
        self.assertTrue(all(page['url'].startswith('https://two.example.org/')
                            for screen in board['worst'].values() for page in screen), "only that website's pages")
        self.assertEqual(self.Log.mtbg_speed_dashboard(website_id=self.one.id)['website_id'], self.one.id)

    def test_websites_measured(self):
        websites = self.Log._mtbg_websites()
        self.assertIn(self.one, websites)
        self.assertIn(self.two, websites)
        default = self.env['website'].sudo().get_current_website()
        self.assertFalse(websites.filtered(lambda w: not (w.domain or '').strip() and w != default),
                         "websites with an address, and the default one")
        self.assertEqual(self.Log._mtbg_base(self.two), 'https://two.example.org')
        self.assertEqual(self.Log._mtbg_website_of('https://two.example.org/shop'), self.two)
        self.assertEqual(self.Log._mtbg_website_of('https://one.example.com/'), self.one)

    def test_sidebar_has_websites(self):
        self.Log.create({'run_date': '2026-11-18', 'url': 'https://two.example.org/', 'strategy': 'mobile',
                         'website_id': self.two.id})
        sections = self.Log._mtbg_sidebar_sections([])
        website = next(s for s in sections if s['key'] == 'website')
        node = next(n for n in website['nodes'] if n['key'] == 'website_%s' % self.two.id)
        self.assertEqual(node['count'], 1)
