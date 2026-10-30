/**
 * The Cards block (s_mtbg_cards): its source's records in its card design, fetched on each visit
 * (/mtbg/cards/render: data-source, data-design, data-limit, data-columns, data-layout, data-f-<filter>; data-layout
 * "slider": one row scrolled sideways, the one slider of static/src/slider). Cards with a booking
 * countdown (data-deadline) count down on the visitor's clock; the countdowns of cards rendered by the server
 * elsewhere (menus, listings) count too.
 */
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { renderToElement } from "@web/core/utils/render";
import { uniqueId } from "@web/core/utils/functions";
import { _t } from "@web/core/l10n/translation";

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

/** Photos of a card (a review's): large, one after the other, in the website's own lightbox. */
export function openCardPhotos(link) {
    const links = [...link.closest(".mtbg-card__k-photos").querySelectorAll("a")];
    const images = links.map((a) => {
        const img = document.createElement("img");
        img.setAttribute("src", a.getAttribute("href"));
        img.alt = a.querySelector("img")?.alt || "";
        return img;
    });
    const modalEl = renderToElement("website.gallery.s_image_gallery_mirror.lightbox", {
        images, index: Math.max(0, links.indexOf(link)), dim: {}, interval: 0, ride: "false",
        id: uniqueId("mtbg_card_photos_"),
    });
    modalEl.classList.add("mtbg-card-lightbox");
    modalEl.addEventListener("keydown", (ev) => {
        if (ev.key === "ArrowLeft" || ev.key === "ArrowRight") {
            modalEl.querySelector(`.carousel-control-${ev.key === "ArrowLeft" ? "prev" : "next"}`)?.click();
        }
    });
    modalEl.addEventListener("hidden.bs.modal", () => {
        modalEl.querySelectorAll(".modal-backdrop").forEach((backdrop) => backdrop.remove());
        modalEl.remove();
    }, { once: true });
    document.body.append(modalEl);
    new Modal(modalEl, { keyboard: true, backdrop: true }).show();  // (Bootstrap's Modal, a global of the website)
}

/**
 * What a card does in place, wherever it is drawn (a block, a menu, a page, a review wall): Read more / Read less
 * on a text cut after its lines; the other text (a review's original language) and back; photos opened large.
 */
export class CardBehaviours extends Interaction {
    static selector = ".mtbg-cards, .mtbg-cards-slider";
    dynamicContent = {
        ".mtbg-card__more": { "t-on-click": (ev) => this.toggleMore(ev.currentTarget) },
        ".mtbg-card__alt-toggle": { "t-on-click": (ev) => this.toggleAlt(ev.currentTarget) },
        ".mtbg-card__photo": { "t-on-click.prevent": (ev) => openCardPhotos(ev.currentTarget) },
    };

    toggleMore(button) {
        const text = button.previousElementSibling?.classList.contains("is-clamped") ? button.previousElementSibling
            : button.closest(".mtbg-card")?.querySelector(".is-clamped");
        if (!text) {
            return;
        }
        const open = text.classList.toggle("is-open");
        button.textContent = open ? _t("Read less") : _t("Read more");
    }

    toggleAlt(button) {
        const item = button.closest(".mtbg-card")?.querySelector(".mtbg-card__alt")?.parentElement;
        if (!item) {
            return;
        }
        const alt = item.querySelector(".mtbg-card__alt");
        const showing = item.classList.toggle("is-showing-alt");
        alt.hidden = !showing;
        button.dataset.label ??= button.textContent;
        button.textContent = showing ? (button.dataset.labelAlt || button.dataset.label) : button.dataset.label;
    }
}

registry.category("public.interactions").add("mtbg_website_cards.cards_block", CardsBlock);
registry.category("public.interactions").add("mtbg_website_cards.card_behaviours", CardBehaviours);
registry.category("public.interactions").add("mtbg_website_cards.card_countdowns", CardCountdowns);
