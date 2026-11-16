"""Cloudflare's page cache: what Odoo lets it keep (ir_http.py) and the purge after every change (sources.py).

Every call to Cloudflare's API goes through Cloudflare Connector (0.7.0: ``cloudflare.api.purge``, a soft check):
this module keeps only the website side (which pages, live values, when to purge).

A change is noted in ``mtbg.edge.cache.change`` (a row per saving transaction: never a system parameter, which would
empty Odoo's caches, and never one shared row, which concurrent bookings would fight over), with the pages it touches
when only some do (0.9.0: an edit to a website page's own content), else every page. Once the transaction is
committed those page addresses are purged (pages.py); a purge of every page, a purge a few seconds after another one,
or one Cloudflare refused, is left to the one-minute job (it is called at once for every page).

0.9.0 (owner 2026-11-16): never Cloudflare's "purge everything" on its own (it emptied the script, style and picture
copies at every Cloudflare location too): page addresses only, 30 per call, a pause between calls, each call tried
again a few times; "Purge everything" stays a button for emergencies (Settings, the purge log). Every purge is logged
with what it emptied, how many addresses, by whom and why.

Re-fill (0.9.0): after a purge the purged homepages and pages under "Pages to re-fill" (default: the homepages and
/tours) are asked for again in the background, one at a time, as an anonymous visitor (no cookie: the copy Cloudflare
keeps is the visitors' one); every one of them again each night at the re-fill time (default 02:00 in the business's
time zone, before the nightly speed log), within a time cap. Prices, seats and statuses are never in the pages (they
load live: live_values.py).

0.8.0: no dependency on any Tours extension; each says what of it pages show (sources.py).
"""
from datetime import datetime, time as dt_time, timedelta
import hashlib
import json
import logging
import threading
import time

import pytz
import requests

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


_logger = logging.getLogger(__name__)

WARM_DELAY = 60         # seconds after a purge before its pages are asked for again
WARM_PAUSE = 1.0        # seconds between two pages (www's workers stay free for visitors)
WARM_MAX = 900          # seconds one re-fill run may take (the rest: the next run, a minute later)
WARM_AGENT = ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36 '
              'MTBG-prefill')
WARM_PATHS = '/ /tours'  # (default of "Pages to re-fill": the homepages and every page under /tours)
WARM_TIME = 2.0         # (default re-fill time: 02:00, before the nightly speed log at 02:30)
TZ_PARAM = 'mtbg_tours.operator_tz'  # (the business's time zone, where a Tours site has one: a soft read, else UTC)
SPACING = 10            # seconds between two purges from one worker (the rest: the one-minute job)
UPDATE_QUIET = 180      # seconds without module updates before their changes are purged (0.6.2: once per update)
# Cloudflare's purge by address ("files"): its documentation (2026-11) allows 100 addresses per call on Free, Pro and
# Business (500 on Enterprise) and 800 addresses a second on Free; 30 (the older limit, the connector's batch) keeps
# well inside every plan
PURGE_BATCH = 30
PURGE_GAP = 0.5         # seconds between two purge calls
PURGE_TRIES = 3         # a refused call tried again after 1 s, then 2 s (the connector also waits on Cloudflare's 429)
INLINE_MAX = PURGE_BATCH  # a save's own purge sends at most one call; more: the one-minute job, called at once
KEEP_LOG = 200
BANNER_KEY = 'mtbg_edge_cache.banner_signature'  # (not mtbg_tours.*: that key would itself empty the cache)
_last = {}              # dbname -> time of this worker's last purge
_lock = threading.Lock()


def _on(value):
    return value not in (False, None, '', '0', 'False', 'false')


