import { TiledGalleryBlock } from "./gallery";
import { registry } from "@web/core/registry";

/** While editing: the tiles at once, wherever the block is on the page. */
class TiledGalleryBlockEdit extends TiledGalleryBlock {
    static loadAtOnce = true;
}

// Also show a block's tiles while editing the page (they are never saved; clicks select the block)
registry.category("public.interactions.edit").add("mtbg_tours_gallery.tiled_gallery_block", {
    Interaction: TiledGalleryBlockEdit,
});
