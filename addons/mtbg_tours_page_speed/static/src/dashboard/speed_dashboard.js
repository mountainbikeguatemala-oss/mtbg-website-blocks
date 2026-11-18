/**
 * The speed log's dashboard (page speed 0.9.0, owner 2026-11-17: "the chart should be first on the page, big, with
 * buttons for different stats and overlays"; "table should be its own page"). Website › Reporting › Speed log:
 *
 * 1. one big chart of the nights' averages: a stat chosen by its button, phone and computer as two lines; overlays
 *    (each switched on or off): a second stat on a right axis, the stat's limit, one of the worst pages' own line;
 *    7, 30 or 90 nights. The choice is kept in this browser.
 * 2. last night against the 7 nights before (score, LCP, pages over the limit, pages not measured), phone and computer;
 * 3. the worst pages (phone or computer), each opening its rows;
 * 4. "See all rows": every night's rows (Speed log: all nights).
 *
 * 0.10.0: several websites on one database: one website at a time (a choice above the chart, kept in this browser).
 *
 * The numbers come in one call (mtbg.page.speed.log.mtbg_speed_dashboard); Chart.js is Odoo's own (web.chartjs_lib),
 * loaded when the page opens, as Odoo's graph view does.
 */
import { Component, onWillStart, onWillUnmount, useRef, useState, useEffect } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";
import { _t } from "@web/core/l10n/translation";
import { deserializeDate, formatDate } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { cookie } from "@web/core/browser/cookie";
import { useService } from "@web/core/utils/hooks";

const STORAGE_KEY = "mtbg_tours_page_speed.dashboard";
const RANGES = [7, 30, 90];

/** The stats drawn, their units and which way is better. */
export const STATS = [
    { key: "score", label: _t("Score"), unit: "", digits: 0, higherIsBetter: true },
    { key: "lcp", label: _t("LCP"), unit: " s", digits: 1 },
    { key: "fcp", label: _t("First paint"), unit: " s", digits: 1 },
    { key: "tbt", label: _t("Blocking time"), unit: " ms", digits: 0 },
    { key: "cls", label: _t("CLS"), unit: "", digits: 3 },
    { key: "ttfb", label: _t("Server response"), unit: " ms", digits: 0 },
    { key: "weight_kb", label: _t("Page weight"), unit: " KB", digits: 0 },
];
const STAT = Object.fromEntries(STATS.map((s) => [s.key, s]));

const SCREENS = [
    { key: "mobile", label: _t("Phone") },
    { key: "desktop", label: _t("Computer") },
];

/** The lines' colours (light / dark): phone, computer, a page, the limit. */
function palette() {
    const dark = cookie.get("color_scheme") === "dark";
    return dark
        ? { mobile: "#3987e5", desktop: "#d95926", page: "#9085e9", limit: "#d03b3b",
            ink: "#c3c2b7", grid: "rgba(255,255,255,.12)" }
        : { mobile: "#2a78d6", desktop: "#eb6834", page: "#6250d6", limit: "#d03b3b",
            ink: "#52514e", grid: "rgba(0,0,0,.08)" };
}

export function formatStat(key, value) {
    if (value === null || value === undefined || Number.isNaN(value)) {
        return "–";
    }
    const stat = STAT[key];
    return `${Number(value).toLocaleString(undefined, {
        minimumFractionDigits: stat.digits, maximumFractionDigits: stat.digits })}${stat.unit}`;
}

function readChoice() {
    try {
        return JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "{}") || {};
    } catch {
        return {};
    }
}

function writeChoice(choice) {
    try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(choice));
    } catch {
        // the choice lasts this page only
    }
}

