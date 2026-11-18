"""The nightly speed log (page speed 0.7.0, owner 2026-11-07: "This computer is not reliable source for nightly data we
should do it from our own www server"; "we have 20+ tour pages that need optimization"). Every night the site asks
Google PageSpeed Insights (Lighthouse, run on Google's computers) for its homepage, its Spanish homepage and every
page under /tours (tours, rentals, categories), on a phone and on a computer, and keeps the scores here
(Website › Reporting › Speed log), the pages over the limits flagged: LCP over 4 s on a phone, 2.5 s on a computer.

It measures through the Google connector (0.7.4, owner 2026-11-08: "the new pagespeed should get its api info from our
main google connector there is no reason for it to have its own google link"): its "PageSpeed Insights" app and the
connector's server API key (Settings › Google). Asked softly: without the connector, or with the app off, the log
says so and does nothing. A few pages per run, a minute apart (the site's workers stay free), each night's rows kept
180 days.

0.10.0 (owner 2026-11-18: page speed on the shop site too, which has two websites): each website is measured on its own
(its address, its homepages, its pages under /tours where it has any), each row names its website, and the dashboard
shows one website at a time. The websites measured: those with an address (Website › Settings › Domain), and the
default website at the site's address when it has none."""
from datetime import datetime, time, timedelta
import html
import json
import logging
import re
from statistics import median
from urllib.parse import urlsplit

import pytz
import requests

from odoo import api, fields, models
from odoo.exceptions import AccessError
from odoo.fields import Domain
from odoo.modules import module as odoo_module

_logger = logging.getLogger(__name__)

PARAM_ON = 'mtbg_page_speed.log'          # (not mtbg_tours.*: that would empty Cloudflare's cache)
OLD_PARAM_KEY = 'mtbg_page_speed.psi_key'  # (0.7.0-0.7.3's own key: moved to the connector by 0.7.4's migration)
BATCH = 4
NIGHT = time(2, 30)                       # the speed log's hour, in the business's time zone (0.7.5)
TZ_PARAM = 'mtbg_tours.operator_tz'       # Core's Operator Timezone (the site's global time zone)
KEEP_DAYS = 180
LIMITS = {'mobile': 4.0, 'desktop': 2.5}  # LCP seconds over which a page is slow
# 0.8.0 (owner, 2026-11-16): steadier numbers. A page Google could not measure is tried again later in the night (two
# more times) before it is "Not measured"; a phone page slow on its first run is measured twice more and keeps the
# median; a page is "Over the limit" only when it is slow two nights in a row (each night's own values stay visible).
REFUSED = re.compile(r'\berror 40[0-3]\b', re.I)  # (the connector's "Google error 403: ...": not tried again)
TRIES = 3                                 # a page's measurements before "Not measured" (the first and two more)
RETRY_AFTER = timedelta(minutes=20)       # ... a while apart (Google's hiccups pass)
PHONE_RUNS = 3                            # a slow phone page: its median of three
RUN_AFTER = timedelta(minutes=10)         # ... the extra runs once the night's first pass has moved on
WINDOW = timedelta(hours=4)               # the night's measuring ends this long after its rows were made
# Lighthouse's LCP breakdown: its parts, as Lighthouse 13 (lcp-breakdown-insight) and older ones name them
PHASES = {'timeToFirstByte': 'lcp_ttfb', 'TTFB': 'lcp_ttfb',
          'resourceLoadDelay': 'lcp_load_delay', 'Load Delay': 'lcp_load_delay',
          'resourceLoadDuration': 'lcp_load_time', 'Load Time': 'lcp_load_time',
          'elementRenderDelay': 'lcp_render_delay', 'Render Delay': 'lcp_render_delay'}


TITLE = re.compile(rb'<title[^>]*>(.*?)</title>', re.I | re.S)
TITLE_BYTES = 256 * 1024                  # a page's <title> is in its head: never more than this read
TITLE_TIMEOUT = 6
TITLES_PER_RUN = 10                       # pages without a title fetched per run of the job (0.9.0's backfill)
# 0.9.0, the dashboard: the stats drawn over time, and their lines (Lighthouse's "good" marks; LCP the log's limits)
STATS = ('score', 'lcp', 'fcp', 'tbt', 'cls', 'ttfb', 'weight_kb')
MARKS = {'score': 90, 'lcp': LIMITS, 'fcp': 1.8, 'tbt': 200, 'cls': 0.1, 'ttfb': 800, 'weight_kb': 1600}
CAUSES = ('lcp_ttfb', 'lcp_load_delay', 'lcp_load_time', 'lcp_render_delay')
WORST = 5
# 0.9.1 (owner 2026-11-17): the breakdown's parts (timed on Google's unslowed load) summing to less than this share of
# the LCP (Google's slowed-down estimate) do not explain it: the card says so and names the LCP element instead of a
# small part ("render delay 1.3 s" for a 9.6 s LCP whose element was the header's logo)
EXPLAINS = 0.5


def _on(value):
    return value not in (False, None, '', '0', 'False', 'false')


def _path(url):
    """An address without its site's: '/tours/a-ride' (the homepage '/')."""
    if not url:
        return ''
    parts = urlsplit(url)
    return (parts.path or '/') + ('?' + parts.query if parts.query else '')


def _round(stat, value):
    if value is None:
        return None
    value = float(value)
    return round(value, 3) if stat == 'cls' else round(value, 2) if stat in ('lcp', 'fcp') else round(value)