class MtbgEdgeCache(models.AbstractModel):
    _name = 'mtbg.edge.cache'
    _description = 'Cloudflare page cache'

    @api.model
    def _mtbg_params(self):
        ICP = self.env['ir.config_parameter'].sudo()
        try:
            ttl = max(0, int(ICP.get_param('mtbg_tours.edge_cache_ttl') or 300))
        except ValueError:
            ttl = 300
        return {
            'on': _on(ICP.get_param('mtbg_tours.edge_cache')),
            'ttl': ttl,
            'paths': (ICP.get_param('mtbg_tours.edge_cache_paths') or '').split(),
        }

    @api.model
    def _mtbg_path_allowed(self, path, paths=None):
        """A page address the cache may keep: an entry ending in "/" is that address alone (with or without its
        "/"), any other is the address and everything under it ("/blog": /blog, /blog/a-post). Each entry stands
        for the page in every language too (0.6.0: "/blog" is /es/blog as well, "/" is /es)."""
        paths = self._mtbg_params()['paths'] if paths is None else paths
        return any(self._mtbg_path_match(p, paths) for p in {path, self._mtbg_without_lang(path)})

    @api.model
    def _mtbg_without_lang(self, path):
        """The address without its language part (/es/blog: /blog, /es: /)."""
        parts = path.split('/', 2)
        if len(parts) > 1 and parts[1] and parts[1] in self._mtbg_lang_prefixes():
            return '/' + (parts[2] if len(parts) > 2 else '')
        return path

    @api.model
    def _mtbg_lang_prefixes(self):
        Lang = self.env['res.lang']
        return {Lang._get_data(code=code).url_code for code, _name in Lang.get_installed()}

    @api.model
    def _mtbg_path_match(self, path, paths):
        for entry in paths:
            if entry.endswith('/'):
                if path in (entry, entry.rstrip('/') or '/'):
                    return True
            elif path == entry or path.startswith(entry + '/'):
                return True
        return False

    # ------------------------------------------------------------------ changes
    @api.model
    def _mtbg_updating(self):
        """Modules are being installed or upgraded in this process (Update all, the updaters): every module's
        templates are written again, one purge each (www 2026-11-03: about every 2 minutes during the updates)."""
        if self.env.context.get('install_mode'):
            return True
        from odoo.modules import module as odoo_module
        return not self.env.registry.ready and not odoo_module.current_test

    @api.model
    def _mtbg_changed(self, paths=None):
        """A page may show something just saved: purge once this transaction is committed. ``paths``: the only
        page addresses that show it (0.9.0: a website page's own content; each is purged in every language), None
        (default): every page. During a module update the change is only noted (every page): the one-minute job
        purges once, when the updates have been quiet a while."""
        if not self._mtbg_params()['on']:
            return
        cr = self.env.cr
        from .pages import forget  # (pages.py extends this model: imported after it)
        forget(cr.dbname)
        if self._mtbg_updating():
            if not cr.postcommit.data.get('mtbg_edge_cache_update'):
                cr.postcommit.data['mtbg_edge_cache_update'] = True
                cr.execute("INSERT INTO mtbg_edge_cache_change (create_date, during_update) "
                           "VALUES (now() at time zone 'UTC', true)")
            return
        if paths is not None:
            paths = {p for p in paths if p and p.startswith('/')}
            if not paths:
                return  # (no page shows it)
        row = cr.postcommit.data.get('mtbg_edge_cache')
        if row:
            # (this transaction's row: its pages widened, or every page)
            noted = cr.postcommit.data.setdefault('mtbg_edge_cache_paths', set())
            if noted is None:
                return
            if paths is None:
                cr.postcommit.data['mtbg_edge_cache_paths'] = None
                cr.execute("UPDATE mtbg_edge_cache_change SET paths = NULL WHERE id = %s", [row])
            elif not paths <= noted:
                noted |= paths
                cr.execute("UPDATE mtbg_edge_cache_change SET paths = %s WHERE id = %s",
                           ['\n'.join(sorted(noted)), row])
            return
        cr.execute("INSERT INTO mtbg_edge_cache_change (create_date, paths) VALUES (now() at time zone 'UTC', %s) "
                   "RETURNING id", ['\n'.join(sorted(paths)) if paths is not None else None])
        cr.postcommit.data['mtbg_edge_cache'] = cr.fetchone()[0]
        cr.postcommit.data['mtbg_edge_cache_paths'] = set(paths) if paths is not None else None
        dbname = cr.dbname

        @cr.postcommit.add
        def purge():
            with _lock:
                if time.monotonic() - _last.get(dbname, 0) < SPACING:
                    return  # (the one-minute job sends it)
                _last[dbname] = time.monotonic()
            try:
                with self.env.registry.cursor() as new_cr:
                    self.with_env(self.env(cr=new_cr))._mtbg_purge_pending(inline=True)
            except Exception:  # never fail the saving request: the job retries
                _logger.exception("Cloudflare page cache: purge after a change failed")

    @api.model
    def _mtbg_pending_scope(self, changes):
        """(page addresses or None for every page, why): what the noted changes empty."""
        if any(change.during_update for change in changes):
            return None, self.env._("Modules updated")
        paths = set()
        for change in changes:
            if not change.paths:
                return None, self.env._("Changes saved")
            paths.update(change.paths.split())
        return sorted(paths), self.env._("Changes saved")

    @api.model
    def _mtbg_purge_pending(self, inline=False):
        """Purge when changes are waiting (the after-save purge: ``inline``, and the one-minute job). A save's own
        purge sends at most one call: every page, or more addresses, are the job's, called at once."""
        Change = self.env['mtbg.edge.cache.change'].sudo()
        last = Change.search([], order='id desc', limit=1)
        if not last:
            return False
        update = Change.search([('during_update', '=', True)], order='id desc', limit=1)
        if update and update.create_date > fields.Datetime.now() - timedelta(seconds=UPDATE_QUIET):
            return False  # (an update is going on: one purge when it is over)
        if not self._mtbg_params()['on']:
            Change.search([]).unlink()
            return False
        changes = Change.search([('id', '<=', last.id)])
        paths, reason = self._mtbg_pending_scope(changes)
        if inline and (paths is None or len(self._mtbg_scope_paths(paths)) > INLINE_MAX):
            self._mtbg_purge_soon()
            return False
        if self._mtbg_purge(reason, paths=paths):
            changes.unlink()
            return True
        return False

    @api.model
    def _mtbg_purge_soon(self):
        """The one-minute job, now (a purge of many addresses never holds a visitor's or an editor's request)."""
        cron = self.env.ref('mtbg_tours_edge_cache.cron_edge_cache_purge', raise_if_not_found=False)
        if cron and cron.sudo().active:
            cron.sudo()._trigger()

    @api.model
    def _mtbg_purge(self, reason, paths=None, everything=False):
        """Empty Cloudflare's copies of the site's pages, through Cloudflare Connector; logged (what, how many, by
        whom, why). ``paths``: those page addresses (in every language), None: every page (pages.py);
        ``everything``: Cloudflare's "purge everything" (the emergency button only: it also empties the scripts,
        styles and pictures at every Cloudflare location). True when Cloudflare took it all."""
        Log = self.env['mtbg.edge.cache.log'].sudo()
        scope = 'everything' if everything else ('pages' if paths is None else 'some')
        if 'cloudflare.api' not in self.env:
            Log._mtbg_add(False, reason, self.env._(
                "Cloudflare Connector is not installed: install it, then Settings › Cloudflare › Set up Cloudflare."),
                scope=scope)
            return False
        Api = self.env['cloudflare.api'].sudo()
        if everything:
            result = Api.purge(everything=True)
            if not result.get('ok'):
                Log._mtbg_add(False, reason, result.get('error') or self.env._("Cloudflare did not purge."),
                              scope=scope, requests=result.get('requests') or 0)
                return False
            Log._mtbg_add(True, reason, '', scope=scope, requests=result.get('requests') or 1)
            self._mtbg_after_purge(None)
            return True
        listed = self._mtbg_scope_paths(paths)
        base = self._mtbg_warm_base()
        if not base:
            Log._mtbg_add(False, reason, self.env._("The website has no address (Website › Settings › Domain)."),
                          scope=scope)
            return False
        sent, failed, error = self._mtbg_purge_urls([base + path for path in listed])
        if failed:
            Log._mtbg_add(False, reason, self.env._(
                "%(failed)s of %(count)s addresses not purged: %(error)s",
                failed=failed, count=len(listed), error=error or self.env._("Cloudflare did not purge.")),
                scope=scope, count=len(listed), requests=sent)
            return False
        message = ', '.join(listed[:5]) + (' …' if len(listed) > 5 else '') if scope == 'some' else ''
        Log._mtbg_add(True, reason, message, scope=scope, count=len(listed), requests=sent)
        self._mtbg_after_purge(listed)
        return True

    @api.model
    def _mtbg_purge_urls(self, urls):
        """Cloudflare purges ``urls`` (full addresses), PURGE_BATCH a call, PURGE_GAP seconds apart; a refused call
        is tried again (1 s, 2 s), then the purge stops there. Returns (calls sent, addresses not purged, error)."""
        Api = self.env['cloudflare.api'].sudo()
        sent = 0
        batches = [urls[i:i + PURGE_BATCH] for i in range(0, len(urls), PURGE_BATCH)]
        for number, batch in enumerate(batches):
            if number:
                time.sleep(PURGE_GAP)
            result = {}
            for attempt in range(PURGE_TRIES):
                if attempt:
                    time.sleep(2 ** (attempt - 1))
                result = Api.purge(urls=batch)
                sent += result.get('requests') or 0
                if result.get('ok'):
                    break
                if not Api.zone()['id']:
                    break  # (not set up: no use trying again)
            else:
                left = sum(len(b) for b in batches[number:])
                _logger.warning("Cloudflare page cache: %s addresses not purged: %s", left, result.get('error'))
                return sent, left, result.get('error') or ''
            if not result.get('ok'):
                return sent, sum(len(b) for b in batches[number:]), result.get('error') or ''
        return sent, 0, ''

    @api.model
    def _mtbg_after_purge(self, paths):
        self._mtbg_warm_soon(paths)
        self._mtbg_banner_note()

    # ------------------------------------------------------------------ what changes by itself (0.6.1, 0.8.0)
    @api.model
    def _mtbg_banner_signature(self):
        """What the pages show that changes without an edit (the site notice: a departure full from bookings, its
        booking deadline passed), as a short fingerprint: each extension's ``_mtbg_edge_cache_fingerprint()`` on its
        own model (0.8.0), '' where none does. One alone is kept as it is (the site notice's, as before 0.8.0)."""
        from .sources import declared
        parts = []
        for name in sorted(declared(self.env, '_mtbg_edge_cache_fingerprint')):
            value = self.env[name].sudo()._mtbg_edge_cache_fingerprint()
            if value:
                parts.append([name, value])
        if not parts:
            return ''
        if len(parts) == 1:
            return parts[0][1]
        return hashlib.sha1(json.dumps(parts, sort_keys=True).encode()).hexdigest()

    @api.model
    def _mtbg_banner_note(self):
        """After a purge: the notice the pages will now carry."""
        try:
            signature = self._mtbg_banner_signature()
            ICP = self.env['ir.config_parameter'].sudo()
            if signature and ICP.get_param(BANNER_KEY) != signature:
                ICP.set_param(BANNER_KEY, signature)
        except Exception:  # noqa: BLE001 - never in the way of a purge
            _logger.exception("Cloudflare page cache: what changes by itself could not be read")

    @api.model
    def _mtbg_banner_check(self):
        """The job: when the site notice is no longer the one the pages carry (a departure full from bookings, its
        booking deadline passed, the next one in its place), a change is noted as for an edit (``_mtbg_changed``: the
        same purge after commit, the same spacing and one-minute catch-up). The purge keeps the new notice's
        fingerprint (``_mtbg_banner_note``), so a change empties the cache once. True when a change was noted."""
        if not self._mtbg_params()['on']:
            return False
        signature = self._mtbg_banner_signature()
        ICP = self.env['ir.config_parameter'].sudo()
        known = ICP.get_param(BANNER_KEY)
        if not signature or signature == known:
            return False
        if not known:
            ICP.set_param(BANNER_KEY, signature)  # (the first look: what the pages carry now)
            return False
        _logger.info("Cloudflare page cache: the site notice changed by itself: purge noted")
        self._mtbg_changed()
        return True

    JOBS = ('cron_edge_cache_purge', 'cron_edge_cache_warm_home', 'cron_edge_cache_banner', 'cron_edge_cache_warm_queue')

    @api.model
    def _mtbg_sync_jobs(self):
        """The cache's jobs (catch-up purge, homepages' re-fill) on while the cache is on, off while it is off."""
        on = self._mtbg_params()['on']
        for xmlid in self.JOBS:
            cron = self.env.ref('mtbg_tours_edge_cache.%s' % xmlid, raise_if_not_found=False)
            if cron and cron.sudo().active != on:
                cron.sudo().active = on

    # ------------------------------------------------------------------ re-fill
    @api.model
    def _mtbg_warm_params(self):
        ICP = self.env['ir.config_parameter'].sudo()
        try:
            at = float(ICP.get_param('mtbg_tours.edge_cache_warm_time') or WARM_TIME)
        except ValueError:
            at = WARM_TIME
        return {'paths': (ICP.get_param('mtbg_tours.edge_cache_warm_paths') or WARM_PATHS).split(),
                'time': min(max(at, 0.0), 23.99)}

    @api.model
    def _mtbg_warm_soon(self, paths=None):
        """After a purge: its pages that are re-filled (every one of them: ``paths`` None) queued, asked for again in
        a minute (once for a burst of edits)."""
        if self._mtbg_warm_queue(self._mtbg_warm_targets(paths)):
            cron = self.env.ref('mtbg_tours_edge_cache.cron_edge_cache_warm_queue', raise_if_not_found=False)
            if cron and cron.sudo().active:
                cron.sudo()._trigger(at=fields.Datetime.now() + timedelta(seconds=WARM_DELAY))

    @api.model
    def _mtbg_warm_base(self):
        website = self.env['website'].sudo().get_current_website()
        domain = (website.domain or '').strip().rstrip('/')
        if domain and '://' not in domain:
            domain = 'https://' + domain
        return domain or self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')

    @api.model
    def _mtbg_warm_targets(self, paths=None):
        """[(path, language code)]: of ``paths`` (default: every page), those re-filled: under "Pages to re-fill"
        (in every language) and kept by Cloudflare (on "Pages Cloudflare may keep", or a website page)."""
        params = self._mtbg_params()
        if not params['on'] or not params['ttl']:
            return []
        website = self._mtbg_website()
        warm = self._mtbg_warm_params()['paths']
        listed = self._mtbg_page_paths(website) if paths is None else paths
        pages = None
        out = []
        for path in listed:
            if path.endswith('/') and path != '/':
                continue  # (/es/: only redirects to /es)
            if not self._mtbg_path_allowed(path, warm):
                continue
            if not self._mtbg_path_allowed(path, params['paths']):
                if pages is None:
                    pages = set(self.env['website.page'].sudo().search([
                        ('website_id', 'in', (False, website.id)), ('website_published', '=', True),
                        ('visibility', '=', False)]).mapped('url'))
                if self._mtbg_without_lang(path) not in pages:
                    continue
            out.append((path, self._mtbg_lang_of(path, website)))
        return out

    @api.model
    def _mtbg_warm_queue(self, targets):
        """``targets`` [(path, language code)] added to the re-fill queue (once each). Returns how many were new."""
        Warm = self.env['mtbg.edge.cache.warm'].sudo()
        queued = set(Warm.search([]).mapped('path'))
        new = [{'path': path, 'lang': code} for path, code in targets if path not in queued]
        # (two of a list once)
        new = list({vals['path']: vals for vals in new}.values())
        if new:
            Warm.create(new)
        return len(new)

    @api.model
    def _mtbg_warm(self):
        """The re-fill job: the queued pages asked for through Cloudflare, one at a time, as an anonymous visitor
        would (no cookie, the page's language), WARM_PAUSE seconds apart, at most WARM_MAX seconds a run (the rest:
        a minute later). Returns {path: Cloudflare's answer (HIT, MISS, ...) or the error}."""
        Warm = self.env['mtbg.edge.cache.warm'].sudo()
        params = self._mtbg_params()
        base = self._mtbg_warm_base()
        if not params['on'] or not params['ttl'] or not base:
            Warm.search([]).unlink()
            return {}
        started = time.monotonic()
        done = {}
        for row in Warm.search([], order='id'):
            if time.monotonic() - started > WARM_MAX:
                cron = self.env.ref('mtbg_tours_edge_cache.cron_edge_cache_warm_queue', raise_if_not_found=False)
                if cron:
                    cron.sudo()._trigger(at=fields.Datetime.now() + timedelta(seconds=WARM_DELAY))
                _logger.info("Cloudflare page cache: re-fill time cap reached, %s pages left for the next run",
                             Warm.search_count([]))
                break
            headers = {'User-Agent': WARM_AGENT, 'Accept-Language': (row.lang or 'en_US').split('_')[0]}
            try:
                res = requests.get(base + row.path, headers=headers, timeout=30, allow_redirects=False)
                done[row.path] = res.headers.get('cf-cache-status') or str(res.status_code)
            except requests.RequestException as e:
                done[row.path] = str(e)[:80]
            row.unlink()
            time.sleep(WARM_PAUSE)
        if done:
            _logger.info("Cloudflare page cache: %s pages re-filled (%s)", len(done),
                         ', '.join('%s %s' % kv for kv in list(done.items())[:10]))
        return done

    @api.model
    def _mtbg_warm_night(self):
        """The nightly job (at the re-fill time, before the nightly speed log): every re-filled page queued and asked
        for (Cloudflare drops copies nobody asked for)."""
        self._mtbg_warm_queue(self._mtbg_warm_targets())
        return self._mtbg_warm()

    @api.model
    def _mtbg_tz(self):
        name = self.env['ir.config_parameter'].sudo().get_param(TZ_PARAM) or 'UTC'
        try:
            return pytz.timezone(name)
        except pytz.UnknownTimeZoneError:
            return pytz.utc

    @api.model
    def _mtbg_next_warm(self, now=None):
        """The next re-fill time in the business's time zone (UTC where none is set), as a naive UTC datetime."""
        tz = self._mtbg_tz()
        at = self._mtbg_warm_params()['time']
        hours, minutes = int(at), int(round((at - int(at)) * 60))
        if minutes == 60:
            hours, minutes = hours + 1, 0
        local = pytz.utc.localize(now or fields.Datetime.now()).astimezone(tz)
        target = tz.localize(datetime.combine(local.date(), dt_time(min(hours, 23), minutes)))
        if target <= local + timedelta(minutes=1):
            target = tz.localize(datetime.combine(local.date() + timedelta(days=1), dt_time(min(hours, 23), minutes)))
        return target.astimezone(pytz.utc).replace(tzinfo=None)

    @api.model
    def _mtbg_schedule_warm(self):
        """The nightly re-fill's next run: the coming re-fill time (settings saved, the time zone changed)."""
        cron = self.env.ref('mtbg_tours_edge_cache.cron_edge_cache_warm_home', raise_if_not_found=False)
        if cron:
            cron.sudo().write({'nextcall': self._mtbg_next_warm(), 'interval_number': 1, 'interval_type': 'days'})
        return cron


