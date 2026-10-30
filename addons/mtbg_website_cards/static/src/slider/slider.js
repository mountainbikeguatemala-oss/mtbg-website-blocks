/**
 * The one slider of the website (owner, 2026-10-29: "Sliding is sliding and cards are cards"): every row of things
 * scrolled sideways (the Cards block, the mega menus' rows, the reviews) is this, so one script is loaded however
 * many sliders a page has. Markup (slider.xml ``mtbg_website_cards.slider``, or built by a script):
 *
 *     <div class="mtbg-slider" data-arrows="1" data-autoplay="6000" data-loop="1"
 *          style="--mtbg-slider-per-lg: 4; --mtbg-slider-per-md: 3; --mtbg-slider-per-sm: 1.2">
 *         <button class="mtbg-slider__prev ..."/>             (optional: made here when data-arrows)
 *         <div class="mtbg-slider__track"><div class="mtbg-slider__slide">…</div>…</div>
 *         <button class="mtbg-slider__next ..."/>
 *     </div>
 *
 * How many show at once: by the slider's own width (slider.scss, container queries); a fraction lets the next one
 * peek. Touch and trackpads scroll natively, snapping to a slide; the arrows page through and hide at either end
 * (data-loop: the last page goes back to the first); data-autoplay pages every that many ms, paused while hovered or
 * focused (never in the website editor). The track's content may come later (a block filled by a script): the
 * slider measures again when it changes size.
 */
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";

export class Slider extends Interaction {
    static selector = ".mtbg-slider";
    dynamicContent = {
        ".mtbg-slider__prev": {
            "t-on-click": () => this.page(-1),
            "t-att-disabled": () => this.atStart && !this.loop,
        },
        ".mtbg-slider__next": {
            "t-on-click": () => this.page(1),
            "t-att-disabled": () => this.atEnd && !this.loop,
        },
        ".mtbg-slider__track": {
            "t-on-scroll": this.debounced(this.updateEnds, 50),
        },
        _root: {
            "t-on-mouseenter": () => (this.paused = true),
            "t-on-mouseleave": () => (this.paused = false),
            "t-on-focusin": () => (this.paused = true),
            "t-on-focusout": () => (this.paused = false),
        },
        _window: {
            "t-on-resize": this.debounced(this.updateEnds, 100),
        },
    };

    setup() {
        this.track = this.el.querySelector(".mtbg-slider__track");
        this.loop = this.el.dataset.loop === "1" || this.el.dataset.loop === "true";
        this.atStart = true;
        this.atEnd = false;
        this.paused = false;
        this.makeArrows();
    }

    start() {
        if (!this.track) {
            return;
        }
        this.updateEnds();
        // hidden at first (a mega menu), or filled later (a block's script): measure again when it changes
        this.observer = new ResizeObserver(() => this.updateEnds());
        this.observer.observe(this.track);
        this.registerCleanup(() => this.observer.disconnect());
        const every = parseInt(this.el.dataset.autoplay || 0);
        if (every >= 1000 && this.autoplays) {
            this.timer = setInterval(() => !this.paused && this.page(1, true), every);
            this.registerCleanup(() => clearInterval(this.timer));
        }
    }

    get autoplays() {
        return true;
    }

    /** data-arrows and no arrows in the markup: made here (classes: data-arrow-class). */
    makeArrows() {
        const wanted = this.el.dataset.arrows === "1" || this.el.dataset.arrows === "true";
        if (!wanted || !this.track || this.el.querySelector(".mtbg-slider__prev")) {
            return;
        }
        const extra = this.el.dataset.arrowClass || "btn btn-light rounded-circle shadow";
        for (const [side, label, icon] of [["prev", _t("Previous"), "fa-chevron-left"], ["next", _t("Next"), "fa-chevron-right"]]) {
            const button = document.createElement("button");
            button.type = "button";
            button.className = `mtbg-slider__${side} ${extra}`;
            button.setAttribute("aria-label", label);
            const i = document.createElement("i");
            i.className = `fa ${icon}`;
            i.setAttribute("aria-hidden", "true");
            button.append(i);
            if (side === "prev") {
                this.track.before(button);
            } else {
                this.track.after(button);
            }
        }
    }

    page(direction, auto = false) {
        const { scrollLeft, scrollWidth, clientWidth } = this.track;
        const end = scrollLeft + clientWidth >= scrollWidth - 2;
        if ((this.loop || auto) && direction > 0 && end) {
            this.track.scrollTo({ left: 0, behavior: "smooth" });
            return;
        }
        if (this.loop && direction < 0 && scrollLeft <= 1) {
            this.track.scrollTo({ left: scrollWidth, behavior: "smooth" });
            return;
        }
        this.track.scrollBy({ left: direction * clientWidth, behavior: "smooth" });
    }

    updateEnds() {
        if (!this.track) {
            return;
        }
        const { scrollLeft, scrollWidth, clientWidth } = this.track;
        this.atStart = scrollLeft <= 1;
        this.atEnd = scrollLeft + clientWidth >= scrollWidth - 1;
        this.el.classList.toggle("mtbg-slider--fits", scrollWidth <= clientWidth + 1);
        this.updateContent();
    }
}

registry.category("public.interactions").add("mtbg_website_cards.slider", Slider);
registry.category("public.interactions.edit").add("mtbg_website_cards.slider", {
    Interaction: Slider,
    mixin: (I) => class extends I {
        get autoplays() {
            return false;  // (never while editing)
        }
    },
});
