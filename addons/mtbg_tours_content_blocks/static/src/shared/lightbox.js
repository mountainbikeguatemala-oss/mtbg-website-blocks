/**
 * One photo viewer for the website (the website blocks base's shared helper, any Odoo website; owner, 2026-11-03:
 * shared JavaScript lives once, in the base; here since 0.11.1, from Tours Core): PhotoSwipe 5 (static/lib/photoswipe, loaded on the first use), full screen, swipes that follow the finger,
 * pinch and double-tap zoom, swipe down to close, a caption and "3 / 15". Extensions decide which photos open and in
 * which order; this opens them.
 *
 *   import { openLightbox, slideFromImage, loadLightbox } from "@mtbg_tours_content_blocks/shared/lightbox";
 *   loadLightbox();                                         // e.g. on pointerdown: starts loading early
 *   await openLightbox(images.map(slideFromImage), index);  // slides: {src, width, height, alt, caption, element}
 *   openLightbox(links.map(slideFromLink), index);          // links to photos, each with its thumbnail inside
 */
import { loadCSS, loadJS } from "@web/core/assets";

const LIB = "/mtbg_tours_content_blocks/static/lib/photoswipe";
const IMAGE_LINK = /(\/web\/image\b|\/web\/content\b|\.(jpe?g|png|webp|gif|avif)(\?.*)?$)/i;

let library = null;
let current = null;

/** PhotoSwipe's script and styles (once). */
export function loadLightbox() {
    library ||= Promise.all([loadJS(`${LIB}/photoswipe.umd.min.js`), loadCSS(`${LIB}/photoswipe.css`)]);
    return library;
}

/** A photo on the page as a slide: its full-size picture (data-mtbg-full, a link to the picture, else the largest of
 * its srcset), its size (the page shows a copy of the same proportions) and its caption (a figure's). */
export function slideFromImage(img, { caption = "" } = {}) {
    const link = img.closest("a");
    const ratio = img.naturalWidth && img.naturalHeight ? img.naturalWidth / img.naturalHeight : 1.5;
    let src = img.currentSrc || img.src;
    let width = Number(img.getAttribute("width")) || img.naturalWidth || 1600;
    if (img.dataset.mtbgFull) {
        src = new URL(img.dataset.mtbgFull, location.href).href;
        width = Number(img.dataset.mtbgWidth) || 1600;
    } else if (link && IMAGE_LINK.test(link.getAttribute("href") || "")) {
        src = link.href;
        width = Math.max(width, 1600);
    } else if (img.srcset) {
        // the largest copy: "<url> <w>w, ..."
        const [url, w] = img.srcset.split(",").map((s) => s.trim().split(/\s+/))
            .sort((a, b) => parseInt(b[1]) - parseInt(a[1]))[0];
        src = new URL(url, location.href).href;
        width = parseInt(w) || width;
    }
    return {
        src, width, height: Math.round(width / ratio), alt: img.alt || "", element: img, msrc: img.currentSrc || img.src,
        caption: caption || img.closest("figure")?.querySelector("figcaption")?.textContent.trim() || "",
    };
}

/** A link to a photo with its thumbnail inside (a review's or a card's photos): the full picture at the link, in the
 * thumbnail's proportions, at least 1600 px wide. */
export function slideFromLink(link) {
    const img = link.querySelector("img");
    const ratio = img?.naturalWidth && img.naturalHeight ? img.naturalWidth / img.naturalHeight : 1.5;
    const width = Math.max(1600, Number(img?.getAttribute("width")) || 0);
    return {
        src: link.href, width, height: Math.round(width / ratio), alt: img?.alt || "", element: img || link,
        msrc: img?.currentSrc || img?.src || link.href, caption: "",
    };
}

/** Open ``slides`` at ``index``; resolves with the viewer (one at a time: an open one closes first). */
export async function openLightbox(slides, index = 0, { onClose } = {}) {
    await loadLightbox();
    current?.destroy();
    const pswp = new window.PhotoSwipe({
        dataSource: slides,
        index: Math.max(0, Math.min(index, slides.length - 1)),
        bgOpacity: 1,
        padding: { top: 0, bottom: 0, left: 0, right: 0 },
        initialZoomLevel: "fit",
        secondaryZoomLevel: 2,
        maxZoomLevel: 4,
        showHideAnimationType: "zoom",
        wheelToZoom: true,
        loop: true,
    });
    pswp.on("uiRegister", () => {
        pswp.ui.registerElement({
            name: "mtbg-caption",
            order: 9,
            isButton: false,
            appendTo: "root",
            onInit: (el) => {
                el.className = "mtbg-pswp-caption";
                pswp.on("change", () => {
                    el.textContent = pswp.currSlide.data.caption || "";
                    el.hidden = !el.textContent;
                });
            },
        });
    });
    pswp.on("destroy", () => {
        if (current === pswp) {
            current = null;
        }
        onClose?.();
    });
    current = pswp;
    pswp.init();
    return pswp;
}

/** The viewer open now, if any (e.g. to close it when its page part goes). */
export function openViewer() {
    return current;
}
