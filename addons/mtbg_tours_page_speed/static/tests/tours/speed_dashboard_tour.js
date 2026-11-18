/** The speed log's dashboard (0.9.0): the big chart first, its stat buttons and overlays, the cards, the worst pages;
 * a worst page opens its rows (the list with the Page title column). Light, then dark. */
import { registry } from "@web/core/registry";

function chartDrawn() {
    return {
        content: "The chart is drawn (Chart.js, Odoo's own)",
        trigger: ".o_mtbg_speed_canvas canvas",
        run() {
            const chart = window.Chart?.getChart(this.anchor);
            if (!chart || !chart.data.datasets.length || !chart.data.labels.length) {
                throw new Error("No chart drawn");
            }
        },
    };
}

function datasets() {
    return window.Chart.getChart(document.querySelector(".o_mtbg_speed_canvas canvas")).data.datasets;
}

const steps = () => [
    {
        content: "The chart is the page's first section",
        trigger: ".o_mtbg_speed_dash section:first-of-type.o_mtbg_speed_chart_card",
    },
    chartDrawn(),
    { content: "Seven stats", trigger: ".o_mtbg_speed_stats:has(.o_mtbg_speed_stat:nth-child(7))" },
    { content: "Score", trigger: ".o_mtbg_speed_stat[data-stat='score']", run: "click" },
    {
        trigger: ".o_mtbg_speed_stat[data-stat='score'].active",
        run() {
            const labels = datasets().map((d) => d.label).join("|");
            if (!labels.includes("Phone · Score") || !labels.includes("Computer · Score")) {
                throw new Error(`Phone and computer score lines expected: ${labels}`);
            }
        },
    },
    { content: "LCP as overlay (right axis)", trigger: "select.o_mtbg_speed_overlay", run: "select lcp" },
    {
        trigger: ".o_mtbg_speed_canvas canvas",
        run() {
            if (!datasets().some((d) => d.yAxisID === "y1" && d.label.includes("LCP"))) {
                throw new Error("No LCP overlay");
            }
        },
    },
    { content: "Computer hidden", trigger: ".o_mtbg_speed_screen[data-screen='desktop']", run: "click" },
    {
        trigger: ".o_mtbg_speed_screen[data-screen='desktop']:not(.active)",
        run() {
            if (datasets().some((d) => d.label.startsWith("Computer"))) {
                throw new Error("Computer still drawn");
            }
        },
    },
    { trigger: ".o_mtbg_speed_screen[data-screen='desktop']", run: "click" },
    { content: "LCP, with its limits", trigger: ".o_mtbg_speed_stat[data-stat='lcp']", run: "click" },
    {
        trigger: ".o_mtbg_speed_stat[data-stat='lcp'].active",
        run() {
            const limits = datasets().filter((d) => d.mtbgLimit).map((d) => d.data[0]);
            if (!limits.includes(4) || !limits.includes(2.5)) {
                throw new Error(`LCP limits 4 s and 2.5 s expected: ${limits}`);
            }
        },
    },
    { content: "One page's own line", trigger: "select.o_mtbg_speed_page", run: "selectByIndex 1" },
    {
        trigger: ".o_mtbg_speed_canvas canvas",
        run() {
            if (!datasets().some((d) => d.label.startsWith("Ride 19"))) {
                throw new Error("No page line");
            }
        },
    },
    { content: "90 nights", trigger: ".o_mtbg_speed_range[data-nights='90']", run: "click" },
    { trigger: ".o_mtbg_speed_range[data-nights='90'].active" },
    chartDrawn(),
    { content: "Four cards, phone and computer", trigger: ".o_mtbg_speed_kpis:has(.o_mtbg_speed_kpi:nth-child(4))" },
    { trigger: ".o_mtbg_speed_kpi_score .o_mtbg_speed_kpi_row:nth-child(3) .o_mtbg_speed_kpi_delta .fa" },
    { content: "Five worst pages", trigger: ".o_mtbg_speed_worst_grid:has(.o_mtbg_speed_page_card:nth-child(5))" },
    {
        content: "The worst first: its title, its path, its main cause, its nights",
        trigger: ".o_mtbg_speed_page_card:first-child:has(.o_mtbg_speed_page_title:contains('Ride 19')):has(.o_mtbg_speed_page_path:contains('/tours/ride-19')):has(.o_mtbg_speed_cause:contains('breakdown doesn')):contains('Over the limit')",
    },
    { content: "Open its rows", trigger: ".o_mtbg_speed_page_card:first-child", run: "click" },
    { content: "The rows' page, filtered on that page", trigger: ".o_list_view .o_searchview_facet:contains('ride-19')" },
    { trigger: ".o_list_view .o_searchview_facet:contains('Phone')" },
    { content: "The Page title column", trigger: ".o_list_view th[data-name='page_title']" },
    {
        content: "Only that page's rows",
        trigger: ".o_list_view .o_data_row td[name='page_title']:contains('Ride 19')",
        run() {
            const titles = [...document.querySelectorAll(".o_data_row td[name='page_title']")].map((td) => td.textContent.trim());
            if (titles.some((t) => t !== "Ride 19")) {
                throw new Error(`Other pages listed: ${[...new Set(titles)]}`);
            }
        },
    },
    { content: "Back to the dashboard", trigger: ".o_breadcrumb .breadcrumb-item a:contains('Speed log')", run: "click" },
    { content: "The choices kept", trigger: ".o_mtbg_speed_range[data-nights='90'].active" },
    { content: "See all rows", trigger: ".o_mtbg_speed_all", run: "click" },
    { trigger: ".o_list_view .o_breadcrumb:contains('Speed log: all nights')" },
    { trigger: ".o_list_view .o_mtbg_sb" },
];

