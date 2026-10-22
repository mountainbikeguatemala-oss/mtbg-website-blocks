import { Plugin } from "@html_editor/plugin";
import { BuilderAction } from "@html_builder/core/builder_action";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { BLOCK_SELECTOR, ContentBlockOption } from "./content_block_option";
import { ContentBlockPicker } from "./content_block_picker";

const MODEL = "mtbg.tours.content.block";
const BODY_SELECTOR = ".s_mtbg_content_block_body";
const PLACEHOLDER_CLASS = "s_mtbg_content_block_placeholder";

function bodyOf(blockEl) {
    return blockEl.querySelector(`:scope > ${BODY_SELECTOR}`);
}

/** Show a block (as returned by the server for the editor) in a Reusable Block element. */
function setBlock(blockEl, block) {
    blockEl.dataset.mtbgBlock = String(block.id);
    blockEl.dataset.mtbgLabel = block.name;
    blockEl.dataset.mtbgUsage = String(block.usage);
    blockEl.classList.remove("o_mtbg_cb_editing");
    blockEl.classList.add("o_not_editable");
    const holder = blockEl.ownerDocument.createElement("div");
    holder.innerHTML = block.html;
    blockEl.replaceChildren(...holder.childNodes);
}

/** Choose…: the block picker; the chosen block's current content replaces the element's content. */
export class ChooseContentBlockAction extends BuilderAction {
    static id = "mtbgChooseContentBlock";
    async load({ editingElement }) {
        const orm = this.services.orm;
        const data = await orm.call(MODEL, "mtbg_picker_data", []);
        let chosen = null;
        await new Promise((resolve) => {
            this.services.dialog.add(
                ContentBlockPicker,
                {
                    blocks: data.blocks,
                    types: data.types,
                    tags: data.tags,
                    currentId: parseInt(editingElement.dataset.mtbgBlock) || 0,
                    onChoose: async (id) => {
                        chosen = await orm.call(MODEL, "mtbg_editor_block", [id]);
                    },
                    onCreate: async (name) => {
                        chosen = await orm.call(MODEL, "mtbg_create_from_editor", [name]);
                        chosen.created = true;
                    },
                },
                { onClose: resolve }
            );
        });
        return chosen;
    }
    apply({ editingElement, loadResult: block }) {
        if (!block) {
            return;
        }
        setBlock(editingElement, block);
        if (block.created) {
            unlock(editingElement); // a new block is written right away
        }
    }
}

// While a block is unlocked its wrapper is not "o_not_editable": the builder only gives options and drop
// zones to elements outside "o_not_editable", so this is what makes the blocks inside the shared content
// (carousels, text, images...) selectable, editable with their native options, and lets new blocks be dropped in.
function unlock(blockEl) {
    const body = bodyOf(blockEl);
    if (!body) {
        return;
    }
    blockEl.classList.add("o_mtbg_cb_editing");
    blockEl.classList.remove("o_not_editable");
    body.removeAttribute("data-oe-readonly");
    body.classList.add("o_editable");
    body.setAttribute("contenteditable", "true");
    body.focus();
}

function lock(blockEl) {
    const body = bodyOf(blockEl);
    blockEl.classList.remove("o_mtbg_cb_editing");
    blockEl.classList.add("o_not_editable");
    if (body) {
        body.setAttribute("data-oe-readonly", "1");
        body.setAttribute("contenteditable", "false");
    }
}

/** Edit in place / Done: unlock the shared content for typing here (it saves to the block itself). */
export class EditContentBlockInPlaceAction extends BuilderAction {
    static id = "mtbgEditContentBlockInPlace";
    isApplied({ editingElement }) {
        return editingElement.classList.contains("o_mtbg_cb_editing");
    }
    apply({ editingElement }) {
        if (editingElement.classList.contains("o_mtbg_cb_editing")) {
            lock(editingElement);
        } else {
            unlock(editingElement);
        }
    }
}

/** Open: the block's back-office form in a new tab. */
export class OpenContentBlockAction extends BuilderAction {
    static id = "mtbgOpenContentBlock";
    apply({ editingElement }) {
        const id = parseInt(editingElement.dataset.mtbgBlock);
        if (id) {
            window.open(`/odoo/action-mtbg_tours_catalog.action_content_block/${id}`, "_blank", "noopener");
        }
    }
}

/** Make a local copy: the element becomes ordinary content of this page (no longer shared). */
export class DetachContentBlockAction extends BuilderAction {
    static id = "mtbgDetachContentBlock";
    apply({ editingElement }) {
        const body = bodyOf(editingElement);
        const copy = editingElement.ownerDocument.createElement("div");
        copy.className = [...editingElement.classList]
            .filter((c) => !c.startsWith("s_mtbg_content_block") && !c.startsWith("o_mtbg_cb") && c !== "o_not_editable")
            .join(" ");
        copy.innerHTML = body ? body.innerHTML : "";
        editingElement.replaceWith(copy);
    }
}

class MtbgContentBlockPlugin extends Plugin {
    static id = "mtbgContentBlock";
    /** @type {import("plugins").WebsiteResources} */
    resources = {
        builder_options: [ContentBlockOption],
        builder_actions: {
            ChooseContentBlockAction,
            EditContentBlockInPlaceAction,
            OpenContentBlockAction,
            DetachContentBlockAction,
        },
        // droppable among content and directly in page areas / HTML fields such as a tour's description
        so_content_addition_selector: [BLOCK_SELECTOR],
        so_snippet_addition_selector: [BLOCK_SELECTOR],
        // the shared content is locked until "Edit in place"
        content_not_editable_selectors: [`${BLOCK_SELECTOR}:not(.o_mtbg_cb_editing) ${BODY_SELECTOR}`],
        on_snippet_dropped_handlers: this.onSnippetDropped.bind(this),
        // a page stores only the block id: the shared content is filled in when the page is rendered
        clean_for_save_handlers: this.cleanForSave.bind(this),
    };

    onSnippetDropped({ snippetEl }) {
        const blockEl = snippetEl.matches(BLOCK_SELECTOR) ? snippetEl : snippetEl.querySelector(BLOCK_SELECTOR);
        if (blockEl && blockEl.parentElement?.closest(BODY_SELECTOR)) {
            blockEl.remove(); // no reusable block inside another one's shared content
            this.services.notification.add(_t("A reusable block cannot be placed inside another reusable block."), {
                type: "warning",
            });
        }
    }

    cleanForSave({ root }) {
        // dynamic slots (filled for each page): stored with their placeholder only
        for (const slotEl of root.querySelectorAll("[data-mtbg-slot]")) {
            slotEl.replaceChildren(slotEl.dataset.mtbgSlotLabel || "");
        }
        for (const blockEl of root.querySelectorAll(BLOCK_SELECTOR)) {
            const placeholder = root.ownerDocument.createElement("div");
            placeholder.className = PLACEHOLDER_CLASS;
            placeholder.textContent = "Reusable block";
            blockEl.replaceChildren(placeholder);
            blockEl.classList.remove("o_mtbg_cb_editing");
            blockEl.classList.add("o_not_editable"); // stored locked, even if saved while unlocked
            delete blockEl.dataset.mtbgLabel;
            delete blockEl.dataset.mtbgUsage;
        }
    }
}

registry.category("website-plugins").add(MtbgContentBlockPlugin.id, MtbgContentBlockPlugin);
