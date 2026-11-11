import { BaseOptionComponent } from "@html_builder/core/utils";

/** Instagram Feed block: how many posts, grid or one row, the Follow button. */
export class InstagramFeedOption extends BaseOptionComponent {
    static template = "meta_connector.InstagramFeedOption";
    static selector = ".s_meta_instagram_feed";
}
