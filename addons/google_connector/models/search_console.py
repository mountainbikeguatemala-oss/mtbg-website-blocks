"""Google Search Console: the connector's "search_console" app imports the website's real search figures (clicks,
impressions, CTR, average position) from the Search Analytics API (owner, 2026-11-16: "Search Console access so we
can see real rankings, clicks and positions"). Read only (webmasters.readonly), with the connector's Google account.

* The property: chosen in the app's settings from the account's Search Console sites (sites.list), an
  ``sc-domain:example.com`` domain property preferred over a URL-prefix one.
* Every night (early morning in the company's time zone, else UTC) the last REFRESH_DAYS days are read again
  (Google's figures settle 2-3 days late); after the property is chosen, the last BACKFILL_DAYS days (Google keeps
  16 months) come in CHUNK_DAYS-day chunks, one chunk an hour.
* Per day: the totals (google.search.console.day), and the rows (google.search.console.row) by query and by page
  (the day's top TOP_ROWS), by country and by device. A day read again replaces its rows (idempotent).
* Kept KEEP_DAYS days (18 months); every run is in the sync log; the last error shows on the app's card."""
import logging
from datetime import date, datetime, timedelta
from urllib.parse import quote

import pytz

from odoo import api, fields, models

from .client import GoogleError

_logger = logging.getLogger(__name__)

APP = "search_console"
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
API = "https://searchconsole.googleapis.com/webmasters/v3"
SITES_URL = API + "/sites"
QUERY_URL = API + "/sites/{site}/searchAnalytics/query"
REFRESH_DAYS = 3
BACKFILL_DAYS = 486      # 16 months: what Google keeps
CHUNK_DAYS = 30          # one backfill chunk per hourly run (2 calls a day of the chunk + 3)
KEEP_DAYS = 548          # 18 months
TOP_ROWS = 250           # the day's top queries / pages
PAGE_ROWS = 25000        # Google's most rows per answer
NIGHT_HOUR = 4           # the nightly import's local hour (or the first run after it)
SUMMARY_DAYS = 28
LAST_NIGHT_PARAM = "google_connector.search_console_last_night"
KINDS = [("query", "Query"), ("page", "Page"), ("country", "Country"), ("device", "Device")]
PERMISSIONS = [("siteOwner", "Owner"), ("siteFullUser", "Full user"), ("siteRestrictedUser", "Restricted user"),
               ("siteUnverifiedUser", "Not verified")]


def gsc_today():
    """Search Console's days are Pacific Time days."""
    return datetime.now(pytz.timezone("America/Los_Angeles")).date()


def site_rank(site_url, permission):
    """The order the properties are offered in: a domain property first, then by access."""
    order = [p for p, _label in PERMISSIONS]
    return (0 if site_url.startswith("sc-domain:") else 1,
            order.index(permission) if permission in order else len(order), site_url)


def weighted(totals):
    """{clicks, impressions, ctr, position} of summed rows (position weighted by impressions, as Google does)."""
    clicks, impressions, position_sum = totals
    return {"clicks": clicks, "impressions": impressions,
            "ctr": clicks / impressions if impressions else 0.0,
            "position": position_sum / impressions if impressions else 0.0}


def change(now, before):
    """The relative change (0.12 = +12%), None without a previous figure."""
    return (now - before) / before if before else None


class GoogleConnector(models.AbstractModel):
    _inherit = "google.connector"

    @api.model
    def _google_app_specs(self):
        """The Search Console app: the connector brings it itself (nothing else to install)."""
        return dict(super()._google_app_specs(), **{APP: {
            "label": "Google Search Console", "module": "google_connector", "sequence": 70,
            "read_scopes": SCOPES, "needs_account": True,
            "settings_action": "google_connector.action_search_console_setup",
            "description": "The website's real Google searches (clicks, impressions, CTR, position), imported every "
                           "night into Search Console reports (read only). Setup: switch it on, then Google accounts "
                           "› Reconnect the Google account that owns the property in Search Console (to grant read "
                           "access to Search Console), then Settings: choose the property from the dropdown, Save.",
        }})

    @api.model
    def _google_search_console_ready(self):
        app = self._google_app(APP)
        return bool(app) and app.status == "ready"

    @api.model
    def _google_search_console_sites(self):
        """[{site_url, permission}] the app's Google account sees in Search Console (GoogleError on failure)."""
        data = self.client(APP).get(SITES_URL)
        return [{"site_url": entry["siteUrl"], "permission": entry.get("permissionLevel") or False}
                for entry in data.get("siteEntry") or [] if entry.get("siteUrl")]

    @api.model
    def _google_search_console_query(self, site_url, start, end, dimensions, row_limit=PAGE_ROWS):
        """Search Analytics rows of ``site_url`` from ``start`` to ``end`` (dates) by ``dimensions``: every page of
        rows up to ``row_limit`` ([{keys, clicks, impressions, ctr, position}])."""
        client = self.client(APP)
        rows, start_row = [], 0
        while True:
            limit = min(PAGE_ROWS, row_limit - len(rows))
            data = client.post(QUERY_URL.format(site=quote(site_url, safe="")), json={
                "startDate": start.isoformat(), "endDate": end.isoformat(), "dimensions": dimensions,
                "type": "web", "dataState": "all", "rowLimit": limit, "startRow": start_row})
            page = (data.get("rows") or []) if isinstance(data, dict) else []
            rows += page
            start_row += len(page)
            if len(page) < limit or len(rows) >= row_limit:
                return rows


