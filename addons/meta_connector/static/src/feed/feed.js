/**
 * Instagram Feed block: the newest posts the Meta connector keeps (WebP copies, refreshed every hour), fetched when
 * the page loads; each opens the post on Instagram. Its colours are the section's own (light or dark).
 */
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";

const COUNTS = [4, 6, 8, 12];

/** The block's number of posts (one of COUNTS, default 6). */
export function feedCount(el) {
    const count = parseInt(el.dataset.count, 10);
    return COUNTS.includes(count) ? count : 6;
}

export class InstagramFeedBlock extends Interaction {
    static selector = ".s_meta_instagram_feed";

    async willStart() {
        this.feed = await this.waitFor(rpc("/meta_connector/instagram/feed", { count: feedCount(this.el) }));
    }

    start() {
        const placeholder = this.el.querySelector(".s_meta_instagram_feed_placeholder");
        const items = this.feed?.items || [];
        if (placeholder && (items.length || !this.isEditMode())) {
            placeholder.classList.add("d-none");
            this.registerCleanup(() => placeholder.classList.remove("d-none"));
        }
        if (!items.length) {
            return;
        }
        const count = feedCount(this.el);
        const wrap = document.createElement("div");
        wrap.className = "o_meta_feed_generated";
        const header = this.header();
        if (header) {
            wrap.append(header);
        }
        const list = document.createElement("div");
        list.className = `o_meta_feed_tiles o_meta_feed_${this.el.dataset.layout === "row" ? "row" : "grid"} o_meta_feed_n${count}`;
        for (const item of items) {
            const link = document.createElement("a");
            link.className = "o_meta_feed_tile";
            link.href = item.url || this.feed.profile_url;
            link.target = "_blank";
            link.rel = "noopener";
            link.title = item.caption || _t("See the post on Instagram");
            const img = document.createElement("img");
            img.src = item.tile;
            img.alt = item.caption || _t("Instagram post");
            img.loading = "lazy";
            link.append(img);
            if (item.type !== "IMAGE") {
                const icon = document.createElement("i");
                icon.className = `fa ${item.type === "VIDEO" ? "fa-play" : "fa-clone"} o_meta_feed_kind`;
                link.append(icon);
            }
            list.append(link);
        }
        wrap.append(list);
        if (this.el.dataset.follow !== "0" && this.feed.profile_url) {
            const follow = document.createElement("a");
            follow.className = "o_meta_feed_follow btn btn-sm mt-3";
            follow.href = this.feed.profile_url;
            follow.target = "_blank";
            follow.rel = "noopener";
            follow.innerHTML = '<i class="fa fa-instagram me-2"></i>';
            follow.append(_t("Follow @%s", this.feed.username));
            const row = document.createElement("div");
            row.className = "text-center";
            row.append(follow);
            wrap.append(row);
        }
        this.insert(wrap, this.el);
    }

    /** The optional header (data-header "profile" or "followers"): photo, @username, name, and the counts. */
    header() {
        const mode = this.el.dataset.header;
        if (!["profile", "followers"].includes(mode) || !this.feed.username) {
            return null;
        }
        const header = document.createElement("a");
        header.className = "o_meta_feed_header";
        header.href = this.feed.profile_url;
        header.target = "_blank";
        header.rel = "noopener";
        if (this.feed.avatar) {
            const img = document.createElement("img");
            img.className = "o_meta_feed_avatar";
            img.src = this.feed.avatar;
            img.alt = `@${this.feed.username}`;
            header.append(img);
        }
        const text = document.createElement("div");
        const handle = document.createElement("div");
        handle.className = "o_meta_feed_handle";
        handle.textContent = `@${this.feed.username}`;
        text.append(handle);
        if (this.feed.name) {
            const name = document.createElement("div");
            name.className = "o_meta_feed_name";
            name.textContent = this.feed.name;
            text.append(name);
        }
        if (mode === "followers" && this.feed.followers) {
            const format = new Intl.NumberFormat(document.documentElement.lang || undefined, {
                notation: "compact",
                maximumFractionDigits: 1,
            });
            const counts = document.createElement("div");
            counts.className = "o_meta_feed_counts";
            const parts = [_t("%s followers", format.format(this.feed.followers))];
            if (this.feed.posts) {
                parts.push(_t("%s posts", format.format(this.feed.posts)));
            }
            counts.textContent = parts.join(" · ");
            text.append(counts);
        }
        header.append(text);
        return header;
    }

    isEditMode() {
        return !!this.el.closest(".o_editable, [contenteditable='true']") || document.body.classList.contains("editor_enable");
    }
}

registry.category("public.interactions").add("meta_connector.instagram_feed", InstagramFeedBlock);
