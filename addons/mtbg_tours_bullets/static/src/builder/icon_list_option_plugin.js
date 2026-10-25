/**
 * Bullets block (s_mtbg_icon_list, views/snippets.xml): its options. A preset sets the block's class and drops the
 * look set one by one; "Choose…" opens the icon picker and keeps the icon's character and font as the block's
 * --mtbg-icon / --mtbg-icon-font (the bullets are drawn by icon_list.scss); colour, sizes, box and spacing are the
 * other --mtbg-icon-* variables (styleAction).
 */
import { BuilderAction } from "@html_builder/core/builder_action";
import { BaseOptionComponent } from "@html_builder/core/utils";
import { Plugin } from "@html_editor/plugin";
import { registry } from "@web/core/registry";

const PRESETS = ["check", "bookmark", "cross", "none"];
const LOOK_VARIABLES = [
    "--mtbg-icon", "--mtbg-icon-font", "--mtbg-icon-color", "--mtbg-icon-size", "--mtbg-icon-box", "--mtbg-icon-bg",
    "--mtbg-icon-radius", "--mtbg-icon-gap",
];

export class IconListOption extends BaseOptionComponent {
    static template = "mtbg_tours_bullets.IconListOption";
    static selector = ".s_mtbg_icon_list";
}

function presetOf(el) {
    return PRESETS.find((preset) => el.classList.contains(`mtbg-icons--${preset}`)) || "";
}

export class IconPresetAction extends BuilderAction {
    static id = "mtbgIconPreset";
    apply({ editingElement, params: { mainParam: preset } }) {
        for (const other of PRESETS) {
            editingElement.classList.remove(`mtbg-icons--${other}`);
        }
        editingElement.classList.add(`mtbg-icons--${preset}`);
        for (const variable of LOOK_VARIABLES) {
            editingElement.style.removeProperty(variable);
        }
        if (!editingElement.getAttribute("style")) {
            editingElement.removeAttribute("style");
        }
        delete editingElement.dataset.icon;
    }
    isApplied({ editingElement, params: { mainParam: preset } }) {
        return presetOf(editingElement) === preset && !editingElement.dataset.icon;
    }
}

export class IconCustomAction extends BuilderAction {
    static id = "mtbgIconCustom";
    static dependencies = ["media"];
    async load({ editingElement }) {
        return new Promise((resolve) => {
            const media = document.createElement("i");
            media.className = editingElement.dataset.icon || "fa fa-check";
            const onClose = this.dependencies.media.openMediaDialog(
                { visibleTabs: ["ICONS"], media, save: (icon) => resolve(icon) },
                this.editable
            );
            onClose.then(() => resolve(null));
        });
    }
    apply({ editingElement, loadResult: iconEl }) {
        if (!iconEl) {
            return;
        }
        // the icon's character and font, read from the icon itself in the page
        const probe = editingElement.ownerDocument.createElement("i");
        probe.className = iconEl.className;
        probe.style.position = "absolute";
        probe.style.visibility = "hidden";
        editingElement.appendChild(probe);
        const style = editingElement.ownerDocument.defaultView.getComputedStyle(probe, "::before");
        const glyph = (style.content || "").replace(/^["']|["']$/g, "");
        const font = style.fontFamily;
        probe.remove();
        if (!glyph || glyph === "none") {
            return;
        }
        const escaped = [...glyph].map((char) => `\\${char.codePointAt(0).toString(16)}`).join("");
        editingElement.style.setProperty("--mtbg-icon", `"${escaped}"`);
        editingElement.style.setProperty("--mtbg-icon-font", font);
        editingElement.dataset.icon = iconEl.className;
    }
}

class MtbgIconListPlugin extends Plugin {
    static id = "mtbgIconList";
    /** @type {import("plugins").WebsiteResources} */
    resources = {
        builder_options: [IconListOption],
        builder_actions: { IconPresetAction, IconCustomAction },
    };
}

registry.category("website-plugins").add(MtbgIconListPlugin.id, MtbgIconListPlugin);
