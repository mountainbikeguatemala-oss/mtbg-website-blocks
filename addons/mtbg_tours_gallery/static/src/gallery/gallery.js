/**
 * Tiled Gallery block: its tiles are fetched for what it shows once it nears the view; a tile opens the page lightbox
 * (page_lightbox.js).
 */
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

const PAGE = /^([a-z][a-z0-9_]*):page$/;

/**
 * What a block shows: "ids:12,14", "<kind>:<id>", or "<kind>:page", the record of the page holding the block, read
 * from the closest data-mtbg-<kind> (e.g. a tour page's data-mtbg-tour); else, while a record's HTML field is edited,
 * the server matches the closest data-oe-model with the kind's model. {gallery, page_model, page_id}
 */
export function gallerySource(el) {
    const gallery = el.dataset.gallery || "";
    const kind = gallery.match(PAGE)?.[1];
    if (!kind) {
        return { gallery };
    }
    const id = el.closest(`[data-mtbg-${kind}]`)?.getAttribute(`data-mtbg-${kind}`);
    if (id) {
        return { gallery: `${kind}:${id}` };
    }
    const record = el.closest("[data-oe-model][data-oe-id]");
    return { gallery, page_model: record?.dataset.oeModel || "", page_id: Number(record?.dataset.oeId) || 0 };
}

// the blocks not loaded yet: each one's load(), run once (galleriesReady() runs them all)
const waiting = new Set();

/**
 * Every Tiled Gallery block of the page loaded: those still waiting for their turn load now. The page lightbox waits
 * for it before it opens (a tap on the cover, the gallery still far below, opens with the gallery's photos too).
 */
export function galleriesReady() {
    return Promise.all([...waiting].map((load) => load()));
}

/**
 * Tiled Gallery block: its tiles, for what it shows (data-gallery), fetched when the block comes within about a
 * screen of the view (owner, 2026-11-10: "there is no reason to load the gallery until the page scrolls that far
 * down"), or when a photo is opened (galleriesReady); at once in the website editor.
 */
export class TiledGalleryBlock extends Interaction {
    static selector = ".s_mtbg_gallery";
    static loadAtOnce = false;

    setup() {
        // stopped while loading (the website editor stops every block when Edit is clicked): the load's wait ends, so
        // the page's start never waits for it forever (www, 2026-11-02: the editor never opened)
        this.stopped = new Promise((resolve) => (this.onStopped = resolve));
        this.loading = null;
    }

    destroy() {
        this.onStopped?.();
        waiting.delete(this.load_);
    }

    async willStart() {
        if (this.constructor.loadAtOnce) {
            this.result = await this.fetchTiles();
        }
    }

    start() {
        const placeholder = this.el.querySelector(".s_mtbg_gallery_placeholder");
        if (this.constructor.loadAtOnce) {
            this.show(placeholder);
            return;
        }
        // visitors never see the editor's placeholder; the tiles come later
        if (placeholder) {
            placeholder.classList.add("d-none");
            this.registerCleanup(() => placeholder.classList.remove("d-none"));
        }
        this.load_ = () => (this.loading ??= this.fetchTiles().then((result) => {
            waiting.delete(this.load_);
            observer?.disconnect();
            this.result = result;
            if (!this.isDestroyed) {
                this.show(null);
            }
        }));
        waiting.add(this.load_);
        const observer = "IntersectionObserver" in window
            ? new IntersectionObserver((entries) => entries.some((e) => e.isIntersecting) && this.load_(),
                                       { rootMargin: "100% 0px" })
            : null;
        if (observer) {
            observer.observe(this.el);
            this.registerCleanup(() => observer.disconnect());
        } else {
            this.load_();
        }
    }

    /** The block's tiles from the server (null when it shows nothing, or once stopped). */
    async fetchTiles() {
        const source = gallerySource(this.el);
        // waitFor alone never settles once the block is stopped: it races the block's stop
        return source.gallery
            ? await Promise.race([this.waitFor(rpc("/mtbg_tours_gallery/render", source)), this.stopped.then(() => null)])
            : null;
    }

    /** The tiles, under the block's heading (the placeholder hidden once there are tiles, or for visitors). */
    show(placeholder) {
        const hasTiles = !!this.result?.html;
        if (placeholder && (hasTiles || !this.isEditMode())) {
            placeholder.classList.add("d-none");
            this.registerCleanup(() => placeholder.classList.remove("d-none"));
        }
        if (!hasTiles) {
            return;
        }
        const wrap = document.createElement("div");
        wrap.className = "o_mtbg_gallery_generated";
        wrap.innerHTML = this.result.html;
        this.insert(wrap, this.el);
    }

    isEditMode() {
        return !!this.el.closest(".o_editable, [contenteditable='true']") || document.body.classList.contains("editor_enable");
    }
}

registry.category("public.interactions").add("mtbg_tours_gallery.tiled_gallery_block", TiledGalleryBlock);