registry.category("web_tour.tours").add("mtbg_speed_log_dashboard", { steps });

registry.category("web_tour.tours").add("mtbg_speed_log_dashboard_dark", {
    steps: () => [
        {
            content: "The admin in dark (the user menu's switch: a cookie)",
            trigger: ".o_mtbg_speed_dash",
            run() {
                document.cookie = "color_scheme=dark; path=/";
                window.location.reload();
            },
            expectUnloadPage: true,
        },
        {
            content: "Odoo's dark bundle",
            trigger: ".o_mtbg_speed_dash",
            run() {
                if (!document.querySelector("link[href*='assets_web_dark'], script[src*='assets_web_dark']")) {
                    throw new Error("Not the dark bundle");
                }
                const background = getComputedStyle(this.anchor).backgroundColor;
                const [r, g, b] = background.match(/\d+/g).map(Number);
                if (r + g + b > 300) {
                    throw new Error(`A light background in dark: ${background}`);
                }
            },
        },
        ...steps(),
    ],
});

/** A phone (390 px wide): nothing wider than the screen, the chart full width, the buttons as chip rows scrolled
 * sideways, two cards a row, the worst pages one under the other, their rows as cards. */
function noSideScroll(content) {
    return {
        content,
        trigger: "body",
        run() {
            const root = document.documentElement;
            const dash = document.querySelector(".o_mtbg_speed_dash, .o_action_manager .o_action");
            for (const el of [root, document.body, dash].filter(Boolean)) {
                if (el.scrollWidth > el.clientWidth + 1) {
                    throw new Error(`Wider than the screen: ${el.className || el.tagName} ${el.scrollWidth} > ${el.clientWidth}`);
                }
            }
        },
    };
}

registry.category("web_tour.tours").add("mtbg_speed_log_dashboard_phone", {
    steps: () => [
        chartDrawn(),
        noSideScroll("No side scroll on the dashboard"),
        {
            content: "The chart full width, about 260 px tall",
            trigger: ".o_mtbg_speed_canvas canvas",
            run() {
                const box = this.anchor.getBoundingClientRect();
                const width = document.documentElement.clientWidth;
                if (box.width < width - 60 || box.height < 200 || box.height > 320) {
                    throw new Error(`Chart ${box.width}x${box.height} on a ${width} px screen`);
                }
            },
        },
        {
            content: "The stats: one row of chips, scrolled sideways, 44 px to tap",
            trigger: ".o_mtbg_speed_stats",
            run() {
                const style = getComputedStyle(this.anchor);
                if (style.overflowX !== "auto" || style.flexWrap !== "nowrap") {
                    throw new Error(`Not a chip row: ${style.overflowX} ${style.flexWrap}`);
                }
                if (this.anchor.scrollWidth <= this.anchor.clientWidth) {
                    throw new Error("Seven stats fit: nothing to scroll (expected wider than a phone)");
                }
                const small = [...this.anchor.querySelectorAll(".btn")].filter((b) => b.getBoundingClientRect().height < 44);
                if (small.length) {
                    throw new Error(`${small.length} chips under 44 px`);
                }
                this.anchor.scrollLeft = 200;
                if (this.anchor.scrollLeft === 0) {
                    throw new Error("The chips do not scroll");
                }
            },
        },
        { content: "The last chip, scrolled to", trigger: ".o_mtbg_speed_stat[data-stat='weight_kb']", run: "click" },
        { trigger: ".o_mtbg_speed_stat[data-stat='weight_kb'].active" },
        chartDrawn(),
        {
            content: "The legend under the chart",
            trigger: ".o_mtbg_speed_canvas canvas",
            run() {
                const chart = window.Chart.getChart(this.anchor);
                if (chart.options.plugins.legend.position !== "bottom") {
                    throw new Error("Legend not at the bottom");
                }
            },
        },
        {
            content: "Two cards a row",
            trigger: ".o_mtbg_speed_kpis:has(.o_mtbg_speed_kpi:nth-child(4))",
            run() {
                const [a, b, c] = [...this.anchor.children].map((el) => el.getBoundingClientRect());
                if (Math.abs(a.top - b.top) > 2 || c.top <= a.top) {
                    throw new Error("Not two cards a row");
                }
            },
        },
        {
            content: "The worst pages one under the other",
            trigger: ".o_mtbg_speed_worst_grid:has(.o_mtbg_speed_page_card:nth-child(5))",
            run() {
                const [a, b] = [...this.anchor.querySelectorAll(".o_mtbg_speed_page_card")].map((el) => el.getBoundingClientRect());
                if (b.top <= a.bottom - 1 || a.width < document.documentElement.clientWidth - 60) {
                    throw new Error("Worst pages not stacked full width");
                }
            },
        },
        noSideScroll("Still no side scroll"),
        { content: "A worst page: its rows", trigger: ".o_mtbg_speed_page_card:first-child", run: "click" },
        { content: "The rows as cards on a phone", trigger: ".o_kanban_view .o_kanban_record:has(.o_mtbg_speed_row_title:contains('Ride 19'))" },
        noSideScroll("No side scroll on the rows"),
        { content: "A tap opens the row", trigger: ".o_kanban_view .o_kanban_record:first-child", run: "click" },
        { trigger: ".o_form_view .o_field_widget[name='page_title']:contains('Ride 19')" },
    ],
});
