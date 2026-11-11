import json
import html
import re
import os
from datetime import timedelta
from unittest.mock import MagicMock, patch

from odoo.exceptions import AccessError, UserError
from odoo.service.model import call_kw
from odoo.tools.misc import file_path
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged
from odoo.tests.common import Opener

from odoo.addons.mtbg_tours_edge_cache.models import edge_cache, live_values
from odoo.addons.mtbg_tours_edge_cache.models import ir_http as edge_ir_http
from odoo.addons.mtbg_tours_edge_cache.models import sources as edge_sources

UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36'


def _settings(env, on=True, paths='/ /es/ /blog', ttl=300):
    ICP = env['ir.config_parameter'].sudo()
    for key, value in {'edge_cache': 'True' if on else 'False', 'edge_cache_paths': paths,
                       'edge_cache_ttl': str(ttl)}.items():
        ICP.set_param(f'mtbg_tours.{key}', value)
    _connector(env)


def _connector(env, zone='ZONE', token='TOKEN'):
    """0.7.0: the zone and the purge token are Cloudflare Connector's (Set up Cloudflare writes them)."""
    ICP = env['ir.config_parameter'].sudo()
    ICP.set_param('cloudflare_connector.zone_id', zone)
    ICP.set_param('cloudflare_connector.api_token', token)


class _declaring:
    """A live values declaration on a registry class for the time of a ``with`` (tests)."""

    def __init__(self, env, rows):
        self.env, self.rows, self.cls = env, rows, type(env['res.partner'])

    def __enter__(self):
        setattr(self.cls, live_values.ATTRIBUTE, self.rows)
        self.env.registry._mtbg_edge_live_keys = None
        return self

    def __exit__(self, *exc):
        delattr(self.cls, live_values.ATTRIBUTE)
        self.env.registry._mtbg_edge_live_keys = None


def _needs_connector(case):
    """The purge goes through Cloudflare Connector (a soft check: Edge Cache installs without it)."""
    if 'cloudflare.api' not in case.env:
        case.skipTest("Cloudflare Connector is not installed: nothing is purged")


PURGE_URL = 'https://api.cloudflare.com/client/v4/zones/ZONE/purge_cache'


@tagged('post_install', '-at_install', 'mtbg')
class TestEdgeCachePages(HttpCase):
    """What Odoo lets Cloudflare keep: anonymous GETs of the listed pages, without cookies."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['website.page'].create({
            'url': '/edge-ride', 'is_published': True, 'name': 'Edge Ride', 'type': 'qweb',
            'key': 'mtbg_tours_edge_cache.edge_ride', 'website_id': cls.env['website'].get_current_website().id,
            'arch': '<t t-call="website.layout"><div id="wrap"><form><input name="x"/></form>Edge Ride</div></t>'})

    def setUp(self):
        super().setUp()
        offline = patch.object(edge_cache.requests, 'post', side_effect=AssertionError("Cloudflare called"))
        offline.start()
        self.addCleanup(offline.stop)

    def _visitor(self):
        self.opener = Opener(self)
        self.opener.headers.update({'User-Agent': UA, 'CF-IPCountry': 'GT'})

    def _get(self, path):
        response = self.url_open(path, allow_redirects=False)
        return response, response.headers.get('Cache-Control') or '', response.headers.get('Set-Cookie') or ''

    def test_off_changes_nothing(self):
        _settings(self.env, on=False)
        self._visitor()
        response, cache, cookies = self._get('/edge-ride')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('s-maxage', cache)
        self.assertIn('session_id', cookies, "Odoo's own cookies, as before")
        self.assertNotIn('name="mtbg-cached"', response.text)

    def test_listed_pages_cached_without_cookies(self):
        _settings(self.env)
        self._visitor()
        for path in ('/edge-ride', '/'):
            response, cache, cookies = self._get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertEqual(cache, 'public, max-age=0, s-maxage=300, stale-if-error=604800', path)
            self.assertFalse(cookies, f"{path}: no cookie on a page every visitor gets")
            self.assertIn('name="mtbg-cached"', response.text, path)

    def test_other_pages_and_requests_not_cached(self):
        _settings(self.env)
        self._visitor()
        for path in ('/edge-ride?debug=1', '/no-such-page', '/web/login', '/my', '/shop/cart'):
            response, cache, cookies = self._get(path)
            self.assertNotIn('s-maxage', cache, path)
        self.assertNotIn('s-maxage', self._get('/blogx')[1], "a prefix is a whole address part")

    def test_website_pages_blog_and_sitemap(self):
        """0.6.0: every public page: the website's own pages (Website › Pages) wherever they are, the blog in each
        language; not a page behind a password; the sitemap without a session."""
        _settings(self.env, paths='/ /blog')
        self._visitor()
        response, cache, cookies = self._get('/contactus')
        self.assertEqual(response.status_code, 200)
        self.assertIn('s-maxage=300', cache, "a website page")
        self.assertFalse(cookies)
        self.env['website.page'].create({
            'url': '/edge-secret', 'is_published': True, 'name': 'Edge secret', 'type': 'qweb',
            'key': 'mtbg_tours_edge_cache.edge_secret', 'visibility': 'password', 'visibility_password': 'x',
            'arch': '<t t-call="website.layout"><div id="wrap">Secret</div></t>'})
        self.assertNotIn('s-maxage', self._get('/edge-secret')[1], "behind a password")
        if 'blog.post' in self.env:
            blog = self.env['blog.blog'].create({'name': 'Edge Journal'})
            post = self.env['blog.post'].create({'name': 'Edge post', 'blog_id': blog.id, 'is_published': True})
            for path in (post.website_url, '/blog'):
                response, cache, cookies = self._get(path)
                self.assertEqual(response.status_code, 200, path)
                self.assertIn('s-maxage=300', cache, path)
                self.assertFalse(cookies, path)
        self._visitor()
        response, cache, cookies = self._get('/sitemap.xml')
        self.assertNotIn('session_id', cookies, "the sitemap makes no session")
        self.assertNotIn('session_id', self._get('/robots.txt')[2])

    def test_logged_in_never_cached_and_marked(self):
        _settings(self.env)
        self.authenticate('admin', 'admin')
        response, cache, cookies = self._get('/edge-ride')
        self.assertEqual(self.opener.cookies.get('mtbg_auth'), '1', "the marker, from the first page with a user")
        self.assertNotIn('s-maxage', cache)
        self.assertNotIn('name="mtbg-cached"', response.text)
        self.url_open('/web/session/logout', allow_redirects=False)
        self.assertFalse(self.opener.cookies.get('mtbg_auth'), "removed at logout")

    def test_browser_gets_its_own_token(self):
        """In a real browser, a cached page's script swaps the page's form token for the visitor's own."""
        _settings(self.env)
        # (the test browser always has a session of its own, so the visitor's token may equal the page's here;
        # that a new visitor gets a token of their own: test_session_token_and_country)
        code = """
const cached = !!document.querySelector('meta[name="mtbg-cached"]');
window.mtbgSession.then((data) => {
    if (cached && data.csrf_token && odoo.csrf_token === data.csrf_token) {
        console.log('test successful');
    } else {
        console.error('test failed: ' + cached + ' ' + JSON.stringify(data));
    }
});
"""
        self.browser_js('/edge-ride', code, ready="'mtbgSession' in window", login=None)

    def test_session_token_and_country(self):
        _settings(self.env)
        self._visitor()
        self._get('/edge-ride')
        self.assertFalse(self.opener.cookies.get('session_id'), "the cached page made no session")
        answer = self.url_open('/mtbg/session')
        self.assertEqual(answer.headers.get('Cache-Control'), 'no-store')
        data = answer.json()
        self.assertEqual(data['country'], 'GT')
        self.assertTrue(self.opener.cookies.get('session_id'), "the session is made here")
        # the token works for a form of this session (a wrong password, but no "session expired")
        login = self.url_open('/web/login', data={'login': 'nobody', 'password': 'x', 'csrf_token': data['csrf_token']})
        self.assertEqual(login.status_code, 200)
        self.assertNotIn('Session expired', login.text)


