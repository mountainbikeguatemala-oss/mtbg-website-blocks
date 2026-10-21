import { clickOnSave, goBackToBlocks, registerWebsitePreviewTour } from "@website/js/tours/tour_utils";

registerWebsitePreviewTour(
    "mtbg_content_block_nested_tour",
    { url: "/tours/cb-nested-tour", edition: true },
    () => [
        {
            content: "Select the reusable block",
            trigger: ":iframe .s_mtbg_content_block .s_mtbg_content_block_body h3:contains('Why Ride')",
            run: "click",
        },
        {
            content: "Unlock it: Edit in place",
            trigger: "button:contains('In place')",
            run: "click",
        },
        {
            content: "Unlocked, the wrapper is no longer o_not_editable",
            trigger: ":iframe .s_mtbg_content_block.o_mtbg_cb_editing:not(.o_not_editable)",
        },
        {
            content: "Click the native Text block inside the shared content",
            trigger: ":iframe .s_mtbg_content_block_body section.s_text_block h3:contains('Why Ride')",
            run: "click",
        },
        {
            content: "The block inside gets its own native options",
            trigger: "[data-container-title='Text']",
        },
        goBackToBlocks(),
        {
            content: "Drop an Alert into the shared content",
            trigger:
                '.o_block_tab:not(.o_we_ongoing_insertion) #snippet_content .o_snippet[name="Alert"].o_draggable .o_snippet_thumbnail',
            run: "drag_and_drop :iframe .s_mtbg_content_block_body section.s_text_block p",
        },
        {
            content: "The Alert is inside the shared content",
            trigger: ":iframe .s_mtbg_content_block_body .s_alert",
        },
        ...clickOnSave(),
        {
            content: "After saving, the page shows the shared content with the Alert",
            trigger: ":iframe .s_mtbg_content_block_body .s_alert",
        },
    ]
);
