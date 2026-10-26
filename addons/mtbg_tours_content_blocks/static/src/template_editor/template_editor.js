/**
 * The page template editor (Catalog › Page Templates), in two halves: on the left, the page outline with its insert
 * points; on the right, the preview of a sample page with the unsaved changes (only the person editing sees them), on
 * a desktop or a phone, in each language. Each insert point's "Add…" list offers what the page does not show yet (the
 * elements left out, the reusable blocks not used), so it shrinks as things are placed; drag a placed element (or its
 * arrows) to move it, the eye leaves it out of the page. Templates are picked, created, duplicated, renamed, archived and made Default in the top bar. Edits stay
 * unsaved until Save. See docs/architecture/page-templates.md.
 */
import { Component, onMounted, onWillStart, onWillUnmount, useEffect, useRef, useState } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const MODEL = "mtbg.page.template";
const LAST_KEY = "mtbg_tours.page_template_editor";  // the template and preview page shown last (per browser)
const DESKTOP_WIDTH = 1280;
const PHONE_WIDTH = 390;
const PREVIEW_DELAY = 400;
// the page outline's rows, as the page lays its insert points out (a row's columns side by side); insert points not
// listed here (an extension's own) come last
const OUTLINE = [
    { key: "top", label: _t("Top"), cols: [["top", "under_title"]] },
    { key: "columns", label: _t("Top section"), cols: [["summary", "top_columns", "ratings"], ["booking", "booking_under"]] },
    { key: "main", label: _t("Main column"), cols: [["under_top", "before_description", "description", "after_description", "after_itinerary"]] },
    { key: "bottom", label: _t("Full width, under the page"), cols: [["reviews", "gallery", "bottom"]] },
];

// the areas whose sections (insert points) move as a whole, within their area (owner, 2026-10-26); the others stay
const AREAS = {
    main: ["under_top", "before_description", "description", "after_description", "after_itinerary"],
    bottom: ["reviews", "gallery", "bottom"],
};
// a phone shows the page as one column: the top, the summary, ratings and the booking column, then the areas
const PHONE_TOP = ["top", "under_title", "summary", "top_columns", "ratings", "booking", "booking_under"];

