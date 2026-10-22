/**
 * Reviews block: loads the published reviews its options ask for (data-platform, data-source-id,
 * data-min-rating, data-limit, data-scope="page": the reviews of the page's record) and shows them as a slider of
 * cards: arrows (data-arrows="true") page through, swipe / scroll works natively, autoplay (data-autoplay) pauses on hover and focus.
 * "Read more" opens a long review in place. Its "See all reviews" button is ordinary, editable content.
 * Also runs in the website editor (preview of the options); the slides are removed before saving.
 */
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";

import { countOptions, countUp, make, openPhotos, pageLang, ratingBadges, reviewCard, toggleMore, toggleOriginal } from "./review_card";

export class ReviewSlider extends Interaction {
    static selector = ".s_review_slider";
    dynamicContent = {
        ".s_review_slider_prev": { "t-on-click": () => this.page(-1) },
        ".s_review_slider_next": { "t-on-click": () => this.page(1) },
        ".s_review_slider_more": { "t-on-click": this.onMore },
        ".s_review_slider_photos a": { "t-on-click.prevent": (ev) => openPhotos(ev.currentTarget) },
        ".s_review_slider_original": { "t-on-click": (ev) => toggleOriginal(ev.currentTarget) },
        _root: {
            "t-on-mouseenter": () => (this.paused = true),
            "t-on-mouseleave": () => (this.paused = false),
            "t-on-focusin": () => (this.paused = true),
            "t-on-focusout": () => (this.paused = false),
        },
    };

    setup() {
        this.track = this.el.querySelector(".s_review_slider_track");
        this.paused = false;
    }

    async willStart() {
        const d = this.el.dataset;
        this.data = await this.waitFor(rpc("/review_sync/slider", {
            lang: pageLang(),
            // ("all": no filter)
            platform: d.platform && d.platform !== "all" ? d.platform : null,
            source_id: d.sourceId && d.sourceId !== "all" ? d.sourceId : null,
            min_rating: parseInt(d.minRating) || 1, limit: parseInt(d.limit) || 12, sort: d.sort || "featured",
            // "this page's reviews only": the page's record (e.g. a product), see review.review._slider_domain
            scope: d.scope || null, main_object: d.scope ? document.documentElement.dataset.mainObject || null : null,
        })).catch(() => ({ reviews: [], summary: [] }));
    }

    start() {
        this.render();
        if (this.el.dataset.autoplay === "true" && this.data.reviews.length > 1) {
            this.timer = setInterval(() => !this.paused && this.page(1, true), 6000);
            this.registerCleanup(() => clearInterval(this.timer));
        }
    }

    render() {
        // the five-star total ("400+"), or (older blocks) a rating badge per source
        this.registerCleanup(countUp(this.el.querySelector(".s_review_total_number"), this.data.five_star, countOptions(this.el)));
        this.el.querySelector(".s_review_slider_summary")?.replaceChildren(...ratingBadges(this.data.summary));
        if (!this.data.reviews.length) {
            this.track.replaceChildren(make("p", "text-muted text-center w-100", _t("No reviews to show yet.")));
            return;
        }
        this.track.replaceChildren(...this.data.reviews.map((r) => reviewCard(r)));
        const body = this.el.querySelector(".s_review_slider_body");
        // navigation arrows (block option "Arrows"; swiping / scrolling always works)
        if (this.el.dataset.arrows !== "true") {
            for (const arrow of body.querySelectorAll(".s_review_slider_prev, .s_review_slider_next")) {
                arrow.remove();
            }
        } else if (!body.querySelector(".s_review_slider_prev")) {
            for (const [cls, label, icon] of [["prev", _t("Previous"), "fa-chevron-left"], ["next", _t("Next"), "fa-chevron-right"]]) {
                const button = make("button", `s_review_slider_${cls} btn btn-light rounded-circle shadow`);
                button.type = "button";
                button.setAttribute("aria-label", label);
                const i = make("i", `fa ${icon}`);
                i.setAttribute("aria-hidden", "true");
                button.append(i);
                body.append(button);
            }
        }
    }

    page(direction, loop = false) {
        const { scrollLeft, scrollWidth, clientWidth } = this.track;
        if (loop && direction > 0 && scrollLeft + clientWidth >= scrollWidth - 2) {
            this.track.scrollTo({ left: 0, behavior: "smooth" });
            return;
        }
        this.track.scrollBy({ left: direction * clientWidth, behavior: "smooth" });
    }

    onMore(ev) {
        toggleMore(ev.currentTarget);
    }
}

registry.category("public.interactions").add("website_review_sync.review_slider", ReviewSlider);
registry.category("public.interactions.edit").add("website_review_sync.review_slider", {
    Interaction: ReviewSlider,
    mixin: (I) => class extends I {
        start() {
            this.render(); // no autoplay while editing
        }
    },
});
