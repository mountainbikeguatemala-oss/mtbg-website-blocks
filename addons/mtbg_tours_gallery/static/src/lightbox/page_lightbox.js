/**
 * One lightbox for the page's photos (PhotoSwipe 5, in static/lib): full screen, swipes that follow the finger,
 * pinch and double-tap zoom, swipe down to close, caption and "3 / 15".
 *
 * A page naming its own photos (``data-mtbg-lightbox-photos``: a selector, e.g. a tour page's cover, description and
 * blocks' big photos) opens those and every Tiled Gallery photo, in page order; any other page, its Tiled Gallery
 * photos. On every page, the photos inside an element marked
 * ``data-mtbg-photo-set`` open as a set of their own (e.g. a hotel card's photos), each at its ``data-mtbg-full``
 * picture when it names one: an extension marks its markup, nothing else. Each opens full size (the picture a tile or a photo link points to, or the
 * largest of its srcset). The click is taken on the window in the capture phase, before any other lightbox (the
 * Booking Form's tour lightbox, Odoo's gallery lightbox) sees it. The viewer is the website blocks base's
 * (@mtbg_tours_content_blocks/shared/lightbox): it loads on the first touch of a photo.
 */
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { loadLightbox, openLightbox, slideFromImage } from "@mtbg_tours_content_blocks/shared/lightbox";
import { galleriesReady } from "../gallery/gallery";

const IMAGE_LINK = /(\/web\/image\b|\.(jpe?g|png|webp|gif|avif)(\?.*)?$)/i;

/** Shown on the page (checkVisibility is missing before iOS 17.4 / Chrome 105: then whether it has a box). */
function isShown(el) {
    return el.checkVisibility ? el.checkVisibility() : el.getClientRects().length > 0;
}

/** A Tiled Gallery tile of the screen size shown (the other size's tiles are the same photos, hidden). */
function isTile(img) {
    return !!img.closest(".mtbg-tg") && isShown(img);
}

/** A photo of a marked set (``data-mtbg-photo-set``): its set's shown photos open together. */
function photoSet(img) {
    const set = img.closest("[data-mtbg-photo-set]");
    return set && isShown(img) ? set : null;
}

/** A page photo (of the page's data-mtbg-lightbox-photos): big enough, not a logo or an icon, not inside a form, not
 * a picture linking to a page; one marked data-mtbg-lightbox-always (e.g. a tour's cover) whatever its size. */
function isPagePhoto(img) {
    if (img.closest("form, .o_not_lightbox, .mtbg-tg, [data-mtbg-photo-set]")) {
        return false;
    }
    const link = img.closest("a");
    if (link && !IMAGE_LINK.test(link.getAttribute("href") || "")) {
        return false;
    }
    if (img.hasAttribute("data-mtbg-lightbox-always")) {
        return true;
    }
    const w = img.naturalWidth, h = img.naturalHeight;
    return w >= 500 && h >= 250 && w / h <= 3.5 && img.getBoundingClientRect().width >= 160;
}

/** A photo's slide (Core's viewer): its full-size picture; a tile's caption is the tile's. */
function slideOf(img) {
    return slideFromImage(img, { caption: img.closest(".mtbg-tg-cell")?.dataset.caption || "" });
}

export class PageLightbox extends Interaction {
    static selector = "#wrapwrap";
    dynamicContent = {
        _window: {
            "t-on-click.capture": this.onClick,
            "t-on-pointerdown.capture": this.onPointerDown,
        },
    };

    setup() {
        // a page whose own photos open too (e.g. a tour page: its cover, the description's and blocks' big photos): the
        // selector of those photos, on any element of the page (data-mtbg-lightbox-photos)
        this.pagePhotos = this.el.querySelector("[data-mtbg-lightbox-photos]")?.dataset.mtbgLightboxPhotos || "";
        this.pswp = null;
    }

    start() {
        // (tests and other lightboxes: this one takes the photos' clicks)
        document.documentElement.dataset.mtbgLightbox = "1";
        this.registerCleanup(() => delete document.documentElement.dataset.mtbgLightbox);
        this.registerCleanup(() => this.pswp?.destroy());
    }

    photos() {
        const selector = this.pagePhotos ? `${this.pagePhotos}, .mtbg-tg img` : ".mtbg-tg img";
        return [...this.el.querySelectorAll(selector)].filter((img) => isTile(img) || (this.pagePhotos && isPagePhoto(img)));
    }

    target(ev) {
        // a photo, or a tile opened from the keyboard (Enter on its link)
        const img = ev.target.closest?.("img") || ev.target.closest?.(".mtbg-tg-cell")?.querySelector("img");
        if (!img || ev.button > 0 || ev.ctrlKey || ev.metaKey || ev.shiftKey || !this.el.contains(img)) {
            return null;
        }
        return photoSet(img) || isTile(img) || (this.pagePhotos && img.matches(this.pagePhotos) && isPagePhoto(img))
            ? img : null;
    }

    onPointerDown(ev) {
        if (this.target(ev)) {
            loadLightbox(); // starts loading while the finger is down
            galleriesReady(); // and the galleries further down, whose photos open with it
        }
    }

    async onClick(ev) {
        const img = this.target(ev);
        if (!img) {
            return;
        }
        ev.preventDefault();
        ev.stopImmediatePropagation();
        const set = photoSet(img);
        if (!set) {
            await this.waitFor(galleriesReady()); // (a gallery not reached yet: its photos join the lightbox)
        }
        const photos = set ? [...set.querySelectorAll("img")].filter(isShown) : this.photos();
        const index = Math.max(0, photos.indexOf(img));
        this.pswp = await this.waitFor(openLightbox(photos.map(slideOf), index, { onClose: () => (this.pswp = null) }));
    }
}

registry.category("public.interactions").add("mtbg_tours_gallery.page_lightbox", PageLightbox);
