"""Cloudflare's page cache: what Odoo lets it keep (ir_http.py) and the purge after every change (sources.py).

Every call to Cloudflare's API goes through Cloudflare Connector (0.7.0: ``cloudflare.api.purge``, a soft check):
this module keeps only the website side (which pages, live values, when to purge).

A change is noted in ``mtbg.edge.cache.change`` (a row per saving transaction: never a system parameter, which would
empty Odoo's caches, and never one shared row, which concurrent bookings would fight over). Once the transaction is
committed the zone is purged (Cloudflare's "purge everything", every plan has it) and the rows it covered are deleted;
a purge a few seconds after another one, or one Cloudflare refused, is left to the one-minute job.

Re-fill (0.3.0, edit-only): the pages change only when something on them is edited, and Cloudflare keeps them a
month; its copies of the homepages (/ and /es) are asked for again once a minute after a purge (a burst of edits:
once), and every night (Cloudflare drops copies nobody asked for). The other pages fill on their first visit. Prices,
seats and statuses are never in the pages (they load live: live_values.py).

0.8.0: no dependency on any Tours extension; each says what of it pages show (sources.py).
"""
from datetime import timedelta
import hashlib
import json
import logging
import threading
import time

import requests

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

WARM_DELAY = 60         # seconds after a purge before the homepages are asked for again
WARM_PAUSE = 0.5        # seconds between two pages (www's workers stay free for visitors)
WARM_AGENT = ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36 '
              'MTBG-prefill')
SPACING = 10            # seconds between two purges from one worker (the rest: the one-minute job)
UPDATE_QUIET = 180      # seconds without module updates before their changes are purged (0.6.2: once per update)
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
    def _mtbg_changed(self):
        """A page may show something just saved: purge once this transaction is committed. During a module update
        the change is only noted: the one-minute job purges once, when the updates have been quiet a while."""
        if not self._mtbg_params()['on']:
            return
        cr = self.env.cr
        if self._mtbg_updating():
            if not cr.postcommit.data.get('mtbg_edge_cache_update'):
                cr.postcommit.data['mtbg_edge_cache_update'] = True
                cr.execute("INSERT INTO mtbg_edge_cache_change (create_date, during_update) "
                           "VALUES (now() at time zone 'UTC', true)")
            return
        if cr.postcommit.data.get('mtbg_edge_cache'):
            return
        cr.postcommit.data['mtbg_edge_cache'] = True
        cr.execute("INSERT INTO mtbg_edge_cache_change (create_date) VALUES (now() at time zone 'UTC')")
        dbname = cr.dbname

        @cr.postcommit.add
        def purge():
            with _lock:
                if time.monotonic() - _last.get(dbname, 0) < SPACING:
                    return  # (the one-minute job sends it)
                _last[dbname] = time.monotonic()
            try:
                with self.env.registry.cursor() as new_cr:
                    self.with_env(self.env(cr=new_cr))._mtbg_purge_pending()
            except Exception:  # never fail the saving request: the job retries
                _logger.exception("Cloudflare page cache: purge after a change failed")

    @api.model
    def _mtbg_purge_pending(self):
        """Purge when changes are waiting (the after-save purge and the one-minute job)."""
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
        if self._mtbg_purge(self.env._("Changes saved")):
            Change.search([('id', '<=', last.id)]).unlink()
            return True
        return False

    @api.model
    def _mtbg_purge(self, reason):
        """Cloudflare's "purge everything" for the site's zone, through Cloudflare Connector; logged. True when
        Cloudflare took it."""
        Log = self.env['mtbg.edge.cache.log'].sudo()
        if 'cloudflare.api' not in self.env:
            Log._mtbg_add(False, reason, self.env._(
                "Cloudflare Connector is not installed: install it, then Settings › Cloudflare › Set up Cloudflare."))
            return False
        result = self.env['cloudflare.api'].sudo().purge(everything=True)
        if result.get('ok'):
            Log._mtbg_add(True, reason, '')
            self._mtbg_warm_soon()
            self._mtbg_banner_note()
            return True
        Log._mtbg_add(False, reason, result.get('error') or self.env._("Cloudflare did not purge."))
        return False

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

    JOBS = ('cron_edge_cache_purge', 'cron_edge_cache_warm_home', 'cron_edge_cache_banner')

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
    def _mtbg_warm_soon(self):
        """After a purge: the homepages asked for again in a minute (once for a burst of edits)."""
        cron = self.env.ref('mtbg_tours_edge_cache.cron_edge_cache_warm_home', raise_if_not_found=False)
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
    def _mtbg_warm_paths(self):
        """[(path, language code)]: the homepage in each of the website's languages, where the cache keeps it."""
        website = self.env['website'].sudo().get_current_website()
        default = website.default_lang_id
        prefixes = [('', default.code or 'en_US')] + [
            ('/' + lang.url_code, lang.code) for lang in website.language_ids if lang != default]
        params = self._mtbg_params()
        # (/es: /es/ only redirects to it)
        return [(prefix or '/', code) for prefix, code in prefixes
                if self._mtbg_path_allowed(prefix or '/', params['paths'])]

    @api.model
    def _mtbg_warm(self):
        """Ask Cloudflare for the homepages, one at a time, as an anonymous visitor would (no cookie). Returns
        {path: Cloudflare's answer (HIT, MISS, ...) or the error}."""
        params = self._mtbg_params()
        base = self._mtbg_warm_base()
        if not params['on'] or not params['ttl'] or not base:
            return {}
        done = {}
        for path, code in self._mtbg_warm_paths():
            headers = {'User-Agent': WARM_AGENT, 'Accept-Language': code.split('_')[0]}
            try:
                res = requests.get(base + path, headers=headers, timeout=30, allow_redirects=False)
                done[path] = res.headers.get('cf-cache-status') or str(res.status_code)
            except requests.RequestException as e:
                done[path] = str(e)[:80]
            time.sleep(WARM_PAUSE)
        _logger.info("Cloudflare page cache: homepages re-filled (%s)", ', '.join('%s %s' % kv for kv in done.items()))
        return done


