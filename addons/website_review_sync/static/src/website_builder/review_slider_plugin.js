import { onWillStart, useState } from "@odoo/owl";
import { BaseOptionComponent } from "@html_builder/core/utils";
import { Plugin } from "@html_editor/plugin";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const SELECTOR = ".s_review_slider";

/** Reviews blocks linked to a preset: which preset (its look, reviews and layout are set on the Reviews page). */
export class ReviewPresetOption extends BaseOptionComponent {
    static template = "website_review_sync.ReviewPresetOption";
    static selector = ".s_review_preset";

    setup() {
        super.setup();
        const orm = useService("orm");
        this.state = useState({ presets: [] });
        onWillStart(async () => {
            this.state.presets = await orm.searchRead("review.preset", [], ["name", "key", "kind"]);
        });
    }
}

/** Reviews block options (blocks placed before presets): which reviews it shows (platform, source, minimum
 * rating, how many) and autoplay. */
export class ReviewSliderOption extends BaseOptionComponent {
    static template = "website_review_sync.ReviewSliderOption";
    static selector = SELECTOR;
    static exclude = ".s_review_preset *";

    setup() {
        super.setup();
        const orm = useService("orm");
        this.state = useState({ sources: [] });
        onWillStart(async () => {
            // (the data attribute holds the id as text)
            const sources = await orm.searchRead("review.source", [], ["name", "platform"]);
            const platforms = { google: "Google", tripadvisor: "Tripadvisor", manual: "Other" };
            this.state.sources = sources.map((source) => ({
                ...source, key: `${source.id}`, name: `${source.name} · ${platforms[source.platform] || source.platform}`,
            }));
        });
    }
}

/** Reviews wall options: the filters it starts with (visitors change them on the page). */
export class ReviewWallOption extends BaseOptionComponent {
    static template = "website_review_sync.ReviewWallOption";
    static selector = ".s_review_wall";
    static exclude = ".s_review_preset *";
}

const WALL_PARTS = ".s_review_wall_summary, .s_review_wall_filters, .s_review_wall_grid, .s_review_wall_status";

class ReviewSliderPlugin extends Plugin {
    static id = "reviewSlider";
    /** @type {import("plugins").WebsiteResources} */
    resources = {
        builder_options: [ReviewPresetOption, ReviewSliderOption, ReviewWallOption],
        // the reviews are loaded on each visit: never stored in the page
        content_not_editable_selectors: [".s_review_preset_body", `${SELECTOR} .s_review_slider_summary`, `${SELECTOR} .s_review_slider_body`,
                                         ...WALL_PARTS.split(", ").map((part) => `.s_review_wall ${part}`)],
        clean_for_save_handlers: ({ root }) => {
            // a preset's block is drawn on each visit: only the preset's name is saved
            for (const el of root.querySelectorAll(".s_review_preset_body")) {
                el.replaceChildren();
            }
            for (const el of root.querySelectorAll(`${SELECTOR} .s_review_slider_summary, ${SELECTOR} .s_review_slider_track`)) {
                el.replaceChildren();
            }
            for (const el of root.querySelectorAll(`${SELECTOR} .s_review_slider_prev, ${SELECTOR} .s_review_slider_next`)) {
                el.remove();
            }
            for (const el of root.querySelectorAll(WALL_PARTS.split(", ").map((part) => `.s_review_wall ${part}`).join(", "))) {
                el.replaceChildren();
            }
            // the five-star total is counted on each visit
            for (const el of root.querySelectorAll(".s_review_total_number")) {
                el.replaceChildren();
            }
        },
    };
}

registry.category("website-plugins").add(ReviewSliderPlugin.id, ReviewSliderPlugin);