class MtbgPageSpeedLog(models.Model):
    _name = 'mtbg.page.speed.log'
    _inherit = ['mtbg.sidebar.mixin']
    _description = 'Page speed: nightly speed log'
    _order = 'run_date desc, strategy, lcp desc, id'
    _rec_name = 'url'

    run_date = fields.Date('Night', required=True, index=True, readonly=True)
    url = fields.Char('Page', required=True, readonly=True)
    strategy = fields.Selection([('mobile', 'Phone'), ('desktop', 'Computer')], required=True, readonly=True)
    state = fields.Selection([('pending', 'Waiting'), ('done', 'Measured'), ('error', 'Not measured')],
                             default='pending', required=True, readonly=True)
    score = fields.Integer('Score', readonly=True, aggregator='avg', help="Lighthouse performance score (0-100)")
    lcp = fields.Float('LCP (s)', digits=(4, 1), readonly=True, aggregator='avg',
                       help="Largest Contentful Paint: when the main picture or text shows")
    fcp = fields.Float('First paint (s)', digits=(4, 1), readonly=True, aggregator='avg')
    tbt = fields.Integer('Blocking (ms)', readonly=True, aggregator='avg', help="Total Blocking Time")
    cls = fields.Float('Layout shift', digits=(4, 3), readonly=True, aggregator='avg')
    speed_index = fields.Float('Speed index (s)', digits=(4, 1), readonly=True, aggregator='avg')
    ttfb = fields.Integer('Server answer (ms)', readonly=True, aggregator='avg')
    weight_kb = fields.Integer('Page weight (KB)', readonly=True, aggregator='avg')
    lcp_element = fields.Char('LCP element', readonly=True)
    # 0.9.0 (owner, 2026-11-17: "Include in the table the page title"): the page's name, kept on each night's row
    page_title = fields.Char('Page title', readonly=True,
                             help="The page's title (its website page's name, else its <title>), as it was that night")
    path = fields.Char('Path', compute='_compute_path', help="The page's address without the site's")
    lcp_selector = fields.Char('LCP element (selector)', readonly=True,
                               help="Where the LCP element is in the page, as Lighthouse names it")
    # 0.8.0: why the LCP took its time (Lighthouse's breakdown, in ms): the server's answer, the wait before the
    # picture was asked for, its download, and the wait between its arrival and its paint
    lcp_ttfb = fields.Integer('LCP: server (ms)', readonly=True, aggregator='avg', help="Time to first byte")
    lcp_load_delay = fields.Integer('LCP: load delay (ms)', readonly=True, aggregator='avg',
                                    help="From the first byte until the browser starts fetching the LCP picture")
    lcp_load_time = fields.Integer('LCP: load time (ms)', readonly=True, aggregator='avg',
                                   help="The LCP picture's download")
    lcp_render_delay = fields.Integer('LCP: render delay (ms)', readonly=True, aggregator='avg',
                                      help="From the picture's arrival (or the first byte, for text) until it shows")
    lcp_runs = fields.Char('LCP runs (s)', readonly=True,
                           help="Each run's LCP, when a slow phone page was measured more than once (the row keeps "
                                "the median run)")
    runs_data = fields.Text(readonly=True)    # (the runs' values, JSON: the median picked from them)
    tries = fields.Integer(readonly=True, default=0)  # (measurements Google could not finish)
    next_try = fields.Datetime(readonly=True)         # (a retry or an extra run: not before)
    slow = fields.Boolean('Slow tonight', readonly=True, index=True,
                          help="This night: LCP over 4 s on a phone or 2.5 s on a computer")
    flagged = fields.Boolean('Over the limit', readonly=True, index=True,
                             help="Slow two nights in a row: LCP over 4 s on a phone or 2.5 s on a computer")
    message = fields.Char(readonly=True)
    # 0.10.0: the website the page is on (several websites on one database: each measured on its own)
    website_id = fields.Many2one('website', 'Website', readonly=True, index=True, ondelete='cascade')

    @api.depends('url')
    def _compute_path(self):
        for row in self:
            row.path = _path(row.url)

    def action_mtbg_setup(self):  # (a list's header button: called with the selected rows, none needed)
        """The Set up button: the switch and the API key, in a window of their own."""
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(self.env._("Only an administrator can set up the speed log."))
        return {'type': 'ir.actions.act_window', 'res_model': 'mtbg.page.speed.log.setup', 'view_mode': 'form',
                'target': 'new', 'name': self.env._("Set up the speed log")}

    # ------------------------------------------------------------------ Core's list: side bar and cog
    @api.model
    def _mtbg_settings_xmlid(self):
        return 'mtbg_tours_page_speed.action_page_speed_settings'

    @api.model
    def _mtbg_sidebar_sections(self, domain):
        sections = super()._mtbg_sidebar_sections(domain)
        count = lambda extra: self.search_count(list(domain or []) + extra)  # noqa: E731
        # (0.8.0: Phone and Computer each counted without the other's filter: with Phone on, Computer said 0)
        screens = Domain(domain or []).map_conditions(
            lambda c: Domain.TRUE if c.field_expr == 'strategy' else c)
        on_screen = lambda strategy: self.search_count(screens & Domain('strategy', '=', strategy))  # noqa: E731
        websites = self.env['website'].sudo().search([])
        if len(websites) > 1:
            sections.append({'key': 'website', 'label': self.env._("Website"), 'icon': 'fa-globe', 'nodes': [
                {'key': 'website_%s' % website.id, 'label': website.name,
                 'count': count([('website_id', '=', website.id)]), 'domain': [('website_id', '=', website.id)]}
                for website in websites]})
        sections.append({'key': 'speed', 'label': self.env._("Speed log"), 'icon': 'fa-tachometer', 'nodes': [
            {'key': 'flagged', 'label': self.env._("Over the limit"), 'count': count([('flagged', '=', True)]),
             'domain': [('flagged', '=', True)]},
            {'key': 'slow', 'label': self.env._("Slow tonight"), 'count': count([('slow', '=', True)]),
             'domain': [('slow', '=', True)]},
            {'key': 'mobile', 'label': self.env._("Phone"), 'count': on_screen('mobile'),
             'domain': [('strategy', '=', 'mobile')]},
            {'key': 'desktop', 'label': self.env._("Computer"), 'count': on_screen('desktop'),
             'domain': [('strategy', '=', 'desktop')]},
            {'key': 'error', 'label': self.env._("Not measured"), 'count': count([('state', '=', 'error')]),
             'domain': [('state', '=', 'error')]},
        ]})
        return sections

    # ------------------------------------------------------------------ the night's run
    @api.model
    def _mtbg_tz(self):
        """The business's time zone (Settings › Operator Timezone), else the user's, else UTC."""
        name = self.env['ir.config_parameter'].sudo().get_param(TZ_PARAM) or self.env.user.tz or 'UTC'
        try:
            return pytz.timezone(name)
        except pytz.UnknownTimeZoneError:
            return pytz.utc

    @api.model
    def _mtbg_next_night(self, now=None):
        """The next 02:30 in the business's time zone, as a UTC datetime (naive, as Odoo stores it)."""
        tz = self._mtbg_tz()
        now_utc = pytz.utc.localize(now or fields.Datetime.now())
        local = now_utc.astimezone(tz)
        target = tz.localize(datetime.combine(local.date(), NIGHT))
        if target <= local + timedelta(minutes=5):
            target = tz.localize(datetime.combine(local.date() + timedelta(days=1), NIGHT))
        return target.astimezone(pytz.utc).replace(tzinfo=None)

    @api.model
    def _mtbg_schedule_night(self):
        """The job's next run: the coming 02:30 in the business's time zone (owner, 2026-11-08: "it should follow
        the global time zone"). Its time no longer comes from the module's data."""
        cron = self.env.ref('mtbg_tours_page_speed.cron_speed_log', raise_if_not_found=False)
        if cron:
            cron.sudo().nextcall = self._mtbg_next_night()
        return cron

    @api.model
    def _mtbg_on(self):
        return _on(self.env['ir.config_parameter'].sudo().get_param(PARAM_ON))

    @api.model
    def _mtbg_connector(self):
        """The Google connector when it can measure (installed, with its PageSpeed app), else None (a soft check:
        Page Speed does not depend on it)."""
        Connector = self.env.get('google.connector')
        if Connector is None or not hasattr(Connector, '_google_pagespeed_run'):
            return None
        return Connector.sudo()

    @api.model
    def _mtbg_google(self):
        """(ready, what to do): the connector, its PageSpeed app on, with the server API key."""
        Connector = self._mtbg_connector()
        if Connector is None:
            return False, self.env._("Install the Google connector, then connect Google (Settings › Google) and "
                                     "switch on PageSpeed.")
        if Connector._google_pagespeed_ready():
            return True, self.env._("Google connection: OK (Settings › Google › PageSpeed Insights).")
        return False, self.env._("Connect Google (Settings › Google) and switch on PageSpeed: the PageSpeed Insights "
                                 "app on, and a server API key in Set up Google › API keys.")

    @api.model
    def _mtbg_websites(self):
        """The websites measured (0.10.0): those with an address, and the default website at the site's address
        (web.base.url) when it has none."""
        websites = self.env['website'].sudo().search([])
        default = self.env['website'].sudo().get_current_website()
        return websites.filtered(lambda w: (w.domain or '').strip() or w == default)

    @api.model
    def _mtbg_website_of(self, url):
        """The website at an address' host (its domain), else the current website."""
        host = (urlsplit(url or '').hostname or '').lower()
        for website in self.env['website'].sudo().search([]):
            domain = (website.domain or '').strip().lower()
            if domain and host and (urlsplit(domain if '://' in domain else '//' + domain).hostname or '') == host:
                return website
        return self.env['website'].sudo().get_current_website()

    @api.model
    def _mtbg_base(self, website=None):
        website = website or self.env['website'].sudo().get_current_website()
        domain = (website.domain or '').strip().rstrip('/')
        if domain and '://' not in domain:
            domain = 'https://' + domain
        return domain or self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')

    @api.model
    def _mtbg_pages(self, website=None):
        """The homepage, the Spanish homepage and every page under /tours, as the sitemap lists them (``website``:
        that website's, default the current one)."""
        website = website or self.env['website'].sudo().get_current_website()
        paths = ['/']
        default = website.default_lang_id
        paths += ['/' + lang.url_code for lang in website.language_ids if lang != default][:1]
        try:
            listed = [page['loc'] for page in website.with_context(website_id=website.id)._enumerate_pages()]
        except Exception:  # noqa: BLE001 - a module's page list failing: the tours from their records
            _logger.exception("Page speed: the sitemap's pages could not be listed")
            listed = []
        tours = sorted({p for p in listed if p.startswith('/tours/') and p.count('/') == 2})
        if not tours and 'mtbg.tour' in self.env:  # (Tours, where installed: a soft check)
            Tour = self.env['mtbg.tour'].sudo()
            domain = [('is_published', '=', True)]
            if 'website_id' in Tour._fields:
                domain.append(('website_id', 'in', (False, website.id)))
            tours = sorted({t.website_url for t in Tour.search(domain) if t.website_url})
        return paths + tours

    @api.model
    def _mtbg_speed_run(self):
        """The job: tonight's rows (made once a night), then a few measured; again in a minute while some wait (0.8.0:
        or when the next retry or extra run is due)."""
        # (0.9.0: the rows without a page title get theirs, a few pages a run, whether the log is on or not)
        self.sudo()._mtbg_fill_titles()
        if not self._mtbg_on() or not self._mtbg_google()[0]:
            return 0
        today = fields.Date.context_today(self)
        Log = self.sudo()
        made = False
        for website in self._mtbg_websites():
            # (0.10.0: each website's own rows, made once a night)
            if Log.search_count([('run_date', '=', today), ('website_id', '=', website.id)]):
                continue
            base = self._mtbg_base(website)
            pages = self._mtbg_pages(website)
            titles = self._mtbg_titles([base + path for path in pages], website=website)
            Log.create([{'run_date': today, 'url': base + path, 'strategy': strategy, 'website_id': website.id,
                         'page_title': titles.get(base + path) or False}
                        for path in pages for strategy in ('mobile', 'desktop')])
            made = True
        if made:
            Log.search([('run_date', '<', today - timedelta(days=KEEP_DAYS))]).unlink()
            if not odoo_module.current_test:
                self.env.cr.commit()
        now = fields.Datetime.now()
        tonight = [('run_date', '=', today), ('state', '=', 'pending')]
        started = Log.search([('run_date', '=', today)], order='create_date', limit=1).create_date or now
        if now > started + WINDOW:
            # (the night is over: a page still to retry is "Not measured", a slow one keeps the runs it has)
            Log.search(tonight)._mtbg_close()
            return 0
        # (the night's first pass first: retries and extra runs once they are due, after it)
        pending = Log.search(tonight + [('next_try', '=', False)], order='id', limit=BATCH)
        if len(pending) < BATCH:
            pending |= Log.search(tonight + [('next_try', '!=', False), ('next_try', '<=', now)],
                                  order='next_try, id', limit=BATCH - len(pending))
        for row in pending:
            row._mtbg_measure()
            if not odoo_module.current_test:
                self.env.cr.commit()  # (each page kept as soon as it is measured: a long night never loses its work)
        waiting = Log.search(tonight)
        if waiting:
            cron = self.env.ref('mtbg_tours_page_speed.cron_speed_log', raise_if_not_found=False)
            if cron:
                due = min((r.next_try for r in waiting if r.next_try), default=None)
                soon = fields.Datetime.now() + timedelta(minutes=1)
                cron._trigger(at=soon if any(not r.next_try for r in waiting) or not due else max(due, soon))
        return len(pending)

    # ------------------------------------------------------------------ page titles (0.9.0)
    @api.model
    def _mtbg_titles(self, urls, fetch=True, website=None):
        """{url: title} for the pages given: the website page's name for an address that is one, else the page's own
        <title> (fetched once, its head only; the site's name after "|" left out), else nothing (a page that did not
        answer gets its title another night). ``website``: the pages' website, else each address' own (0.10.0)."""
        Page = self.env['website.page'].sudo()
        titles = {}
        for url in dict.fromkeys(urls):
            website_of = website or self._mtbg_website_of(url)
            path = _path(url)
            page = Page.search([('url', '=', path), ('website_id', 'in', (False, website_of.id))],
                               order='website_id asc', limit=1)
            title = page.name if page else ''
            if not title and fetch:
                title = self._mtbg_fetch_title(url)
            if title:
                titles[url] = self._mtbg_clean_title(title, website_of.name)[:200]
        return titles

    @api.model
    def _mtbg_clean_title(self, title, site_name):
        title = ' '.join(html.unescape(title).split())
        for sep in (' | ', ' - ', ' – ', ' — '):
            head, _sep, tail = title.rpartition(sep)
            if head and site_name and tail.strip().lower() == site_name.strip().lower():
                return head.strip()
        return title

    @api.model
    def _mtbg_fetch_title(self, url):
        """The page's <title>, from the first bytes of its HTML ('' when it does not answer)."""
        try:
            with requests.get(url, timeout=TITLE_TIMEOUT, stream=True,
                              headers={'User-Agent': 'Mozilla/5.0 (speed log; page title)'}) as answer:
                if answer.status_code != 200:
                    return ''
                head = b''
                for chunk in answer.iter_content(16384):
                    head += chunk
                    if b'</title>' in head.lower() or len(head) >= TITLE_BYTES:
                        break
        except requests.RequestException:
            return ''
        found = TITLE.search(head)
        return found.group(1).decode(answer.encoding or 'utf-8', 'replace').strip() if found else ''

    @api.model
    def _mtbg_fill_titles(self, limit=TITLES_PER_RUN, fetch=True):
        """The rows without a page title (logged before 0.9.0, or a page that did not answer): the title their page
        had on another night, else the page's own (a few pages a call). Returns the pages given a title."""
        self.env.cr.execute("""
            SELECT url, (SELECT page_title FROM mtbg_page_speed_log known
                          WHERE known.url = log.url AND known.page_title IS NOT NULL AND known.page_title != ''
                          ORDER BY run_date DESC LIMIT 1)
              FROM mtbg_page_speed_log log
             WHERE page_title IS NULL OR page_title = ''
             GROUP BY url ORDER BY MAX(run_date) DESC
        """)
        missing = self.env.cr.fetchall()
        titles = {url: known for url, known in missing if known}
        unknown = [url for url, known in missing if not known][:limit]
        titles.update(self._mtbg_titles(unknown, fetch=fetch))
        for url, title in titles.items():
            # (in SQL: a few thousand old rows at once, none of them changed otherwise)
            self.env.cr.execute("""UPDATE mtbg_page_speed_log SET page_title = %s
                                     WHERE url = %s AND (page_title IS NULL OR page_title = '')""", (title, url))
        if titles:
            self.invalidate_model(['page_title'])
        return len(titles)

    # ------------------------------------------------------------------ the dashboard (0.9.0)
    @api.model
    def mtbg_speed_dashboard(self, nights=30, website_id=None):
        """The Speed log dashboard in one call: each night's averages per screen (the chart), last night against the
        7 nights before (the cards), the slowest pages with their main cause, and the lines of the worst pages.
        0.10.0: one website's (``website_id``; default the current website when it has rows, else the first website
        that has); ``websites``: the websites with rows, to choose from."""
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(self.env._("Only an administrator can see the speed log."))
        nights = max(1, min(int(nights or 30), KEEP_DAYS))
        cr = self.env.cr
        cr.execute("SELECT DISTINCT website_id FROM mtbg_page_speed_log WHERE website_id IS NOT NULL")
        measured = self.env['website'].sudo().browse([row[0] for row in cr.fetchall()]).exists().sorted('id')
        website = measured.filtered(lambda w: w.id == int(website_id or 0))[:1]
        if not website:
            current = self.env['website'].sudo().get_current_website()
            website = current if current in measured else measured[:1]
        site = website.id or None
        cr.execute("SELECT MAX(run_date) FROM mtbg_page_speed_log"
                   " WHERE state = 'done' AND website_id IS NOT DISTINCT FROM %s", (site,))
        last = cr.fetchone()[0]
        result = {'nights': nights, 'last': fields.Date.to_string(last) if last else False,
                  'limits': {'lcp': LIMITS}, 'marks': MARKS, 'series': {}, 'kpis': {}, 'worst': {}, 'pages': {},
                  'website_id': site or False,
                  'websites': [{'id': w.id, 'name': w.name} for w in measured]}
        self = self.with_context(mtbg_speed_website=site)
        if not last:
            return result
        start = last - timedelta(days=nights - 1)
        avgs = ', '.join('AVG(%s)' % stat for stat in STATS)
        cr.execute(f"""
            SELECT run_date, strategy, {avgs}
              FROM mtbg_page_speed_log
             WHERE state = 'done' AND run_date BETWEEN %s AND %s AND website_id IS NOT DISTINCT FROM %s
             GROUP BY run_date, strategy ORDER BY run_date
        """, (start, last, site))
        dates = []
        series = {strategy: {stat: {} for stat in STATS} for strategy in LIMITS}
        for row in cr.fetchall():
            day = fields.Date.to_string(row[0])
            if day not in dates:
                dates.append(day)
            for stat, value in zip(STATS, row[2:]):
                series[row[1]][stat][day] = _round(stat, value)
        result['dates'] = dates
        result['series'] = {strategy: {stat: [values.get(day) for day in dates] for stat, values in stats.items()}
                            for strategy, stats in series.items()}
        result['kpis'] = self._mtbg_kpis(last)
        worst_urls = set()
        for strategy in LIMITS:
            worst = self._mtbg_worst(last, start, strategy)
            result['worst'][strategy] = worst
            worst_urls.update(page['url'] for page in worst)
        result['pages'] = self._mtbg_page_lines(worst_urls, start, last, dates)
        return result

    @api.model
    def _mtbg_kpis(self, last):
        """Per screen: last night's average score and LCP, pages over the limit and not measured, and the same as a
        nightly average of the 7 nights before it."""
        cr = self.env.cr
        site = self.env.context.get('mtbg_speed_website')
        cr.execute("""
            SELECT strategy, run_date = %s AS tonight,
                   AVG(score) FILTER (WHERE state = 'done'), AVG(lcp) FILTER (WHERE state = 'done'),
                   COUNT(*) FILTER (WHERE flagged AND state = 'done'), COUNT(*) FILTER (WHERE state = 'error'),
                   COUNT(DISTINCT run_date)
              FROM mtbg_page_speed_log
             WHERE run_date BETWEEN %s AND %s AND website_id IS NOT DISTINCT FROM %s
             GROUP BY strategy, run_date = %s
        """, (last, last - timedelta(days=7), last, site, last))
        kpis = {strategy: {'last': {}, 'week': {}} for strategy in LIMITS}
        for strategy, tonight, score, lcp, over, errors, count in cr.fetchall():
            if strategy not in kpis:
                continue
            per = 1 if tonight else max(count, 1)
            kpis[strategy]['last' if tonight else 'week'] = {
                'score': _round('score', score), 'lcp': _round('lcp', lcp),
                'over': round(over / per, 1), 'error': round(errors / per, 1)}
        return kpis

    @api.model
    def _mtbg_worst(self, last, start, strategy):
        """The slowest pages on a screen on their latest measured night (the highest LCP, then the lowest score):
        title, address, score, LCP, the LCP breakdown's biggest part, nights slow in the range."""
        cr = self.env.cr
        site = self.env.context.get('mtbg_speed_website')
        cr.execute("""
            WITH latest AS (
                SELECT DISTINCT ON (url) id, url, run_date, lcp, score
                  FROM mtbg_page_speed_log
                 WHERE strategy = %s AND state = 'done' AND run_date BETWEEN %s AND %s
                   AND website_id IS NOT DISTINCT FROM %s
                 ORDER BY url, run_date DESC, id DESC
            )
            SELECT latest.id,
                   (SELECT COUNT(*) FROM mtbg_page_speed_log o
                     WHERE o.url = latest.url AND o.strategy = %s AND o.slow AND o.run_date BETWEEN %s AND %s)
              FROM latest ORDER BY latest.lcp DESC, latest.score ASC, latest.url LIMIT %s
        """, (strategy, start, last, site, strategy, start, last, WORST))
        found = cr.fetchall()
        rows = self.browse([row_id for row_id, _count in found])
        slow_nights = dict(found)
        labels = {'lcp_ttfb': self.env._("server answer"), 'lcp_load_delay': self.env._("load delay"),
                  'lcp_load_time': self.env._("load time"), 'lcp_render_delay': self.env._("render delay")}
        worst = []
        for row in rows:
            part = max(CAUSES, key=lambda name: row[name] or 0)
            cause, cause_ms = (labels[part] if row[part] else ''), row[part] or 0
            explained = sum(row[name] or 0 for name in CAUSES)
            if explained and row.lcp and explained < EXPLAINS * row.lcp * 1000:
                element = self._mtbg_element_label(row.lcp_selector or row.lcp_element or '')
                cause = (self.env._("LCP element: %(element)s; the breakdown doesn't explain the time", element=element)
                         if element else self.env._("The breakdown doesn't explain the time"))
                cause_ms = 0
            worst.append({
                'id': row.id, 'url': row.url, 'path': row.path, 'title': row.page_title or row.path,
                'night': fields.Date.to_string(row.run_date), 'score': row.score, 'lcp': round(row.lcp, 1),
                'cause': cause, 'cause_ms': cause_ms,
                'slow_nights': slow_nights[row.id], 'flagged': row.flagged, 'slow': row.slow,
                'limit': LIMITS[strategy]})
        return worst

    @api.model
    def _mtbg_element_label(self, element):
        """A short name for the LCP element from its selector (else its HTML): the header logo, the tour's cover, the
        page's background, the title, else its last part ('img.mtbg-card__img')."""
        element = (element or '').strip()
        if not element:
            return ''
        if re.search(r'navbar-brand|\blogo\b', element):
            return self.env._("header logo")
        if 'mtbg-tour-cover' in element:
            return self.env._("tour cover")
        last = re.split(r'\s*>\s*|\s+', element)[-1] if not element.startswith('<') else element
        if last in ('div#wrap', '#wrap') or re.search(r'has-page-bg|mtbg-tour-page', last):
            return self.env._("page background")
        if element.startswith('<'):
            tag = re.match(r'<([a-zA-Z][\w-]*)', element)
            classes = re.search(r'\sclass="([^"]*)"', element)
            last = (tag.group(1).lower() if tag else '') + ('.' + classes.group(1).split()[0]
                                                           if classes and classes.group(1).split() else '')
        if re.match(r'^h1\b', last):
            return self.env._("title")
        return last[:40]

    @api.model
    def _mtbg_page_lines(self, urls, start, last, dates):
        """Each of these pages' own values per night and screen (the chart's page line)."""
        if not urls:
            return {}
        cr = self.env.cr
        cr.execute(f"""
            SELECT url, strategy, run_date, {', '.join(STATS)}
              FROM mtbg_page_speed_log
             WHERE state = 'done' AND url IN %s AND run_date BETWEEN %s AND %s
        """, (tuple(urls), start, last))
        found = {}
        for url, strategy, day, *values in cr.fetchall():
            found.setdefault(url, {}).setdefault(strategy, {})[fields.Date.to_string(day)] = dict(zip(STATS, values))
        return {url: {strategy: {stat: [_round(stat, (by_day.get(day) or {}).get(stat)) if day in by_day else None
                                        for day in dates] for stat in STATS}
                      for strategy, by_day in screens.items()}
                for url, screens in found.items()}

    def _mtbg_runs(self):
        try:
            return json.loads(self.runs_data or '[]')
        except ValueError:
            return []

    def _mtbg_measure(self):
        """One page on one screen, through the connector (Google's refusal kept as the row's message). 0.8.0: a page
        Google could not measure is tried again later (TRIES in all); a phone page slow on its first run is measured
        PHONE_RUNS times, its median run kept."""
        self.ensure_one()
        Connector = self._mtbg_connector()
        if Connector is None:
            self.write({'state': 'error', 'message': self._mtbg_google()[1]})
            return
        try:
            data = Connector._google_pagespeed_run(self.url, self.strategy)
        except Exception as error:  # noqa: BLE001 - the connector's GoogleError (not imported: a soft check)
            # (Google's "Lighthouse returned error: FAILED_DOCUMENT_REQUEST" and other hiccups are tried again; a
            # refusal of the key or the project (400-403) would only be refused again)
            self._mtbg_failed(str(error)[:200], again=not REFUSED.search(str(error)))
            return
        failed = self._mtbg_lighthouse_error(data or {})
        if failed:  # (0.7.6: Lighthouse could not finish: "Not measured" with its reason, never a score of 0)
            self._mtbg_failed(failed)
            return
        runs = self._mtbg_runs() + [self._mtbg_values(data or {}, self.strategy)]
        more = (self.strategy == 'mobile' and len(runs) < PHONE_RUNS
                and runs[0]['lcp'] > LIMITS['mobile'])
        self.write({'runs_data': json.dumps(runs), 'message': False, 'tries': 0,
                    'next_try': fields.Datetime.now() + RUN_AFTER if more else False})
        if not more:
            self._mtbg_finish()

    def _mtbg_failed(self, message, again=True):
        """Google could not measure the page: again later in the night, else "Not measured" (with its reason); a
        slow phone page's runs already made are kept."""
        tries = self.tries + 1
        if again and tries < TRIES:
            self.write({'tries': tries, 'message': message,
                        'next_try': fields.Datetime.now() + RETRY_AFTER})
        elif self._mtbg_runs():
            self.write({'tries': tries})
            self._mtbg_finish(message)
        else:
            self.write({'tries': tries, 'state': 'error', 'message': message, 'score': 0, 'lcp': 0, 'slow': False,
                        'flagged': False, 'next_try': False})

    def _mtbg_close(self):
        """The night is over: each page still waiting ends with what it has."""
        for row in self:
            if row._mtbg_runs():
                row._mtbg_finish()
            else:
                row.write({'state': 'error', 'next_try': False, 'slow': False, 'flagged': False,
                           'message': row.message or self.env._("Not measured before the night was over.")})

    def _mtbg_finish(self, message=False):
        """The row's values: its run (or the median run of a slow phone page's), slow or not tonight, over the limit
        when its page was slow the night before too."""
        runs = self._mtbg_runs()
        lcps = sorted(run['lcp'] for run in runs)
        middle = median(lcps)
        # (the median run's own values, so the row is one real measurement; of two, the faster)
        pick = min(runs, key=lambda run: (abs(run['lcp'] - middle), run['lcp']))
        values = dict(pick, lcp=middle if len(runs) % 2 else pick['lcp'])
        values['slow'] = values.pop('flagged')
        values['flagged'] = values['slow'] and self._mtbg_slow_before()
        values['lcp_runs'] = ', '.join('%.1f' % run['lcp'] for run in runs) if len(runs) > 1 else False
        self.write(dict(values, state='done', next_try=False, message=message))

    def _mtbg_slow_before(self):
        """The page on the same screen was slow on its last measured night before this one."""
        before = self.sudo().search([('url', '=', self.url), ('strategy', '=', self.strategy),
                                     ('run_date', '<', self.run_date), ('state', '=', 'done')],
                                    order='run_date desc', limit=1)
        return bool(before.slow)

    @api.model
    def _mtbg_lighthouse_error(self, data):
        """Why Lighthouse could not measure the page (its runtime error, or no performance score), else ''."""
        lighthouse = data.get('lighthouseResult') or {}
        error = lighthouse.get('runtimeError') or {}
        if error.get('code') and error.get('code') != 'NO_ERROR':
            return self.env._("Google could not measure it: %s", (error.get('message') or error['code'])[:180])
        score = ((lighthouse.get('categories') or {}).get('performance') or {}).get('score')
        if score is None:
            return self.env._("Google could not measure it: no performance score in its answer.")
        return ''

    @api.model
    def _mtbg_lcp_node(self, audits, want='snippet'):
        """The LCP element's HTML snippet (else its CSS selector) from Lighthouse's answer, in either shape: Lighthouse
        13 (PageSpeed since late 2025) gives it in the "lcp-breakdown-insight" audit as a node item of its list; older
        ones in "largest-contentful-paint-element" (items > items > node). Empty when the answer has none (0.7.8: the
        old path alone left the log's LCP element empty every night)."""
        def find(value):
            if isinstance(value, dict):
                if value.get('type') == 'node' and (value.get('snippet') or value.get('selector')):
                    # (0.8.0: the selector asked for on its own: where the element is)
                    return (value.get('selector') or '' if want == 'selector'
                            else value.get('snippet') or value.get('selector'))
                for key in ('node', 'items', 'details'):
                    found = find(value.get(key))
                    if found:
                        return found
            elif isinstance(value, list):
                for item in value:
                    found = find(item)
                    if found:
                        return found
            return ''
        for audit in ('lcp-breakdown-insight', 'largest-contentful-paint-element', 'lcp-discovery-insight'):
            found = find((audits.get(audit) or {}).get('details'))
            if found:
                return found
        return ''

    @api.model
    def _mtbg_values(self, data, strategy):
        """The row's values from PageSpeed's answer."""
        lighthouse = data.get('lighthouseResult') or {}
        audits = lighthouse.get('audits') or {}

        def num(audit):
            return (audits.get(audit) or {}).get('numericValue') or 0
        element = self._mtbg_lcp_node(audits)
        score = ((lighthouse.get('categories') or {}).get('performance') or {}).get('score')
        lcp = num('largest-contentful-paint') / 1000
        return dict({
            'score': round((score or 0) * 100), 'lcp': lcp, 'fcp': num('first-contentful-paint') / 1000,
            'tbt': round(num('total-blocking-time')), 'cls': num('cumulative-layout-shift'),
            'speed_index': num('speed-index') / 1000, 'ttfb': round(num('server-response-time')),
            'weight_kb': round(num('total-byte-weight') / 1024), 'lcp_element': element[:200],
            'lcp_selector': self._mtbg_lcp_node(audits, 'selector')[:200],
            'flagged': lcp > LIMITS.get(strategy, 4.0),
        }, **self._mtbg_lcp_breakdown(audits))

    @api.model
    def _mtbg_lcp_breakdown(self, audits):
        """{lcp_ttfb, lcp_load_delay, lcp_load_time, lcp_render_delay} (ms) from Lighthouse's LCP breakdown: Lighthouse
        13's "lcp-breakdown-insight" (a table of subparts and durations) or older ones' "largest-contentful-paint-
        element" (a table of phases and timings). A part Lighthouse leaves out (no picture: no load parts) is 0."""
        out = dict.fromkeys(set(PHASES.values()), 0)

        def rows(value):
            if isinstance(value, dict):
                if 'subpart' in value or 'phase' in value:
                    yield value
                for key in ('items', 'details'):
                    yield from rows(value.get(key))
            elif isinstance(value, list):
                for item in value:
                    yield from rows(item)
        for audit in ('lcp-breakdown-insight', 'largest-contentful-paint-element'):
            found = False
            for row in rows((audits.get(audit) or {}).get('details')):
                field = PHASES.get(row.get('subpart') or row.get('phase'))
                timing = row.get('duration', row.get('timing'))
                if field and isinstance(timing, (int, float)):
                    out[field] = round(timing)
                    found = True
            if found:
                break
        return out


