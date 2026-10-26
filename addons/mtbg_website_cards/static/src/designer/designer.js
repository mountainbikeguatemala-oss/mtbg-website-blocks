/**
 * Card Designer (client action ``mtbg_card_designer``, Website › Content › Card Designs): a card design's style, photo
 * frame, corners, shadow, hover, its source's fields in order (drag and drop, or the arrows) each in a place, and its
 * colours for light and for dark pages (the preview's light / dark switch picks which ones you set). On the right,
 * the cards live on a website page (the design's unsaved settings, only for the person designing), on a computer or
 * a phone. Saved for every page using the design.
 */
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const MODEL = "mtbg.website.card.design";
const COLOR = /^#[0-9a-fA-F]{6}$/;
const DRAFT_DELAY = 400;

export class CardDesigner extends Component {
    static template = "mtbg_website_cards.CardDesigner";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            data: null, settings: null, saved: "", saving: false, dark: false, device: "desktop", frameKey: 1,
            creating: null,
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
            style: d.style, ratio: d.ratio, corners: d.corners, shadow: d.shadow,
            hover_zoom: d.hover_zoom, hover_darken: d.hover_darken, look: d.look,
        })) : null;
        this.state.saved = JSON.stringify(this.state.settings);
        this.state.frameKey++;
    }

    get design() {
        return this.state.data?.design;
    }

    get dirty() {
        return this.state.settings && JSON.stringify(this.state.settings) !== this.state.saved;
    }

    get styles() {
        return [
            { key: "below", label: _t("Text below"), icon: "fa-picture-o" },
            { key: "overlay", label: _t("Text over"), icon: "fa-font" },
            { key: "above", label: _t("Text above"), icon: "fa-header" },
        ];
    }

    get colors() {
        return [
            { key: "card_bg", label: _t("Card background") }, { key: "text", label: _t("Text") },
            { key: "muted", label: _t("Small text") }, { key: "accent", label: _t("Accent (price, badges)") },
            { key: "accent_text", label: _t("Text on the accent") }, { key: "overlay", label: _t("Photo shade") },
        ];
    }

    get mode() {
        return this.state.dark ? "dark" : "light";
    }

    fieldLabel(key) {
        return this.state.data.fields.find((f) => f.key === key)?.label || key;
    }

    // ------------------------------------------------------------------ changes
    change(key, value) {
        this.state.settings[key] = value;
        this.queueDraft();
    }

    setPlace(part, place) {
        part.place = place;
        this.queueDraft();
    }

    movePart(index, step) {
        const parts = this.state.settings.look.parts;
        const to = index + step;
        if (to < 0 || to >= parts.length) {
            return;
        }
        [parts[index], parts[to]] = [parts[to], parts[index]];
        this.queueDraft();
    }

    onDragStart(index, ev) {
        this.drag = index;
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", String(index));
    }

    onDragOver(ev) {
        if (this.drag !== undefined && this.drag !== null) {
            ev.preventDefault();
        }
    }

    onDrop(index, ev) {
        ev.preventDefault();
        const from = this.drag;
        this.drag = null;
        if (from === null || from === undefined || from === index) {
            return;
        }
        const parts = this.state.settings.look.parts;
        const [moved] = parts.splice(from, 1);
        parts.splice(index, 0, moved);
        this.queueDraft();
    }

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
        await this.sendDraft();
    }

    // ------------------------------------------------------------------ preview
    setDark(dark) {
        this.state.dark = dark;
        this.state.frameKey++;
    }

    get previewUrl() {
        return `/mtbg/cards/preview/${this.design.id}?dark=${this.state.dark ? 1 : 0}&k=${this.state.frameKey}`;
    }
}

registry.category("actions").add("mtbg_card_designer", CardDesigner);
