from datetime import date, datetime, timedelta
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.google_connector.models import client as client_module
from odoo.addons.google_connector.models import search_console as sc
from odoo.addons.google_connector.models.client import GoogleError

from .test_connector import Response

TODAY = date(2026, 11, 16)
DOMAIN = "sc-domain:example.com"
PREFIX = "https://www.example.com/"


@tagged("post_install", "-at_install")
class TestSearchConsole(TransactionCase):
    """1.7.0: the Google Search Console app (sites.list, searchAnalytics.query, nightly import, history, summary)."""

    def setUp(self):
        super().setUp()
        patcher = patch.object(sc, "gsc_today", lambda: TODAY)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.G = self.env["google.connector"]
        self.Site = self.env["google.search.console.site"]
        self.Day = self.env["google.search.console.day"]
        self.Row = self.env["google.search.console.row"]
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("google_connector.per_second", 100000)
        ICP.set_param("google_connector.per_day", 1000000)
        ICP.set_param(sc.LAST_NIGHT_PARAM, False)
        self.G._google_set_credentials(client_id="cid", client_secret="secret")
        self.env["google.connector.account"].search([]).write({"state": "draft"})
        self.account = self.env["google.connector.account"].create({
            "name": "owner@example.com", "email": "owner@example.com", "state": "connected", "refresh_token": "r",
            "access_token": "a", "token_expiry": 9999999999, "granted_scopes": "openid %s" % sc.SCOPES[0]})
        self.G._google_sync_apps()
        self.app = self.G._google_app(sc.APP)
        self.app.write({"on": True, "account_id": self.account.id})
        self.sites = [{"siteUrl": PREFIX, "permissionLevel": "siteOwner"},
                      {"siteUrl": DOMAIN, "permissionLevel": "siteFullUser"},
                      {"siteUrl": "https://other.example.org/", "permissionLevel": "siteUnverifiedUser"}]
        self.clicks = 10
        self.fail = None
        self.calls = []
        patcher = patch.object(client_module.requests, "request", side_effect=self._fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _fake(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs.get("json")))
        if self.fail:
            return Response(self.fail, {"error": {"message": "refused"}})
        if url == sc.SITES_URL:
            return Response(200, {"siteEntry": self.sites})
        body = kwargs["json"]
        start, end = date.fromisoformat(body["startDate"]), date.fromisoformat(body["endDate"])
        dims = body["dimensions"]
        rows, day = [], start
        while day <= end:
            keys = {"country": ["gtm", "usa"], "device": ["MOBILE", "DESKTOP"], "query": ["bike tour", "mtb"],
                    "page": [PREFIX, PREFIX + "tours"]}.get(dims[-1], [None])
            for key in keys:
                rows.append({"keys": [day.isoformat()] + ([key] if key else []), "clicks": self.clicks,
                             "impressions": 100, "ctr": self.clicks / 100, "position": 5.5})
            day += timedelta(days=1)
        return Response(200, {"rows": rows[body["startRow"]:body["startRow"] + body["rowLimit"]]})

    def _queries(self):
        return [body for _m, url, body in self.calls if url != sc.SITES_URL]

    # properties
    def test_sites_list_prefers_a_domain_property(self):
        sites = self.Site._sc_refresh_sites()
        self.assertEqual(len(sites), 3)
        self.assertEqual(self.Site._sc_preferred(sites).name, DOMAIN)
        wizard = self.env["google.search.console.setup"].create({})
        self.assertEqual(wizard.site_id.name, DOMAIN, "the dropdown offers the domain property first")
        self.assertEqual(wizard.site_count, 3)
        self.sites = self.sites[:1]
        self.Site._sc_refresh_sites()
        self.assertFalse(self.Site.search([("name", "=", DOMAIN)]).listed, "a property no longer seen is not offered")

    def test_url_prefix_property_end_to_end(self):
        self.sites = [{"siteUrl": PREFIX, "permissionLevel": "siteOwner"}]
        wizard = self.env["google.search.console.setup"].create({})
        self.assertEqual(wizard.site_id.name, PREFIX, "a URL-prefix property is the default without a domain one")
        wizard.action_save()
        site = self.Site._sc_selected()
        self.assertEqual(site.name, PREFIX)
        self.assertEqual(site.backfill_next, TODAY - timedelta(days=1), "the history starts from yesterday")
        self.calls.clear()
        self.assertTrue(site._sc_refresh())
        urls = {url for _m, url, _b in self.calls}
        self.assertEqual(urls, {sc.API + "/sites/https%3A%2F%2Fwww.example.com%2F/searchAnalytics/query"},
                         "the siteUrl is encoded whole in the address")
        self.assertEqual(self.Day.search_count([("site_id", "=", site.id)]), 3)

    def test_domain_property_address(self):
        site = self.Site.create({"name": DOMAIN})
        site._sc_select()
        site._sc_refresh()
        self.assertIn(sc.API + "/sites/sc-domain%3Aexample.com/searchAnalytics/query",
                      {url for _m, url, _b in self.calls})

    # import
    def test_import_parses_rows_and_is_idempotent(self):
        site = self.Site.create({"name": DOMAIN})
        start, end = date(2026, 11, 1), date(2026, 11, 2)
        site._sc_import_range(start, end)
        day = self.Day.search([("site_id", "=", site.id), ("date", "=", start)])
        self.assertEqual((day.clicks, day.impressions, day.ctr, day.position), (10, 100, 0.1, 5.5))
        rows = self.Row.search([("site_id", "=", site.id)])
        self.assertEqual(len(rows), 2 * 8, "2 queries, 2 pages, 2 countries, 2 devices a day")
        self.assertEqual(set(rows.filtered(lambda r: r.kind == "country").mapped("key")), {"GTM", "USA"})
        self.assertEqual(set(rows.filtered(lambda r: r.kind == "query").mapped("key")), {"bike tour", "mtb"})
        queries = self._queries()
        per_day = [q for q in queries if q["dimensions"] == ["date", "query"]]
        self.assertEqual(len(per_day), 2, "the top queries are read day by day")
        self.assertEqual({(q["startDate"], q["rowLimit"]) for q in per_day},
                         {("2026-11-01", sc.TOP_ROWS), ("2026-11-02", sc.TOP_ROWS)})
        self.clicks = 20
        site._sc_import_range(start, end)
        self.assertEqual(self.Day.search_count([("site_id", "=", site.id)]), 2, "a day read again is updated")
        self.assertEqual(day.clicks, 20)
        self.assertEqual(self.Row.search_count([("site_id", "=", site.id)]), 16, "its rows replaced, not doubled")
        self.assertEqual(set(self.Row.search([("site_id", "=", site.id)]).mapped("clicks")), {20})

    def test_paging_of_large_answers(self):
        with patch.object(sc, "PAGE_ROWS", 3):
            rows = self.G._google_search_console_query(DOMAIN, date(2026, 11, 1), date(2026, 11, 3),
                                                       ["date", "country"])
        self.assertEqual(len(rows), 6)
        self.assertEqual([q["startRow"] for q in self._queries()], [0, 3, 6])

    def test_nightly_refresh_reads_the_last_three_days(self):
        site = self.Site.create({"name": DOMAIN})
        site._sc_select()
        site.backfill_done = True
        self.Site._cron_import(now=datetime(2026, 11, 16, 5, 0))
        totals = [q for q in self._queries() if q["dimensions"] == ["date"]]
        self.assertEqual([(q["startDate"], q["endDate"]) for q in totals], [("2026-11-13", "2026-11-15")])
        log = self.env["google.connector.log"].search([("app_code", "=", sc.APP)], limit=1)
        self.assertEqual((log.operation, log.state, log.updated), ("Nightly import", "done", 3))
        self.calls.clear()
        self.Site._cron_import(now=datetime(2026, 11, 16, 6, 0))
        self.assertFalse(self.calls, "once a night")
        self.Site._cron_import(now=datetime(2026, 11, 17, 3, 0))
        self.assertFalse(self.calls, "early morning, not before")

    def test_backfill_in_chunks(self):
        site = self.Site.create({"name": PREFIX})
        site._sc_select()
        with patch.object(sc, "BACKFILL_DAYS", 70), patch.object(sc, "CHUNK_DAYS", 30):
            self.assertTrue(site._sc_backfill_chunk())
            self.assertEqual(site.backfill_next, TODAY - timedelta(days=31))
            self.fail = 403
            self.assertFalse(site._sc_backfill_chunk())
            self.assertEqual(site.backfill_next, TODAY - timedelta(days=31), "a refused chunk comes again")
            self.assertIn("Owner or Full user", site.last_error)
            self.fail = None
            self.assertTrue(site._sc_backfill_chunk())
            self.assertTrue(site._sc_backfill_chunk())
            self.assertTrue(site.backfill_done)
            self.assertFalse(site.backfill_next)
            self.assertFalse(site.last_error)
        self.assertEqual(self.Day.search_count([("site_id", "=", site.id)]), 70)
        self.assertEqual(site.first_day, TODAY - timedelta(days=70))
        chunks = [(q["startDate"], q["endDate"]) for q in self._queries() if q["dimensions"] == ["date"]]
        self.assertEqual(chunks, [("2026-10-17", "2026-11-15"), ("2026-09-17", "2026-10-16"),
                                  ("2026-09-17", "2026-10-16"), ("2026-09-07", "2026-09-16")],
                         "newest first; the refused chunk asked again")

    # summary
    def test_summary_math(self):
        site = self.Site.create({"name": DOMAIN})
        end = date(2026, 11, 13)
        values = []
        for offset in range(56):
            current = offset < 28
            values.append({"site_id": site.id, "date": end - timedelta(days=offset),
                           "clicks": 20 if current else 10, "impressions": 400 if current else 400,
                           "ctr": 0.05 if current else 0.025,
                           "position": (4.0 if offset % 2 else 8.0) if current else 10.0})
        values.append({"site_id": site.id, "date": end - timedelta(days=60), "clicks": 999, "impressions": 999,
                       "position": 1.0})
        self.Day.create(values)
        summary = site._sc_summary()
        self.assertEqual(summary["end"], end)
        self.assertEqual(summary["start"], end - timedelta(days=27))
        cur, prev, delta = summary["current"], summary["previous"], summary["change"]
        self.assertEqual((cur["clicks"], cur["impressions"]), (560, 11200))
        self.assertEqual((prev["clicks"], prev["impressions"]), (280, 11200), "the day 60 days back is outside")
        self.assertAlmostEqual(cur["ctr"], 0.05)
        self.assertAlmostEqual(cur["position"], 6.0, msg="weighted by impressions")
        self.assertAlmostEqual(delta["clicks"], 1.0)
        self.assertAlmostEqual(delta["impressions"], 0.0)
        self.assertAlmostEqual(delta["ctr"], 2.5, msg="in points")
        self.assertAlmostEqual(delta["position"], -4.0)
        site._sc_select()
        card = [c for c in self.env["google.connector.app"].google_card_data() if c["code"] == sc.APP][0]
        self.assertIn("560 clicks (+100%)", card["summary"])
        self.assertIn("average position 6.0 (-4.0)", card["summary"])
        self.assertFalse(card["error"])

    # errors
    def test_scope_missing(self):
        self.account.granted_scopes = "openid"
        self.app.invalidate_recordset(["status"])
        self.assertEqual(self.app.status, "missing")
        wizard = self.env["google.search.console.setup"].create({})
        self.assertTrue(wizard.needs_reconnect)
        self.assertIn("Reconnect", wizard.problem)
        self.assertFalse(self.calls, "nothing asked of Google without the access")
        action = wizard.action_reconnect()
        self.assertEqual(action["type"], "ir.actions.act_url")
        self.assertIn("webmasters.readonly", action["url"])
        site = self.Site.create({"name": DOMAIN})
        site._sc_select()
        self.assertFalse(site._sc_refresh())
        self.assertIn("Reconnect", site.last_error)
        self.Site._cron_import(now=datetime(2026, 11, 16, 5, 0))
        log = self.env["google.connector.log"].search([("app_code", "=", sc.APP)], limit=1)
        self.assertEqual(log.state, "failed")
        self.assertIn("Reconnect", log.note)
        card = [c for c in self.env["google.connector.app"].google_card_data() if c["code"] == sc.APP][0]
        self.assertIn("Reconnect", card["error"])

    def test_no_property_chosen(self):
        self.Site._cron_import(now=datetime(2026, 11, 16, 5, 0))
        log = self.env["google.connector.log"].search([("app_code", "=", sc.APP)], limit=1)
        self.assertEqual(log.state, "failed")
        self.assertIn("No Search Console property chosen", log.note)
        self.assertFalse(self.calls)

    def test_error_words(self):
        site = self.Site.create({"name": DOMAIN})
        self.assertIn("quota", site._sc_error_text(GoogleError("Google error 429: Quota exceeded", status=429)))
        self.assertIn("Owner or Full user", site._sc_error_text(GoogleError("Google error 403: x", status=403)))
        self.fail = 400
        self.assertFalse(site._sc_refresh())
        self.assertIn("Google", site.last_error)
        log = self.env["google.connector.log"].search([("app_code", "=", sc.APP)], limit=1)
        self.assertEqual(log.state, "failed")

    def test_off_does_nothing(self):
        self.app.on = False
        self.Site._cron_import(now=datetime(2026, 11, 16, 5, 0))
        self.assertFalse(self.calls)
        self.assertFalse(self.env["google.connector.log"].search([("app_code", "=", sc.APP)]))

    # retention, menus
    def test_retention_keeps_18_months(self):
        site = self.Site.create({"name": DOMAIN})
        old, kept = TODAY - timedelta(days=sc.KEEP_DAYS + 1), TODAY - timedelta(days=sc.KEEP_DAYS)
        self.Day.create([{"site_id": site.id, "date": old}, {"site_id": site.id, "date": kept}])
        self.Row.create([{"site_id": site.id, "date": old, "kind": "query", "key": "a"},
                         {"site_id": site.id, "date": kept, "kind": "query", "key": "b"}])
        self.Day._sc_clean()
        self.assertEqual(self.Day.search([("site_id", "=", site.id)]).mapped("date"), [kept])
        self.assertEqual(self.Row.search([("site_id", "=", site.id)]).mapped("key"), ["b"])

    def test_menus_placed(self):
        self.env["ir.ui.menu"]._sc_place_menus()
        root = self.env.ref("google_connector.menu_search_console_root")
        leaf = self.env.ref("google_connector.menu_search_console_performance")
        reporting = self.env.ref("website.menu_reporting", raise_if_not_found=False)
        self.assertEqual(leaf.parent_id, reporting or root)
        self.assertEqual(root.active, not reporting)

    def test_apis_and_scope_words(self):
        from odoo.addons.google_connector.models.catalog import APIS
        from odoo.addons.google_connector.wizard.setup import SCOPE_WORDS
        self.assertIn(("searchconsole.googleapis.com", "Google Search Console API"), APIS[sc.APP])
        self.assertIn(sc.SCOPES[0], SCOPE_WORDS)
        self.assertIn(sc.SCOPES[0], self.G._google_scopes_wanted(), "a sign-in asks for Search Console's access")
        self.assertEqual(self.app.read_scopes, sc.SCOPES[0])

