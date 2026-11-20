/**
 * The photo gallery (19.0.0.6.5, the shared ``.mtbg-gallery``: a main photo, a grid of 5 thumbnails, "+N"): a gallery
 * listing more than 5 thumbnails without its "+N" tile (one written by hand in a content block) gets it on the fifth,
 * N the photos not seen; the ones beyond are hidden by its SCSS (still in the lightbox). Markup made on the server
 * (with its "+N" tile) is left as it is. Undone when the website editor starts (the block is saved as written).
 */
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

export class PhotoGallery extends Interaction {
    static selector = ".mtbg-gallery";

    start() {
        for (const grid of this.el.querySelectorAll(":scope > .mtbg-gallery__thumbs")) {
            const thumbs = [...grid.children].filter((el) => el.classList.contains("mtbg-gallery__thumb"));
            if (thumbs.length <= 5 || grid.querySelector(".mtbg-gallery__thumb--more")) {
                continue;
            }
            const fifth = thumbs[4];
            const hidden = grid.querySelectorAll(":scope > .mtbg-gallery__hidden").length;
            fifth.classList.add("mtbg-gallery__thumb--more");
            fifth.dataset.more = `+${thumbs.length - 4 + hidden}`;
            this.registerCleanup(() => {
                fifth.classList.remove("mtbg-gallery__thumb--more");
                delete fifth.dataset.more;
            });
        }
    }
}

registry.category("public.interactions").add("mtbg_tours_gallery.photo_gallery", PhotoGallery);
