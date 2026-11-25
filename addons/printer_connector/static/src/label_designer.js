/** @odoo-module **/
/**
 * The Label layout page's drag and drop editor (field widget "bsx_label_designer" on bsx.label.layout.elements;
 * owner, 2026-11-19: "make it a drag and drop field editor like our tour cards extension", "reorder the items").
 *
 * Like the Card Designer: the fields on the left (Logo, Barcode, Code, Name, Price); the label as a plan of rows,
 * top to bottom, each with its Left, Center and Right (owner: "we need left right center per row"). Drag a field
 * into a row's slot, drag placed items within or between slots and rows, add / remove rows, click an item for its
 * size, bold, lines, turn, and the logo's spacing (top, right, bottom, left). Above it, the label itself, redrawn at
 * once on every change on the page, and "Print a test label". Saved with the page's Save.
 */
import { Component, onMounted, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useRecordObserver } from "@web/model/relational_model/utils";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { LABEL_FIELDS, newItem, newRow, prepareLabelAssets, renderLabel, rowsOf, SLOTS } from "./label_render";
import { PrinterUnsupportedNote, printLabelsWithLayout, warningText } from "./label_print";
import { makeIdPrinter } from "./makeid_printer";

const ICONS = { logo: "fa-picture-o", barcode: "fa-barcode", code: "fa-hashtag", name: "fa-font", price: "fa-tag" };

/** A binary field's value as the form holds it: base64 once changed here, else a size text (saved file). */
function isBase64(value) {
    return typeof value === "string" && value.length > 200 && !/^[\d.,]+ ?[kmg]?b/i.test(value);
}