export class SpeedLogDashboard extends Component {
    static template = "mtbg_tours_page_speed.SpeedLogDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.canvas = useRef("canvas");
        this.STATS = STATS;
        this.SCREENS = SCREENS;
        this.RANGES = RANGES;
        this.formatStat = formatStat;
        const saved = readChoice();
        this.state = useState({
            data: null,
            loading: true,
            stat: STAT[saved.stat] ? saved.stat : "lcp",
            overlay: STAT[saved.overlay] ? saved.overlay : "",
            nights: RANGES.includes(saved.nights) ? saved.nights : 30,
            screens: { mobile: saved.mobile !== false, desktop: saved.desktop !== false },
            limit: saved.limit !== false,
            page: saved.page || "",
            worstScreen: saved.worstScreen === "desktop" ? "desktop" : "mobile",
            website: Number.isInteger(saved.website) ? saved.website : false,
        });
        onWillStart(async () => {
            await Promise.all([loadBundle("web.chartjs_lib"), this.load()]);
        });
        useEffect(() => this.draw(), () => [
            this.state.data, this.state.stat, this.state.overlay, this.state.screens.mobile,
            this.state.screens.desktop, this.state.limit, this.state.page,
        ]);
        onWillUnmount(() => this.chart?.destroy());
    }

    async load() {
        this.state.loading = true;
        const data = await this.orm.call("mtbg.page.speed.log", "mtbg_speed_dashboard", [], {
            nights: this.state.nights, website_id: this.state.website || false });
        this.state.data = data;
        this.state.website = data.website_id || false;
        this.state.loading = false;
        const pages = this.pageChoices.map((p) => p.url);
        if (this.state.page && !pages.includes(this.state.page)) {
            this.state.page = "";
        }
    }

    save() {
        const s = this.state;
        writeChoice({ stat: s.stat, overlay: s.overlay, nights: s.nights, mobile: s.screens.mobile,
                      desktop: s.screens.desktop, limit: s.limit, page: s.page, worstScreen: s.worstScreen,
                      website: s.website || false });
    }

    // ------------------------------------------------------------------ the controls
    chooseStat(key) {
        this.state.stat = key;
        if (this.state.overlay === key) {
            this.state.overlay = "";
        }
        this.save();
    }

    chooseOverlay(ev) {
        this.state.overlay = ev.target.value;
        this.save();
    }

    choosePage(ev) {
        this.state.page = ev.target.value;
        this.save();
    }

    async chooseWebsite(ev) {
        this.state.website = parseInt(ev.target.value, 10) || false;
        this.state.page = "";
        this.save();
        await this.load();
    }

    get websiteChoices() {
        return this.state.data?.websites || [];
    }

    async chooseNights(nights) {
        this.state.nights = nights;
        this.save();
        await this.load();
    }

    toggleScreen(key) {
        this.state.screens[key] = !this.state.screens[key];
        this.save();
    }

    toggleLimit() {
        this.state.limit = !this.state.limit;
        this.save();
    }

    chooseWorstScreen(key) {
        this.state.worstScreen = key;
        this.save();
    }

    get overlayChoices() {
        return STATS.filter((s) => s.key !== this.state.stat);
    }

    /** The worst pages of both screens (once each), to pick a page's line from. */
    get pageChoices() {
        const seen = new Map();
        for (const screen of SCREENS) {
            for (const page of this.state.data?.worst?.[screen.key] || []) {
                if (!seen.has(page.url)) {
                    seen.set(page.url, { url: page.url, title: page.title });
                }
            }
        }
        return [...seen.values()];
    }

    get hasData() {
        return !!this.state.data?.last;
    }

    get lastNight() {
        return this.state.data?.last ? formatDate(deserializeDate(this.state.data.last)) : "";
    }

    // ------------------------------------------------------------------ the chart
    /** A stat's limit line on a screen: LCP the log's own limits, the others Lighthouse's "good" marks. */
    mark(stat, screen) {
        const mark = this.state.data?.marks?.[stat];
        return mark && typeof mark === "object" ? mark[screen] : mark;
    }

    datasets() {
        const data = this.state.data;
        const colors = palette();
        const sets = [];
        const { stat, overlay, page, limit } = this.state;
        const shown = SCREENS.filter((s) => this.state.screens[s.key]);
        for (const screen of shown) {
            sets.push({
                label: `${screen.label} · ${STAT[stat].label}`, data: data.series[screen.key]?.[stat] || [],
                borderColor: colors[screen.key], backgroundColor: colors[screen.key], yAxisID: "y",
                borderWidth: 2, pointRadius: 0, pointHoverRadius: 5, tension: 0.25, spanGaps: true,
                mtbgStat: stat,
            });
        }
        if (overlay) {
            for (const screen of shown) {
                sets.push({
                    label: `${screen.label} · ${STAT[overlay].label}`, data: data.series[screen.key]?.[overlay] || [],
                    borderColor: colors[screen.key], backgroundColor: colors[screen.key], yAxisID: "y1",
                    borderWidth: 2, borderDash: [6, 4], pointRadius: 0, pointHoverRadius: 5, tension: 0.25,
                    spanGaps: true, mtbgStat: overlay,
                });
            }
        }
        if (page && data.pages?.[page]) {
            const title = this.pageChoices.find((p) => p.url === page)?.title || page;
            for (const screen of shown) {
                const values = data.pages[page][screen.key]?.[stat];
                if (values) {
                    sets.push({
                        label: `${title} (${screen.label})`, data: values, borderColor: colors.page,
                        backgroundColor: colors.page, yAxisID: "y", borderWidth: 2,
                        borderDash: screen.key === "desktop" ? [2, 3] : [], pointRadius: 3, pointHoverRadius: 6,
                        spanGaps: true, mtbgStat: stat,
                    });
                }
            }
        }
        if (limit) {
            const marks = [...new Set(shown.map((s) => this.mark(stat, s.key)))].filter((m) => m !== undefined);
            for (const value of marks) {
                const screens = shown.filter((s) => this.mark(stat, s.key) === value).map((s) => s.label);
                sets.push({
                    label: `${_t("Limit")} ${formatStat(stat, value)}${marks.length > 1 ? ` · ${screens.join(", ")}` : ""}`,
                    data: data.dates.map(() => value), borderColor: colors.limit, backgroundColor: colors.limit,
                    yAxisID: "y", borderWidth: 1.5, borderDash: [3, 3], pointRadius: 0, pointHoverRadius: 0,
                    mtbgStat: stat, mtbgLimit: true,
                });
            }
        }
        return sets;
    }

    draw() {
        if (!this.canvas.el || !this.hasData || !window.Chart) {
            this.chart?.destroy();
            this.chart = null;
            return;
        }
        const colors = palette();
        const { stat, overlay } = this.state;
        const axis = (key, position) => ({
            position, beginAtZero: key !== "score", grid: { color: position === "left" ? colors.grid : "transparent" },
            ticks: { color: colors.ink, callback: (v) => formatStat(key, v) },
            title: { display: true, text: STAT[key].label, color: colors.ink },
            ...(key === "score" ? { suggestedMin: 0, max: 100 } : {}),
        });
        const config = {
            type: "line",
            data: {
                labels: this.state.data.dates.map((d) => formatDate(deserializeDate(d), { format: "d LLL" })),
                datasets: this.datasets(),
            },
            options: {
                responsive: true, maintainAspectRatio: false, animation: false,
                interaction: { mode: "index", intersect: false },
                scales: {
                    x: { grid: { display: false }, ticks: { color: colors.ink, maxRotation: 0, autoSkipPadding: 16 } },
                    y: axis(stat, "left"),
                    ...(overlay ? { y1: axis(overlay, "right") } : {}),
                },
                plugins: {
                    legend: { position: "bottom", labels: { color: colors.ink, usePointStyle: true, boxHeight: 6,
                                                            filter: () => true } },
                    tooltip: {
                        callbacks: { label: (ctx) => `${ctx.dataset.label}: ${formatStat(ctx.dataset.mtbgStat, ctx.parsed.y)}` },
                        filter: (item) => !item.dataset.mtbgLimit,
                    },
                },
            },
        };
        this.chart?.destroy();
        this.chart = new window.Chart(this.canvas.el, config);
    }

    // ------------------------------------------------------------------ the cards
    get kpiCards() {
        const kpis = this.state.data?.kpis || {};
        const cards = [
            { key: "score", label: _t("Average score"), stat: "score", better: "up" },
            { key: "lcp", label: _t("Average LCP"), stat: "lcp", better: "down" },
            { key: "over", label: _t("Pages over the limit"), better: "down" },
            { key: "error", label: _t("Pages not measured"), better: "down" },
        ];
        return cards.map((card) => ({
            ...card,
            rows: SCREENS.map((screen) => {
                const last = kpis[screen.key]?.last?.[card.key];
                const week = kpis[screen.key]?.week?.[card.key];
                const delta = last !== undefined && last !== null && week !== undefined && week !== null
                    ? last - week : null;
                const good = delta === null || Math.abs(delta) < 1e-9 ? null
                    : (card.better === "up") === delta > 0;
                return {
                    screen, value: this.formatKpi(card, last), week: this.formatKpi(card, week),
                    delta: delta === null ? "" : `${delta > 0 ? "+" : delta < 0 ? "−" : "±"}${this.formatKpi(card, Math.abs(delta))}`,
                    arrow: delta === null || Math.abs(delta) < 1e-9 ? "fa-minus" : delta > 0 ? "fa-arrow-up" : "fa-arrow-down",
                    tone: good === null ? "text-muted" : good ? "text-success" : "text-danger",
                };
            }),
        }));
    }

    formatKpi(card, value) {
        if (value === undefined || value === null) {
            return "–";
        }
        if (card.stat) {
            return formatStat(card.stat, value);
        }
        return Number(value).toLocaleString(undefined, { maximumFractionDigits: 1 });
    }

    get worstPages() {
        return this.state.data?.worst?.[this.state.worstScreen] || [];
    }

    scoreTone(score) {
        return score >= 90 ? "text-bg-success" : score >= 50 ? "text-bg-warning" : "text-bg-danger";
    }

    cause(page) {
        // (0.9.1: a cause without time says itself why: "LCP element: header logo; the breakdown doesn't explain...")
        if (!page.cause) {
            return "";
        }
        return page.cause_ms ? `${page.cause} ${formatStat("lcp", page.cause_ms / 1000)}` : page.cause;
    }

    // ------------------------------------------------------------------ to the rows
    async openRows(extra = {}) {
        const website = this.websiteChoices.length > 1 && this.state.website
            ? { search_default_website_id: this.state.website } : {};
        await this.action.doAction("mtbg_tours_page_speed.action_speed_log", {
            additionalContext: { ...website, ...extra } });
    }

    async openPage(page) {
        // (the page's rows on the screen its card is for: both filters stay removable in the search)
        const screen = this.state.worstScreen === "desktop" ? "computer" : "phone";
        await this.openRows({ search_default_url: page.url, [`search_default_${screen}`]: 1 });
    }

    onCardKey(ev, page) {
        if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            this.openPage(page);
        }
    }

    async openLatest(page) {
        await this.action.doAction({
            type: "ir.actions.act_window", res_model: "mtbg.page.speed.log", res_id: page.id,
            views: [[false, "form"]], target: "current", name: page.title,
        });
    }

    async openSetup() {
        await this.action.doAction(await this.orm.call("mtbg.page.speed.log", "action_mtbg_setup", [[]]));
    }
}

registry.category("actions").add("mtbg_speed_log_dashboard", SpeedLogDashboard);
