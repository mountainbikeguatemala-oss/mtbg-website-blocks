import { InstagramFeedBlock } from "./feed";
import { registry } from "@web/core/registry";

// Also show the posts while editing the page (they are never saved; clicks select the block)
registry.category("public.interactions.edit").add("meta_connector.instagram_feed", {
    Interaction: InstagramFeedBlock,
});