export class LabelDesigner extends Component {
    static template = "printer_connector.LabelDesigner";
    static components = { PrinterUnsupportedNote };
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.holder = useRef("holder");
        this.state = useState({ selected: null, drag: null, dropAt: null, warnings: [], size: "", busy: false });
        this.fontSpecs = null;
        this.drawing = 0;
        // every change on the page (an item, the logo, the font, a size...) redraws the label at once
        useRecordObserver((record) => this.draw(record));
        onMounted(() => this.draw(this.props.record));
    }

    get labels() {
        return { logo: _t("Logo"), barcode: _t("Barcode"), code: _t("Code"), name: _t("Name"), price: _t("Price") };
    }

    get slotLabels() {
        return { left: _t("Left"), center: _t("Center"), right: _t("Right") };
    }

    get fields() {
        return LABEL_FIELDS.map((key) => ({ key, label: this.labels[key], icon: ICONS[key] }));
    }

    get slots() {
        return SLOTS;
    }

    icon(field) {
        return ICONS[field];
    }

    /** The saved items, if readable. */
    saved(record = this.props.record) {
        try {
            return record.data[this.props.name] ? JSON.parse(record.data[this.props.name]) : null;
        } catch {
            return null;
        }
    }

    /** The rows as the page holds them, a fresh copy to edit (not saved from here yet: made from its settings). */
    get rows() {
        return rowsOf({ ...this.props.record.data, elements: this.saved() });
    }

    commit(rows) {
        this.props.record.update({ [this.props.name]: JSON.stringify({ rows }) });
    }

    find(rows, uid) {
        for (let r = 0; r < rows.length; r++) {
            for (const slot of SLOTS) {
                const index = rows[r][slot].findIndex((i) => i.uid === uid);
                if (index >= 0) {
                    return { row: r, slot, index, item: rows[r][slot][index] };
                }
            }
        }
        return null;
    }

    get selectedItem() {
        return this.state.selected ? this.find(this.rows, this.state.selected) : null;
    }

    placedCount(field) {
        return this.rows.reduce((n, row) => n + SLOTS.reduce((m, k) => m + row[k].filter((i) => i.field === field).length, 0), 0);
    }

    // ------------------------------------------------------------------ editing
    /** A field added: into a row's slot (clicked in the list: the middle of the last row, a new row when it is full). */
    add(field, row = null, slot = "center", index = null) {
        const rows = this.rows;
        if (row === null) {
            row = rows.length - 1;
            if (row < 0 || SLOTS.some((k) => rows[row][k].length)) {
                rows.push(newRow());
                row = rows.length - 1;
            }
        }
        const item = newItem(field, this.props.record.data);
        const items = rows[row][slot];
        items.splice(index === null ? items.length : index, 0, item);
        this.commit(rows);
        this.state.selected = item.uid;
    }

    addRow() {
        const rows = this.rows;
        rows.push(newRow());
        this.commit(rows);
    }

    removeRow(r) {
        const rows = this.rows;
        rows.splice(r, 1);
        this.commit(rows.length ? rows : [newRow()]);
    }

    moveRow(r, delta) {
        const rows = this.rows;
        const to = r + delta;
        if (to < 0 || to >= rows.length) {
            return;
        }
        [rows[r], rows[to]] = [rows[to], rows[r]];
        this.commit(rows);
    }

    remove(uid) {
        const rows = this.rows;
        const at = this.find(rows, uid);
        if (at) {
            rows[at.row][at.slot].splice(at.index, 1);
            this.commit(rows);
        }
        if (this.state.selected === uid) {
            this.state.selected = null;
        }
    }

    change(key, value) {
        const rows = this.rows;
        const at = this.state.selected && this.find(rows, this.state.selected);
        if (!at) {
            return;
        }
        rows[at.row][at.slot][at.index] = { ...at.item, [key]: value };
        this.commit(rows);
    }

    changeNumber(key, ev, min, max) {
        const value = Number(String(ev.target.value).replace(",", "."));
        if (Number.isFinite(value)) {
            this.change(key, Math.min(max, Math.max(min, value)));
        }
    }

    // ------------------------------------------------------------------ drag and drop (as the Card Designer)
    onDragField(ev, field) {
        this.state.drag = { type: "field", field };
        ev.dataTransfer.effectAllowed = "copy";
        ev.dataTransfer.setData("text/plain", field);
    }

    onDragItem(ev, item) {
        this.state.drag = { type: "item", uid: item.uid };
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", item.uid);
    }

    onDragEnd() {
        this.state.drag = null;
        this.state.dropAt = null;
    }

    onDragOver(ev, row, slot, index) {
        if (!this.state.drag) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        const at = this.state.dropAt;
        if (!at || at.row !== row || at.slot !== slot || at.index !== index) {
            this.state.dropAt = { row, slot, index };
        }
    }

    onDrop(ev, row, slot, index) {
        ev.preventDefault();
        ev.stopPropagation();
        const drag = this.state.drag;
        this.onDragEnd();
        if (!drag) {
            return;
        }
        if (drag.type === "field") {
            this.add(drag.field, row, slot, index);
            return;
        }
        const rows = this.rows;
        const from = this.find(rows, drag.uid);
        if (!from) {
            return;
        }
        rows[from.row][from.slot].splice(from.index, 1);
        if (from.row === row && from.slot === slot && from.index < index) {
            index -= 1;
        }
        rows[row][slot].splice(index, 0, from.item);
        this.commit(rows);
        this.state.selected = from.item.uid;
    }

    isDropAt(row, slot, index) {
        const at = this.state.dropAt;
        return Boolean(at && at.row === row && at.slot === slot && at.index === index);
    }

    // ------------------------------------------------------------------ the label, live
    async layoutOf(record) {
        const d = record.data;
        const id = record.resId;
        const unique = encodeURIComponent(String(d.write_date || "")).replace(/\D/g, "");
        if (!this.fontSpecs) {
            this.fontSpecs = await this.orm.call("bsx.label.layout", "get_font_specs", []);
        }
        let fontSpec = this.fontSpecs[d.font] || { family: "", faces: [] };
        if (d.font === "custom") {
            const file = d.font_file;
            if (isBase64(file)) {
                const url = `data:font/ttf;base64,${file}`;
                fontSpec = { family: `Label Preview Font ${file.length}`, faces: [{ weight: 400, url }, { weight: 700, url }] };
            } else if (file && id) {
                const url = `/web/content/bsx.label.layout/${id}/font_file?unique=${unique}`;
                fontSpec = { family: `Label Font ${id}`, faces: [{ weight: 400, url }, { weight: 700, url }] };
            } else {
                fontSpec = { family: "", faces: [], missing: true };
            }
        }
        let logoSrc = "";
        if (isBase64(d.logo)) {
            logoSrc = `data:image/png;base64,${d.logo}`;
        } else if (d.logo && id) {
            logoSrc = `/web/image/bsx.label.layout/${id}/logo?unique=${unique}`;
        }
        const rows = rowsOf({ ...d, elements: this.saved(record) });
        return { layout: { ...d, elements: { rows }, font_spec: fontSpec, logo_url: logoSrc }, logoSrc };
    }

    sampleOf(record) {
        const d = record.data;
        return { name: d.sample_name || "", barcode: d.sample_code || "", default_code: "",
                 price_display: d.sample_price || "" };
    }

    async draw(record) {
        const ticket = ++this.drawing;
        let rendered;
        try {
            const { layout, logoSrc } = await this.layoutOf(record);
            const assets = await prepareLabelAssets(layout, { logoSrc });
            rendered = renderLabel(layout, this.sampleOf(record), assets);
        } catch {
            return;
        }
        const holder = this.holder.el;
        if (!holder || ticket !== this.drawing) {
            return; // a newer drawing is on its way
        }
        const { canvas } = rendered;
        canvas.className = "bsx_label_canvas";
        // 3x the real size, smaller on a narrow screen
        canvas.style.width = `min(100%, ${rendered.widthDots * 3}px)`;
        holder.replaceChildren(canvas);
        this.state.warnings = warningText(rendered.warnings);
        this.state.size = `${(rendered.widthDots / 8).toFixed(1)} × ${(rendered.heightDots / 8).toFixed(1)} mm`;
    }

    async testPrint() {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            await makeIdPrinter.connect(); // first: the browser's printer chooser needs the click
            const { layout, logoSrc } = await this.layoutOf(this.props.record);
            const assets = await prepareLabelAssets(layout, { logoSrc });
            await printLabelsWithLayout(layout, this.sampleOf(this.props.record), 1, assets);
            this.notification.add(_t("Test label printed."), { type: "success" });
        } catch (error) {
            if (error?.name !== "NotFoundError") {
                this.notification.add(error?.message || _t("The label could not print."), { type: "danger" });
            }
        } finally {
            this.state.busy = false;
        }
    }

    get supported() {
        return makeIdPrinter.supported;
    }

    get hasLogo() {
        return Boolean(this.props.record.data.logo);
    }
}

registry.category("fields").add("bsx_label_designer", { component: LabelDesigner, supportedTypes: ["text"] });
