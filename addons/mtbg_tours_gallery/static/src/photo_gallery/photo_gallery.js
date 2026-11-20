/**
 * The photo gallery (the shared ``.mtbg-gallery``: a main photo, a grid of 5 thumbnails, "+N"; 19.0.0.6.5).
 *
 * 19.0.0.6.7 (owner, 2026-11-20: "each small thumb should change the main photo above. and then clicking on the main
 * photo launches the lightbox"): a thumbnail (a button: a tap, Enter or Space) shows its photo in the main photo's
 * box (same size, nothing moves; the thumbnail marked), the active one again brings back the first photo; the main
 * photo opens the page's lightbox at the photo it shows, with every photo of the gallery as one set (the ones beyond
 * the grid too, each once); the "+N" thumbnail opens the lightbox at its photo.
 *
 * Markup written by hand in a content block is accepted as the template makes it or as older blocks have it: thumbnails
 * as ``div`` (the template's, since 19.0.0.6.7: the website editor merges identical neighbouring spans on save) or
 * ``span``, a span the editor merged holding several photos (split here into one thumbnail each), a thumbnail repeating
 * the main photo (the first photo's button, once in the lightbox). A grid listing more than 5 without its "+N" tile
 * gets it on the fifth. Everything done here is undone when the website editor starts (the block is saved as written).
 */
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { loadLightbox, openLightbox, slideFromImage } from "@mtbg_tours_content_blocks/shared/lightbox";

