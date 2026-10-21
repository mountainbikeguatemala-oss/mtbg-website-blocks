import { BaseOptionComponent, useDomState } from "@html_builder/core/utils";

export const BLOCK_SELECTOR = ".s_mtbg_content_block";

/** Block options: which shared block this is, edit it in place or in the back office, or detach it. */
export class ContentBlockOption extends BaseOptionComponent {
    static template = "mtbg_tours_content_blocks.ContentBlockOption";
    static selector = BLOCK_SELECTOR;

    setup() {
        super.setup();
        this.state = useDomState((editingElement) => ({
            blockId: parseInt(editingElement.dataset.mtbgBlock) || 0,
            name: editingElement.dataset.mtbgLabel || "",
            usage: parseInt(editingElement.dataset.mtbgUsage) || 0,
            editing: editingElement.classList.contains("o_mtbg_cb_editing"),
        }));
    }
}
