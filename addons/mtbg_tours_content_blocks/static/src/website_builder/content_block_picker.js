import { Component, onMounted, onWillUnmount, useEffect, useRef, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

const PREVIEW_BATCH = 24; // the cards' previews asked for at once
const PREVIEW_DELAY = 40; // ms: the cards coming into view together go in one call

/**
 * Dialog listing the reusable blocks: search by name or text, filter by type and tag, pick a card or create one.
 * Two stages: the cards show at once as text (name, type, tags, usage: ``blocks``), usable right away; their previews
 * (excerpt and thumbnail, ``loadPreviews``) are filled in as they come into view, a batch at a time, with a
 * placeholder until then.
 */
export class ContentBlockPicker extends Component {
    static template = "mtbg_tours_content_blocks.ContentBlockPicker";
    static components = { Dialog };
    static props = {
        blocks: Array,
        types: Array,
        tags: { type: Array, optional: true },
        currentId: { type: Number, optional: true },
        loadPreviews: { type: Function, optional: true },
        onChoose: Function,
        onCreate: Function,
        close: Function,
    };

    setup() {
        this.state = useState({ query: "", type: "", tag: 0, newName: "", creating: false, previews: {} });
        const search = useRef("search");
        onMounted(() => search.el?.focus());
        this.grid = useRef("grid");
        this.asked = new Set(); // ids asked for (or loaded)
        this.queue = new Set();
        this.timer = null;
        this.observer = null;
        onMounted(() => {
            if (!this.props.loadPreviews || !window.IntersectionObserver) {
                return;
            }
            this.observer = new IntersectionObserver((entries) => {
                for (const entry of entries) {
                    if (entry.isIntersecting) {
                        this.observer.unobserve(entry.target);
                        this.ask(parseInt(entry.target.dataset.blockId));
                    }
                }
            }, { root: this.grid.el, rootMargin: "200px 0px" });
        });
        // the cards shown (after a search or a filter too): watched until their preview is asked for
        useEffect(() => {
            if (!this.observer) {
                return;
            }
            for (const card of this.grid.el?.querySelectorAll("[data-block-id]") || []) {
                if (!this.asked.has(parseInt(card.dataset.blockId))) {
                    this.observer.observe(card);
                }
            }
        });
        onWillUnmount(() => {
            this.observer?.disconnect();
            clearTimeout(this.timer);
        });
    }

    ask(id) {
        if (!id || this.asked.has(id)) {
            return;
        }
        this.asked.add(id);
        this.queue.add(id);
        clearTimeout(this.timer);
        this.timer = setTimeout(() => this.flush(), PREVIEW_DELAY);
    }

    async flush() {
        while (this.queue.size) {
            const ids = [...this.queue].slice(0, PREVIEW_BATCH);
            ids.forEach((id) => this.queue.delete(id));
            try {
                Object.assign(this.state.previews, await this.props.loadPreviews(ids));
            } catch {
                ids.forEach((id) => this.asked.delete(id)); // asked again when it comes back into view
            }
        }
    }

    preview(block) {
        return this.state.previews[block.id];
    }

    get filtered() {
        const words = this.state.query.toLowerCase().split(/\s+/).filter(Boolean);
        return this.props.blocks.filter((block) => {
            if (this.state.type && block.type !== this.state.type) {
                return false;
            }
            if (this.state.tag && !(block.tag_ids || []).includes(this.state.tag)) {
                return false;
            }
            // name, type and tags at once; the text too once the card's preview is in
            const tags = (block.tag_ids || []).map((id) => this.tagById(id)?.name || "").join(" ");
            const text = `${block.name} ${block.type_label || ""} ${tags} ${this.preview(block)?.excerpt || ""}`.toLowerCase();
            return words.every((word) => text.includes(word));
        });
    }

    tagById(id) {
        return (this.props.tags || []).find((t) => t.id === id);
    }

    setTag(id) {
        this.state.tag = this.state.tag === id ? 0 : id;
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
