import { BaseOptionComponent } from "@html_builder/core/utils";
import { Plugin } from "@html_editor/plugin";
import { registry } from "@web/core/registry";

const GROUP_STRUCTURE_SELECTOR = ".s_mtbg_group > .oe_structure";
// Background classes of a block (color combination, color, image, filter, scroll effect, video).
const BACKGROUND_CLASS_RE = /^(o_cc\d?|bg-.+|text-bg-.+|oe_img_bg|o_bg_img_.+|parallax|s_parallax_.+|o_background_video)$/;
const BACKGROUND_LAYERS_SELECTOR = ":scope > .o_we_bg_filter, :scope > .s_parallax_bg, :scope > .o_bg_video_container";

/** Make a block transparent: the group's background shows behind it. */
export function clearBackground(el) {
    el.classList.remove(...[...el.classList].filter((c) => BACKGROUND_CLASS_RE.test(c)));
    for (const prop of ["background", "background-color", "background-image", "background-position", "background-size"]) {
        el.style.removeProperty(prop);
    }
    if (!el.getAttribute("style")) {
        el.removeAttribute("style");
    }
    delete el.dataset.scrollBackgroundRatio;
    delete el.dataset.parallaxType;
    delete el.dataset.bgVideoSrc;
    for (const layer of el.querySelectorAll(BACKGROUND_LAYERS_SELECTOR)) {
        layer.remove();
    }
}

/** Group options (width, corners, shadow); background, filter and scroll effect are the native section options. */
export class GroupOption extends BaseOptionComponent {
    static template = "mtbg_tours_content_blocks.GroupOption";
    static selector = ".s_mtbg_group";
}

class MtbgGroupPlugin extends Plugin {
    static id = "mtbgGroup";
    /** @type {import("plugins").WebsiteResources} */
    resources = {
        builder_options: [GroupOption],
        // like the native Parallax block: text is typed in the blocks of the group, not in the group itself
        content_not_editable_selectors: GROUP_STRUCTURE_SELECTOR,
        on_snippet_dropped_handlers: this.onSnippetDropped.bind(this),
    };

    /** A block dropped into a group is transparent, slides included: the group carries the background. */
    onSnippetDropped({ snippetEl }) {
        if (!snippetEl.parentElement?.matches(GROUP_STRUCTURE_SELECTOR)) {
            return;
        }
        clearBackground(snippetEl);
        for (const slideEl of snippetEl.querySelectorAll(".carousel-item")) {
            clearBackground(slideEl);
        }
    }
}

registry.category("website-plugins").add(MtbgGroupPlugin.id, MtbgGroupPlugin);
