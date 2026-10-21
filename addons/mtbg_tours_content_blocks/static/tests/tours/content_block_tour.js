import { clickOnSave, registerWebsitePreviewTour } from "@website/js/tours/tour_utils";

registerWebsitePreviewTour(
    "mtbg_content_block_tour",
    { url: "/tours/cb-editor-tour", edition: true },
    () => [
        {
            content: "Drag the Reusable Block into the tour description",
            trigger:
                '.o_block_tab:not(.o_we_ongoing_insertion) #snippet_content .o_snippet[name="Reusable Block"].o_draggable .o_snippet_thumbnail',
            run: "drag_and_drop :iframe .mtbg-description p",
        },
        {
            content: "The new block asks for a block to show",
            trigger: ":iframe .mtbg-description .s_mtbg_content_block .s_mtbg_content_block_placeholder",
            run: "click",
        },
        {
            content: "Open the block picker",
            trigger: "button.o_mtbg_cb_choose",
            run: "click",
        },
        {
            content: "Search the blocks",
            trigger: ".o_mtbg_cb_picker input[type=search]",
            run: "edit Rain",
        },
        {
            content: "Pick the Rain Policy card",
            trigger: ".o_mtbg_cb_picker .o_mtbg_cb_card:contains('Rain Policy')",
            run: "click",
        },
        {
            content: "The shared content shows in the page, locked",
            trigger: ":iframe .s_mtbg_content_block[data-mtbg-label='Rain Policy'] .s_mtbg_content_block_body[data-oe-readonly]:contains('We ride in the rain.')",
        },
        {
            content: "Unlock it: Edit in place",
            trigger: "button:contains('In place')",
            run: "click",
        },
        {
            content: "Type in the shared content",
            trigger: ":iframe .s_mtbg_content_block.o_mtbg_cb_editing .s_mtbg_content_block_body p",
            run: "editor Ponchos are provided.",
        },
        ...clickOnSave(),
        {
            content: "After saving, the page shows the edited shared content",
            trigger: ":iframe .mtbg-description .s_mtbg_content_block_body:contains('Ponchos are provided.')",
        },
    ]
);