class GoogleConnectorApp(models.Model):
    _inherit = "google.connector.app"

    @api.model
    def google_card_data(self):
        """The Search Console card also shows its SEO summary (28 days vs the 28 before) and its last error."""
        cards = super().google_card_data()
        for card in cards:
            if card["code"] == APP:
                site = self.env["google.search.console.site"].sudo()._sc_selected()
                card["summary"] = site._sc_summary_text() if site else ""
                card["error"] = site._sc_problem() if card["on"] else ""
        return cards


class SearchConsoleSite(models.Model):
    _name = "google.search.console.site"
    _description = "Search Console property"
    _order = "selected desc, name"

    name = fields.Char(string="Property", required=True, readonly=True,
                       help="sc-domain:example.com (a domain property) or a URL prefix (https://www.example.com/).")
    permission = fields.Selection(PERMISSIONS, string="Access", readonly=True,
                                  help="What the Google account may see of the property in Search Console.")
    listed = fields.Boolean(default=True, readonly=True, help="The Google account still sees it in Search Console.")
    selected = fields.Boolean(string="Imported", readonly=True, help="The property imported every night.")
    backfill_next = fields.Date(readonly=True, help="The newest day still to read of the 16 months' history.")
    backfill_done = fields.Boolean(readonly=True)
    last_import = fields.Datetime(readonly=True)
    last_error = fields.Text(readonly=True)
    first_day = fields.Date(compute="_compute_days")
    last_day = fields.Date(compute="_compute_days")

    _name_unique = models.Constraint("UNIQUE(name)", "One row per Search Console property.")

    def _compute_days(self):
        groups = {site.id: (first, last) for site, first, last in self.env["google.search.console.day"]._read_group(
            [("site_id", "in", self.ids)], ["site_id"], ["date:min", "date:max"])}
        for site in self:
            site.first_day, site.last_day = groups.get(site.id, (False, False))

    @api.model
    def _sc_selected(self):
        return self.search([("selected", "=", True)], limit=1)

    @api.model
    def _sc_refresh_sites(self):
        """The account's properties from Google (sites.list): new ones added, gone ones marked not listed."""
        found = self.env["google.connector"]._google_search_console_sites()
        sites = {site.name: site for site in self.with_context(active_test=False).search([])}
        for entry in found:
            values = {"permission": entry["permission"], "listed": True}
            if entry["site_url"] in sites:
                sites.pop(entry["site_url"]).write(values)
            else:
                self.create(dict(values, name=entry["site_url"]))
        for site in sites.values():
            site.listed = False
        return self.search([("listed", "=", True)])

    @api.model
    def _sc_preferred(self, sites):
        """The property to offer first: the one imported, else a domain property, else the best access."""
        chosen = sites.filtered("selected")
        if chosen:
            return chosen[:1]
        return sites.sorted(lambda s: site_rank(s.name, s.permission))[:1]

    def _sc_select(self):
        """Import this property from now on (its history comes over the next hours)."""
        self.ensure_one()
        self.search([("selected", "=", True), ("id", "!=", self.id)]).write({"selected": False})
        values = {"selected": True, "last_error": False}
        if not self.backfill_done and not self.backfill_next:
            values["backfill_next"] = gsc_today() - timedelta(days=1)
        self.write(values)

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------
    def _sc_import_range(self, start, end):
        """Read ``start`` to ``end`` from Google, then replace those days' figures (nothing is replaced when a call
        fails). Returns (days, rows) written."""
        self.ensure_one()
        Connector = self.env["google.connector"]
        totals = Connector._google_search_console_query(self.name, start, end, ["date"])
        rows = {}
        for kind in ("country", "device"):
            rows[kind] = Connector._google_search_console_query(self.name, start, end, ["date", kind])
        for kind in ("query", "page"):
            rows[kind] = []
            day = start
            while day <= end:
                rows[kind] += Connector._google_search_console_query(self.name, day, day, ["date", kind],
                                                                     row_limit=TOP_ROWS)
                day += timedelta(days=1)
        return self._sc_store(start, end, totals, rows)

    def _sc_store(self, start, end, totals, rows):
        self.ensure_one()
        Day = self.env["google.search.console.day"].sudo()
        Row = self.env["google.search.console.row"].sudo()
        days = {day.date: day for day in Day.search([("site_id", "=", self.id), ("date", ">=", start),
                                                     ("date", "<=", end)])}
        new_days = []
        for row in totals:
            values = {"clicks": int(row.get("clicks") or 0), "impressions": int(row.get("impressions") or 0),
                      "ctr": float(row.get("ctr") or 0.0), "position": float(row.get("position") or 0.0)}
            when = date.fromisoformat(row["keys"][0])
            if when in days:
                days[when].write(values)
            else:
                new_days.append(dict(values, site_id=self.id, date=when))
        Day.create(new_days)
        Row.search([("site_id", "=", self.id), ("date", ">=", start), ("date", "<=", end),
                    ("kind", "in", list(rows))]).unlink()
        new_rows = [{"site_id": self.id, "date": date.fromisoformat(row["keys"][0]), "kind": kind,
                     "key": row["keys"][1].upper() if kind in ("country", "device") else row["keys"][1],
                     "clicks": int(row.get("clicks") or 0), "impressions": int(row.get("impressions") or 0),
                     "ctr": float(row.get("ctr") or 0.0), "position": float(row.get("position") or 0.0)}
                    for kind, kind_rows in rows.items() for row in kind_rows if len(row.get("keys") or []) > 1]
        Row.create(new_rows)
        return len(totals), len(new_rows)

    def _sc_run(self, operation, start, end):
        """One import into the sync log; a Google error is kept on the property (and the log), not raised."""
        self.ensure_one()
        Connector = self.env["google.connector"]
        try:
            with Connector.sync_log(APP, operation) as log:
                try:
                    days, rows = self._sc_import_range(start, end)
                except GoogleError as error:
                    raise GoogleError(self._sc_error_text(error), status=error.status, auth=error.auth,
                                      retryable=error.retryable, missing_scopes=error.missing_scopes) from error
                log.add(updated=days, created=rows, note="%s %s – %s" % (self.name, start, end))
        except GoogleError as error:
            _logger.warning("Search Console %s (%s): %s", operation, self.name, error)
            self.write({"last_error": str(error)})
            return False
        self.write({"last_import": fields.Datetime.now(), "last_error": False})
        return True

    def _sc_error_text(self, error):
        """A Google error in words the administrator can act on."""
        message = str(error)
        if error.missing_scopes or "not granted" in message:
            return self.env._("Search Console access is not granted yet: Settings › Google › Google accounts › "
                              "Reconnect (the account that owns the property), then accept Search Console.")
        if error.status == 429:
            return self.env._("Google's Search Console quota is reached for now: the import tries again at its "
                              "next run. Google said: %s", message[:300])
        if error.status == 403:
            return self.env._("Google refused %(site)s: the connected Google account must be an Owner or Full user "
                              "of this property in Search Console, and the Google Search Console API must be "
                              "enabled in the Google Cloud project (Set up Google › APIs). Google said: %(error)s",
                              site=self.name, error=message[:300])
        if error.auth:
            return self.env._("The Google sign-in is no longer valid: Settings › Google › Google accounts › "
                              "Reconnect. Google said: %s", message[:300])
        return self.env._("Google: %s", message[:300])

    def _sc_refresh(self):
        """The last REFRESH_DAYS days read again."""
        end = gsc_today() - timedelta(days=1)
        return self._sc_run("Nightly import", end - timedelta(days=REFRESH_DAYS - 1), end)

    def _sc_backfill_chunk(self):
        """The next CHUNK_DAYS days of the history (newest first), until 16 months are in."""
        self.ensure_one()
        oldest = gsc_today() - timedelta(days=BACKFILL_DAYS)
        end = self.backfill_next or gsc_today() - timedelta(days=1)
        if self.backfill_done or end < oldest:
            self.write({"backfill_done": True, "backfill_next": False})
            return True
        start = max(oldest, end - timedelta(days=CHUNK_DAYS - 1))
        if not self._sc_run("History import", start, end):
            return False  # the same chunk again at the next run
        done = start <= oldest
        self.write({"backfill_next": False if done else start - timedelta(days=1), "backfill_done": done})
        return True

    @api.model
    def _sc_local_now(self):
        admin = self.env.ref("base.user_admin", raise_if_not_found=False)
        tz = self.env.company.partner_id.tz or (admin.tz if admin else False)
        try:
            zone = pytz.timezone(tz or "UTC")
        except pytz.UnknownTimeZoneError:
            zone = pytz.utc
        return datetime.now(zone)

    @api.model
    def _cron_import(self, now=None):
        """Hourly: once a day early in the morning (company time zone, else UTC) the nightly import and the clean-up;
        each hour one chunk of the history until it is in. Nothing when the app is off."""
        Connector = self.env["google.connector"]
        self.env["ir.ui.menu"].sudo()._sc_place_menus()
        app = Connector._google_app(APP)
        if not app or not app.on:
            return
        now = now or self._sc_local_now()
        ICP = self.env["ir.config_parameter"].sudo()
        night = now.hour >= NIGHT_HOUR and ICP.get_param(LAST_NIGHT_PARAM) != now.date().isoformat()
        site = self._sc_selected()
        if night:
            ICP.set_param(LAST_NIGHT_PARAM, now.date().isoformat())
            self.env["google.search.console.day"]._sc_clean()
            problem = site._sc_blocker() if site else self._sc_blocker()
            if problem:
                self.env["google.connector.log"].sudo().create({
                    "app_code": APP, "operation": "Nightly import", "state": "failed", "note": problem,
                    "finished_at": fields.Datetime.now()})
                if site:
                    site.last_error = problem
                return
            site._sc_refresh()
        if site and not site.backfill_done and Connector._google_search_console_ready():
            site._sc_backfill_chunk()

    def _sc_blocker(self):
        """What stops the import before it calls Google, in plain words ("" when nothing does)."""
        app = self.env["google.connector"]._google_app(APP)
        if not app or not app.on:
            return self.env._("Google Search Console is off (Settings › Google).")
        if app.status == "no_account":
            return self.env._("No Google account is connected: Set up Google › Sign in, with the account that owns "
                              "the property in Search Console.")
        if app.status == "missing":
            return self.env._("Search Console access is not granted yet: Settings › Google › Google accounts › "
                              "Reconnect (the account that owns the property), then accept Search Console.")
        if not self or not self.selected:
            return self.env._("No Search Console property chosen yet: Settings › Google › Google Search Console › "
                              "Settings, choose the property.")
        return ""

    def _sc_problem(self):
        """What the card shows: what stops the import, else the last import's error ("" when all is well)."""
        return self._sc_blocker() or (self.last_error or "") if self else self._sc_blocker()

    def _sc_progress(self):
        """Where the import is: the days imported, the history still coming."""
        self.ensure_one()
        if not self.last_day:
            return self.env._("Nothing imported yet.")
        if self.backfill_done:
            return self.env._("Imported: %(first)s to %(last)s (the whole history Google keeps).",
                              first=self.first_day, last=self.last_day)
        return self.env._("Imported: %(first)s to %(last)s; the older history is still coming (a chunk an hour).",
                          first=self.first_day, last=self.last_day)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    def _sc_summary(self, end=None):
        """The last SUMMARY_DAYS days up to ``end`` (the newest day imported) against the SUMMARY_DAYS before:
        {'current': figures, 'previous': figures, 'change': {clicks, impressions: relative; ctr: points;
        position: places}, 'start', 'end'}, or {} with nothing imported."""
        self.ensure_one()
        Day = self.env["google.search.console.day"].sudo()
        end = end or self.last_day
        if not end:
            return {}
        start = end - timedelta(days=SUMMARY_DAYS - 1)
        before_end = start - timedelta(days=1)
        before_start = before_end - timedelta(days=SUMMARY_DAYS - 1)

        def figures(first, last):
            days = Day.search([("site_id", "=", self.id), ("date", ">=", first), ("date", "<=", last)])
            return weighted((sum(days.mapped("clicks")), sum(days.mapped("impressions")),
                             sum(d.position * d.impressions for d in days)))

        current, previous = figures(start, end), figures(before_start, before_end)
        return {"start": start, "end": end, "current": current, "previous": previous, "change": {
            "clicks": change(current["clicks"], previous["clicks"]),
            "impressions": change(current["impressions"], previous["impressions"]),
            "ctr": (current["ctr"] - previous["ctr"]) * 100 if previous["impressions"] else None,
            "position": current["position"] - previous["position"] if previous["impressions"] else None}}

    def _sc_summary_text(self):
        summary = self._sc_summary()
        if not summary:
            return self.env._("%s: nothing imported yet (the first import comes within the hour once the app is "
                              "ready).", self.name)
        cur, delta = summary["current"], summary["change"]

        def pct(value):
            return "" if value is None else " (%+.0f%%)" % (value * 100)

        def pts(value, unit):
            return "" if value is None else " (%+.1f%s)" % (value, " " + unit if unit else "")

        return self.env._("Last %(days)s days to %(end)s: %(clicks)s clicks%(dc)s, %(impr)s impressions%(di)s, CTR "
                          "%(ctr).1f%%%(dctr)s, average position %(pos).1f%(dpos)s (vs the %(days)s days before).",
                          days=SUMMARY_DAYS, end=summary["end"], clicks="{:,}".format(cur["clicks"]),
                          dc=pct(delta["clicks"]), impr="{:,}".format(cur["impressions"]),
                          di=pct(delta["impressions"]), ctr=cur["ctr"] * 100, dctr=pts(delta["ctr"], "pt"),
                          pos=cur["position"], dpos=pts(delta["position"], ""))


