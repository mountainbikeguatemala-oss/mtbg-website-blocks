/**
 * Card editor (client action ``mtbg_card_editor``, params ``{model}``): the look of a model's record card, one for the
 * whole site (its kanban, other records' pages). Left: what the card shows and in which order; right: the real card
 * of a record, live with the unsaved changes, in a language and light or dark. Saved for everyone. Every model with a
 * card (Core's card mixin) gets the same editor, as its extension's settings page (its tile in Configuration › Extensions)
 */
import { Component, onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { RecordCard } from "../record_card/record_card";
import { adminIsDark } from "../dark/color_scheme";
import { MtbgDataTransfer } from "../data_transfer/data_transfer";


export class CardEditor extends Component {
    static template = "mtbg_tours_core.CardEditor";
    static components = { RecordCard, MtbgDataTransfer };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.model = this.props.action?.params?.model;
        this.state = useState({ data: null, look: null, saved: "", lang: null, recordId: 0, card: null,
                                dark: adminIsDark(), saving: false });
        onWillStart(async () => {
            const data = await this.orm.call(this.model, "mtbg_card_settings", []);
            this.state.data = data;
            this.state.lang = data.langs[0]?.code || "en_US";
            this.state.recordId = data.records[0]?.id ?? 0;
            this.setLook(data.look);
            await this.preview();
        });
    }

    setLook(look) {
        this.state.look = JSON.parse(JSON.stringify(look));
        this.state.saved = JSON.stringify(look);
    }

    get dirty() {
        return this.state.look && JSON.stringify(this.state.look) !== this.state.saved;
    }

    get canEdit() {
        return this.state.data?.can_edit;
    }

    get langName() {
        return this.state.data.langs.find((l) => l.code === this.state.lang)?.name || "";
    }

    lineLabel(key) {
        return this.state.data.fields.find((f) => f.key === key)?.label || key;
    }

    // ------------------------------------------------------------------
    // Drag and drop: the fields, the dropdown's columns, the top right (the arrows do the same)
    // ------------------------------------------------------------------
    onDragStart(list, index, ev) {
        this.drag = { list, index };
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", String(index));
    }

    onDragOver(list, ev) {
        if (this.drag?.list === list) {
            ev.preventDefault();
            ev.dataTransfer.dropEffect = "move";
        }
    }

    onDrop(list, index, ev) {
        ev.preventDefault();
        if (!this.drag || this.drag.list !== list || this.drag.index === index) {
            this.drag = null;
            return;
        }
        const items = this.state.look[list];
        const [moved] = items.splice(this.drag.index, 1);
        items.splice(index, 0, moved);
        this.drag = null;
        this.preview();
    }

    get cornerItems() {
        const labels = { figure: _t("Big figure"), status: _t("Status pill"), countdown: _t("Countdown pill") };
        return this.state.look.corner.map((key) => ({ key, label: labels[key] || key }));
    }

    moveCorner(index, step) {
        const items = this.state.look.corner;
        const to = index + step;
        if (to < 0 || to >= items.length) {
            return;
        }
        [items[index], items[to]] = [items[to], items[index]];
        this.preview();
    }

    moveColumn(index, step) {
        const cols = this.state.look.detail_columns;
        const to = index + step;
        if (to < 0 || to >= cols.length) {
            return;
        }
        [cols[index], cols[to]] = [cols[to], cols[index]];
        this.preview();
    }

    columnLabel(key) {
        return this.state.data.detail_columns.find((c) => c.key === key)?.label || key;
    }

    /** The fields with a label on the card (renamable per language). */
    get labelled() {
        return this.state.data.fields.filter((f) => f.short);
    }

    /** A preset: its options and fields over the draft (the labels kept). */
    async applyPreset(key) {
        if (key) {
            this.state.look = await this.orm.call(this.model, "mtbg_card_preset", [key, this.state.look]);
            await this.preview();
        }
    }

    /** The real card of the record picked, with the look being edited, in the language picked. */
    async preview() {
        // record 0: the sample, every field filled
        this.state.card = this.state.data.records.length
            ? await this.orm.call(this.model, "mtbg_card_preview", [this.state.recordId, this.state.look, this.state.lang])
            : null;
    }

    change(key, value) {
        this.state.look[key] = value;
        this.preview();
    }

    /** In the small stats row, or a line of its own (owner, 2026-11-07). */
    isSmall(key) {
        return (this.state.look.small || []).includes(key);
    }

    toggleSmall(key) {
        const small = this.state.look.small || [];
        this.state.look.small = small.includes(key) ? small.filter((k) => k !== key) : [...small, key];
        this.preview();
    }

    toggleLine(line) {
        line.show = !line.show;
        this.preview();
    }

    moveLine(index, step) {
        const lines = this.state.look.lines;
        const to = index + step;
        if (to < 0 || to >= lines.length) {
            return;
        }
        [lines[index], lines[to]] = [lines[to], lines[index]];
        this.preview();
    }

    label(key) {
        return this.state.look.labels[key]?.[this.state.lang] || "";
    }

    setLabel(key, value) {
        const texts = (this.state.look.labels[key] ||= {});
        if (value) {
            texts[this.state.lang] = value;
        } else {
            delete texts[this.state.lang];
        }
        this.preview();
    }

    setLang(code) {
        this.state.lang = code;
        this.preview();
    }

    setRecord(id) {
        this.state.recordId = parseInt(id) || 0;
        this.preview();
    }

    setDark(dark) {
        this.state.dark = dark;
    }

    async save() {
        this.state.saving = true;
        try {
            this.setLook(await this.orm.call(this.model, "mtbg_save_card_look", [this.state.look]));
            this.notification.add(_t("Card saved."), { type: "success" });
        } finally {
            this.state.saving = false;
        }
    }

    discard() {
        this.setLook(JSON.parse(this.state.saved));
        this.preview();
    }
}

registry.category("actions").add("mtbg_card_editor", CardEditor);
