import { clickOnSave } from "@website/js/tours/tour_utils";
import { registry } from "@web/core/registry";

/** The website tour helpers' "noPrepend" key is only understood by registerWebsitePreviewTour. */
function withoutNoPrepend(steps) {
    return steps.map(({ noPrepend, ...step }) => step);
}

// Group dragged straight from the Blocks panel (not through the Content category's window) into an html field
// (a reusable block's content here, a tour's Description on tour pages), given a background, saved.
registry.category("web_tour.tours").add("mtbg_group_panel_tour", {
    steps: () => withoutNoPrepend([
        {
            content: "Wait for the edit mode to be started",
            trigger: ".o_builder_sidebar_open",
            timeout: 30000,
        },
        {
            content: "Drag the Group tile from the panel into the content",
            trigger:
                ".o_block_tab:not(.o_we_ongoing_insertion) #snippet_content .o_snippet[name='Group'].o_draggable .o_snippet_thumbnail",
            run: "drag_and_drop :iframe main [data-oe-type=html] > p",
        },
        {
            content: "Select the group through its Text block",
            trigger: ":iframe main [data-oe-type=html] .s_mtbg_group > .oe_structure > section.s_text_block h2",
            run: "click",
        },
        {
            content: "Open the group's background colour",
            trigger: "[data-container-title='Group'] [data-label='Background'] .o_we_color_preview",
            run: "click",
        },
        {
            content: "Theme colours",
            trigger: ".o_popover .o_font_color_selector .btn-tab:contains('Theme')",
            run: "click",
        },
        {
            content: "Pick colour combination 4",
            trigger: ".o_popover [data-color='o_cc4']",
            run: "click",
        },
        {
            content: "The group has the new background",
            trigger: ":iframe main [data-oe-type=html] .s_mtbg_group.o_cc4",
        },
        ...clickOnSave(),
        {
            content: "After saving, the page shows the group with its background",
            trigger: ":iframe .s_mtbg_group.o_cc4 h2:contains('Group title')",
        },
    ]),
});
