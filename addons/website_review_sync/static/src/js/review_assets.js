/**
 * The Reviews blocks' and the Counter's code, on the pages that have one only (owner, 2026-11-04, JS consolidation
 * part B: an extension's own code in its own bundle, loaded where it is used): this small loader is in every page's
 * bundle; on a page with a Reviews block (preset, slider or wall) or a counted number it loads
 * website_review_sync.assets_reviews and starts it. The blocks are drawn by that code (their reviews come from the
 * server), so their styles come with it, unless the page has them in its head already (the Reviews page's preview).
 * The website editor has the code from the start (website.assets_inside_builder_iframe).
 */
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { loadBundle } from "@web/core/assets";

const BUNDLE = "website_review_sync.assets_reviews";
let loading;

export class ReviewAssets extends Interaction {
    static selector = ".s_review_preset, .s_review_slider, .s_review_wall, [data-review-preset-preview], [data-mtbg-count]";

    start() {
        const inHead = !!document.querySelector(`link[href*="/${BUNDLE}."]`);
        loading ??= loadBundle(BUNDLE, { css: !inHead });
        loading.then(() => {
            if (!this.isDestroyed) {
                // the bundle's interactions, on this block (the ones running already are skipped)
                this.services["public.interactions"].activate(registry.category("public.interactions").getAll(), this.el);
            }
        });
    }
}

registry.category("public.interactions").add("website_review_sync.review_assets", ReviewAssets);
