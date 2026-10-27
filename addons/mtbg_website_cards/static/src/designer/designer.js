/**
 * Card Designer (client action ``mtbg_card_designer``, Website Blocks › Card Designer): a card design's regions and
 * the fields placed in them, its photo frame, corners, shadow, photo hover and colours (light and dark pages).
 *
 * In the middle, the card as a plan: Header (above the card), the photo's Top strip, Center and Bottom strip (each
 * shown always or on hover; the strips coloured, the bottom one also as a shade), Below and its Footer line. Drag a
 * field from the list on the left into a region (a field can be placed more than once), drag placed fields between
 * regions or within one, click one for its look (plain, pill, button, bar), its words ("Book (from {price})"), its
 * icon, and on the photo when it shows. On the right, the cards live on a website page (the unsaved settings, only
 * for the person designing), on a computer or a phone, light or dark, and hovered or not. Saved for every page using
 * the design.
 */
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const MODEL = "mtbg.website.card.design";
const COLOR = /^#[0-9a-fA-F]{6}$/;
const ICON = /^fa-[a-z0-9-]+$/;
const DRAFT_DELAY = 400;
const PHOTO = ["top", "center", "bottom"];

function uid() {
    return Math.random().toString(16).slice(2, 10);
}

export class CardDesigner extends Component {
    static template = "mtbg_website_cards.CardDesigner";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            data: null, settings: null, saved: "", saving: false, dark: false, device: "desktop", hover: false,
            frameKey: 1, creating: null, selected: null, drag: null, dropAt: null,
        });
        onWillStart(() => this.load(this.props.action?.context?.design_id || 0));
        onWillUnmount(() => clearTimeout(this.timer));
    }

    async load(designId) {
        this.apply(await this.orm.call(MODEL, "mtbg_designer_data", [designId]));
    }

    apply(data) {
        this.state.data = data;
        const d = data.design;
        this.state.settings = d ? JSON.parse(JSON.stringify({
            ratio: d.ratio, corners: d.corners, shadow: d.shadow,
            hover_zoom: d.hover_zoom, hover_darken: d.hover_darken, look: d.look,
        })) : null;
        this.state.saved = JSON.stringify(this.state.settings);
        this.state.selected = null;
        this.state.frameKey++;
    }

    get design() {
        return this.state.data?.design;
    }

    get dirty() {
        return this.state.settings && JSON.stringify(this.state.settings) !== this.state.saved;
    }

    get regions() {
        return this.state.data.regions;
    }

    get colors() {
        return [
            { key: "card_bg", label: _t("Card background") }, { key: "text", label: _t("Text") },
            { key: "muted", label: _t("Small text") }, { key: "accent", label: _t("Accent (pills, buttons, dates)") },
            { key: "accent_text", label: _t("Text on the accent") }, { key: "top_bg", label: _t("Top strip") },
            { key: "top_text", label: _t("Top strip text") }, { key: "bottom_bg", label: _t("Bottom strip") },
            { key: "bottom_text", label: _t("Bottom strip text") }, { key: "early_bg", label: _t("Early bird strip") },
            { key: "early_text", label: _t("Early bird text") }, { key: "footer_bg", label: _t("Footer line") },
            { key: "overlay", label: _t("Photo shade on hover") },
        ];
    }

    get mode() {
        return this.state.dark ? "dark" : "light";
    }

    isPhoto(region) {
        return PHOTO.includes(region);
    }

    region(key) {
        return this.state.settings.look.regions[key];
    }

    field(key) {
        return this.state.data.fields.find((f) => f.key === key) || { key, label: key };
    }

    lookLabel(key) {
        return this.state.data.looks.find((l) => l.key === key)?.label || key;
    }

    /** How often each field is placed (the list on the left shows it). */
    placedCount(key) {
        let n = 0;
        for (const region of Object.values(this.state.settings.look.regions)) {
            n += region.items.filter((i) => i.field === key).length;
        }
        return n;
    }

    get selectedItem() {
        const sel = this.state.selected;
        return sel && this.region(sel.region).items.find((i) => i.uid === sel.uid);
    }

    // ------------------------------------------------------------------ changes
    change(key, value) {
        this.state.settings[key] = value;
        this.queueDraft();
    }

    setRegion(key, prop, value) {
        this.region(key)[prop] = value;
        this.queueDraft();
    }

    setItem(prop, value) {
        const item = this.selectedItem;
        if (!item) {
            return;
        }
        if (prop === "icon") {
            value = (value || "").trim();
            if (value && !value.startsWith("fa-")) {
                value = `fa-${value}`;
            }
            if (value && !ICON.test(value)) {
                return;
            }
        }
        item[prop] = value;
        this.queueDraft();
    }

    newItem(fieldKey) {
        const field = this.field(fieldKey);
        return { uid: uid(), field: fieldKey, look: field.kind === "button" ? "button" : "plain", show: "",
                 text: "", icon: field.icon || "" };
    }

    addField(fieldKey, region = this.state.selected?.region || "below") {
        const item = this.newItem(fieldKey);
        this.region(region).items.push(item);
        this.state.selected = { region, uid: item.uid };
        this.queueDraft();
    }

    select(region, item) {
        const same = this.state.selected?.uid === item.uid;
        this.state.selected = same ? null : { region, uid: item.uid };
    }

    duplicateItem() {
        const sel = this.state.selected;
        const items = this.region(sel.region).items;
        const index = items.findIndex((i) => i.uid === sel.uid);
        const copy = { ...items[index], uid: uid() };
        items.splice(index + 1, 0, copy);
        this.state.selected = { region: sel.region, uid: copy.uid };
        this.queueDraft();
    }

    removeItem() {
        const sel = this.state.selected;
        const items = this.region(sel.region).items;
        items.splice(items.findIndex((i) => i.uid === sel.uid), 1);
        this.state.selected = null;
        this.queueDraft();
    }

    // ------------------------------------------------------------------ drag and drop
    onDragField(ev, fieldKey) {
        this.state.drag = { type: "field", field: fieldKey };
        ev.dataTransfer.effectAllowed = "copy";
        ev.dataTransfer.setData("text/plain", fieldKey);
    }

    onDragItem(ev, region, item) {
        this.state.drag = { type: "item", region, uid: item.uid };
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", item.uid);
    }

    onDragEnd() {
        this.state.drag = null;
        this.state.dropAt = null;
    }

    /** Over a region: where the field would land (before the item under the pointer, else last). */
    onDragOver(ev, region, index) {
        if (!this.state.drag) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        const at = this.state.dropAt;
        if (!at || at.region !== region || at.index !== index) {
            this.state.dropAt = { region, index };
        }
    }

    onDrop(ev, region, index) {
        ev.preventDefault();
        ev.stopPropagation();
        const drag = this.state.drag;
        this.onDragEnd();
        if (!drag) {
            return;
        }
        const target = this.region(region).items;
        let item;
        if (drag.type === "field") {
            item = this.newItem(drag.field);
        } else {
            const from = this.region(drag.region).items;
            const at = from.findIndex((i) => i.uid === drag.uid);
            if (at < 0) {
                return;
            }
            [item] = from.splice(at, 1);
            if (drag.region === region && at < index) {
                index -= 1;
            }
            if (!this.isPhoto(region)) {
                item.show = "";
            }
        }
        target.splice(Math.min(index, target.length), 0, item);
        this.state.selected = { region, uid: item.uid };
        this.queueDraft();
    }

    isDropAt(region, index) {
        const at = this.state.dropAt;
        return Boolean(at && at.region === region && at.index === index);
    }

    // ------------------------------------------------------------------ colours
    colorOf(key) {
        return this.state.settings.look[this.mode]?.[key] || "";
    }

    setColor(key, value) {
        value = (value || "").trim();
        if (value && !value.startsWith("#")) {
            value = `#${value}`;
        }
        const look = this.state.settings.look;
        look[this.mode] ||= {};
        if (!value) {
            delete look[this.mode][key];
        } else if (COLOR.test(value)) {
            look[this.mode][key] = value;
        } else {
            return;
        }
        this.queueDraft();
    }

    queueDraft() {
        clearTimeout(this.timer);
        this.timer = setTimeout(() => this.sendDraft(), DRAFT_DELAY);
    }

    async sendDraft() {
        if (!this.design) {
            return;
        }
        await this.orm.call(MODEL, "mtbg_designer_draft", [[this.design.id], this.state.settings]);
        this.state.frameKey++;
    }

    // ------------------------------------------------------------------ designs
    async pickDesign(ev) {
        if (this.dirty && !window.confirm(_t("Leave this design? Your changes are not saved."))) {
            ev.target.value = this.design.id;
            return;
        }
        await this.load(parseInt(ev.target.value));
    }

    startCreate() {
        this.state.creating = { name: "", source: this.design?.source || this.state.data.sources[0]?.key || "" };
    }

    async create() {
        const c = this.state.creating;
        this.apply(await this.orm.call(MODEL, "mtbg_designer_create", [c.name, c.source,
            this.design && this.design.source === c.source ? this.design.id : 0]));
        this.state.creating = null;
    }

    async makeDefault() {
        await this.orm.call(MODEL, "action_make_default", [[this.design.id]]);
        const settings = this.state.settings;
        const saved = this.state.saved;
        await this.load(this.design.id);
        this.state.settings = settings;
        this.state.saved = saved;
    }

    async save() {
        this.state.saving = true;
        try {
            this.apply(await this.orm.call(MODEL, "mtbg_designer_save", [[this.design.id], this.state.settings]));
            this.notification.add(_t("Card design saved: every page using it shows it now."), { type: "success" });
        } finally {
            this.state.saving = false;
        }
    }

    async discard() {
        this.state.settings = JSON.parse(this.state.saved);
        this.state.selected = null;
        await this.sendDraft();
    }

    // ------------------------------------------------------------------ preview
    setDark(dark) {
        this.state.dark = dark;
        this.state.frameKey++;
    }

    setHover(hover) {
        this.state.hover = hover;
        this.state.frameKey++;
    }

    get previewUrl() {
        return `/mtbg/cards/preview/${this.design.id}?dark=${this.state.dark ? 1 : 0}&hover=${this.state.hover ? 1 : 0}&k=${this.state.frameKey}`;
    }
}

registry.category("actions").add("mtbg_card_designer", CardDesigner);
