/**
 * The Reusable Blocks page: every reusable block, organised by type and tags (drag blocks onto a tag, or tick
 * several and act on them at once), with the selected block's details, where it is used and a live preview. The
 * content is edited in the full website builder ("Edit in Website Builder"), which links back here.
 */
import { Component, onWillStart, useEffect, useRef, useState } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const MODEL = "mtbg.content.block.library";
const LAST_KEY = "mtbg_tours.block_library_last";  // the block shown last (per browser)
const TAG_COLORS = 12;

export class BlockLibrary extends Component {
    static template = "mtbg_tours_content_blocks.BlockLibrary";
    static props = ["*"];
    static components = { Dropdown, DropdownItem };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.newName = useRef("newName");
        this.newTagInput = useRef("newTag");
        this.tagInput = useRef("tagInput");
        this.state = useState({
            data: null, query: "", view: "all", type: "", tag: 0, sort: "name", selected: [],
            currentId: 0, current: null, theme: "light", device: "desktop", frameKey: 1,
            dragging: 0, dropTag: 0, editingTag: null, creatingTag: false, newTag: "", adding: false,
        });
        // fields that open on a click take the focus
        useEffect((el) => el?.focus(), () => [this.newTagInput.el]);
        useEffect((el) => el?.select(), () => [this.tagInput.el]);
        useEffect((el) => el?.focus(), () => [this.newName.el]);
        onWillStart(async () => {
            await this.load();
            const fromUrl = parseInt(new URLSearchParams(window.location.search).get("block"));
            let last = 0;
            try {
                last = parseInt(window.localStorage.getItem(LAST_KEY));
            } catch {
                // blocked storage: the first block
            }
            const start = [fromUrl, last].find((id) => this.blockById(id)) || this.visible[0]?.id;
            if (start) {
                await this.open(start);
            }
        });
    }

    async load() {
        this.state.data = await this.orm.call(MODEL, "mtbg_get_library", []);
        const ids = new Set(this.state.data.blocks.map((b) => b.id));
        this.state.selected = this.state.selected.filter((id) => ids.has(id));
    }

    blockById(id) {
        return this.state.data.blocks.find((b) => b.id === id);
    }

    tagById(id) {
        return this.state.data.tags.find((t) => t.id === id);
    }

    typeLabel(key) {
        return this.state.data.types.find((t) => t.key === key)?.label || key;
    }

    // ------------------------------------------------------------------
    // Filters
    // ------------------------------------------------------------------
    get views() {
        const blocks = this.state.data.blocks;
        const active = blocks.filter((b) => b.active);
        return [
            { key: "all", label: _t("All blocks"), icon: "fa-clone", count: active.length },
            { key: "unused", label: _t("Not used anywhere"), icon: "fa-chain-broken", count: active.filter((b) => !b.usage).length },
            { key: "builtin", label: _t("Built into extensions"), icon: "fa-puzzle-piece", count: active.filter((b) => b.builtin).length },
            { key: "empty", label: _t("Empty (no text or image)"), icon: "fa-square-o", count: active.filter((b) => b.empty).length },
            { key: "duplicates", label: _t("Possible duplicates"), icon: "fa-files-o", count: active.filter((b) => b.duplicate).length },
            { key: "untagged", label: _t("No tag"), icon: "fa-tag", count: active.filter((b) => !b.tag_ids.length).length },
            { key: "archived", label: _t("Archived"), icon: "fa-archive", count: blocks.length - active.length },
        ];
    }

    typeCount(key) {
        return this.state.data.blocks.filter((b) => b.active && b.type === key).length;
    }

    tagCount(id) {
        return this.state.data.blocks.filter((b) => b.active && b.tag_ids.includes(id)).length;
    }

    setView(view) {
        this.state.view = view;
        this.state.type = "";
        this.state.tag = 0;
    }

    setType(type) {
        this.state.type = this.state.type === type ? "" : type;
    }

    setTag(id) {
        this.state.tag = this.state.tag === id ? 0 : id;
    }

    /** The list: the sidebar's view, type and tag, then the search words (name, text, tags, type). */
    get visible() {
        const s = this.state;
        const words = s.query.toLowerCase().split(/\s+/).filter(Boolean);
        const blocks = s.data.blocks.filter((b) => {
            if (s.view === "archived" ? b.active : !b.active) {
                return false;
            }
            if ((s.view === "unused" && b.usage) || (s.view === "empty" && !b.empty) || (s.view === "builtin" && !b.builtin)
                || (s.view === "duplicates" && !b.duplicate) || (s.view === "untagged" && b.tag_ids.length)) {
                return false;
            }
            if ((s.type && b.type !== s.type) || (s.tag && !b.tag_ids.includes(s.tag))) {
                return false;
            }
            const tags = b.tag_ids.map((id) => this.tagById(id)?.name || "").join(" ");
            const text = `${b.name} ${b.excerpt} ${tags} ${this.typeLabel(b.type)}`.toLowerCase();
            return words.every((w) => text.includes(w));
        });
        const sorters = {
            name: (a, b) => a.name.localeCompare(b.name),
            recent: (a, b) => (b.write_date || "").localeCompare(a.write_date || ""),
            usage: (a, b) => b.usage - a.usage || a.name.localeCompare(b.name),
        };
        return blocks.sort(sorters[s.sort]);
    }

    // ------------------------------------------------------------------
    // The selected block
    // ------------------------------------------------------------------
    async open(id) {
        this.state.currentId = id;
        this.state.current = await this.orm.call(MODEL, "mtbg_get_block", [id]);
        try {
            window.localStorage.setItem(LAST_KEY, String(id));
        } catch {
            // private mode: not remembered
        }
        this.state.frameKey++;
    }

    async save(vals) {
        const current = this.state.current;
        try {
            this.state.current = await this.orm.call(MODEL, "mtbg_save_block", [current.id, vals]);
        } catch (error) {
            this.state.current = await this.orm.call(MODEL, "mtbg_get_block", [current.id]);
            throw error;
        }
        await this.load();
    }

    toggleCurrentTag(id) {
        const tags = this.state.current.tag_ids;
        return this.save({ tag_ids: tags.includes(id) ? tags.filter((t) => t !== id) : [...tags, id] });
    }

    get availableTags() {
        return this.state.data.tags.filter((t) => !this.state.current.tag_ids.includes(t.id));
    }

    editInBuilder() {
        // the builder page's "Back to Reusable Blocks" brings the user back to this block
        window.location.href = `/odoo/action-website.website_preview?path=${encodeURIComponent(`/mtbg/block/${this.state.currentId}`)}&enable_editor=1`;
    }

    openForm() {
        this.action.doAction({
            type: "ir.actions.act_window", res_model: "mtbg.tours.content.block", res_id: this.state.currentId,
            views: [[false, "form"]],
        });
    }

    openList() {
        this.action.doAction(this.state.data.list_action);
    }

    async newBlock() {
        const name = this.newName.el?.value.trim();
        if (!name) {
            this.state.adding = true;
            return;
        }
        const id = await this.orm.call(MODEL, "mtbg_create_block", [name, this.state.tag ? [this.state.tag] : [],
            this.state.type || false]);
        this.state.adding = false;
        this.state.view = "all";
        await this.load();
        await this.open(id);
    }

    onNewKey(ev) {
        if (ev.key === "Enter") {
            this.newBlock();
        } else if (ev.key === "Escape") {
            this.state.adding = false;
        }
    }

    // ------------------------------------------------------------------
    // Several blocks at once
    // ------------------------------------------------------------------
    isSelected(id) {
        return this.state.selected.includes(id);
    }

    toggleSelected(id) {
        const selected = this.state.selected;
        this.state.selected = selected.includes(id) ? selected.filter((i) => i !== id) : [...selected, id];
    }

    get allVisibleSelected() {
        const visible = this.visible;
        return visible.length > 0 && visible.every((b) => this.isSelected(b.id));
    }

    toggleAll() {
        this.state.selected = this.allVisibleSelected ? [] : this.visible.map((b) => b.id);
    }

    async bulk(operation, value = null, ids = null) {
        ids = ids || this.state.selected;
        const result = await this.orm.call(MODEL, "mtbg_bulk", [ids, operation, value]);
        if (["archive", "restore", "delete"].includes(operation)) {
            this.state.selected = [];
        }
        await this.load();
        if (operation === "duplicate" && result.length) {
            this.state.view = "all";
            await this.open(result[0]);
        } else if (this.state.currentId && this.blockById(this.state.currentId)) {
            this.state.current = await this.orm.call(MODEL, "mtbg_get_block", [this.state.currentId]);
        } else {
            this.state.current = null;
            this.state.currentId = 0;
        }
        const messages = {
            add_tag: _t("Tag added to %s block(s).", ids.length), remove_tag: _t("Tag removed from %s block(s).", ids.length),
            set_type: _t("Type set on %s block(s).", ids.length), archive: _t("%s block(s) archived.", ids.length),
            restore: _t("%s block(s) restored.", ids.length), duplicate: _t("%s block(s) duplicated.", ids.length),
            delete: _t("%s block(s) deleted.", ids.length),
        };
        this.notification.add(messages[operation], { type: "success" });
    }

    /** Archive, asking first when other reusable blocks contain them (they would show nothing there). */
    async confirmArchive(ids = null) {
        ids = ids || this.state.selected;
        const inside = await this.orm.call(MODEL, "mtbg_used_inside", [ids]);
        const names = Object.entries(inside);
        if (!names.length) {
            return this.bulk("archive", null, ids);
        }
        const lines = names.map(([name, parents]) => `${name} (in ${parents.join(", ")})`).join(" · ");
        this.dialog.add(ConfirmationDialog, {
            title: _t("Used inside other blocks"),
            body: _t("Archived, these blocks show nothing inside the blocks that contain them: %s", lines),
            confirmLabel: _t("Archive"),
            confirm: () => this.bulk("archive", null, ids),
            cancel: () => {},
        });
    }

    confirmDelete(ids = null) {
        ids = ids || this.state.selected;
        this.dialog.add(ConfirmationDialog, {
            title: _t("Delete for good?"),
            body: _t("%s block(s) will be deleted permanently. Only blocks not used anywhere can be deleted; archive the others.", ids.length),
            confirmLabel: _t("Delete"),
            confirm: () => this.bulk("delete", null, ids),
            cancel: () => {},
        });
    }

    // drag a block (or the ticked blocks, when it is one of them) onto a tag of the sidebar to tag them
    onDragStart(ev, id) {
        this.state.dragging = id;
        ev.dataTransfer.effectAllowed = "copy";
        // its own type: dropped on a text field it does not type the id
        ev.dataTransfer.setData("application/x-mtbg-block", String(id));
    }

    onDragEnd() {
        this.state.dragging = 0;
        this.state.dropTag = 0;
    }

    onTagDragOver(ev, id) {
        if (this.state.dragging) {
            ev.preventDefault();
            this.state.dropTag = id;
        }
    }

    async onTagDrop(id) {
        const dragged = this.state.dragging;
        const ids = this.isSelected(dragged) ? this.state.selected : [dragged];
        this.onDragEnd();
        if (dragged) {
            await this.bulk("add_tag", id, ids);
        }
    }

    // ------------------------------------------------------------------
    // Tags
    // ------------------------------------------------------------------
    async saveTag(id, name, color = null) {
        await this.orm.call(MODEL, "mtbg_save_tag", [id || false, name, color]);
        this.state.editingTag = null;
        this.state.creatingTag = false;
        this.state.newTag = "";
        await this.load();
    }

    onTagKey(ev, id) {
        if (ev.key === "Enter" && !ev.target.value.trim()) {
            this.state.editingTag = null;
            this.state.creatingTag = false;
        } else if (ev.key === "Enter") {
            this.saveTag(id, ev.target.value);
        } else if (ev.key === "Escape") {
            this.state.editingTag = null;
            this.state.creatingTag = false;
        }
    }

    cycleColor(tag) {
        return this.saveTag(tag.id, tag.name, (tag.color + 1) % TAG_COLORS);
    }

    deleteTag(tag) {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Remove the tag %s?", tag.name),
            body: _t("It comes off %s block(s); the blocks stay.", this.tagCount(tag.id)),
            confirmLabel: _t("Remove tag"),
            confirm: async () => {
                await this.orm.call(MODEL, "mtbg_delete_tag", [tag.id]);
                if (this.state.tag === tag.id) {
                    this.state.tag = 0;
                }
                this.state.editingTag = null;
                await this.load();
                if (this.state.currentId) {
                    this.state.current = await this.orm.call(MODEL, "mtbg_get_block", [this.state.currentId]);
                }
            },
            cancel: () => {},
        });
    }

    // ------------------------------------------------------------------
    // Preview
    // ------------------------------------------------------------------
    get previewUrl() {
        // a new address on each reload: never a cached copy
        return `/mtbg/block/${this.state.currentId}?preview=1&theme=${this.state.theme}&v=${this.state.frameKey}`;
    }

    reloadPreview() {
        this.state.frameKey++;
    }

    setTheme(theme) {
        this.state.theme = theme;
        this.reloadPreview();
    }

    usageIcon(kind) {
        return {
            tour: "fa-bicycle", page: "fa-file-o", template: "fa-window-maximize", block: "fa-clone", extension: "fa-puzzle-piece",
        }[kind];
    }

    formatDate(iso) {
        return iso ? new Date(`${iso}Z`).toLocaleString() : "";
    }
}

registry.category("actions").add("mtbg_content_block_library", BlockLibrary);