class SearchConsoleDay(models.Model):
    _name = "google.search.console.day"
    _description = "Search Console day"
    _order = "date desc"
    _rec_name = "date"

    site_id = fields.Many2one("google.search.console.site", string="Property", required=True, ondelete="cascade",
                              index=True)
    date = fields.Date(required=True, index=True)
    clicks = fields.Integer(aggregator="sum")
    impressions = fields.Integer(aggregator="sum")
    ctr = fields.Float(string="CTR", aggregator="avg", digits=(16, 4))
    position = fields.Float(string="Average Position", aggregator="avg", digits=(16, 1),
                            help="Google's average position that day (1 = the top result).")

    _site_date_unique = models.Constraint("UNIQUE(site_id, date)", "One row per property and day.")

    @api.model
    def _sc_clean(self, today=None):
        """Keep KEEP_DAYS days (18 months)."""
        limit = (today or gsc_today()) - timedelta(days=KEEP_DAYS)
        self.sudo().search([("date", "<", limit)]).unlink()
        self.env["google.search.console.row"].sudo().search([("date", "<", limit)]).unlink()


class SearchConsoleRow(models.Model):
    _name = "google.search.console.row"
    _description = "Search Console row"
    _order = "date desc, clicks desc, impressions desc"
    _rec_name = "key"

    site_id = fields.Many2one("google.search.console.site", string="Property", required=True, ondelete="cascade",
                              index=True)
    date = fields.Date(required=True, index=True)
    kind = fields.Selection(KINDS, required=True, index=True)
    key = fields.Char(string="Query / Page / Country / Device", required=True)
    clicks = fields.Integer(aggregator="sum")
    impressions = fields.Integer(aggregator="sum")
    ctr = fields.Float(string="CTR", aggregator="avg", digits=(16, 4))
    position = fields.Float(string="Average Position", aggregator="avg", digits=(16, 1))

    _site_date_kind_index = models.Index("(site_id, date, kind)")


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    @api.model
    def _sc_place_menus(self):
        """The Search Console reports go under Website › Reporting when Website is installed, else under their own
        menu (Website is no dependency: it may come after this module)."""
        reporting = self.env.ref("website.menu_reporting", raise_if_not_found=False)
        root = self.env.ref("google_connector.menu_search_console_root", raise_if_not_found=False)
        if not root:
            return
        parent = reporting or root
        leaves = self.browse([menu.id for menu in (
            self.env.ref("google_connector.menu_search_console_%s" % name, raise_if_not_found=False)
            for name in ("performance", "rows", "position")) if menu])
        leaves.filtered(lambda m: m.parent_id != parent).write({"parent_id": parent.id})
        if root.active != (not reporting):
            root.active = not reporting
