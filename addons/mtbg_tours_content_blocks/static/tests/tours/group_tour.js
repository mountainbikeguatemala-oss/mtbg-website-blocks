import { clickOnSave, goBackToBlocks, insertSnippet } from "@website/js/tours/tour_utils";
import { registry } from "@web/core/registry";

/** The website tour helpers' "noPrepend" key is only understood by registerWebsitePreviewTour. */
function withoutNoPrepend(steps) {
    return steps.map(({ noPrepend, ...step }) => step);
}

// Runs on a reusable block's editor page: the test opens /mtbg/block/<id> in the builder, so the tour has no url
// of its own (registerWebsitePreviewTour would send it to the homepage).
registry.category("web_tour.tours").add("mtbg_group_tour", {
    steps: () => withoutNoPrepend([
        {
            content: "Wait for the edit mode to be started",
            trigger: ".o_builder_sidebar_open",
            timeout: 30000,
        },
        ...insertSnippet({ id: "s_mtbg_group", name: "Group", groupName: "Content" }),
        {
            content: "The Group holds a Text block in its drop area",
            trigger: ":iframe .mtbg-cb-page-body .s_mtbg_group > .oe_structure > section.s_text_block h2",
            run: "click",
        },
        {
            content: "The block inside the group keeps its own background options",
            trigger: "[data-container-title='Text'] [data-label='Background']",
        },
        {
            content: "The group has its own background options",
            trigger: "[data-container-title='Group'] [data-label='Background']",
        },
        goBackToBlocks(),
        {
            content: "Drag the Intro category into the group, after its Text block",
            trigger:
                ".o_block_tab:not(.o_we_ongoing_insertion) #snippet_groups .o_snippet[name='Intro'].o_draggable .o_snippet_thumbnail_area",
            run: "drag_and_drop :iframe .s_mtbg_group > .oe_structure > section.s_text_block",
        },
        {
            content: "Pick the Cover block (it comes with a background image, filter and colors)",
            trigger: ".modal .show:iframe .o_snippet_preview_wrap[data-snippet-id='s_cover']:not(.d-none)",
            run: "click",
        },
        {
            content: "In the group the Cover is transparent: the group carries the background",
            trigger:
                ":iframe .s_mtbg_group > .oe_structure > .s_cover:not(.oe_img_bg):not(.o_cc):not(:has(.o_we_bg_filter))",
        },
        {
            content: "Select the group with its tab",
            trigger: ":iframe .s_mtbg_group > .oe_structure > section.s_text_block h2",
            run: "click",
        },
        {
            content: "Open the group's Width option",
            trigger: "[data-container-title='Group'] [data-label='Width'] .dropdown-toggle",
            run: "click",
        },
        {
            content: "Make the group boxed",
            trigger: ".o_popover .o-dropdown-item:contains('Boxed')",
            run: "click",
        },
        {
            content: "The group is boxed",
            trigger: ":iframe .s_mtbg_group.s_mtbg_group_boxed",
        },
        ...clickOnSave(),
        {
            content: "After saving, the page shows the boxed group",
            trigger: ":iframe .mtbg-cb-page-body .s_mtbg_group.s_mtbg_group_boxed",
        },
    ]),
});
