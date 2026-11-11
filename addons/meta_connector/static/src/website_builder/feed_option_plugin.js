import { Plugin } from "@html_editor/plugin";
import { registry } from "@web/core/registry";
import { InstagramFeedOption } from "./feed_option";

class InstagramFeedOptionPlugin extends Plugin {
    static id = "metaInstagramFeedOption";
    /** @type {import("plugins").WebsiteResources} */
    resources = {
        builder_options: [InstagramFeedOption],
        // droppable next to content in sections and columns (the footer too)
        so_content_addition_selector: [".s_meta_instagram_feed"],
        so_snippet_addition_selector: [".s_meta_instagram_feed"],
        // only the block and its options are saved, never the posts
        clean_for_save_handlers: ({ root }) => {
            for (const el of root.querySelectorAll(".o_meta_feed_generated")) {
                el.remove();
            }
            for (const el of root.querySelectorAll(".s_meta_instagram_feed_placeholder.d-none")) {
                el.classList.remove("d-none");
            }
        },
    };
}

registry.category("website-plugins").add(InstagramFeedOptionPlugin.id, InstagramFeedOptionPlugin);
