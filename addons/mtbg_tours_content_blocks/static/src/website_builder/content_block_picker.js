import { Component, onMounted, useRef, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

/** Dialog listing the reusable blocks: search by name or text, filter by type, pick a card or create one. */
export class ContentBlockPicker extends Component {
    static template = "mtbg_tours_content_blocks.ContentBlockPicker";
    static components = { Dialog };
    static props = {
        blocks: Array,
        types: Array,
        currentId: { type: Number, optional: true },
        onChoose: Function,
        onCreate: Function,
        close: Function,
    };

    setup() {
        this.state = useState({ query: "", type: "", newName: "", creating: false });
        const search = useRef("search");
        onMounted(() => search.el?.focus());
    }

    get filtered() {
        const words = this.state.query.toLowerCase().split(/\s+/).filter(Boolean);
        return this.props.blocks.filter((block) => {
            if (this.state.type && block.type !== this.state.type) {
                return false;
            }
            const text = `${block.name} ${block.excerpt}`.toLowerCase();
            return words.every((word) => text.includes(word));
        });
    }

    async choose(block) {
        await this.props.onChoose(block.id); // the block is fetched before the picker closes
        this.props.close();
    }

    async create() {
        if (this.state.creating) {
            return;
        }
        this.state.creating = true;
        try {
            await this.props.onCreate(this.state.newName || this.state.query);
            this.props.close();
        } finally {
            this.state.creating = false;
        }
    }
}
