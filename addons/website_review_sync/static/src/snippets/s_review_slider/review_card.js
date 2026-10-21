/**
 * Review cards and rating badges, shared by the Reviews slider and the Reviews wall.
 */
import { _t } from "@web/core/l10n/translation";
import { uniqueId } from "@web/core/utils/functions";
import { renderToElement } from "@web/core/utils/render";

export const ICONS = { google: "fa-google", tripadvisor: "fa-tripadvisor" };
const LONG = 260; // characters before "Read more"

export function make(tag, cls, text) {
    const el = document.createElement(tag);
    if (cls) {
        el.className = cls;
    }
    if (text !== undefined) {
        el.textContent = text;
    }
    return el;
}

/** "G 4.9 ★★★★★ 239 reviews on Mountain Bike Guatemala", one per source (links to its profile). */
export function ratingBadges(summary) {
    return summary.map((s) => {
        const link = make(s.url ? "a" : "span", "s_review_slider_badge");
        if (s.url) {
            link.href = s.url;
            link.target = "_blank";
            link.rel = "noopener";
        }
        const icon = make("i", `fa ${ICONS[s.platform] || "fa-star"}`);
        icon.setAttribute("aria-hidden", "true");
        link.append(icon, make("b", "", ` ${s.average.toFixed(1)} `), make("span", "s_review_slider_stars", "★★★★★"),
            make("span", "", " " + _t("%(count)s reviews on %(name)s", { count: s.count, name: s.name })));
        return link;
    });
}

/**
 * One review: its words in a bubble (stars, title, text, Read more, photos, link to the review), then who said it.
 * The block's style lays it out: a card (the reviewer first) or a speech bubble with the reviewer below it.
 */
export function reviewCard(r) {
    const card = make("article", "s_review_slider_card");
    const bubble = make("div", "s_review_slider_bubble");
    const stars = make("div", "s_review_slider_rating", "★".repeat(r.rating) + "☆".repeat(5 - r.rating));
    stars.setAttribute("aria-label", _t("%s out of 5 stars", r.rating));
    bubble.append(stars);
    if (r.title) {
        bubble.append(make("h3", "s_review_slider_title", r.title));
    }
    const text = make("p", "s_review_slider_text", r.text);
    bubble.append(text);
    if (r.text.length > LONG) {
        text.classList.add("is-clamped");
        bubble.append(make("button", "btn btn-link p-0 s_review_slider_more", _t("Read more")));
    }
    if (r.original) {
        // shown in the page's language: the original a click away
        const note = make("p", "s_review_slider_translated");
        note.append(make("span", "", _t("Translated")), " · ",
            make("button", "btn btn-link p-0 s_review_slider_original", _t("See original")));
        bubble.append(note);
    }
    if (r.photos?.length) {
        const strip = make("div", "s_review_slider_photos");
        for (const src of r.photos) {
            const link = make("a", "");
            link.href = src.replace(/\/\d+x\d+$/, "");
            link.target = "_blank";
            link.rel = "noopener";
            const img = make("img", "");
            img.src = src;
            img.alt = "";
            img.loading = "lazy";
            link.append(img);
            strip.append(link);
        }
        bubble.append(strip);
    }
    if (r.url) {
        const link = make("a", "s_review_slider_link", _t("View on %s", r.platform === "tripadvisor" ? "Tripadvisor" : "Google"));
        link.href = r.url;
        link.target = "_blank";
        link.rel = "noopener";
        bubble.append(link);
    }
    const head = make("div", "s_review_slider_head");
    if (r.photo) {
        const img = make("img", "s_review_slider_photo");
        img.src = r.photo;
        img.alt = "";
        img.loading = "lazy";
        img.referrerPolicy = "no-referrer";
        head.append(img);
    } else {
        head.append(make("span", "s_review_slider_photo s_review_slider_initial", (r.author || "?")[0].toUpperCase()));
    }
    const who = make("div", "s_review_slider_who");
    who.append(make("b", "", r.author), make("small", "", [r.from, r.date && new Date(r.date + "T00:00").toLocaleDateString(undefined, { month: "short", year: "numeric" })].filter(Boolean).join(" · ")));
    const platform = make("i", `fa ${ICONS[r.platform] || "fa-comment"} s_review_slider_platform`);
    platform.setAttribute("aria-label", r.platform);
    head.append(who, platform);
    card.append(bubble, head);
    card.mtbgReview = r; // for See original
    return card;
}