class MtbgPageSpeedLogSetup(models.TransientModel):
    """Set up the nightly speed log, step by step (Website › Reporting › Speed log › Set up, or Page Speed's settings
    page): enable the PageSpeed Insights API in the Google project and give the connector a server key, switch on
    the connector's PageSpeed app, test one measurement, turn the nightly measuring on (0.7.4: through the Google
    connector, no key of Page Speed's own). Writes only the speed log's switch, never the Settings page."""
    _name = 'mtbg.page.speed.log.setup'
    _description = 'Page speed: set up the nightly speed log'

    step = fields.Selection([('api', 'Google project'), ('app', 'Google connector'), ('test', 'Test'),
                             ('on', 'Turn on')], default='api', required=True)
    on = fields.Boolean('Measure every night', default=lambda self: self.env['mtbg.page.speed.log']._mtbg_on())
    google_ok = fields.Boolean(compute='_compute_google')
    google_note = fields.Char(compute='_compute_google')
    has_connector = fields.Boolean(compute='_compute_google')
    test_ok = fields.Boolean(readonly=True)
    test_result = fields.Char(readonly=True)
    pages_note = fields.Char(compute='_compute_pages_note')

    def _compute_google(self):
        Log = self.env['mtbg.page.speed.log']
        ready, note = Log._mtbg_google()
        has = Log._mtbg_connector() is not None
        for wizard in self:
            wizard.google_ok, wizard.google_note, wizard.has_connector = ready, note, has

    def _compute_pages_note(self):
        try:
            pages = self.env['mtbg.page.speed.log']._mtbg_pages()
        except Exception:  # noqa: BLE001 - only a hint
            pages = []
        tours = [p for p in pages if p.startswith('/tours/')]
        note = self.env._("The homepage, the Spanish homepage and %(count)s pages under /tours (tours, rentals, "
                          "categories), each on a phone and on a computer: %(calls)s measurements a night, at 02:30 "
                          "%(tz)s time (Settings › Operator Timezone).", count=len(tours), calls=len(pages) * 2,
                          tz=self.env['mtbg.page.speed.log']._mtbg_tz().zone)
        for wizard in self:
            wizard.pages_note = note

    def _reopen(self):
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id, 'view_mode': 'form',
                'target': 'new', 'name': self.env._("Set up the speed log")}

    def action_go(self):
        """Next / Back: the step named in the button's context."""
        self.ensure_one()
        self.step = self.env.context.get('mtbg_step') or 'api'
        return self._reopen()

    def action_open_google(self):
        """Settings › Google's Set up Google, at its apps step (the connector's own pages)."""
        action = self.env.ref('google_connector.action_google_setup', raise_if_not_found=False)
        if not action:
            return self._reopen()
        result = action.sudo().read()[0]
        result['context'] = {'default_step': self.env.context.get('mtbg_google_step') or 'apps'}
        return result

    def action_test(self):
        """One measurement of the homepage on a phone through the connector: OK and its score, or Google's refusal
        in plain words. Nothing is saved."""
        self.ensure_one()
        Log = self.env['mtbg.page.speed.log']
        Connector = Log._mtbg_connector()
        ready, note = Log._mtbg_google()
        if Connector is None or not ready:
            self.write({'test_ok': False, 'test_result': note})
            return self._reopen()
        try:
            data = Connector._google_pagespeed_run(Log._mtbg_base() + '/', 'mobile')
        except Exception as error:  # noqa: BLE001 - the connector's GoogleError
            self.write({'test_ok': False, 'test_result': self._mtbg_plain_error(str(error))})
            return self._reopen()
        values = Log._mtbg_values(data or {}, 'mobile')
        self.write({'test_ok': True, 'test_result': self.env._(
            "Google measured it. Your homepage on a phone: score %(score)s, main picture shown after %(lcp)s s.",
            score=values['score'], lcp=round(values['lcp'], 1))})
        return self._reopen()

    def _mtbg_plain_error(self, message):
        """Google's refusal in plain words."""
        text = (message or '').lower()
        if 'api key not valid' in text or 'api_key_invalid' in text:
            return self.env._("Google says the server key is not valid: paste it again in Set up Google › API keys.")
        if 'has not been used' in text or 'is disabled' in text or 'service_disabled' in text:
            return self.env._("The PageSpeed Insights API is not turned on in the Google project: open step 1's link, "
                              "press Enable, then try again in a minute.")
        if 'referer' in text or 'referrer' in text or 'blocked' in text or 'ip address' in text:
            return self.env._("The server key is limited to other websites or apps: in Credentials, open the key, set "
                              "Application restrictions to None and API restrictions to PageSpeed Insights API.")
        if 'quota' in text or 'daily limit' in text:
            return self.env._("The daily allowance is used up: try again tomorrow.")
        return self.env._("Google refused: %s", (message or '')[:160] or self.env._("no reason given"))

    def action_save(self):
        self.ensure_one()
        self.env['ir.config_parameter'].sudo().set_param(PARAM_ON, 'True' if self.on else 'False')
        if self.on:
            self.env['mtbg.page.speed.log']._mtbg_schedule_night()
        return {'type': 'ir.actions.act_window_close'}


class IrConfigParameter(models.Model):
    _inherit = 'ir.config_parameter'

    # the business's time zone changed (Settings › Operator Timezone): the speed log keeps to 02:30 in the new one
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if any(vals.get('key') == TZ_PARAM for vals in vals_list):
            self.env['mtbg.page.speed.log']._mtbg_schedule_night()
        return records

    def write(self, vals):
        moved = 'value' in vals and any(p.key == TZ_PARAM for p in self)
        result = super().write(vals)
        if moved:
            self.env['mtbg.page.speed.log']._mtbg_schedule_night()
        return result
