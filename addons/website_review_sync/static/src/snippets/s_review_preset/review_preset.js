/**
 * A Reviews block linked to a preset (data-preset): draws the block from the preset (/review_sync/preset), then
 * the slider / wall inside it loads the reviews. Also in the website editor (the body is emptied before saving).
 *
 * The Reviews page's preview ([data-review-preset-preview]) gets the block with the page's unsaved changes
 * (``review_preset_preview`` event, or ``window.reviewPresetPreview`` before this starts).
 */
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

import { pageLang } from "../s_review_slider/review_card";

/** Put ``html`` in ``el`` and start what it holds (the slider or wall), stopping what was there. */
function replaceBlock(interactions, el, html) {
    for (const child of [...el.children]) {
        interactions.stopInteractions(child);
    }
    el.innerHTML = html || "";
    for (const child of [...el.children]) {
        interactions.startInteractions(child);
    }
}

export class ReviewPreset extends Interaction {
    static selector = ".s_review_preset";

    setup() {
        this.body = this.el.querySelector(".s_review_preset_body");
    }

    async willStart() {
        const key = this.el.dataset.preset;
        this.html = key ? await this.waitFor(rpc("/review_sync/preset", { key, lang: pageLang() }))
            .then((result) => result.html).catch(() => "") : "";
    }

    start() {
        if (!this.body) {
            return;
        }
        const interactions = this.services["public.interactions"];
        replaceBlock(interactions, this.body, this.html);
        this.registerCleanup(() => {
            for (const child of [...this.body.children]) {
                interactions.stopInteractions(child);
            }
        });
    }
}

export class ReviewPresetPreview extends Interaction {
    static selector = "[data-review-preset-preview]";
    dynamicContent = {
        _document: { "t-on-review_preset_preview": (ev) => this.apply(ev.detail) },
    };

    start() {
        if (window.reviewPresetPreview) {
            this.apply(window.reviewPresetPreview);
        }
    }

    apply({ html }) {
        if (html !== undefined) {
            replaceBlock(this.services["public.interactions"], this.el, html);
        }
    }
}

registry.category("public.interactions").add("website_review_sync.review_preset", ReviewPreset);
registry.category("public.interactions").add("website_review_sync.review_preset_preview", ReviewPresetPreview);
registry.category("public.interactions.edit").add("website_review_sync.review_preset", { Interaction: ReviewPreset });