class MtbgEdgeCacheChange(models.Model):
    _name = 'mtbg.edge.cache.change'
    _description = 'Cloudflare page cache: a change to purge'
    _log_access = False

    create_date = fields.Datetime(readonly=True)
    during_update = fields.Boolean(readonly=True)  # (0.6.2: noted while modules were installed or upgraded)


class MtbgEdgeCacheLog(models.Model):
    _name = 'mtbg.edge.cache.log'
    _description = 'Cloudflare page cache: purges'
    _order = 'id desc'

    def action_mtbg_purge_now(self):  # (a list's header button: called with the selected rows, none needed)
        """The "Purge cache now" button (settings, purge log; owner 2026-11-01): Cloudflare empties the page cache
        now, whatever was edited; the homepages are asked for again a minute later."""
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(self.env._("Only an administrator can empty the page cache."))
        if not self.env['mtbg.edge.cache']._mtbg_purge(self.env._("Purged by hand")):
            log = self.sudo().search([], limit=1)
            raise UserError(self.env._("Cloudflare did not purge: %s", log.message or ''))
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'success', 'message': self.env._("Cloudflare emptied the page cache."),
            'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}}}

    ok = fields.Boolean(string='Done', readonly=True)
    reason = fields.Char(readonly=True)
    message = fields.Char(readonly=True)

    @api.model
    def _mtbg_add(self, ok, reason, message):
        self.sudo().create({'ok': ok, 'reason': reason, 'message': message or False})
        old = self.sudo().search([], offset=KEEP_LOG)
        if old:
            old.unlink()
        if not ok:
            _logger.warning("Cloudflare page cache: %s: %s", reason, message)