// an Odoo picture at a size: /web/image/<id or xmlid>[-<checksum>]/<w>x<h>[/<name>]
const SIZED = /^((?:https?:\/\/[^/]+)?\/web\/image\/[^/?#]+)\/(\d+x\d+)(\/[^?#]*)?(\?.*)?$/;
const MAIN_ATTRS = ["src", "srcset", "sizes", "alt", "data-mtbg-full"];

/** The addresses that name a photo (its full picture, its shown one), without an Odoo size: a thumbnail repeating the
 * main photo is the same photo. */
function photoKeys(img) {
    return [img.dataset.mtbgFull, img.getAttribute("src")].filter(Boolean).map((url) => {
        try {
            const path = new URL(url, location.href).pathname;
            return path.replace(/^(\/web\/image\/[^/]+)\/\d+x\d+(\/.*)?$/, "$1");
        } catch {
            return url;
        }
    });
}

function samePhoto(a, b) {
    const keys = photoKeys(a);
    return photoKeys(b).some((key) => keys.includes(key));
}

export class PhotoGallery extends Interaction {
    static selector = ".mtbg-gallery";
    dynamicContent = {
        // (the window, capture phase: before the page's lightbox and any other one; the page lightbox leaves
        // .mtbg-gallery photos to this)
        _window: {
            "t-on-click.capture": this.onClick,
            "t-on-pointerdown.capture": this.onPointerDown,
        },
        _root: { "t-on-keydown": this.onKeydown },
    };

    setup() {
        this.main = this.el.querySelector(":scope > .mtbg-gallery__main");
        this.grid = this.el.querySelector(":scope > .mtbg-gallery__thumbs");
        this.current = 0;
        this.pswp = null;
    }

    start() {
        if (!this.grid) {
            return;
        }
        this.splitMerged();
        const thumbs = [...this.grid.children].filter((el) => el.classList.contains("mtbg-gallery__thumb") && el.querySelector("img"));
        // beyond the grid: the template's hidden photos (and any photo written straight in the grid)
        const hidden = [...this.grid.children].filter((el) => el.tagName === "IMG");
        this.addMore(thumbs, hidden);
        if (!this.main) {
            return;
        }
        this.registerCleanup(() => this.pswp?.destroy());
        // the photos, each once, in the gallery's order: the main photo's first photo, the thumbnails', the rest
        const first = this.main.cloneNode(false);
        first.removeAttribute("loading"); // (not in the page: its size is read once loaded, from the cache)
        this.mainAttrs = Object.fromEntries(MAIN_ATTRS.map((name) => [name, this.main.getAttribute(name)]));
        this.registerCleanup(() => this.setMain(this.mainAttrs));
        this.photos = [{ img: first }];
        this.thumbIndex = new Map();
        for (const el of [...thumbs, ...hidden]) {
            const img = el.tagName === "IMG" ? el : el.querySelector("img");
            let index = this.photos.findIndex((photo) => samePhoto(photo.img, img));
            if (index < 0) {
                index = this.photos.push({ img }) - 1;
            }
            if (el !== img) {
                this.thumbIndex.set(el, index);
            }
        }
        // the thumbnails and the main photo: buttons
        const total = this.photos.length;
        thumbs.forEach((thumb, n) => {
            const more = thumb.classList.contains("mtbg-gallery__thumb--more");
            this.attrs(thumb, {
                role: "button",
                tabindex: "0",
                "aria-label": more ? _t("Show all %s photos", total) : _t("Show photo %s", this.thumbIndex.get(thumb) + 1),
            });
        });
        this.attrs(this.main, { role: "button", tabindex: "0", "aria-label": _t("Open the photo full screen") });
        this.markActive();
        this.registerCleanup(() => {
            for (const thumb of thumbs) {
                thumb.classList.remove("mtbg-gallery__thumb--active");
                thumb.removeAttribute("aria-pressed");
            }
        });
    }

    /** Sets attributes, put back as they were when the editor starts. */
    attrs(el, values) {
        for (const [name, value] of Object.entries(values)) {
            const before = el.getAttribute(name);
            el.setAttribute(name, value);
            this.registerCleanup(() => (before === null ? el.removeAttribute(name) : el.setAttribute(name, before)));
        }
    }

    /** A thumbnail holding several photos (the website editor merged identical neighbouring spans on save): one
     * thumbnail each, as written. */
    splitMerged() {
        for (const thumb of [...this.grid.querySelectorAll(":scope > .mtbg-gallery__thumb")]) {
            const imgs = [...thumb.querySelectorAll(":scope > img")];
            let after = thumb;
            for (const img of imgs.slice(1)) {
                const copy = thumb.cloneNode(false);
                copy.classList.remove("mtbg-gallery__thumb--more");
                delete copy.dataset.more;
                copy.append(img);
                after.after(copy);
                after = copy;
                this.registerCleanup(() => {
                    thumb.append(img);
                    copy.remove();
                });
            }
        }
    }

    /** "+N" on the fifth thumbnail of a grid listing more (a content block's): N the photos not seen. */
    addMore(thumbs, hidden) {
        if (thumbs.length + hidden.length <= 5 || thumbs.length < 5 || this.grid.querySelector(".mtbg-gallery__thumb--more")) {
            return;
        }
        const fifth = thumbs[4];
        fifth.classList.add("mtbg-gallery__thumb--more");
        fifth.dataset.more = `+${thumbs.length - 4 + hidden.length}`;
        this.registerCleanup(() => {
            fifth.classList.remove("mtbg-gallery__thumb--more");
            delete fifth.dataset.more;
        });
    }

    markActive() {
        for (const [thumb, index] of this.thumbIndex) {
            const active = index === this.current;
            thumb.classList.toggle("mtbg-gallery__thumb--active", active);
            if (!thumb.classList.contains("mtbg-gallery__thumb--more")) {
                thumb.setAttribute("aria-pressed", active ? "true" : "false");
            }
        }
    }

    setMain(values) {
        for (const [name, value] of Object.entries(values)) {
            if (value === null || value === undefined) {
                this.main.removeAttribute(name);
            } else {
                this.main.setAttribute(name, value);
            }
        }
    }

    /** The main photo's picture for a photo: a thumbnail's Odoo picture at the main photo's size, its own picture
     * when it is big enough (e.g. 512 px), else its full picture; ``data-mtbg-main`` names one. */
    mainSrc(img) {
        if (img.dataset.mtbgMain) {
            return img.dataset.mtbgMain;
        }
        const src = img.getAttribute("src") || "";
        const thumb = src.match(SIZED);
        const main = (this.mainAttrs.src || "").match(SIZED);
        if (thumb && main) {
            return `${thumb[1]}/${main[2]}${thumb[3] || ""}${thumb[4] || ""}`;
        }
        if (img.naturalWidth >= 480 || !img.dataset.mtbgFull) {
            return src;
        }
        return img.dataset.mtbgFull;
    }

    /** Shows a photo in the main photo's box (its picture loaded first: no blank box). */
    async show(index) {
        this.current = index;
        this.markActive();
        if (index === 0) {
            this.setMain(this.mainAttrs);
            return;
        }
        const img = this.photos[index].img;
        const src = this.mainSrc(img);
        const next = new Image();
        next.src = src;
        await this.waitFor(next.decode().catch(() => {}));
        if (this.current !== index) {
            return; // (another thumbnail since)
        }
        this.setMain({ src, srcset: null, sizes: null, alt: img.getAttribute("alt") || this.mainAttrs.alt,
                       "data-mtbg-full": img.dataset.mtbgFull || null });
    }

    async open(index) {
        const slides = this.photos.map((photo, n) => {
            const slide = slideFromImage(photo.img);
            // the photo shown: opens from (and closes to) the main photo
            return n === this.current ? { ...slide, element: this.main, msrc: this.main.currentSrc || slide.msrc } : slide;
        });
        this.pswp = await this.waitFor(openLightbox(slides, index, { onClose: () => (this.pswp = null) }));
    }

    /** What a click, Enter or Space does: the main photo opens the lightbox, a thumbnail shows its photo (the active
     * one: the first photo again), the "+N" one opens the lightbox at its photo. */
    act(target) {
        if (!this.main || !this.el.contains(target)) {
            return false;
        }
        if (target.closest(".mtbg-gallery__main")) {
            this.open(this.current);
            return true;
        }
        const thumb = target.closest(".mtbg-gallery__thumb");
        if (!thumb || !this.thumbIndex.has(thumb)) {
            return false;
        }
        const index = this.thumbIndex.get(thumb);
        if (thumb.classList.contains("mtbg-gallery__thumb--more")) {
            this.open(index);
        } else {
            this.show(index === this.current ? 0 : index);
        }
        return true;
    }

    onPointerDown(ev) {
        if (this.main && this.el.contains(ev.target) && ev.target.closest(".mtbg-gallery__main, .mtbg-gallery__thumb--more")) {
            loadLightbox(); // starts loading while the finger is down
        }
    }

    onClick(ev) {
        if (ev.button > 0 || ev.ctrlKey || ev.metaKey || ev.shiftKey || !this.act(ev.target)) {
            return;
        }
        ev.preventDefault();
        ev.stopImmediatePropagation();
    }

    onKeydown(ev) {
        if ((ev.key === "Enter" || ev.key === " ") && ev.target.matches?.(".mtbg-gallery__main, .mtbg-gallery__thumb") && this.act(ev.target)) {
            ev.preventDefault();
        }
    }
}

registry.category("public.interactions").add("mtbg_tours_gallery.photo_gallery", PhotoGallery);