/** The page's language ("es_ES"): the reviews come in it (translated when they have a translation). */
export function pageLang() {
    return (document.documentElement.lang || "").replace("-", "_");
}

/** See original / See translation: the card's title and text in the review's own language, or back. */
export function toggleOriginal(button) {
    const card = button.closest(".s_review_slider_card");
    const r = card?.mtbgReview;
    if (!r?.original) {
        return;
    }
    const original = card.classList.toggle("is-original");
    const shown = original ? r.original : r;
    const text = card.querySelector(".s_review_slider_text");
    text.textContent = shown.text;
    let title = card.querySelector(".s_review_slider_title");
    if (shown.title && !title) {
        title = make("h3", "s_review_slider_title");
        card.querySelector(".s_review_slider_rating").after(title);
    }
    if (title) {
        title.textContent = shown.title || "";
        title.hidden = !shown.title;
    }
    button.textContent = original ? _t("See translation") : _t("See original");
}

const COUNT_MS = 5000; // the count-up's length: long, slowing right down as it reaches the total

/** Ease-out (quint): fast at first, then slower and slower to the end. */
function easeOut(t) {
    return 1 - Math.pow(1 - t, 5);
}

/**
 * The block's five-star total: counts up to the exact number ("416+") when it comes into view, easing out over
 * a few seconds (at once without motion). Returns a cleanup function.
 */
export function countUp(el, count) {
    if (!el) {
        return () => {};
    }
    const target = count || 0;
    const show = (n) => (el.textContent = `${n.toLocaleString()}+`);
    if (!target) {
        el.textContent = "";
        return () => {};
    }
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches || !window.IntersectionObserver) {
        show(target);
        return () => {};
    }
    show(0);
    let frame;
    const observer = new IntersectionObserver((entries) => {
        if (!entries[0].isIntersecting) {
            return;
        }
        observer.disconnect();
        const start = performance.now();
        const step = (now) => {
            const t = Math.min(1, (now - start) / COUNT_MS);
            show(Math.round(target * easeOut(t)));
            if (t < 1) {
                frame = requestAnimationFrame(step);
            }
        };
        frame = requestAnimationFrame(step);
    }, { threshold: 0.4 });
    observer.observe(el);
    return () => {
        observer.disconnect();
        cancelAnimationFrame(frame);
    };
}

/**
 * A card's photos in Odoo's image lightbox (the gallery one), starting at the one clicked; arrows, swipe and the
 * keyboard browse them. ``link`` is the clicked photo's link inside a card.
 */
export function openPhotos(link) {
    const links = [...link.closest(".s_review_slider_photos").querySelectorAll("a")];
    const images = links.map((a) => {
        const img = document.createElement("img");
        img.setAttribute("src", a.getAttribute("href"));
        img.alt = "";
        return img;
    });
    const modalEl = renderToElement("website.gallery.s_image_gallery_mirror.lightbox", {
        images, index: Math.max(0, links.indexOf(link)), dim: {}, interval: 0, ride: "false",
        id: uniqueId("review_photos_"),
    });
    modalEl.classList.add("s_review_lightbox");
    const onKeydown = (ev) => {
        if (ev.key === "ArrowLeft" || ev.key === "ArrowRight") {
            modalEl.querySelector(`.carousel-control-${ev.key === "ArrowLeft" ? "prev" : "next"}`)?.click();
        }
    };
    modalEl.addEventListener("keydown", onKeydown);
    modalEl.addEventListener("hidden.bs.modal", () => {
        for (const backdrop of modalEl.querySelectorAll(".modal-backdrop")) {
            backdrop.remove();
        }
        modalEl.remove();
    }, { once: true });
    document.body.append(modalEl);
    new Modal(modalEl, { keyboard: true, backdrop: true }).show();
}

/** "Read more" / "Read less" on a card (delegated by the blocks). */
export function toggleMore(button) {
    const text = button.closest(".s_review_slider_card").querySelector(".s_review_slider_text");
    const open = text.classList.toggle("is-clamped");
    button.textContent = open ? _t("Read more") : _t("Read less");
}