@tagged('post_install', '-at_install', 'mtbg')
class TestEdgeCachePurge(TransactionCase):
    """A change shown on the pages empties Cloudflare's cache once the save is committed, at most every 10 s per
    worker; the one-minute job sends what is left."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Cache = cls.env['mtbg.edge.cache']
        cls.Change = cls.env['mtbg.edge.cache.change'].sudo()
        cls.Log = cls.env['mtbg.edge.cache.log'].sudo()
        website = cls.env['website'].get_current_website()
        # (a menu entry: shown on every page; 0.8.0: any watched record, the Tours ones declared by their extensions)
        cls.tour = cls.env['website.menu'].create({'name': 'Purge Ride', 'url': '/purge-ride',
                                                   'parent_id': website.menu_id.id, 'website_id': website.id})

    def setUp(self):
        super().setUp()
        _needs_connector(self)
        self.registry_enter_test_mode()  # (the after-commit purge's own cursor sees this test's changes)
        # never Cloudflare itself: every purge of these tests goes to this mock
        offline = patch.object(edge_cache.requests, 'post', side_effect=AssertionError("Cloudflare called"))
        offline.start()
        self.addCleanup(offline.stop)
        self.env.cr.postcommit.clear()

    def _ready(self, on=True):
        """The settings saved and their own purge done: a clean start."""
        with self._cloudflare():
            _settings(self.env, on=on)
            self._commit()
        edge_cache._last.clear()
        self.Change.search([]).unlink()

    def _cloudflare(self, success=True):
        answer = MagicMock(status_code=200 if success else 403)
        answer.json.return_value = {'success': success, 'errors': [] if success else [{'message': 'Bad token'}]}
        return patch.object(edge_cache.requests, 'post', return_value=answer)

    def _commit(self):
        self.env.flush_all()
        self.env.cr.postcommit.run()

    def test_change_purges_once_after_commit(self):
        self._ready()
        with self._cloudflare() as post:
            self.tour.name = 'Purge Ride 2'
            self.tour.url = '/purge-ride-2'
            self.assertEqual(post.call_count, 0, "nothing before the commit")
            self._commit()
        self.assertEqual(post.call_count, 1, "one purge for the save")
        url, kw = post.call_args[0][0], post.call_args[1]
        self.assertEqual(url, PURGE_URL)
        self.assertEqual(kw['json'], {'purge_everything': True})
        self.assertEqual(kw['headers']['Authorization'], 'Bearer TOKEN')
        self.assertFalse(self.Change.search([]), "nothing left to purge")
        self.assertTrue(self.Log.search([], limit=1).ok)

    def test_module_updates_purge_once_when_over(self):
        """0.6.2: while modules are installed or upgraded (every module's templates written again), changes are
        only noted; the one-minute job purges once the updates have been quiet UPDATE_QUIET seconds."""
        self._ready()
        with self._cloudflare() as post, patch.object(type(self.Cache), '_mtbg_updating', autospec=True,
                                                      return_value=True):
            self.tour.name = 'Purge Ride update'
            self._commit()
            self.assertEqual(post.call_count, 0, "no purge after the save during an update")
            noted = self.Change.search([])
            self.assertTrue(noted and all(noted.mapped('during_update')))
            self.assertFalse(self.Cache._mtbg_purge_pending(), "the job waits while the update goes on")
            self.env.cr.execute("UPDATE mtbg_edge_cache_change SET create_date = create_date - interval '4 minutes'")
            self.env.invalidate_all()
            self.assertTrue(self.Cache._mtbg_purge_pending())
            self.assertEqual(post.call_count, 1, "one purge for the whole update")
        self.assertFalse(self.Change.search([]))

    def test_updating_detected(self):
        self.assertFalse(self.Cache._mtbg_updating(), "a running site (tests: not an update)")
        self.assertTrue(self.Cache.with_context(install_mode=True)._mtbg_updating(), "a module's data loading")

    def test_spacing_then_the_job(self):
        self._ready()
        with self._cloudflare() as post:
            self.tour.name = 'A'
            self._commit()
            self.tour.name = 'B'
            self._commit()
            self.assertEqual(post.call_count, 1, "a second purge seconds later waits for the job")
            self.assertTrue(self.Change.search([]))
            self.Cache._mtbg_purge_pending()
            self.assertEqual(post.call_count, 2)
            self.assertFalse(self.Change.search([]))
            self.Cache._mtbg_purge_pending()
            self.assertEqual(post.call_count, 2, "nothing waiting: nothing sent")

    def test_refused_kept_for_the_job(self):
        self._ready()
        with self._cloudflare(success=False) as post:
            self.tour.name = 'C'
            self._commit()
        self.assertEqual(post.call_count, 1)
        self.assertTrue(self.Change.search([]), "kept for the next try")
        log = self.Log.search([], limit=1)
        self.assertFalse(log.ok)
        self.assertIn('Bad token', log.message)

    def test_off_and_unrelated_changes_send_nothing(self):
        self._ready(on=False)
        with self._cloudflare() as post:
            self.tour.name = 'D'
            self._commit()
            self.assertFalse(post.called, "switched off")
        self._ready()
        with self._cloudflare() as post:
            self.env['res.partner'].create({'name': 'Not on a page'})
            self._commit()
            self.assertFalse(post.called, "a change no page shows")

    def test_neutralize(self):
        self._ready()
        path = os.path.join(os.path.dirname(edge_cache.__file__), '..', 'data', 'neutralize.sql')
        with open(path) as sql:
            self.env.cr.execute(sql.read())
        self.env.registry.clear_cache('stable')
        params = self.Cache._mtbg_params()
        self.assertFalse(params['on'])
        # the connector lives in another repository: found by module name, wherever its folder is
        connector_sql = file_path('cloudflare_connector/data/neutralize.sql')
        with open(connector_sql) as sql:
            self.env.cr.execute(sql.read())
        self.env.registry.clear_cache('stable')
        self.assertFalse(self.env['ir.config_parameter'].sudo().get_param('cloudflare_connector.api_token'),
                         "a copy keeps no purge token (the connector's neutralize)")

    def test_paths(self):
        langs = patch.object(type(self.Cache), '_mtbg_lang_prefixes', autospec=True, return_value={'es'})
        langs.start()
        self.addCleanup(langs.stop)
        allowed = self.Cache._mtbg_path_allowed
        paths = ['/', '/es/', '/shop']
        self.assertTrue(allowed('/', paths))
        self.assertTrue(allowed('/es', paths))
        self.assertTrue(allowed('/es/', paths))
        self.assertTrue(allowed('/es/shop', paths), "each entry in every language (0.6.0)")
        self.assertFalse(allowed('/es/blog', paths))
        self.assertTrue(allowed('/es/blog/journal-1/a-post', ['/blog']))
        self.assertFalse(allowed('/esshop', paths))
        self.assertTrue(allowed('/shop/a-bike', paths))
        self.assertFalse(allowed('/shopx', paths))
        self.assertFalse(allowed('/contactus', paths))


@tagged('post_install', '-at_install', 'mtbg')
class TestEdgeCacheButtons(TransactionCase):
    """The settings' buttons, called as the web client calls an object button: on the settings record."""

    def setUp(self):
        super().setUp()
        _needs_connector(self)
        self.registry_enter_test_mode()
        offline = patch.object(edge_cache.requests, 'post', side_effect=AssertionError("Cloudflare called"))
        offline.start()
        self.addCleanup(offline.stop)

    def _settings_record(self):
        settings = self.env['res.config.settings'].create({})
        return self.env['res.config.settings'].browse(settings.id)

    def test_purge_log_button(self):
        action = self._settings_record().action_mtbg_edge_cache_log()
        self.assertEqual(action['res_model'], 'mtbg.edge.cache.log')

    def test_purge_now_button(self):
        answer = MagicMock(status_code=200)
        answer.json.return_value = {'success': True, 'errors': []}
        with patch.object(edge_cache.requests, 'post', return_value=answer) as post:
            _connector(self.env)
            settings = self._settings_record()
            result = settings.action_mtbg_edge_cache_purge()
        self.assertEqual(result['params']['type'], 'success')
        self.assertEqual(post.call_args.kwargs['json'], {'purge_everything': True})
        log = self.env['mtbg.edge.cache.log'].search([], limit=1)
        self.assertEqual((log.ok, log.reason), (True, 'Purged by hand'))
        answer.json.return_value = {'success': False, 'errors': [{'message': 'Bad token'}]}
        with patch.object(edge_cache.requests, 'post', return_value=answer), self.assertRaises(UserError):
            self._settings_record().action_mtbg_edge_cache_purge()

    def test_purge_now_from_the_log(self):
        """The purge log's own button (0.5.1), administrators only."""
        answer = MagicMock(status_code=200)
        answer.json.return_value = {'success': True, 'errors': []}
        _settings(self.env)
        with patch.object(edge_cache.requests, 'post', return_value=answer) as post:
            # as the web client calls a list's header button: with the selected rows' ids (none)
            result = call_kw(self.env['mtbg.edge.cache.log'], 'action_mtbg_purge_now', [[]], {})
        self.assertEqual((result['params']['type'], post.call_count), ('success', 1))
        arch = self.env.ref('mtbg_tours_edge_cache.edge_cache_log_list').arch
        self.assertIn('action_mtbg_purge_now', arch)
        user = new_test_user(self.env, 'edge_editor', groups='base.group_user,website.group_website_designer')
        with patch.object(edge_cache.requests, 'post', return_value=answer) as post, self.assertRaises(AccessError):
            self.env['mtbg.edge.cache.log'].with_user(user).action_mtbg_purge_now()
        self.assertFalse(post.called)


@tagged('post_install', '-at_install', 'mtbg')
class TestEdgeCacheRefill(TransactionCase):
    """0.3.0: the homepages (/ and /es) asked for again through Cloudflare, as an anonymous visitor without cookies:
    nightly and a minute after a purge; the other pages fill on their first visit."""

    def setUp(self):
        super().setUp()
        self.Cache = self.env['mtbg.edge.cache']
        self.env['website'].get_current_website().domain = 'https://www.example.com'
        _settings(self.env)
        sleep = patch.object(edge_cache.time, 'sleep')
        sleep.start()
        self.addCleanup(sleep.stop)

    def _get(self):
        answer = MagicMock(status_code=200, headers={'cf-cache-status': 'MISS'})
        return patch.object(edge_cache.requests, 'get', return_value=answer)

    def test_homepages_only(self):
        with self._get() as get:
            done = self.Cache._mtbg_warm()
        self.assertIn('/', done)
        self.assertFalse([p for p in done if p.startswith(('/blog', '/es/blog'))], "the homepages alone")
        if self.env['website'].get_current_website().language_ids.filtered(lambda l: l.url_code == 'es'):
            self.assertIn('/es', done, "the Spanish homepage at its own address (/es/ redirects to it)")
        url, kw = get.call_args_list[0][0][0], get.call_args_list[0][1]
        self.assertEqual(url, 'https://www.example.com/')
        self.assertEqual(kw['headers']['Accept-Language'], 'en')
        self.assertNotIn('Cookie', kw['headers'], "never as a visitor with a session, never logged in")
        self.assertNotIn('cookies', kw)
        self.assertFalse(kw['allow_redirects'])

    def test_only_where_the_cache_keeps_it(self):
        _settings(self.env, paths='/blog')
        with self._get() as get:
            self.assertEqual(self.Cache._mtbg_warm(), {})
        self.assertFalse(get.called)

    def test_off_asks_for_nothing(self):
        _settings(self.env, on=False)
        with self._get() as get:
            self.assertEqual(self.Cache._mtbg_warm(), {})
        self.assertFalse(get.called)

    def test_purge_brings_the_refill_forward_once(self):
        _needs_connector(self)
        self.env.ref('mtbg_tours_edge_cache.cron_edge_cache_warm_home').active = True
        Trigger = self.env['ir.cron.trigger']
        before = Trigger.search_count([])
        answer = MagicMock(status_code=200)
        answer.json.return_value = {'success': True}
        with patch.object(edge_cache.requests, 'post', return_value=answer):
            self.assertTrue(self.Cache._mtbg_purge('test'))
        self.assertEqual(Trigger.search_count([]) - before, 1)

    def test_switch_turns_the_jobs_on_and_off(self):
        answer = MagicMock(status_code=200)
        answer.json.return_value = {'success': True}
        crons = [self.env.ref('mtbg_tours_edge_cache.%s' % x) for x in self.Cache.JOBS]
        self.assertEqual(len(crons), 3, "the catch-up purge, the homepages' re-fill, the site notice's check (0.6.1)")
        _settings(self.env, on=False)
        with patch.object(edge_cache.requests, 'post', return_value=answer):
            self.env['res.config.settings'].create({'mtbg_edge_cache': True}).execute()
            self.assertTrue(all(c.active for c in crons))
            self.env['res.config.settings'].create({'mtbg_edge_cache': False}).execute()
            self.assertFalse(any(c.active for c in crons))


@tagged('post_install', '-at_install', 'mtbg')
class TestEdgeCacheJobsSurviveUpgrades(TransactionCase):
    """An upgrade never switches the cache's jobs off; 0.3.0's migration: a month in Cloudflare, the 0.2.0 pre-fill
    jobs and nightly purge gone, the homepages' re-fill nightly, every job on where the cache is on."""

    def _migrate(self, version):
        import importlib.util
        from odoo.modules.module import get_module_path
        path = os.path.join(get_module_path('mtbg_tours_edge_cache'), 'migrations', version, 'post-migrate.py')
        spec = importlib.util.spec_from_file_location('mtbg_edge_cache_%s' % version.replace('.', '_'), path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        migration.migrate(self.env.cr, '19.0.0.2.1')

    def test_upgrade_to_edit_only(self):
        from odoo.tools import convert_file
        _settings(self.env, ttl=3600)  # (as www before: the cache on, an hour)
        Cron = self.env['ir.cron'].sudo()
        old = {}
        for xmlid in ('cron_edge_cache_warm_all', 'cron_edge_cache_nightly'):  # (0.2.0's jobs, still there)
            old[xmlid] = Cron.create({'name': xmlid, 'model_id': self.env.ref('mtbg_tours_edge_cache.model_mtbg_edge_cache').id,
                                      'state': 'code', 'code': 'model._mtbg_warm()', 'active': True})
            self.env['ir.model.data'].create({'module': 'mtbg_tours_edge_cache', 'name': xmlid, 'model': 'ir.cron',
                                              'res_id': old[xmlid].id, 'noupdate': True})
        home = self.env.ref('mtbg_tours_edge_cache.cron_edge_cache_warm_home')
        home.write({'interval_number': 15, 'interval_type': 'minutes', 'active': False})
        self._migrate('19.0.0.3.0')
        self.assertEqual(self.env['ir.config_parameter'].sudo().get_param('mtbg_tours.edge_cache_ttl'), '2592000')
        self.assertFalse(any(job.exists() for job in old.values()), "0.2.0's pre-fill jobs and nightly purge gone")
        self.assertEqual((home.interval_number, home.interval_type), (1, 'days'))
        self.assertEqual((home.nextcall.hour, home.nextcall.minute), (6, 5), "00:05 in Guatemala")
        jobs = [self.env.ref('mtbg_tours_edge_cache.%s' % x) for x in self.env['mtbg.edge.cache'].JOBS]
        self.assertTrue(all(job.active for job in jobs))
        convert_file(self.env, 'mtbg_tours_edge_cache', 'data/cron.xml', {}, mode='update')
        self.assertTrue(all(job.active for job in jobs), "the job file loaded again: nothing switched off")

    def test_cache_off_jobs_off(self):
        _settings(self.env, on=False)
        jobs = [self.env.ref('mtbg_tours_edge_cache.%s' % x) for x in self.env['mtbg.edge.cache'].JOBS]
        for job in jobs:
            job.active = True
        self.env['mtbg.edge.cache']._mtbg_sync_jobs()
        self.assertFalse(any(job.active for job in jobs))


@tagged('post_install', '-at_install', 'mtbg')
class TestEdgeCacheFiles(HttpCase):
    """0.2.1: the site's script bundles and files carry no session cookie for a visitor without one, so Cloudflare keeps
    them; a private file stays private."""

    def test_bundle_and_file_without_cookie(self):
        page = self.url_open('/').text
        bundle = re.search(r'(/web/assets/[^"]+\.min\.js)', page).group(1)
        self.opener = Opener(self)  # (a new visitor: no cookie yet)
        response = self.url_open(bundle)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('session_id', response.headers.get('Set-Cookie', ''))
        attachment = self.env['ir.attachment'].create({'name': 'f.txt', 'raw': b'x', 'public': True})
        self.opener = Opener(self)
        response = self.url_open('/web/content/%d' % attachment.id)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('session_id', response.headers.get('Set-Cookie', ''))

    def test_private_file_stays_private(self):
        attachment = self.env['ir.attachment'].create({'name': 'p.pdf', 'raw': b'%PDF-1.4', 'public': False,
                                                       'res_model': 'res.partner', 'res_id': self.env.user.partner_id.id})
        self.assertEqual(self.url_open('/web/content/%d' % attachment.id).status_code, 404, "logged out: not found")
        self.authenticate('admin', 'admin')
        response = self.url_open('/web/content/%d' % attachment.id)
        self.assertEqual(response.status_code, 200)
        self.assertIn('private', response.headers.get('Cache-Control', ''))
        self.assertNotIn('public', response.headers.get('Cache-Control', ''))

    def test_declared_file_prefixes(self):
        """0.8.0: an extension's public file addresses (``_mtbg_edge_cache_static_prefixes``) get no session either."""
        cls = type(self.env['res.partner.category'])
        cls._mtbg_edge_cache_static_prefixes = ('/edge-files/',)
        self.env.registry._mtbg_edge_static_prefixes = None

        def undo():
            del cls._mtbg_edge_cache_static_prefixes
            self.env.registry._mtbg_edge_static_prefixes = None
        self.addCleanup(undo)
        with patch.object(edge_ir_http, 'request', MagicMock(env=self.env)):
            self.assertTrue(self.env['ir.http']._mtbg_no_session_path('/edge-files/a.jpg'))
            self.assertTrue(self.env['ir.http']._mtbg_no_session_path('/web/assets/x.js'))
            self.assertFalse(self.env['ir.http']._mtbg_no_session_path('/edge-filesx/a.jpg'))


@tagged('post_install', '-at_install', 'mtbg')
class TestLiveValues(HttpCase):
    """0.4.0: the live values' declarations (owner: "a table of declarations of any live pricing values that need to be
    excluded from cache global"): every page's live placeholders are declared, empty, and their values never in it."""

    def test_filled_and_declared(self):
        page = (b'<div><span class="mtbg-live" data-mtbg-live="tour:1:from" aria-busy="true"></span>'
                b'<div data-mtbg-live="tour:2:table"><span class="x"></span> </div>'
                b'<span data-mtbg-live="departure:3:spots"><b>4</b> spaces left</span></div>')
        self.assertEqual(live_values.filled_hooks(page), [('departure:3:spots', '4 spaces left')])
        emptied, taken = live_values.empty_filled(page)
        self.assertEqual(taken, [('departure:3:spots', '4 spaces left')])
        self.assertIn(b'<span data-mtbg-live="departure:3:spots"></span></div>', emptied)
        self.assertIn(b'<div data-mtbg-live="tour:2:table"><span class="x"></span> </div>', emptied, "the rest as is")
        self.assertEqual(live_values.filled_hooks(emptied), [])
        nested = b'<div data-mtbg-live="tour:1:board"><p data-mtbg-live="tour:1:from">$9</p></div><i>after</i>'
        self.assertEqual(live_values.empty_filled(nested)[0], b'<div data-mtbg-live="tour:1:board"></div><i>after</i>')
        with _declaring(self.env, (('thing:<id>:from', "A thing's price", "Precio de una cosa", 'price'),
                                   ('things=<id>', "Things", "Cosas", 'form'))):
            self.assertTrue(live_values.declared(self.env, 'thing:12:from'))
            self.assertTrue(live_values.declared(self.env, 'things'))
            self.assertFalse(live_values.declared(self.env, 'thing:12:secret_margin'))
            module = getattr(type(self.env['res.partner']), '_module', None) or ''
            self.assertIn(('thing:<id>:from', "A thing's price", "Precio de una cosa", module, 'price'),
                          live_values.declarations(self.env), "the extension: the declaring class's module")
        self.assertFalse(live_values.declared(self.env, 'thing:12:from'), "only while declared")

    def test_filled_page_emptied_and_cached(self):
        """0.6.0: a template saved in the website editor with the prices its script had filled in (www, 2026-11-03:
        every tour page showed the same day-old prices, and was not cached): emptied, the page cached."""
        _settings(self.env)
        self.env['website.page'].create({
            'url': '/edge-baked', 'is_published': True, 'type': 'qweb',
            'name': 'Edge baked', 'key': 'mtbg_tours_edge_cache.edge_baked',
            'arch': '<t t-call="website.layout"><div id="wrap"><p class="edge-keep">Kept</p>'
                    '<div class="mtbg-live mtbg-live--done" data-mtbg-live="tour:1:from">'
                    '<p data-base="From USD $78 /pp">From USD $78 /pp</p></div></div></t>'})
        self.opener = Opener(self)
        with self.assertLogs(edge_ir_http.__name__, 'WARNING') as logs:
            response = self.url_open('/edge-baked')
        self.assertIn('tour:1:from "From USD $78 /pp"', '\n'.join(logs.output))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('$78', response.text)
        self.assertIn('data-mtbg-live="tour:1:from"></div>', response.text)
        self.assertIn('edge-keep', response.text)
        self.assertIn('s-maxage=300', response.headers.get('Cache-Control', ''))
        self.assertFalse(response.headers.get('Set-Cookie'))

    def test_settings_table(self):
        with _declaring(self.env, (('thing:<id>:from', "A thing's price", "Precio de una cosa", 'price'),)):
            table = self.env['res.config.settings'].create({}).mtbg_edge_cache_live_values
            self.assertIn('thing:&lt;id&gt;:from', str(table))
            self.assertIn("A thing&#39;s price", str(table))


@tagged('post_install', '-at_install', 'mtbg')
class TestEdgeCacheSiteNotice(TransactionCase):
    """0.6.1 (owner: "yes when banner changes"): the cache is emptied when the site notice changes by itself, only
    then."""

    def setUp(self):
        super().setUp()
        _needs_connector(self)
        _settings(self.env)
        self.Cache = self.env['mtbg.edge.cache']
        self.ICP = self.env['ir.config_parameter'].sudo()
        self.ICP.set_param(edge_cache.BANNER_KEY, '')
        answer = MagicMock(status_code=200)
        answer.json.return_value = {'success': True, 'errors': []}
        post = patch.object(edge_cache.requests, 'post', return_value=answer)
        self.post = post.start()
        self.addCleanup(post.stop)

    def _signature(self, value):
        return patch.object(type(self.Cache), '_mtbg_banner_signature', autospec=True, return_value=value)

    def test_purged_once_when_it_changes(self):
        """A change is noted as an edit's (the same purge after commit, spacing and catch-up job); the purge keeps the
        new fingerprint, so the next checks note nothing."""
        changed = patch.object(type(self.Cache), '_mtbg_changed', autospec=True)
        noted = changed.start()
        self.addCleanup(changed.stop)
        with self._signature('a'):
            self.assertFalse(self.Cache._mtbg_banner_check(), "the first look: what the pages carry")
            self.assertFalse(self.Cache._mtbg_banner_check(), "the same notice")
        self.assertFalse(noted.called)
        with self._signature('b'):
            self.assertTrue(self.Cache._mtbg_banner_check())
            self.assertEqual(noted.call_count, 1)
            self.Cache._mtbg_purge('Changes saved')  # (what the noted change brings, after commit)
            self.assertFalse(self.Cache._mtbg_banner_check(), "once")
        self.assertEqual(noted.call_count, 1)
        self.assertEqual(self.ICP.get_param(edge_cache.BANNER_KEY), 'b')

    def test_a_refused_purge_is_tried_again(self):
        changed = patch.object(type(self.Cache), '_mtbg_changed', autospec=True)
        noted = changed.start()
        self.addCleanup(changed.stop)
        with self._signature('a'):
            self.Cache._mtbg_banner_check()
        self.post.return_value.json.return_value = {'success': False, 'errors': [{'message': 'busy'}]}
        with self._signature('b'):
            self.Cache._mtbg_banner_check()
            self.Cache._mtbg_purge('Changes saved')  # (refused: the fingerprint stays the old one)
            self.assertTrue(self.Cache._mtbg_banner_check(), "still to do")
        self.assertEqual(noted.call_count, 2)

    def test_the_change_goes_through_the_purge_queue(self):
        with self._signature('a'):
            self.Cache._mtbg_banner_check()
        Change = self.env['mtbg.edge.cache.change'].sudo()
        before = Change.search_count([])
        # (the job runs in a transaction of its own; here the settings' saving has noted one already)
        self.env.cr.postcommit.data.pop('mtbg_edge_cache', None)
        with self._signature('b'):
            self.Cache._mtbg_banner_check()
        self.assertEqual(Change.search_count([]), before + 1, "a change row, as for an edit")
        self.assertFalse(self.post.called, "the purge waits for the commit")
        with self._signature('b'):
            self.assertTrue(self.Cache._mtbg_purge_pending())
        self.assertEqual(self.post.call_count, 1)

    def test_off_and_without_site_notice(self):
        _settings(self.env, on=False)
        with self._signature('z'):
            self.assertFalse(self.Cache._mtbg_banner_check())
        self.assertFalse(self.post.called)
        _settings(self.env)
        with self._signature(''):
            self.assertFalse(self.Cache._mtbg_banner_check())
        self.assertFalse(self.post.called)

    def test_declared_fingerprints(self):
        """0.8.0: each extension's ``_mtbg_edge_cache_fingerprint()``; one alone as it is, several hashed together."""
        cls = type(self.env['res.partner.category'])
        cls._mtbg_edge_cache_fingerprint = lambda rec: 'one'
        self.addCleanup(delattr, cls, '_mtbg_edge_cache_fingerprint')
        others = sorted(n for n in edge_sources.declared(self.env, '_mtbg_edge_cache_fingerprint')
                        if n != 'res.partner.category')
        if not others:
            self.assertEqual(self.Cache._mtbg_banner_signature(), 'one')
        second = type(self.env['res.partner.industry'])
        second._mtbg_edge_cache_fingerprint = lambda rec: 'two'
        self.addCleanup(delattr, second, '_mtbg_edge_cache_fingerprint')
        both = self.Cache._mtbg_banner_signature()
        self.assertEqual(len(both), 40)
        second._mtbg_edge_cache_fingerprint = lambda rec: 'three'
        self.assertNotEqual(self.Cache._mtbg_banner_signature(), both)

    def test_job_with_the_cache(self):
        cron = self.env.ref('mtbg_tours_edge_cache.cron_edge_cache_banner')
        self.Cache._mtbg_sync_jobs()
        self.assertTrue(cron.active)
        _settings(self.env, on=False)
        self.Cache._mtbg_sync_jobs()
        self.assertFalse(cron.active)


@tagged('post_install', '-at_install', 'mtbg')
class TestEdgeCacheDeclaredSources(TransactionCase):
    """0.5.0 / 0.8.0: the models an extension declares (``_mtbg_edge_cache_watch``) and the blog empty the cache,
    wrapped once, where installed; the parameter prefixes declared too."""

    def setUp(self):
        super().setUp()
        _settings(self.env)
        changed = patch.object(type(self.env['mtbg.edge.cache']), '_mtbg_changed', autospec=True)
        self.calls = changed.start()
        self.addCleanup(changed.stop)

    def test_optional_models_watched_where_present(self):
        name = 'res.partner.category'  # (a model standing in for an optional one)
        self.addCleanup(edge_sources.unwatch, self.env, [name])
        edge_sources.watch_softly(self.env, {'mtbg.no.such.model': None, name: {'color'}})
        edge_sources.watch_softly(self.env, {name: {'color'}})  # (twice: wrapped once)
        tag = self.env[name].create({'name': 'Edge tag'})
        self.assertTrue(self.calls.called, "created")
        self.calls.reset_mock()
        tag.write({'name': 'Edge tag 2'})
        self.assertFalse(self.calls.called, "a field not watched")
        tag.write({'color': 3})
        self.assertTrue(self.calls.called, "a watched field")
        self.calls.reset_mock()
        tag.unlink()
        self.assertTrue(self.calls.called, "deleted")
        edge_sources.unwatch(self.env, [name])
        self.calls.reset_mock()
        self.env[name].create({'name': 'Edge tag 3'})
        self.assertFalse(self.calls.called, "unwrapped")

    def test_a_failing_note_never_breaks_the_save(self):
        name = 'res.partner.category'
        self.addCleanup(edge_sources.unwatch, self.env, [name])
        edge_sources.watch_softly(self.env, {name: None})
        self.calls.side_effect = RuntimeError("table locked")
        with self.assertLogs(edge_sources.__name__, 'ERROR'):
            tag = self.env[name].create({'name': 'Safe tag'})
        self.assertTrue(tag.exists())

    def test_declared_models_watched(self):
        for name, watched in edge_sources.sources(self.env).items():
            if name in self.env:
                self.assertTrue(type(self.env[name]).__dict__.get('_mtbg_edge_soft'), name)

    def test_a_declaration(self):
        name = 'res.partner.category'
        cls = type(self.env[name])
        cls._mtbg_edge_cache_watch = {'color'}
        self.addCleanup(edge_sources.unwatch, self.env, [name])
        self.addCleanup(delattr, cls, '_mtbg_edge_cache_watch')
        self.assertEqual(edge_sources.sources(self.env)[name], {'color'})
        self.assertIn('blog.post', edge_sources.sources(self.env), "the blog: Odoo's own, listed here")
        edge_sources.watch_softly(self.env)
        tag = self.env[name].create({'name': 'Declared tag'})
        self.assertTrue(self.calls.called)
        self.calls.reset_mock()
        tag.write({'name': 'Declared tag 2'})
        self.assertFalse(self.calls.called, "a field not declared")
        tag.write({'color': 2})
        self.assertTrue(self.calls.called)
        self.calls.reset_mock()
        cls._mtbg_edge_cache_watch = True
        edge_sources.unwatch(self.env, [name])
        edge_sources.watch_softly(self.env)
        self.calls.reset_mock()
        tag._update_field_translations('name', {self.env.lang or 'en_US': 'Declared tag 3'})
        self.assertTrue(self.calls.called, "a text translated, not through write")

    def test_declared_param_prefixes(self):
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('edge_test.colour', 'red')
        self.assertFalse(self.calls.called, "no one declared it")
        ICP.set_param('mtbg_tours.edge_cache_ttl', '301')
        self.assertTrue(self.calls.called, "this module's own settings")
        self.calls.reset_mock()
        cls = type(self.env['res.partner.category'])
        cls._mtbg_edge_cache_param_prefixes = ('edge_test.',)
        self.env.registry._mtbg_edge_param_prefixes = None

        def undo():
            del cls._mtbg_edge_cache_param_prefixes
            self.env.registry._mtbg_edge_param_prefixes = None
        self.addCleanup(undo)
        ICP.set_param('edge_test.colour', 'blue')
        self.assertTrue(self.calls.called)

    def test_paths_migration_050(self):
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('mtbg_tours.edge_cache_paths', '/ /es/ /tours /es/tours')
        import importlib.util
        from odoo.modules.module import get_module_path
        path = os.path.join(get_module_path('mtbg_tours_edge_cache'), 'migrations', '19.0.0.5.0', 'post-migrate.py')
        spec = importlib.util.spec_from_file_location('mtbg_edge_cache_050_post', path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        migration.migrate(self.env.cr, '19.0.0.4.0')
        self.assertEqual(ICP.get_param('mtbg_tours.edge_cache_paths'), '/ /es/ /tours /es/tours /hotels /es/hotels')
        self.assertTrue(self.env['mtbg.edge.cache']._mtbg_path_allowed('/hotels/casa-santo-domingo'))
        self.assertTrue(self.env['mtbg.edge.cache']._mtbg_path_allowed('/es/hotels/casa-santo-domingo'))


@tagged('post_install', '-at_install', 'mtbg')
class TestHoldingPage(TransactionCase):
    """0.6.7 (owner: "is there anyway to keep the site live while we do backend updates?"): the holding page nginx
    serves while Odoo restarts or updates (deploy/), and the kept pages' stale-if-error."""

    DEPLOY = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'deploy')

    def _read(self, name):
        with open(os.path.join(self.DEPLOY, name), encoding='utf-8') as handle:
            return handle.read()

    def test_page_stands_alone(self):
        page = self._read('updating.html')
        self.assertLess(len(page.encode()), 20 * 1024, "small: nginx sends it as is")
        self.assertIn("We're updating the site", page)
        self.assertIn('Estamos actualizando el sitio', page)
        self.assertIn('about 2 minutes', page)
        self.assertIn('<header><span class="site">', page, "a plain header: no business name or logo shipped")
        self.assertIn('noindex', page)
        # nothing from Odoo or anywhere else: Odoo may be down when it shows
        self.assertFalse(re.findall(r'''(?:src|href)\s*=\s*["'](?!#|["'])''', page), "no file loaded")
        self.assertNotIn('@import', page)
        self.assertNotIn('url(', page)

    def test_nginx_snippet(self):
        conf = self._read('nginx-updating.conf')
        self.assertIn('error_page 502 503 504 =503 /mtbg-updating.html;', conf)
        self.assertIn('add_header Retry-After 120 always;', conf)
        self.assertIn('internal;', conf)
        self.assertIn('proxy_intercept_errors on;', conf)

    def test_stale_if_error_a_week(self):
        from odoo.addons.mtbg_tours_edge_cache.models import ir_http
        self.assertEqual(ir_http.STALE_IF_ERROR, 604800)


@tagged('post_install', '-at_install', 'mtbg')
class TestEdgeCacheConnector(TransactionCase):
    """0.7.0: the purge goes through Cloudflare Connector; the old zone and token move into it."""

    def _migrate(self):
        import importlib.util
        path = os.path.join(os.path.dirname(edge_cache.__file__), '..', 'migrations', '19.0.0.7.0', 'post-migrate.py')
        spec = importlib.util.spec_from_file_location('ec_070_post', path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.migrate(self.env.cr, '19.0.0.6.8')
        self.env.registry.clear_cache('stable')

    def _p(self, key):
        return self.env['ir.config_parameter'].sudo().get_param(key)

    def test_migration_moves_zone_and_token(self):
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('cloudflare_connector.zone_id', False)
        ICP.set_param('cloudflare_connector.api_token', False)
        ICP.set_param('mtbg_tours.edge_cache_zone', 'OLDZONE')
        ICP.set_param('mtbg_tours.edge_cache_token', 'OLDTOKEN')
        self._migrate()
        self.assertEqual(self._p('cloudflare_connector.zone_id'), 'OLDZONE')
        self.assertEqual(self._p('cloudflare_connector.api_token'), 'OLDTOKEN')
        self.assertFalse(self._p('mtbg_tours.edge_cache_token'), "the old secret is gone")
        self.assertFalse(self._p('mtbg_tours.edge_cache_zone'))

    def test_migration_keeps_the_connectors_own(self):
        _connector(self.env, 'NEWZONE', 'NEWTOKEN')
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('mtbg_tours.edge_cache_zone', 'OLDZONE')
        ICP.set_param('mtbg_tours.edge_cache_token', 'OLDTOKEN')
        self._migrate()
        self.assertEqual((self._p('cloudflare_connector.zone_id'), self._p('cloudflare_connector.api_token')),
                         ('NEWZONE', 'NEWTOKEN'))
        self.assertFalse(self._p('mtbg_tours.edge_cache_token'))

    def test_purge_uses_the_connector(self):
        _needs_connector(self)
        _connector(self.env)
        answer = MagicMock(status_code=200)
        answer.json.return_value = {'success': True, 'errors': []}
        with patch.object(edge_cache.requests, 'post', return_value=answer) as post, \
                patch.object(type(self.env['cloudflare.api']), 'purge', autospec=True,
                             side_effect=lambda rec, **kw: {'ok': True, 'requests': 1, 'error': ''}) as purge:
            self.assertTrue(self.env['mtbg.edge.cache']._mtbg_purge('test'))
        self.assertEqual(purge.call_args.kwargs, {'everything': True})
        self.assertFalse(post.called, "no Cloudflare call of its own")

    def test_not_set_up_is_logged(self):
        _connector(self.env, '', '')
        self.assertFalse(self.env['mtbg.edge.cache']._mtbg_purge('test'))
        log = self.env['mtbg.edge.cache.log'].sudo().search([], limit=1)
        self.assertIn('Set up Cloudflare', log.message)

    def test_settings_show_the_connection(self):
        _needs_connector(self)
        _connector(self.env)
        self.env['ir.config_parameter'].sudo().set_param('cloudflare_connector.zone_name', 'example.com')
        settings = self.env['res.config.settings'].create({})
        self.assertIn('example.com', settings.mtbg_edge_cache_connection)
