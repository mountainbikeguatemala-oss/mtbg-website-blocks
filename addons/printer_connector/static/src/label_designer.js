/** @odoo-module **/
/**
 * The Label layout page's drag and drop editor (field widget "bsx_label_designer" on bsx.label.layout.elements;
 * owner, 2026-11-19: "make it a drag and drop field editor like our tour cards extension", "reorder the items").
 *
 * Like the Card Designer: the fields on the left (Logo, Barcode, Code, Name, Price); the label as a plan in three
 * regions (Left, Center, Right). Drag a field into a region, drag placed items within or between regions to reorder
 * them, click one for its size, bold, lines, turn, or "on the same line" as the item before it (Center). Above it,
 * the label itself, redrawn at once on every change on the page (its items, the logo, the font, the sizes...), and
 * "Print a test label". The items are saved with the page's Save.
 */
import { Component, onMounted, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useRecordObserver } from "@web/model/relational_model/utils";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { elementsOf, LABEL_FIELDS, newItem, prepareLabelAssets, REGIONS, renderLabel } from "./label_render";
import { printLabelsWithLayout, warningText } from "./label_print";
import { makeIdPrinter } from "./makeid_printer";

const ICONS = { logo: "fa-picture-o", barcode: "fa-barcode", code: "fa-hashtag", name: "fa-font", price: "fa-tag" };

/** A binary field's value as the form holds it: base64 once changed here, else a size text (saved file). */
function isBase64(value) {
    return typeof value === "string" && value.length > 200 && !/^[\d.,]+ ?[kmg]?b/i.test(value);
}

export class LabelDesigner extends Component {
    static template = "printer_connector.LabelDesigner";
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

    get regionLabels() {
        return { left: _t("Left"), center: _t("Center"), right: _t("Right") };
    }

    get fields() {
        return LABEL_FIELDS.map((key) => ({ key, label: this.labels[key], icon: ICONS[key] }));
    }

    get regions() {
        return REGIONS;
    }

    /**
     * The items as the page holds them, a fresh copy to edit (a layout not edited here yet: made once from its
     * settings, so its items keep their ids until it is saved).
     */
    get elements() {
        let saved = null;
        try {
            saved = this.props.record.data[this.props.name] ? JSON.parse(this.props.record.data[this.props.name]) : null;
        } catch {
            saved = null;
        }
        const made = elementsOf({ ...this.props.record.data, elements: saved });
        if (saved && Object.values(made).some((items) => items.length)) {
            return made;
        }
        if (!this.fromSettings || this.fromSettings.record !== this.props.record.id) {
            this.fromSettings = { record: this.props.record.id, elements: made };
        }
        return JSON.parse(JSON.stringify(this.fromSettings.elements));
    }

    commit(elements) {
        this.props.record.update({ [this.props.name]: JSON.stringify(elements) });
    }

    get selectedItem() {
        const uid = this.state.selected;
        for (const region of REGIONS) {
            const index = this.elements[region].findIndex((i) => i.uid === uid);
            if (index >= 0) {
                return { region, index, item: this.elements[region][index] };
            }
        }
        return null;
    }

    placedCount(field) {
        return REGIONS.reduce((n, r) => n + this.elements[r].filter((i) => i.field === field).length, 0);
    }

    // ------------------------------------------------------------------ editing
    add(field, region = "center", index = null) {
        const elements = this.elements;
        const item = newItem(field, this.props.record.data);
        elements[region].splice(index === null ? elements[region].length : index, 0, item);
        this.commit(elements);
        this.state.selected = item.uid;
    }

    remove(uid) {
        const elements = this.elements;
        for (const region of REGIONS) {
            elements[region] = elements[region].filter((i) => i.uid !== uid);
        }
        this.commit(elements);
        if (this.state.selected === uid) {
            this.state.selected = null;
        }
    }

    change(key, value) {
        const sel = this.selectedItem;
        if (!sel) {
            return;
        }
        const elements = this.elements;
        elements[sel.region][sel.index] = { ...sel.item, [key]: value };
        this.commit(elements);
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

    onDragItem(ev, region, item) {
        this.state.drag = { type: "item", region, uid: item.uid };
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", item.uid);
    }

    onDragEnd() {
        this.state.drag = null;
        this.state.dropAt = null;
    }

    onDragOver(ev, region, index) {
        if (!this.state.drag) {
            return;
        }
        ev.preventDefault();
        const at = this.state.dropAt;
        if (!at || at.region !== region || at.index !== index) {
            this.state.dropAt = { region, index };
        }
    }

    onDrop(ev, region, index) {
        ev.preventDefault();
        const drag = this.state.drag;
        this.onDragEnd();
        if (!drag) {
            return;
        }
        if (drag.type === "field") {
            this.add(drag.field, region, index);
            return;
        }
        const elements = this.elements;
        const from = elements[drag.region];
        const at = from.findIndex((i) => i.uid === drag.uid);
        if (at < 0) {
            return;
        }
        const [item] = from.splice(at, 1);
        if (drag.region === region && at < index) {
            index -= 1;
        }
        if (region !== "center") {
            item.inline = false;
        }
        elements[region].splice(index, 0, item);
        this.commit(elements);
        this.state.selected = item.uid;
    }

    isDropAt(region, index) {
        const at = this.state.dropAt;
        return Boolean(at && at.region === region && at.index === index);
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
        let saved = null;
        try {
            saved = d[this.props.name] ? JSON.parse(d[this.props.name]) : null;
        } catch {
            saved = null;
        }
        return { layout: { ...d, elements: elementsOf({ ...d, elements: saved }), font_spec: fontSpec, logo_url: logoSrc },
                 logoSrc };
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