export class PageTemplateEditor extends Component {
    static template = "mtbg_tours_content_blocks.PageTemplateEditor";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.stage = useRef("stage");
        this.nameInput = useRef("nameInput");
        this.state = useState({
            data: null, lines: [], dirty: false, saving: false, selected: null, renaming: false, creating: null,
            drag: null, dropSlot: null, dropIndex: -1, dropSection: null, order: [],
            sampleId: 0, lang: null, device: "desktop", mobileFollows: true, previewKey: 1, scale: 1, stageHeight: 600,
        });
        this.newKey = 0;
        this.previewTimer = null;
        useEffect((el) => el?.select(), () => [this.nameInput.el]);
        onWillStart(async () => {
            const last = this.readLast();
            await this.load(this.props.action?.context?.template_id || last.template || 0, last);
        });
        onMounted(() => {
            this.resizer = new ResizeObserver(() => this.fitPreview());
            if (this.stage.el) {
                this.resizer.observe(this.stage.el);
            }
            this.fitPreview();
        });
        onWillUnmount(() => {
            this.resizer?.disconnect();
            clearTimeout(this.previewTimer);
        });
    }

    // ------------------------------------------------------------------
    // Loading, saving
    // ------------------------------------------------------------------
    readLast() {
        try {
            return JSON.parse(window.localStorage.getItem(LAST_KEY) || "{}") || {};
        } catch {
            return {};
        }
    }

    writeLast() {
        try {
            window.localStorage.setItem(LAST_KEY, JSON.stringify({
                template: this.state.data?.template.id, sample: this.state.sampleId, lang: this.state.lang,
            }));
        } catch {
            // blocked storage: nothing remembered
        }
    }

    async load(templateId, last = {}) {
        const data = await this.orm.call(MODEL, "mtbg_editor_data", [templateId || 0]);
        this.applyData(data, last);
        await this.sendPreview();
    }

    applyData(data, last = {}) {
        this.state.data = data;
        // the Desktop and Mobile layouts: the preview's device says which one is edited; Mobile follows Desktop
        // (null) until it is changed, then it is a copy of its own
        this.layouts = {
            desktop: data.lines.map((line) => ({ ...line, key: this.lineKey(line) })),
            mobile: data.mobile_lines ? data.mobile_lines.map((line) => ({ ...line, key: this.lineKey(line) })) : null,
        };
        this.state.mobileFollows = !data.mobile_lines;
        this.state.lines = this.linesFor(this.state.device);
        // the sections' order, per layout (Mobile, while it follows Desktop: a copy of Desktop's)
        this.orders = { desktop: [...(data.slot_order?.desktop || [])],
                        mobile: data.slot_order?.mobile ? [...data.slot_order.mobile] : null };
        this.state.order = this.orderFor(this.state.device);
        // the sections left out of the page, per layout (Mobile, while it follows Desktop: a copy of Desktop's)
        this.hiddens = { desktop: [...(data.hidden_slots?.desktop || [])],
                         mobile: data.hidden_slots?.mobile ? [...data.hidden_slots.mobile] : null };
        this.state.hidden = this.hiddenFor(this.state.device);
        this.state.dirty = false;
        this.state.selected = null;
        this.state.renaming = false;
        // the pages of the template's kind to preview on (the module drawing that kind gives them)
        const samples = data.samples || [];
        const keep = [this.state.sampleId, last.sample ?? last.tour].find((id) => samples.some((t) => t.id === id));
        this.state.sampleId = keep || samples[0]?.id || 0;
        const keepLang = [this.state.lang, last.lang].find((code) => data.langs.some((l) => l.code === code));
        this.state.lang = keepLang || data.langs[0]?.code;
        this.writeLast();
    }

    lineKey(line) {
        if (line.id) {
            return `l${line.id}`;
        }
        if (line.code) {
            return `c${line.code}`;
        }
        this.newKey += 1;
        return `n${this.newKey}`;
    }

    /** The lines of the layout a device edits: Mobile, while it follows Desktop, a fresh copy of Desktop's. */
    linesFor(device) {
        if (device !== "phone") {
            return this.layouts.desktop;
        }
        if (!this.layouts.mobile) {
            this.layouts.mobile = this.layouts.desktop.map((line) => {
                const copy = { ...line, id: 0 };
                return { ...copy, key: this.lineKey(copy) };
            });
        }
        return this.layouts.mobile;
    }

    orderFor(device) {
        if (device !== "phone") {
            return this.orders.desktop;
        }
        if (!this.orders.mobile) {
            this.orders.mobile = [...this.orders.desktop];
        }
        return this.orders.mobile;
    }

    hiddenFor(device) {
        if (device !== "phone") {
            return this.hiddens.desktop;
        }
        if (!this.hiddens.mobile) {
            this.hiddens.mobile = [...this.hiddens.desktop];
        }
        return this.hiddens.mobile;
    }

    /** Keep what is being edited in its layout (before switching layouts or sending it). */
    stashLayout() {
        this.layouts[this.layoutKey] = this.state.lines;
        this.orders[this.layoutKey] = this.state.order;
        this.hiddens[this.layoutKey] = this.state.hidden;
    }

    get layoutKey() {
        return this.state.device === "phone" ? "mobile" : "desktop";
    }

    /** [Desktop lines, Mobile lines or null (phones show Desktop)] for the server. */
    get payload() {
        this.stashLayout();
        const clean = (lines) => lines.map((l) => ({
            id: l.id || 0, code: l.code || false, block_id: l.block_id || 0, slot: l.slot, active: l.active,
        }));
        const follows = this.state.mobileFollows;
        return [clean(this.layouts.desktop), follows ? null : clean(this.layouts.mobile),
                { desktop: this.orders.desktop, mobile: follows ? null : this.orders.mobile },
                { desktop: this.hiddens.desktop, mobile: follows ? null : this.hiddens.mobile }];
    }

    /** Mobile follows Desktop again (its own layout dropped on Save). */
    followDesktop() {
        this.layouts.mobile = null;
        this.orders.mobile = null;
        this.hiddens.mobile = null;
        this.state.mobileFollows = true;
        this.state.lines = this.linesFor(this.state.device);
        this.state.order = this.orderFor(this.state.device);
        this.state.hidden = this.hiddenFor(this.state.device);
        this.state.dirty = true;
        this.queuePreview();
    }

    async save() {
        this.state.saving = true;
        try {
            const data = await this.orm.call(MODEL, "mtbg_editor_save", [[this.template.id], ...this.payload]);
            this.applyData(data);
            this.notification.add(_t("Template saved: the pages that use it show it now."), { type: "success" });
            await this.sendPreview();
        } finally {
            this.state.saving = false;
        }
    }

    async discard() {
        await this.load(this.template.id);
    }

    /** Leaving unsaved changes: ask first. */
    confirmLeave(then) {
        if (!this.state.dirty) {
            return then();
        }
        this.dialog.add(ConfirmationDialog, {
            title: _t("Unsaved changes"),
            body: _t("This template has changes that are not saved. Leave them?"),
            confirmLabel: _t("Leave them"),
            confirm: then,
            cancel: () => {},
        });
    }

    changed() {
        if (this.state.device === "phone") {
            this.state.mobileFollows = false;  // the Mobile layout's own from now on
        }
        this.state.dirty = true;
        this.queuePreview();
    }

    // ------------------------------------------------------------------
    // Templates: pick, create, duplicate, rename, archive, make default
    // ------------------------------------------------------------------
    get template() {
        return this.state.data.template;
    }

    get templateGroups() {
        return this.state.data.kinds.map((kind) => ({
            ...kind, templates: this.state.data.templates.filter((t) => t.kind === kind.key),
        }));
    }

    onPickTemplate(ev) {
        const id = parseInt(ev.target.value);
        ev.target.value = this.template.id;
        this.confirmLeave(() => this.load(id));
    }

    startCreate(kind) {
        this.confirmLeave(() => {
            this.state.creating = { kind: kind || this.template.kind, name: "" };
        });
    }

    async create() {
        const { kind, name } = this.state.creating;
        if (!name.trim()) {
            return;
        }
        const [id] = await this.orm.create(MODEL, [{ name: name.trim(), kind }]);
        this.state.creating = null;
        await this.orm.call(MODEL, "mtbg_editor_save", [[id], []]);
        await this.load(id);
    }

    onCreateKey(ev) {
        if (ev.key === "Enter") {
            this.create();
        } else if (ev.key === "Escape") {
            this.state.creating = null;
        }
    }

    duplicate() {
        this.confirmLeave(async () => {
            const ids = await this.orm.call(MODEL, "copy", [[this.template.id]]);
            await this.load(Array.isArray(ids) ? ids[0] : ids);
            this.state.renaming = true;
        });
    }

    async rename(ev) {
        const name = ev.target.value.trim();
        this.state.renaming = false;
        if (name && name !== this.template.name) {
            await this.orm.write(MODEL, [this.template.id], { name });
            this.template.name = name;
            const listed = this.state.data.templates.find((t) => t.id === this.template.id);
            if (listed) {
                listed.name = name;
            }
        }
    }

    onRenameKey(ev) {
        if (ev.key === "Enter") {
            ev.target.blur();
        } else if (ev.key === "Escape") {
            this.state.renaming = false;
        }
    }

    async toggleArchive() {
        if (this.template.is_default) {
            this.notification.add(_t("Make another template the Default first: the Default cannot be archived."),
                { type: "warning" });
            return;
        }
        await this.orm.write(MODEL, [this.template.id], { active: !this.template.active });
        await this.reloadKeepingEdits();
    }

    async makeDefault() {
        await this.orm.call(MODEL, "action_make_default", [[this.template.id]]);
        await this.reloadKeepingEdits();
        this.notification.add(_t("Default template changed: the pages of this kind use it now."), { type: "success" });
    }

    /** Fresh template list and flags, the lines being edited stay. */
    async reloadKeepingEdits() {
        this.stashLayout();
        const layouts = { ...this.layouts };
        const orders = { ...this.orders };
        const hiddens = { ...this.hiddens };
        const follows = this.state.mobileFollows;
        const dirty = this.state.dirty;
        const data = await this.orm.call(MODEL, "mtbg_editor_data", [this.template.id]);
        this.applyData(data);
        if (dirty) {
            this.layouts = layouts;
            this.orders = orders;
            this.hiddens = hiddens;
            this.state.mobileFollows = follows;
            this.state.lines = this.linesFor(this.state.device);
            this.state.order = this.orderFor(this.state.device);
            this.state.hidden = this.hiddenFor(this.state.device);
            this.state.dirty = true;
        }
    }

    openList() {
        this.confirmLeave(() => this.action.doAction("mtbg_tours_content_blocks.action_page_template"));
    }

    // ------------------------------------------------------------------
    // What the page shows
    // ------------------------------------------------------------------
    get slots() {
        return this.state.data.slots;
    }

    /** The insert points of an area in this layout's order (those it lacks at their usual place). */
    areaSlots(area) {
        const codes = AREAS[area];
        const order = (this.state.order || []).filter((c) => codes.includes(c));
        return [...order, ...codes.filter((c) => !order.includes(c))];
    }

    slotArea(code) {
        return Object.keys(AREAS).find((area) => AREAS[area].includes(code)) || null;
    }

    /** The outline's rows: [{key, label, cols: [[slot, ...], ...]}] with the insert points this page has. On a phone:
     * one column, top to bottom, as the phone shows the page. */
    get outline() {
        const known = new Map(this.slots.map((s) => [s.code, s]));
        const used = new Set();
        if (this.state.device === "phone") {
            const codes = [...PHONE_TOP, ...this.areaSlots("main"), ...this.areaSlots("bottom")];
            const col = codes.filter((c) => known.has(c)).map((c) => known.get(c));
            const others = this.slots.filter((s) => !codes.includes(s.code));
            return [{ key: "phone", label: _t("On a phone, top to bottom"), cols: [[...col, ...others]] }];
        }
        const layout = OUTLINE.map((row) => row.key === "main" || row.key === "bottom"
            ? { ...row, cols: [this.areaSlots(row.key)] } : row);
        const rows = layout.map((row) => ({
            ...row,
            cols: row.cols.map((col) => col.filter((code) => known.has(code)).map((code) => {
                used.add(code);
                return known.get(code);
            })).filter((col) => col.length),
        })).filter((row) => row.cols.length);
        const others = this.slots.filter((s) => !used.has(s.code));
        if (others.length) {
            rows.push({ key: "other", label: _t("More insert points"), cols: [others] });
        }
        return rows;
    }

    /** The side panel: every section of the layout (in the outline's order) with all its blocks, shown or not. */
    get panelSections() {
        return this.outline.flatMap((row) => row.cols.flat()).map((slot) => ({
            code: slot.code, name: slot.name, hidden: this.isHidden(slot.code),
            lines: this.state.lines.filter((l) => l.slot === slot.code && !l.missing),
        }));
    }

    isHidden(code) {
        return this.state.hidden.includes(code);
    }

    /** Show / hide a whole section on the page (its blocks stay as they are, and come back with it). */
    toggleSection(code) {
        this.state.hidden = this.isHidden(code) ? this.state.hidden.filter((c) => c !== code) : [...this.state.hidden, code];
        this.changed();
    }

    /** Show / hide one block (an element hides with its group, as the eye does). */
    toggleLine(line) {
        const card = !line.block_id && this.cards.find((c) => c.codes.includes(line.code));
        const show = !line.active;
        for (const l of card ? card.lines : [line]) {
            l.active = show;
        }
        this.changed();
    }

    slotName(code) {
        return this.slots.find((s) => s.code === code)?.name || code;
    }

    elementOf(code) {
        return this.state.data.elements.find((e) => e.code === code);
    }

    lineOf(code) {
        return this.state.lines.find((l) => l.code === code);
    }

    lineName(line) {
        if (line.block_id) {
            return line.block_name;
        }
        return this.elementOf(line.code)?.name || line.code;
    }

    lineIcon(line) {
        return line.block_id ? "fa-clone" : this.elementOf(line.code)?.icon || "fa-square-o";
    }

    /** The cards on the left: an element each, or one card for a group (e.g. Stats & ratings), then the reusable
     * blocks the template places. */
    get cards() {
        const cards = [];
        const groups = {};
        for (const element of this.state.data.elements) {
            if (element.group) {
                if (!groups[element.group]) {
                    groups[element.group] = {
                        key: `g:${element.group}`, name: element.group_name || element.name, icon: element.icon,
                        description: element.description, panel: element.panel, kind: element.kind, codes: [],
                    };
                    cards.push(groups[element.group]);
                }
                groups[element.group].codes.push(element.code);
                groups[element.group].panel ||= element.panel;
            } else {
                cards.push({
                    key: `e:${element.code}`, name: element.name, icon: element.icon, description: element.description,
                    panel: element.panel, kind: element.kind, codes: [element.code],
                });
            }
        }
        for (const card of cards) {
            card.lines = card.codes.map((code) => this.lineOf(code)).filter(Boolean);
            card.placed = card.lines.some((l) => l.active);
            card.where = [...new Set(card.lines.filter((l) => l.active).map((l) => this.slotName(l.slot)))].join(" · ");
        }
        return cards;
    }

    get missingLines() {
        return this.state.lines.filter((l) => l.missing);
    }

    /** What an insert point's "Add…" list offers: the elements not on the page (a group as one) and the reusable
     * blocks the page does not show yet. It shrinks as they are placed and grows back when they are left out. */
    get addOptions() {
        const used = new Set(this.state.lines.filter((l) => l.block_id).map((l) => l.block_id));
        return {
            elements: this.cards.filter((c) => !c.placed).map((c) => ({ value: `card:${c.key}`, label: c.name })),
            blocks: this.state.data.blocks.filter((b) => !used.has(b.id)).map((b) => ({ value: `block:${b.id}`, label: b.name })),
        };
    }

    /** "Add…" on an insert point: the element (or group) or the reusable block goes last in it. */
    addToSlot(ev, slot) {
        const value = ev.target.value;
        ev.target.value = "";
        if (value.startsWith("card:")) {
            const card = this.cards.find((c) => c.key === value.slice(5));
            if (card) {
                this.placeAt(card.lines, slot, -1);
            }
        } else if (value.startsWith("block:")) {
            const block = this.state.data.blocks.find((b) => b.id === parseInt(value.slice(6)));
            if (!block) {
                return;
            }
            const line = { id: 0, code: false, block_id: block.id, block_name: block.name, slot, active: true, missing: false };
            line.key = this.lineKey(line);
            this.state.lines.push(line);
            this.placeAt([line], slot, -1);
        } else {
            return;
        }
        this.changed();
    }

    slotLines(code) {
        return this.state.lines.filter((l) => l.slot === code && l.active && !l.missing);
    }

    isSelected(line) {
        const card = this.state.selected;
        return Boolean(card && (card === `b:${line.key}` || this.cards.find((c) => c.key === card)?.codes.includes(line.code)));
    }

    select(key) {
        this.state.selected = this.state.selected === key ? null : key;
    }

    selectLine(line) {
        const card = line.block_id ? `b:${line.key}` : this.cards.find((c) => c.codes.includes(line.code))?.key;
        this.select(card);
    }

    // ------------------------------------------------------------------
    // Placing: drag and drop, switch on / off
    // ------------------------------------------------------------------
    onDragStart(ev, drag) {
        this.state.drag = drag;
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", JSON.stringify(drag));
    }

    onDragEnd() {
        this.state.drag = null;
        this.state.dropSlot = null;
        this.state.dropIndex = -1;
        this.state.dropSection = null;
    }

    /** A whole section (an insert point and its blocks) dragged by its name: it moves within its area. */
    onSectionDragStart(ev, code) {
        ev.stopPropagation();
        this.onDragStart(ev, { type: "section", code, area: this.slotArea(code) });
    }

    onSlotDragOver(ev, slot) {
        if (!this.state.drag) {
            return;
        }
        if (this.state.drag.type === "section") {
            if (this.slotArea(slot) !== this.state.drag.area || slot === this.state.drag.code) {
                this.state.dropSection = null;
                return;
            }
            ev.preventDefault();
            ev.dataTransfer.dropEffect = "move";
            const box = ev.currentTarget.getBoundingClientRect();
            this.state.dropSection = { code: slot, after: ev.clientY > box.top + box.height / 2 };
            return;
        }
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "move";
        const chips = [...ev.currentTarget.querySelectorAll(".mtbg_pte_chip")];
        let index = chips.length;
        for (const [n, chip] of chips.entries()) {
            const box = chip.getBoundingClientRect();
            if (ev.clientY < box.top + box.height / 2) {
                index = n;
                break;
            }
        }
        this.state.dropSlot = slot;
        this.state.dropIndex = index;
    }

    onSlotDragLeave(ev, slot) {
        if (this.state.dropSlot === slot && !ev.currentTarget.contains(ev.relatedTarget)) {
            this.state.dropSlot = null;
        }
    }

    onSlotDrop(ev, slot) {
        ev.preventDefault();
        const drag = this.state.drag;
        const index = this.state.dropIndex;
        const section = this.state.dropSection;
        this.onDragEnd();
        if (!drag) {
            return;
        }
        if (drag.type === "section") {
            if (section) {
                this.moveSection(drag.code, section.code, section.after);
            }
            return;
        }
        let moving = [];
        if (drag.type === "chip") {
            moving = this.state.lines.filter((l) => l.key === drag.key);
        }
        this.placeAt(moving, slot, index);
        this.changed();
    }

    /** Move the section ``code`` before (or after) ``target`` in their area; the page's other sections stay. */
    moveSection(code, target, after = false) {
        const area = this.slotArea(code);
        const seq = this.areaSlots(area).filter((c) => c !== code);
        const at = seq.indexOf(target) + (after ? 1 : 0);
        seq.splice(at, 0, code);
        const full = [...(this.state.order || [])];
        for (const c of AREAS[area]) {
            if (!full.includes(c)) {
                full.push(c);
            }
        }
        let n = 0;
        this.state.order = full.map((c) => (AREAS[area].includes(c) ? seq[n++] : c));
        this.changed();
    }

    /** Move a section one place up or down in its area (its arrows). */
    stepSection(code, step) {
        const seq = this.areaSlots(this.slotArea(code));
        const to = seq.indexOf(code) + step;
        if (to >= 0 && to < seq.length) {
            this.moveSection(code, seq[to], step > 0);
        }
    }

    /** Move ``moving`` (lines) into ``slot`` before its ``index``-th visible line, keeping their order. */
    placeAt(moving, slot, index) {
        const keys = new Set(moving.map((l) => l.key));
        const target = this.slotLines(slot).filter((l) => !keys.has(l.key));
        const before = index >= 0 && index < target.length ? target[index] : null;
        const rest = this.state.lines.filter((l) => !keys.has(l.key));
        for (const line of moving) {
            line.slot = slot;
            line.active = true;
        }
        let at = before ? rest.indexOf(before) : rest.length;
        if (!before && target.length) {
            at = rest.indexOf(target[target.length - 1]) + 1;
        }
        rest.splice(at, 0, ...moving);
        this.state.lines = rest;
    }

    /** Leave a line out of the page (a block line goes; an element's line is remembered, with its group). */
    removeLine(line) {
        if (line.block_id) {
            this.state.lines = this.state.lines.filter((l) => l.key !== line.key);
        } else {
            const card = this.cards.find((c) => c.codes.includes(line.code));
            for (const l of card ? card.lines : [line]) {
                l.active = false;
            }
        }
        this.changed();
    }

    moveLine(line, delta) {
        const visible = this.slotLines(line.slot);
        const index = visible.indexOf(line) + delta;
        if (index < 0 || index >= visible.length) {
            return;
        }
        this.placeAt([line], line.slot, delta > 0 ? index + 1 : index);
        this.changed();
    }

    openPanel(card) {
        this.action.doAction({ type: "ir.actions.client", tag: card.panel, name: card.name, target: "new",
            context: { dialog_size: "fullscreen" } }, { onClose: () => this.refreshPreview() });
    }

    // ------------------------------------------------------------------
    // Preview
    // ------------------------------------------------------------------
    get previewSample() {
        return (this.state.data.samples || []).find((t) => t.id === this.state.sampleId);
    }

    get previewUrl() {
        const sample = this.previewSample;
        if (!sample) {
            return "";
        }
        const lang = this.state.data.langs.find((l) => l.code === this.state.lang);
        const layout = this.state.device === "phone" ? "mobile" : "desktop";
        const sep = sample.url.includes("?") ? "&" : "?";
        return `${lang?.prefix || ""}${sample.url}${sep}mtbg_template_preview=${this.template.id}&mtbg_layout=${layout}&k=${this.state.previewKey}`;
    }

    /** The page at its real width, scaled down to the preview half, as tall as the half (in page pixels). */
    get frameStyle() {
        const width = this.state.device === "phone" ? PHONE_WIDTH : DESKTOP_WIDTH;
        const height = Math.round(this.state.stageHeight / this.state.scale);
        return `width: ${width}px; height: ${height}px; transform: scale(${this.state.scale});`;
    }

    fitPreview() {
        const stage = this.stage.el;
        if (!stage) {
            return;
        }
        const width = this.state.device === "phone" ? PHONE_WIDTH : DESKTOP_WIDTH;
        this.state.scale = Math.min(1, (stage.clientWidth - 16) / width);
        this.state.stageHeight = Math.max(300, stage.clientHeight - 16);
    }

    /** The preview's device, and the layout edited: Desktop or Mobile. */
    setDevice(device) {
        if (device !== this.state.device) {
            this.stashLayout();
            this.state.device = device;
            this.state.selected = null;
            this.state.lines = this.linesFor(device);
            this.state.order = this.orderFor(device);
            this.state.hidden = this.hiddenFor(device);
            this.refreshPreview();
        }
        this.fitPreview();
    }

    setLang(code) {
        this.state.lang = code;
        this.writeLast();
        this.refreshPreview();
    }

    onPickSample(ev) {
        this.state.sampleId = parseInt(ev.target.value);
        this.writeLast();
        this.refreshPreview();
    }

    queuePreview() {
        clearTimeout(this.previewTimer);
        this.previewTimer = setTimeout(() => this.sendPreview(), PREVIEW_DELAY);
    }

    async sendPreview() {
        if (!this.state.data) {
            return;
        }
        await this.orm.call(MODEL, "mtbg_editor_preview", [[this.template.id], ...this.payload]);
        this.refreshPreview();
    }

    refreshPreview() {
        this.state.previewKey += 1;
    }

    openPage() {
        const sample = this.previewSample;
        if (sample) {
            const lang = this.state.data.langs.find((l) => l.code === this.state.lang);
            window.open(`${lang?.prefix || ""}${sample.url}`, "_blank");
        }
    }
}

registry.category("actions").add("mtbg_page_template_editor", PageTemplateEditor);
