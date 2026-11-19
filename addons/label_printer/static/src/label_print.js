/** @odoo-module **/
/**
 * Product labels on the Bluetooth label printer, for every shop screen:
 * - printProductLabels(orm, product, copies): the layout from Settings › Label layout, the printer's own head
 *   width and chunk size, then the labels.
 * - <LabelPrintButton product="..."/>: Print label + copies, for a product card ({name or label_name, barcode,
 *   default_code, price_display}).
 * - view widget "bsx_label_preview": the live preview and a test print on the Label layout form.
 */
import { Component, onMounted, onWillUpdateProps, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { labelCode, labelRows, renderLabel } from "./label_render";
import { makeIdPrinter } from "./makeid_printer";

let layoutPromise = null;

/** The print layout (read once per page; Settings changes show after a reload). */
export function getLabelLayout(orm) {
    if (!layoutPromise) {
        layoutPromise = orm.call("bsx.label.layout", "get_print_layout", []).catch((error) => {
            layoutPromise = null;
            throw error;
        });
    }
    return layoutPromise;
}

export function warningText(warnings) {
    const texts = {
        no_code: _t("This product has no barcode and no internal reference: add one first."),
        bad_code: _t("The code has characters a barcode can't hold."),
        barcode_too_long: _t("The code is too long: its barcode goes over the max length."),
        too_tall: _t("The content is taller than the label: use smaller text or fewer lines."),
    };
    return warnings.map((w) => texts[w]).filter(Boolean);
}

/** Connects (asks for the printer the first time; call it from a click) and prints `copies` labels. */
export async function printLabelsWithLayout(layout, product, copies = 1) {
    await makeIdPrinter.connect();
    const status = await makeIdPrinter.readStatus();
    const rendered = renderLabel({ ...layout, tape_mm: Math.min(layout.tape_mm, status.headDots / 8) }, product);
    const blocking = rendered.warnings.filter((w) => w === "no_code" || w === "bad_code");
    if (blocking.length) {
        throw new Error(warningText(blocking).join(" "));
    }
    const label = labelRows(rendered, status.headDots);
    const labels = Array.from({ length: Math.max(1, copies) }, () => label);
    await makeIdPrinter.printLabels(labels, { darkness: layout.darkness, gapMode: layout.gap_mode });
}

export async function printProductLabels(orm, product, copies = 1) {
    product = { ...product, name: product.label_name || product.name };
    if (!labelCode(product)) {
        throw new Error(warningText(["no_code"])[0]);
    }
    const layout = await getLabelLayout(orm);
    await printLabelsWithLayout(layout, product, copies);
}

export class LabelPrintButton extends Component {
    static template = "label_printer.LabelPrintButton";
    static props = {
        product: Object,
        highlight: { type: Boolean, optional: true },
        class: { type: String, optional: true },
        // e.g. a form whose code is not valid yet
        disabled: { type: Boolean, optional: true },
        // shown under the button while disabled
        disabledReason: { type: String, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ copies: 1, busy: false });
        this.printer = makeIdPrinter;
    }

    get supported() {
        return makeIdPrinter.supported;
    }

    get hasCode() {
        return Boolean(labelCode(this.props.product));
    }

    changeCopies(delta) {
        this.state.copies = Math.min(50, Math.max(1, this.state.copies + delta));
    }

    async print() {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            await printProductLabels(this.orm, this.props.product, this.state.copies);
            this.notification.add(
                this.state.copies > 1 ? _t("%s labels printed.", this.state.copies) : _t("Label printed."),
                { type: "success" });
        } catch (error) {
            if (error?.name === "NotFoundError") {
                return; // the printer chooser was closed
            }
            this.notification.add(error?.message || _t("The label could not print."), { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }
}

export class BsxLabelPreview extends Component {
    static template = "label_printer.LabelPreview";
    static props = { ...standardWidgetProps };

    setup() {
        this.notification = useService("notification");
        this.canvasHolder = useRef("holder");
        this.state = useState({ warnings: [], size: "", busy: false });
        onMounted(() => this.draw(this.props));
        onWillUpdateProps((next) => this.draw(next));
    }

    layoutOf(props) {
        return { ...props.record.data };
    }

    sampleOf(props) {
        const d = props.record.data;
        return { name: d.sample_name || "", barcode: d.sample_code || "", default_code: "",
                 price_display: d.sample_price || "" };
    }

    draw(props) {
        const holder = this.canvasHolder.el;
        if (!holder) {
            return;
        }
        let rendered;
        try {
            rendered = renderLabel(this.layoutOf(props), this.sampleOf(props));
        } catch {
            return;
        }
        const { canvas } = rendered;
        canvas.className = "bsx_label_canvas";
        // 2x the real size, smaller on a narrow screen
        canvas.style.width = `min(100%, ${rendered.widthDots * 2}px)`;
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
            await printLabelsWithLayout(this.layoutOf(this.props), this.sampleOf(this.props), 1);
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
}

registry.category("view_widgets").add("bsx_label_preview", { component: BsxLabelPreview });
