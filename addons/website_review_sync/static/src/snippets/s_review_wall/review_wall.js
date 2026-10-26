/**
 * Reviews wall (the full reviews page): every published review, filters across the top (platform / listing,
 * stars, with photos, language, newest / best first) and endless scroll (the next page loads as the end of the
 * list comes into view). The block's options set where it starts (data-platform, data-min-rating).
 */
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";

import { cardLayout, countOptions, countUp, make, openPhotos, pageLang, ratingBadges, reviewCard, toggleMore, toggleOriginal } from "../s_review_slider/review_card";

const PAGE = 12;

export class ReviewWall extends Interaction {
    static selector = ".s_review_wall";
    dynamicContent = {
        ".s_review_wall_filter": { "t-on-change": this.onFilter },
        ".s_review_slider_more": { "t-on-click": (ev) => toggleMore(ev.currentTarget) },
        ".s_review_slider_photos a": { "t-on-click.prevent": (ev) => openPhotos(ev.currentTarget) },
        ".s_review_slider_original": { "t-on-click": (ev) => toggleOriginal(ev.currentTarget) },
    };

    setup() {
        this.grid = this.el.querySelector(".s_review_wall_grid");
        this.status = this.el.querySelector(".s_review_wall_status");
        this.offset = 0;
        this.total = null;
        this.loading = false;
        const d = this.el.dataset;
        this.filters = { platform: d.platform && d.platform !== "all" ? d.platform : "", source_id: "", min_rating: d.minRating || "1", with_photos: false,
                         language: "", sort: "newest" };
        // a preset's sources (data-source-id "3,5"): the wall shows those unless a visitor picks one
        this.baseSources = d.sourceId && d.sourceId !== "all" ? d.sourceId : "";
    }

    async willStart() {
        this.meta = await this.waitFor(rpc("/review_sync/wall", { ...this.query(), limit: 0, lang: pageLang() })).catch(() => null);
    }

    start() {
        this.renderFilters();
        this.registerCleanup(countUp(this.el.querySelector(".s_review_total_number"), this.meta?.five_star, countOptions(this.el)));
        this.el.querySelector(".s_review_wall_summary")?.replaceChildren(...ratingBadges(this.meta?.summary || []));
        const sentinel = this.el.querySelector(".s_review_wall_more");
        this.observer = new IntersectionObserver((entries) => entries[0].isIntersecting && this.loadMore(), { rootMargin: "600px" });
        this.observer.observe(sentinel);
        this.registerCleanup(() => this.observer.disconnect());
        this.loadMore();
    }

    query() {
        const f = this.filters;
        return { platform: f.platform || null, source_id: f.source_id || this.baseSources || null, min_rating: parseInt(f.min_rating) || 1,
                 with_photos: f.with_photos, language: f.language || null, sort: f.sort };
    }

    renderFilters() {
        const bar = this.el.querySelector(".s_review_wall_filters");
        if (!bar) {
            return; // a preset without the filters
        }
        const select = (name, label, options) => {
            const wrap = make("label", "s_review_wall_field");
            wrap.append(make("span", "visually-hidden", label));
            const el = make("select", "form-select form-select-sm s_review_wall_filter");
            el.name = name;
            el.setAttribute("aria-label", label);
            for (const [value, text] of options) {
                const o = make("option", "", text);
                o.value = value;
                o.selected = String(this.filters[name]) === String(value);
                el.append(o);
            }
            wrap.append(el);
            return wrap;
        };
        const sources = (this.meta?.sources || []).map((s) => [`source:${s.id}`, s.name]);
        const platforms = (this.meta?.platforms || []).map((p) => [`platform:${p.key}`, p.name]);
        const where = select("where", _t("Where"), [["", _t("All reviews")], ...platforms, ...(sources.length > 1 ? sources : [])]);
        where.querySelector("select").value = this.filters.source_id ? `source:${this.filters.source_id}`
            : this.filters.platform ? `platform:${this.filters.platform}` : "";
        const photos = make("label", "form-check form-switch s_review_wall_field mb-0");
        const box = make("input", "form-check-input s_review_wall_filter");
        box.type = "checkbox";
        box.name = "with_photos";
        photos.append(box, make("span", "form-check-label", _t("With photos")));
        bar.replaceChildren(
            where,
            select("min_rating", _t("Rating"), [["1", _t("All ratings")], ["5", _t("5 stars")], ["4", _t("4 stars and up")]]),
            select("language", _t("Language"), [["", _t("All languages")], ...(this.meta?.languages || []).map((l) => [l.code, l.name])]),
            select("sort", _t("Sort"), [["newest", _t("Newest first")], ["best", _t("Highest rated")], ["photos", _t("Photos first")]]),
            photos,
        );
    }

    onFilter(ev) {
        const el = ev.currentTarget;
        if (el.name === "where") {
            const [kind, value] = (el.value || ":").split(":");
            this.filters.platform = kind === "platform" ? value : "";
            this.filters.source_id = kind === "source" ? value : "";
        } else if (el.name === "with_photos") {
            this.filters.with_photos = el.checked;
        } else {
            this.filters[el.name] = el.value;
        }
        this.offset = 0;
        this.total = null;
        this.grid.replaceChildren();
        this.loadMore();
    }

    async loadMore() {
        if (this.loading || (this.total !== null && this.offset >= this.total)) {
            return;
        }
        this.loading = true;
        this.status.textContent = _t("Loading reviews…");
        const key = JSON.stringify(this.filters);
        const data = await this.waitFor(rpc("/review_sync/wall", { ...this.query(), offset: this.offset, limit: PAGE, lang: pageLang() }))
            .catch(() => ({ reviews: [], total: 0 }));
        this.loading = false;
        if (key !== JSON.stringify(this.filters)) {
            return this.loadMore(); // the filters changed meanwhile
        }
        this.total = data.total;
        this.offset += data.reviews.length;
        this.grid.append(...data.reviews.map((r) => reviewCard(r, cardLayout(this.el))));
        this.status.textContent = !this.total ? _t("No reviews match these filters.")
            : this.offset >= this.total ? _t("%s reviews", this.total) : "";
        // a short page can leave the end in view: keep loading
        const rect = this.el.querySelector(".s_review_wall_more").getBoundingClientRect();
        if (this.offset < this.total && rect.top < window.innerHeight + 600) {
            this.loadMore();
        }
    }
}

registry.category("public.interactions").add("website_review_sync.review_wall", ReviewWall);
registry.category("public.interactions.edit").add("website_review_sync.review_wall", { Interaction: ReviewWall });
