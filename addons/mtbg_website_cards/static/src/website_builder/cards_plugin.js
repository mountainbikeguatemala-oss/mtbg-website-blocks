import { onWillStart, useState } from "@odoo/owl";
import { BaseOptionComponent, useDomState } from "@html_builder/core/utils";
import { Plugin } from "@html_editor/plugin";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/** The Cards block's options: its source and that source's filters, its design, how many, columns. */
export class CardsOption extends BaseOptionComponent {
    static template = "mtbg_website_cards.CardsOption";
    static selector = ".s_mtbg_cards";

    setup() {
        super.setup();
        const orm = useService("orm");
        this.state = useState({ sources: [] });
        this.domState = useDomState((el) => ({ source: el.dataset.source || "" }));
        onWillStart(async () => {
            this.state.sources = (await orm.call("mtbg.website.card.design", "mtbg_block_data", [])).sources;
        });
    }

    get currentSource() {
        return this.state.sources.find((s) => s.key === this.domState.source) || null;
    }

    /** The source's filters, each with its data attribute (data-f-<key>, dataset fKey). */
    get currentFilters() {
        return (this.currentSource?.filters || []).map((f) => ({
            ...f, attr: "f" + f.key.charAt(0).toUpperCase() + f.key.slice(1),
        }));
    }

    get currentDesigns() {
        return this.currentSource?.designs || [];
    }
}

class CardsPlugin extends Plugin {
    static id = "mtbgCards";
    /** @type {import("plugins").WebsiteResources} */
    resources = {
        builder_options: [CardsOption],
        // the cards are drawn on each visit: never stored in the page
        content_not_editable_selectors: [".s_mtbg_cards_body"],
        clean_for_save_handlers: ({ root }) => {
            for (const el of root.querySelectorAll(".s_mtbg_cards_body")) {
                el.replaceChildren();
            }
        },
    };
}

registry.category("website-plugins").add(CardsPlugin.id, CardsPlugin);
