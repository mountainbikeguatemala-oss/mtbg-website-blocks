import html as html_lib
import json
import re
from unittest.mock import patch

from odoo.tests import HttpCase, tagged
from odoo.tests.common import Opener

from odoo.addons.mtbg_tours_visit.controllers import visit

CF = {'CF-IPCountry': 'GT', 'cf-ipcity': 'Antigua Guatemala', 'cf-region': 'Sacatepequez',
      'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36'}
# what a visit records (Odoo's, and Communication Flows' when installed)
VISITOR_FIELDS = ('country_id', 'lang_id', 'website_id', 'partner_id', 'cfd_city', 'cfd_region', 'cfd_place',
                  'cfd_device', 'cfd_bot')
TRACK_FIELDS = ('url', 'page_id', 'cfd_title', 'cfd_lang')


@tagged('post_install', '-at_install', 'mtbg')
class TestVisitByScript(HttpCase):
    """An anonymous page view recorded by the page's script is the one Odoo records while building the page."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.set_registry_readonly_mode(False)  # (as Odoo's visitor tests: the page's request records the visitor)
        cls.ICP = cls.env['ir.config_parameter'].sudo()
        cls.page = cls.env['website.page'].search([('url', '=', '/contactus')], limit=1)
        cls.page.view_id.track = True
        cls.Visitor = cls.env['website.visitor'].sudo()
        cls.Track = cls.env['website.track'].sudo()

    def _switch(self, on):
        self.ICP.set_param('mtbg_tours.visit_by_script', 'True' if on else 'False')

    def _browser(self, agent=None):
        """A visitor's own browser: its own cookies (session), Cloudflare's headers."""
        browser = Opener(self)
        browser.headers.update(dict(CF, **({'User-Agent': agent} if agent else {})))
        return browser

    def _open(self, browser, path, **kw):
        self.opener = browser
        return self.url_open(path, timeout=30, **kw)

    def _get(self, browser, path):
        response = self._open(browser, path)
        self.assertEqual(response.status_code, 200)
        return response

    def _beacon(self, browser, path, page_id=0, title='Contact us | My Website', **extra):
        body = dict({'url': self.base_url() + path, 'page_id': page_id, 'title': title}, **extra)
        return self._open(browser, '/mtbg/visit', data=json.dumps(body), headers={'Content-Type': 'application/json'})

    def _recorded(self, url):
        track = self.Track.search([('url', '=', url)], order='id desc', limit=1)
        visitor = track.visitor_id
        keep = lambda record, names: {n: record[n] for n in names if n in record._fields}  # noqa: E731
        return keep(visitor, VISITOR_FIELDS), keep(track, TRACK_FIELDS), visitor

    def test_same_as_while_built(self):
        path = '/contactus?utm_source=speedtest'
        url = self.base_url() + path
        self._switch(False)
        self._get(self._browser(), path)
        before = self._recorded(url)
        self.assertTrue(before[2], "recorded while the page is built (switch off)")
        self.Track.search([('url', '=', url)]).unlink()

        self._switch(True)
        browser = self._browser()
        html = self._get(browser, path).text
        self.assertIn('name="mtbg-visit"', html)
        self.assertIn(f'data-page="{self.page.id}"', html)
        self.assertFalse(self.Track.search([('url', '=', url)]), "not recorded while the page is built")
        title = html_lib.unescape(re.search(r'<title>(.*?)</title>', html, re.S).group(1).strip())  # document.title
        answer = self._beacon(browser, path, page_id=self.page.id, title=title)
        self.assertEqual(answer.status_code, 204)
        after = self._recorded(url)
        self.assertTrue(after[2], "recorded by the script")
        self.assertEqual(after[0], before[0], "the same visitor details")
        self.assertEqual(after[1], before[1], "the same page view")
        self.assertEqual(browser.cookies.get('odoo_utm_source'), 'speedtest', "the marketing cookie")
        # a page that set no cookie (cached, phase 3): the script's visit sets it
        cached = self._browser()
        answer = self._beacon(cached, path, page_id=self.page.id, title=title)
        self.assertEqual(answer.cookies.get('odoo_utm_source'), 'speedtest', "set by the visit when the page did not")

    def test_same_visitor_for_the_session(self):
        self._switch(True)
        browser = self._browser()
        self._get(browser, '/contactus')
        self._beacon(browser, '/contactus', page_id=self.page.id)
        self._beacon(browser, '/contactus?again=1', page_id=self.page.id)
        first = self._recorded(self.base_url() + '/contactus')[2]
        second = self._recorded(self.base_url() + '/contactus?again=1')[2]
        self.assertTrue(first)
        self.assertEqual(first, second, "one visitor for the browser's session")

    def test_refused(self):
        self._switch(True)
        browser = self._browser()
        self._get(browser, '/contactus')
        count = self.Track.search_count([])
        self._beacon(browser, '/contactus', page_id=self.page.id, url='https://elsewhere.example/contactus')
        self._beacon(self._browser('Googlebot/2.1 (+http://www.google.com/bot.html)'), '/contactus',
                     page_id=self.page.id)
        self.assertEqual(self._open(browser, '/mtbg/visit', data='not json').status_code, 204)
        self.assertEqual(self.Track.search_count([]), count, "another site's address, a bot, garbage: nothing")
        # headless browsers and page tools: not people
        self._beacon(self._browser('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 HeadlessChrome/130.0 '
                                   'Safari/537.36'), '/contactus', page_id=self.page.id)
        self.assertEqual(self.Track.search_count([]), count)

    def test_refusals_logged_with_their_reason(self):
        self._switch(True)
        with self.assertLogs('odoo.addons.mtbg_tours_visit.controllers.visit', level='INFO') as logs:
            self._beacon(self._browser('Googlebot/2.1 (+http://www.google.com/bot.html)'), '/contactus',
                         page_id=self.page.id)
            self._beacon(self._browser(), '/contactus', url='https://elsewhere.example/contactus')
        self.assertEqual([line.split(':', 2)[2] for line in logs.output],
                         ['visit refused: crawler (bot)', 'visit refused: another address (elsewhere.example)'])

    def test_apps_browsers_are_people(self):
        """Links opened inside Instagram, Facebook, WhatsApp or Pinterest open in the app's own browser, whose name
        Odoo's bot list matches; the page ran in it, so its visit is a person's (0.1.2)."""
        self._switch(True)
        agents = {
            'instagram': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like '
                         'Gecko) Mobile/22B83 Instagram 356.0.0.24.98 (iPhone15,2; iOS 18_1; en_US; en)',
            'facebook': 'Mozilla/5.0 (Linux; Android 14; SM-S911B) AppleWebKit/537.36 (KHTML, like Gecko) '
                        'Version/4.0 Chrome/130.0 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/485.0.0.40.80;]',
            'whatsapp': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like '
                        'Gecko) Mobile/15E148 WhatsApp/24.21.78',
            'pinterest': 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile '
                         'Safari/537.36 [Pinterest/Android]',
        }
        for name, agent in agents.items():
            browser = self._browser(agent)
            self._get(browser, f'/contactus?app={name}')
            self.assertEqual(self._beacon(browser, f'/contactus?app={name}', page_id=self.page.id).status_code, 204)
            self.assertTrue(self._recorded(self.base_url() + f'/contactus?app={name}')[2], f"{name}'s browser")

    def test_logged_in_and_switch_off_as_before(self):
        self._switch(True)
        self.opener = Opener(self)
        self.authenticate('admin', 'admin')
        html = self.url_open('/contactus').text
        self.assertNotIn('name="mtbg-visit"', html, "logged-in users are recorded while the page is built")
        self._switch(False)
        self.assertNotIn('name="mtbg-visit"', self._get(self._browser(), '/contactus').text)

    def test_browser_sends_the_visit(self):
        """In a real browser, the page's script records the view once the page has loaded."""
        self._switch(True)
        url = self.base_url() + '/contactus?from=browser'
        # (the tests' browser is a headless Chrome, refused as a crawler on the website: here it is a person)
        people = tuple(name for name in visit.CRAWLERS if name != 'headlesschrome')
        with patch.object(visit, 'CRAWLERS', people):
            self.browser_js('/contactus?from=browser', "setTimeout(() => console.log('test successful'), 1500)",
                            ready="document.readyState === 'complete'", login=None)
        track = self.Track.search([('url', '=', url)])
        self.assertEqual(len(track), 1, "recorded once, by the script")
        if 'cfd_title' in track._fields:
            self.assertTrue(track.cfd_title, "with the page's title")

    def test_referrer_handed_on(self):
        """0.1.4 (owner OK, 2026-11-10): the page's referrer, for Visit Analytics' source (cfd_website_visitors 1.3.0):
        request.cfd_referrer while the visit is recorded, a string only, at most 2048 characters."""
        self._switch(True)
        seen = []
        Visitor = type(self.env['website.visitor'])
        original = Visitor._handle_webpage_dispatch

        def spy(this, page):
            from odoo.http import request
            seen.append(getattr(request, 'cfd_referrer', None))
            return original(this, page)
        with patch.object(Visitor, '_handle_webpage_dispatch', spy):
            browser = self._browser()
            self._beacon(browser, '/contactus', page_id=self.page.id, referrer='https://www.google.com/')
            self._beacon(browser, '/contactus?r=2', page_id=self.page.id, referrer='https://x.example/' + 'a' * 3000)
            self._beacon(browser, '/contactus?r=3', page_id=self.page.id, referrer=['not', 'a', 'string'])
            self._beacon(browser, '/contactus?r=4', page_id=self.page.id)
        self.assertEqual(seen[0], 'https://www.google.com/')
        self.assertEqual(len(seen[1]), 2048)
        self.assertIsNone(seen[2], "not a string: none")
        self.assertIsNone(seen[3], "no referrer sent (a page cached before 0.1.4): none")

    def test_beacon_sends_the_referrer(self):
        self._switch(True)
        html = self._get(self._browser(), '/contactus').text
        self.assertIn('referrer: document.referrer', html)