class MtbgEdgeCacheWarm(models.Model):
    _name = 'mtbg.edge.cache.warm'
    _description = 'Cloudflare page cache: a page to re-fill'
    _log_access = False
    _order = 'id'

    path = fields.Char(required=True, readonly=True)
    lang = fields.Char(readonly=True)


class MtbgEdgeCacheChange(models.Model):
    _name = 'mtbg.edge.cache.change'
    _description = 'Cloudflare page cache: a change to purge'
    _log_access = False

    create_date = fields.Datetime(readonly=True)
    during_update = fields.Boolean(readonly=True)  # (0.6.2: noted while modules were installed or upgraded)
    paths = fields.Text(readonly=True)  # (0.9.0: the only pages it touches, one a line; empty: every page)


class MtbgEdgeCacheLog(models.Model):
    _name = 'mtbg.edge.cache.log'
    _description = 'Cloudflare page cache: purges'
    _order = 'id desc'

    def _mtbg_check_admin(self):
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(self.env._("Only an administrator can empty the page cache."))

    def _mtbg_purged(self, done, message):
        if not done:
            log = self.sudo().search([], limit=1)
            raise UserError(self.env._("Cloudflare did not purge: %s", log.message or ''))
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'success', 'message': message,
            'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}}}

    def action_mtbg_purge_now(self):  # (a list's header button: called with the selected rows, none needed)
        """The "Purge pages now" button (settings, purge log; owner 2026-11-01): Cloudflare empties its copies of
        every page now, whatever was edited (0.9.0: the pages only); they are asked for again a minute later."""
        self._mtbg_check_admin()
        done = self.env['mtbg.edge.cache']._mtbg_purge(self.env._("Purged by hand"))
        return self._mtbg_purged(done, self.env._("Cloudflare emptied its copies of the pages."))

    def action_mtbg_purge_everything(self):
        """The emergency "Purge everything" button (0.9.0, with a confirmation): Cloudflare's "purge everything",
        the scripts, styles and pictures too, at every Cloudflare location."""
        self._mtbg_check_admin()
        done = self.env['mtbg.edge.cache']._mtbg_purge(self.env._("Everything purged by hand"), everything=True)
        return self._mtbg_purged(done, self.env._("Cloudflare emptied everything it kept of the site."))

    ok = fields.Boolean(string='Done', readonly=True)
    reason = fields.Char(string='Why', readonly=True)
    message = fields.Char(readonly=True)
    scope = fields.Selection([('everything', 'Everything'), ('pages', 'Every page'), ('some', 'Some pages')],
                             string='Emptied', readonly=True)
    url_count = fields.Integer(string='Addresses', readonly=True)
    request_count = fields.Integer(string='Calls', readonly=True)

    @api.model
    def _mtbg_add(self, ok, reason, message, scope=False, count=0, requests=0):
        self.sudo().create({'ok': ok, 'reason': reason, 'message': message or False, 'scope': scope,
                            'url_count': count, 'request_count': requests})
        old = self.sudo().search([], offset=KEEP_LOG)
        if old:
            old.unlink()
        if not ok:
            _logger.warning("Cloudflare page cache: %s: %s", reason, message)
        else:
            _logger.info("Cloudflare page cache: %s: %s purged (%s addresses, %s calls)", reason, scope, count,
                         requests)
