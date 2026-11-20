import { clickOnSave } from "@website/js/tours/tour_utils";
import { registry } from "@web/core/registry";

/** The website tour helpers' "noPrepend" key is only understood by registerWebsitePreviewTour. */
function withoutNoPrepend(steps) {
    return steps.map(({ noPrepend, ...step }) => step);
}

// A reusable block holding a photo gallery, edited and saved in the website editor (the test opens /mtbg/block/<id>
// in the builder): its thumbnails stay one element each (19.0.0.6.7: the editor merged identical neighbouring spans)
// and nothing the page's code adds is saved.
registry.category("web_tour.tours").add("mtbg_photo_gallery_save_tour", {
    steps: () => withoutNoPrepend([
        {
            content: "Wait for the edit mode to be started",
            trigger: ".o_builder_sidebar_open",
            timeout: 30000,
        },
        {
            content: "The gallery is in the editor as written (the page's buttons and ring undone)",
            trigger: ":iframe .mtbg-cb-page-body .mtbg-gallery .mtbg-gallery__thumbs:not(:has([role])):not(:has(.mtbg-gallery__thumb--active))",
        },
        {
            content: "Edit the text next to the gallery",
            trigger: ":iframe .mtbg-cb-page-body p.mtbg-test-text",
            run: "editor Edited next to the gallery",
        },
        ...clickOnSave(),
        {
            content: "After saving, the page shows the gallery",
            trigger: ":iframe .mtbg-cb-page-body .mtbg-gallery .mtbg-gallery__thumb",
        },
    ]),
});
