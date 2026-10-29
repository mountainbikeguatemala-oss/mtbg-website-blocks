/**
 * The Cards block (s_mtbg_cards): its source's records in its card design, fetched on each visit
 * (/mtbg/cards/render: data-source, data-design, data-limit, data-columns, data-layout, data-f-<filter>; data-layout
 * "slider": one row scrolled sideways, CardsSlider below). Cards with a booking
 * countdown (data-deadline) count down on the visitor's clock; the countdowns of cards rendered by the server
 * elsewhere (menus, listings) count too.
 */
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

/** "3d 04:10:33", under a day "04:10:33". */
function clock(ms) {
    const total = Math.max(0, Math.floor(ms / 1000));
    const pad = (n) => String(n).padStart(2, "0");
    const days = Math.floor(total / 86400);
    const time = `${pad(Math.floor((total % 86400) / 3600))}:${pad(Math.floor((total % 3600) / 60))}:${pad(total % 60)}`;
    return days ? `${days}d ${time}` : time;
}

export function tickCountdowns(root) {
    const now = Date.now();
    for (const el of root.querySelectorAll(".mtbg-card__k-countdown[data-deadline]")) {
        const left = new Date(el.dataset.deadline).getTime() - now;
        const out = el.querySelector(".mtbg-card__countdown-clock");
        if (out) {
            out.textContent = left > 0 ? clock(left) : "";
        }
        el.hidden = left <= 0;
    }
}

export class CardsBlock extends Interaction {
    static selector = ".s_mtbg_cards";

    async willStart() {
        const d = this.el.dataset;
        if (!d.source) {
            return;
        }
        const filters = {};
        for (const [key, value] of Object.entries(d)) {
            if (/^f[A-Z]/.test(key) && value) {
                filters[key[1].toLowerCase() + key.slice(2)] = value;
            }
        }
        const lang = (document.documentElement.lang || "en-US").replace("-", "_");
        const result = await this.waitFor(rpc("/mtbg/cards/render", {
            source: d.source, design_id: parseInt(d.design || 0), filters, limit: parseInt(d.limit || 6),
            columns: parseInt(d.columns || 3), lang, layout: d.layout === "slider" ? "slider" : "grid",
        }));
        this.html = result.html || "";
    }

    start() {
        const body = this.el.querySelector(".s_mtbg_cards_body");
        if (body && this.html !== undefined) {
            body.innerHTML = this.html;
            this.registerCleanup(() => body.replaceChildren());
            // other modules' scripts on the cards' fields (e.g. Tours: the price's currency, the early bird)
            this.services["public.interactions"].startInteractions(body);
        }
        tickCountdowns(this.el);
        this.timer = setInterval(() => tickCountdowns(this.el), 1000);
        this.registerCleanup(() => clearInterval(this.timer));
    }
}

/** Countdowns of cards the server drew in place (listings, menus): ticking. */
export class CardCountdowns extends Interaction {
    static selector = ".mtbg-cards:not(.s_mtbg_cards .mtbg-cards)";

    start() {
        if (!this.el.querySelector(".mtbg-card__k-countdown[data-deadline]")) {
            return;
        }
        tickCountdowns(this.el);
        this.timer = setInterval(() => tickCountdowns(this.el), 1000);
        this.registerCleanup(() => clearInterval(this.timer));
    }
}

/**
 * The cards as a slider: the arrows scroll one page of cards at a time and hide at either end (as the mega menu's
 * Image Cards (slider)); touch and trackpads scroll natively, snapping to a card.
 */
export class CardsSlider extends Interaction {
    static selector = ".mtbg-cards-slider";
    dynamicContent = {
        ".mtbg-cards-slider-prev": {
            "t-on-click": () => this.page(-1),
            "t-att-disabled": () => this.atStart,
        },
        ".mtbg-cards-slider-next": {
            "t-on-click": () => this.page(1),
            "t-att-disabled": () => this.atEnd,
        },
        ".mtbg-cards--slider": {
            "t-on-scroll": this.debounced(this.updateEnds, 50),
        },
        _window: {
            "t-on-resize": this.debounced(this.updateEnds, 100),
        },
    };

    setup() {
        this.track = this.el.querySelector(".mtbg-cards--slider");
        this.atStart = true;
        this.atEnd = false;
    }

    start() {
        this.updateEnds();
        this.observer = new ResizeObserver(() => this.updateEnds());
        this.observer.observe(this.track);
        this.registerCleanup(() => this.observer.disconnect());
    }

    page(direction) {
        this.track.scrollBy({ left: direction * this.track.clientWidth, behavior: "smooth" });
    }

    updateEnds() {
        const { scrollLeft, scrollWidth, clientWidth } = this.track;
        this.atStart = scrollLeft <= 1;
        this.atEnd = scrollLeft + clientWidth >= scrollWidth - 1;
        this.updateContent();
    }
}

registry.category("public.interactions").add("mtbg_website_cards.cards_block", CardsBlock);
registry.category("public.interactions").add("mtbg_website_cards.cards_slider", CardsSlider);
registry.category("public.interactions").add("mtbg_website_cards.card_countdowns", CardCountdowns);
