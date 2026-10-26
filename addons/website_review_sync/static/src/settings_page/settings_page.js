/**
 * The Reviews page: everything about the website's reviews in one place.
 *
 * - Presets: the Reviews blocks' looks. Each block on a page names its preset, so a change here changes every
 *   block using it. Per preset: bubble or card style, tail, corners, shadow, colours, which reviews (platform,
 *   sources, minimum rating, order, how many), the block's parts and a review card's parts in order (drag and
 *   drop), texts in every language of the website; with a live preview (unsaved changes included).
 * - Reviews: the reviews table (search, filters, on website / featured, open one).
 * - Sources and Accounts: where the reviews come from (sync now, open, add).
 */
import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { deserializeDateTime, formatDateTime } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const DESKTOP_WIDTH = 1280; // the preview's desktop width, scaled to fit
const PREVIEW_DELAY = 250;
const TEXTS = ["heading", "total_label", "button_text"];
const ICONS = { google: "fa-google", tripadvisor: "fa-tripadvisor", manual: "fa-pencil" };

function clone(value) {
    return JSON.parse(JSON.stringify(value));
}

export class ReviewSettingsPage extends Component {
    static template = "website_review_sync.ReviewSettingsPage";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.frame = useRef("frame");
        this.stage = useRef("stage");
        this.state = useState({
            data: null, tab: "presets", presets: [], current: null, deleted: [], dirty: [], saving: false,
            lang: null, drag: null, device: "desktop", frameKey: 1, scale: 1, stageHeight: 600, dark: false, currency: "base",
            reviews: null, filters: { search: "", source_id: "", rating: "", status: "" }, offset: 0, busy: false,
        });
        this.nextUid = 0;
        this.previewTimer = null;
        this.previewSeq = 0;
        onWillStart(() => this.load());
        onMounted(() => {
            this.resizer = new ResizeObserver(() => this.fitPreview());
            this.observeStage();
        });
        onWillUnmount(() => {
            this.resizer?.disconnect();
            clearTimeout(this.previewTimer);
        });
    }

    async load(page = null, select = null) {
        const data = page || (await this.orm.call("review.settings.page", "get_page", []));
        this.state.data = data;
        this.state.presets = data.presets.map((p) => ({ ...clone(p), uid: `p${++this.nextUid}` }));
        this.state.deleted = [];
        this.state.dirty = [];
        const keep = select ?? this.preset?.id;
        this.state.current = (this.state.presets.find((p) => p.id === keep) || this.state.presets[0])?.uid || null;
        if (!this.state.lang || !data.langs.some((l) => l.code === this.state.lang)) {
            this.state.lang = data.langs[0]?.code;
        }
    }

    // ------------------------------------------------------------------
    // What the page shows
    // ------------------------------------------------------------------
    get preset() {
        return this.state.presets.find((p) => p.uid === this.state.current) || null;
    }

    get mainLang() {
        return this.state.data.langs[0]?.code;
    }

    get langInfo() {
        return this.state.data.langs.find((l) => l.code === this.state.lang) || this.state.data.langs[0];
    }

    get isTranslating() {
        return this.state.lang !== this.mainLang;
    }

    get translatingNote() {
        return _t("Editing the %(lang)s texts. An empty field shows the %(main)s text (in grey).", {
            lang: this.langInfo.name, main: this.state.data.langs[0].name });
    }

    get isDirty() {
        return this.state.dirty.length > 0 || this.state.deleted.length > 0;
    }

    isPresetDirty(preset) {
        return this.state.dirty.includes(preset.uid);
    }

    get tabs() {
        const tabs = [
            { key: "presets", label: _t("Presets"), icon: "fa-paint-brush" },
            { key: "reviews", label: _t("Reviews"), icon: "fa-comments", count: this.state.data.total_reviews },
            { key: "sources", label: _t("Sources"), icon: "fa-map-marker", count: this.state.data.sources.length },
        ];
        if (this.state.data.is_admin) {
            tabs.push({ key: "accounts", label: _t("Accounts"), icon: "fa-key", count: this.state.data.accounts.length });
        }
        return tabs;
    }

    get styles() {
        return [
            { key: "bubbles", label: _t("Speech bubbles"), help: _t("The review in a bubble, the reviewer under it") },
            { key: "cards", label: _t("Cards"), help: _t("Each review on a card") },
        ];
    }

    get tails() {
        return [{ key: "left", label: _t("Left") }, { key: "center", label: _t("Centre") },
                { key: "right", label: _t("Right") }, { key: "none", label: _t("None") }];
    }

    get themes() {
        return [{ key: "light", label: _t("Light") }, { key: "dark", label: _t("Dark") },
                { key: "site", label: _t("Website colours") }];
    }

    get colorRows() {
        return [
            { key: "bg", label: _t("Background"), help: _t("Behind the whole block") },
            { key: "text", label: _t("Text"), help: _t("Heading, five-star total, reviewer names") },
            { key: "bubble", label: _t("Bubble / card"), help: _t("Behind each review") },
            { key: "bubble_text", label: _t("Bubble / card text"), help: _t("The review's words") },
            { key: "star", label: _t("Stars") },
            { key: "link", label: _t("Links"), help: _t("And the button, unless it has its own colours") },
        ];
    }

    /** A row with texts or options under it: heading, total, reviews (slider), button; a review's reviewer. */
    hasEdit(list, part) {
        if (!part.show) {
            return false;
        }
        if (list === "card_parts") {
            return part.key === "reviewer";
        }
        return ["heading", "total", "button"].includes(part.key)
            || (part.key === "reviews" && this.preset.kind === "slider");
    }

    get logoChoices() {
        return [{ key: "reviewer", label: _t("Beside the reviewer") }, { key: "bubble", label: _t("Top right") },
                { key: "none", label: _t("Hidden") }];
    }

    get buttonColorRows() {
        return [
            { key: "button", label: _t("Button"), help: _t("Solid: its background; outline: its line and text") },
            { key: "button_text", label: _t("Button text") },
        ];
    }

    /** The count-up's speed curves, each with a little drawing of the count over time. */
    get easings() {
        const curve = (fn) => "M0 16 " + Array.from({ length: 13 }, (_, i) => {
            const t = i / 12;
            return `L${(t * 24).toFixed(1)} ${(16 - fn(t) * 16).toFixed(1)}`;
        }).join(" ");
        return [
            { key: "linear", label: _t("Steady"), help: _t("The same speed all the way"), path: curve((t) => t) },
            { key: "smooth", label: _t("Smooth"), help: _t("Slows down gently at the end"),
              path: curve((t) => 1 - Math.pow(1 - t, 3)) },
            { key: "slow", label: _t("Slow finish"), help: _t("Fast at first, slower and slower near the top"),
              path: curve((t) => 1 - Math.pow(1 - t, 5)) },
            { key: "slower", label: _t("Crawl to the top"), help: _t("Almost there quickly, then the last few one by one"),
              path: curve((t) => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t))) },
            { key: "log", label: _t("Logarithmic"), help: _t("Very fast at first, then a long slow climb"),
              path: curve((t) => Math.log1p(99 * t) / Math.log(100)) },
        ];
    }

    get countLabel() {
        return _t("%s s", (this.preset.count_ms / 1000).toLocaleString(undefined, { maximumFractionDigits: 2 }));
    }

    get sorts() {
        return [{ key: "recent", label: _t("Most recent") }, { key: "featured", label: _t("Featured first") },
                { key: "best", label: _t("Highest rated") }, { key: "photos", label: _t("With photos first") }];
    }

    get platformChoices() {
        return [{ key: "all", label: _t("All") }, { key: "google", label: "Google" },
                { key: "tripadvisor", label: "Tripadvisor" }];
    }

    partLabel(key) {
        return {
            heading: _t("Heading"), stars: _t("Stars ★★★★★"), total: _t("Five-star total (400+ …)"),
            reviews: _t("The reviews"), button: _t("Button"),
            filters: _t("Filters (platform, rating, language…)"), rating: _t("Stars"), title: _t("Title"),
            text: _t("Review text"), photos: _t("Photos"), link: _t("Link to the review"),
            reviewer: _t("Reviewer (photo, name, date)"), date: _t("Date only"),
            bubble_start: _t("Bubble starts"), bubble_end: _t("Bubble ends"),
        }[key] || key;
    }

    partIcon(key) {
        return {
            heading: "fa-header", stars: "fa-star", total: "fa-sort-numeric-asc", reviews: "fa-comments", button: "fa-hand-pointer-o",
            filters: "fa-filter", rating: "fa-star-o", title: "fa-bold", text: "fa-align-left", photos: "fa-picture-o",
            link: "fa-external-link", reviewer: "fa-user-circle", date: "fa-calendar",
            bubble_start: "fa-comment-o", bubble_end: "fa-comment-o",
        }[key] || "fa-square";
    }

    /** A part that cannot be hidden (the reviews themselves, the bubble's dividers). */
    isFixed(key) {
        return key === "reviews" || this.isMarker(key);
    }

    /** The speech bubble's dividers in a review card's parts (only with speech bubbles). */
    isMarker(key) {
        return key === "bubble_start" || key === "bubble_end";
    }

    /** A part's row in the list (the dividers: speech bubbles only). */
    showsRow(list, part) {
        return list !== "card_parts" || !this.isMarker(part.key) || this.preset.style === "bubbles";
    }

    get reviewerNote() {
        if (this.preset.style !== "bubbles") {
            return _t("Cards: every part goes where you drag it.");
        }
        return _t("Speech bubbles: the parts between Bubble starts and Bubble ends are in the bubble; above it, over the " +
                  "bubble; below it, under the bubble. Date only: the date on its own (the reviewer's line then leaves it out).");
    }

    text(field) {
        return this.preset.texts[field][this.state.lang] || "";
    }

    placeholder(field) {
        const main = this.preset.texts[field][this.mainLang];
        if (this.isTranslating && main) {
            return main;
        }
        return { heading: _t("e.g. Check out some of our recent reviews"), total_label: _t("e.g. Five star reviews"),
                 button_text: _t("e.g. See all reviews") }[field];
    }

    usageLabel(preset) {
        if (!preset.usage) {
            return _t("not on a page yet");
        }
        return preset.usage === 1 ? _t("on 1 page") : _t("on %s pages", preset.usage);
    }

    platformIcon(platform) {
        return ICONS[platform] || "fa-star";
    }

    stars(n) {
        return "★".repeat(n) + "☆".repeat(5 - n);
    }

    when(value) {
        return value ? formatDateTime(deserializeDateTime(value)) : _t("never");
    }

    // ------------------------------------------------------------------
    // Presets: edits
    // ------------------------------------------------------------------
    changed() {
        const preset = this.preset;
        if (preset && !this.state.dirty.includes(preset.uid)) {
            this.state.dirty.push(preset.uid);
        }
        this.schedulePreview();
    }

    set(key, value) {
        this.preset[key] = value;
        if (key === "kind") {
            // the parts of the other kind of block, in their usual order
            const parts = this.state.data.block_parts[value];
            this.preset.layout = parts.map((k) => ({ key: k, show: k !== "heading" }));
            this.preset.min_rating = value === "wall" ? 1 : 4;
        }
        this.changed();
    }

    setNumber(key, value) {
        this.set(key, parseInt(value) || 0);
    }

    setColor(key, value) {
        this.preset.colors[key] = value;
        this.changed();
    }

    setText(field, value) {
        this.preset.texts[field][this.state.lang] = value;
        this.changed();
    }

    toggleSource(id) {
        const ids = this.preset.source_ids;
        this.preset.source_ids = ids.includes(id) ? ids.filter((s) => s !== id) : [...ids, id];
        this.changed();
    }

    togglePart(list, part) {
        if (this.isFixed(part.key)) {
            return;
        }
        part.show = !part.show;
        this.changed();
    }

    selectUid(uid) {
        this.state.current = uid;
        this.reloadPreview();
    }

    /** A preset in the dropdown: "Website colours · Slider · on 2 pages", a dot when it has unsaved changes. */
    presetOption(preset) {
        const kind = preset.kind === "wall" ? _t("Wall") : _t("Slider");
        return `${preset.name}${this.isPresetDirty(preset) ? " •" : ""} · ${kind} · ${this.usageLabel(preset)}`;
    }

    setLang(code) {
        this.state.lang = code;
        this.reloadPreview(); // the preview opens in that language, the unsaved changes go in on load
    }

    newPreset() {
        const from = this.preset;
        const texts = Object.fromEntries(TEXTS.map((f) => [f, { ...(from?.texts[f] || {}) }]));
        const preset = {
            ...clone(from || this.state.presets[0]), id: null, key: "", builtin: false, usage: 0, texts,
            name: from ? _t("%s (copy)", from.name) : _t("New preset"), uid: `p${++this.nextUid}`,
        };
        this.state.presets.push(preset);
        this.state.current = preset.uid;
        this.changed();
        this.reloadPreview();
    }

    removePreset() {
        const preset = this.preset;
        if (!preset || preset.builtin) {
            return;
        }
        const remove = () => {
            if (preset.id) {
                this.state.deleted.push(preset.id);
            }
            this.state.dirty = this.state.dirty.filter((uid) => uid !== preset.uid);
            this.state.presets = this.state.presets.filter((p) => p.uid !== preset.uid);
            this.state.current = this.state.presets[0]?.uid || null;
            this.reloadPreview();
        };
        if (!preset.usage) {
            return remove();
        }
        this.dialog.add(ConfirmationDialog, {
            title: _t("Delete %s?", preset.name),
            body: _t("%s pages show this preset: their Reviews blocks will be empty until they get another preset.",
                     preset.usage),
            confirmLabel: _t("Delete"),
            confirm: remove,
            cancel: () => {},
        });
    }

    // ------------------------------------------------------------------
    // Order of the parts: drag a row by its grip (or focus the grip and use the arrow keys)
    // ------------------------------------------------------------------
    onDragStart(ev, list, part) {
        this.state.drag = { list, key: part.key };
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", part.key);
    }

    onDragOver(ev, list, target) {
        const drag = this.state.drag;
        if (!drag || drag.list !== list) {
            return;
        }
        ev.preventDefault();
        if (drag.key === target.key) {
            return;
        }
        const rect = ev.currentTarget.getBoundingClientRect();
        this.move(list, drag.key, target.key, ev.clientY > rect.top + rect.height / 2);
    }

    onDragEnd() {
        this.state.drag = null;
    }

    move(list, key, targetKey, after) {
        const parts = this.preset[list];
        const part = parts.find((p) => p.key === key);
        const order = parts.filter((p) => p !== part);
        order.splice(order.findIndex((p) => p.key === targetKey) + (after ? 1 : 0), 0, part);
        if (order.map((p) => p.key).join() !== parts.map((p) => p.key).join()) {
            this.preset[list] = order;
            this.changed();
        }
    }

    onGripKey(ev, list, part) {
        const step = { ArrowUp: -1, ArrowDown: 1 }[ev.key];
        if (!step) {
            return;
        }
        ev.preventDefault();
        const parts = this.preset[list];
        const target = parts[parts.indexOf(part) + step];
        if (target) {
            this.move(list, part.key, target.key, step > 0);
        }
        const grip = ev.currentTarget;
        setTimeout(() => grip?.focus());
    }

    // ------------------------------------------------------------------
    // Save / discard
    // ------------------------------------------------------------------
    payloadOf(preset) {
        const { uid, builtin, usage, ...values } = preset;
        return clone(values);
    }

    async save() {
        const dirty = this.state.presets.filter((p) => this.state.dirty.includes(p.uid));
        this.state.saving = true;
        try {
            const current = this.preset;
            const page = await this.orm.call("review.settings.page", "save_presets",
                [dirty.map((p) => this.payloadOf(p)), [...this.state.deleted]]);
            const index = dirty.indexOf(current);
            await this.load(page, index >= 0 ? page.saved[index] : current?.id);
            this.reloadPreview();
            this.notification.add(_t("Presets saved: every Reviews block using them shows the change."),
                                  { type: "success" });
        } finally {
            this.state.saving = false;
        }
    }

    async discard() {
        await this.load();
        this.reloadPreview();
    }

    // ------------------------------------------------------------------
    // Preview
    // ------------------------------------------------------------------
    get previewUrl() {
        const lang = this.langInfo ? `/${this.langInfo.url_code}` : "";
        return `${lang}/review_sync/preset/preview?preset=${this.preset?.id || 0}&v=${this.state.frameKey}`;
    }

    get frameStyle() {
        if (this.state.device === "mobile") {
            return "";
        }
        const s = this.state.scale;
        return `width: ${DESKTOP_WIDTH}px; height: ${Math.round(this.state.stageHeight / s)}px; transform: scale(${s});`;
    }

    observeStage() {
        if (this.stage.el && this.resizer && this.observed !== this.stage.el) {
            this.resizer.disconnect();
            this.resizer.observe(this.stage.el);
            this.observed = this.stage.el;
            this.fitPreview();
        }
    }

    fitPreview() {
        const el = this.stage.el;
        if (!el) {
            return;
        }
        this.state.scale = Math.min(1, el.clientWidth / DESKTOP_WIDTH) || 1;
        this.state.stageHeight = el.clientHeight || 600;
    }

    setDevice(device) {
        this.state.device = device;
        setTimeout(() => this.fitPreview());
    }

    reloadPreview() {
        this.state.frameKey++;
    }

    /** The preview's page look: light / dark (the site's dark page look) or currency (base / alt). */
    setPreviewLook(key, value) {
        this.state[key] = value;
        this.applyLook();
    }

    /** Put the page look and the currency in the preview (same site: its document is reachable). */
    applyLook() {
        const doc = this.frame.el?.contentDocument;
        const wrap = doc?.getElementById("wrap");
        if (!wrap) {
            return;
        }
        wrap.classList.add("mtbg-tour-page");
        wrap.classList.toggle("mtbg-theme-dark", this.state.dark);
        wrap.classList.toggle("mtbg-theme-light", !this.state.dark);
        // the site's prices follow (MTBG Tours' currency switch)
        doc.dispatchEvent(new CustomEvent("mtbg_currency", { detail: { alt: this.state.currency === "alt" } }));
    }

    schedulePreview() {
        clearTimeout(this.previewTimer);
        this.previewTimer = setTimeout(() => this.refreshPreview(), PREVIEW_DELAY);
    }

    async refreshPreview() {
        const preset = this.preset;
        if (!preset) {
            return;
        }
        const seq = ++this.previewSeq;
        const html = await this.orm.call("review.settings.page", "preview", [this.payloadOf(preset), this.state.lang]);
        if (seq === this.previewSeq) {
            this.push({ html });
        }
    }

    push(detail) {
        const win = this.frame.el?.contentWindow;
        if (!win) {
            return;
        }
        win.reviewPresetPreview = { ...(win.reviewPresetPreview || {}), ...detail };
        win.document.dispatchEvent(new CustomEvent("review_preset_preview", { detail }));
    }

    /** The preview has loaded the saved preset: unsaved (or new) ones go in now. */
    onFrameLoad() {
        this.observeStage();
        this.applyLook();
        if (this.preset && (!this.preset.id || this.isPresetDirty(this.preset))) {
            this.refreshPreview();
        }
    }

    // ------------------------------------------------------------------
    // Tabs: reviews, sources, accounts
    // ------------------------------------------------------------------
    async setTab(tab) {
        this.state.tab = tab;
        if (tab === "reviews" && !this.state.reviews) {
            await this.loadReviews();
        }
        if (tab === "presets") {
            this.reloadPreview();
        }
    }

    async loadReviews(offset = this.state.offset) {
        this.state.reviews = await this.orm.call("review.settings.page", "reviews", [this.state.filters, offset]);
        this.state.offset = this.state.reviews.offset;
    }

    isFilter(key, value) {
        return String(value) === String(this.state.filters[key]);
    }

    get reviewRange() {
        const r = this.state.reviews;
        if (!r.total) {
            return _t("No reviews");
        }
        return _t("%(from)s–%(to)s of %(total)s", {
            from: r.offset + 1, to: Math.min(r.offset + r.page_size, r.total), total: r.total });
    }

    setFilter(key, value) {
        this.state.filters[key] = value;
        clearTimeout(this.searchTimer);
        this.searchTimer = setTimeout(() => this.loadReviews(0), key === "search" ? 300 : 0);
    }

    page(step) {
        const r = this.state.reviews;
        const offset = Math.min(Math.max(0, r.offset + step * r.page_size), Math.max(0, r.total - 1));
        this.loadReviews(offset - (offset % r.page_size));
    }

    async setReview(row, key, value) {
        await this.orm.call("review.settings.page", "set_review", [row.id, { [key]: value }]);
        row[key === "is_published" ? "published" : "featured"] = value;
    }

    openRecord(model, id = false, context = {}) {
        return this.action.doAction({
            type: "ir.actions.act_window", res_model: model, res_id: id || false, views: [[false, "form"]],
            target: "new", context,
        }, { onClose: () => this.refreshLists() });
    }

    async refreshLists() {
        const page = await this.orm.call("review.settings.page", "get_page", []);
        // keep the presets being edited: only the lists and counts are new
        Object.assign(this.state.data, { sources: page.sources, accounts: page.accounts,
                                         total_reviews: page.total_reviews });
        if (this.state.tab === "reviews") {
            await this.loadReviews();
        }
    }

    async sync(source = null) {
        this.state.busy = true;
        try {
            this.state.data.sources = await this.orm.call("review.settings.page", "sync_sources",
                [source ? [source.id] : []]);
            const failed = this.state.data.sources.filter((s) => s.last_error && (!source || s.id === source.id));
            this.notification.add(failed.length ? _t("Some sources could not be synced: see their error.")
                : _t("Synced."), { type: failed.length ? "warning" : "success" });
            await this.refreshLists();
        } finally {
            this.state.busy = false;
        }
    }
}

registry.category("actions").add("review_settings_page", ReviewSettingsPage);
