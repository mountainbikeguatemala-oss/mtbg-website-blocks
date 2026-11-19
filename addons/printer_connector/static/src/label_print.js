/** @odoo-module **/
/**
 * Labels on the Bluetooth label printer, for every screen:
 * - printProductLabels(orm, item, copies, {usage}): the screen's layout (Settings › Label layout: the first one "Used
 *   for" ``usage``, else the first "Every screen" one), its font and logo, the printer's own head width and chunk
 *   size, then the labels. item: {name or label_name, barcode, default_code, price_display}.
 * - <LabelPrintButton product="..." usage="..."/>: Print label (one label a press: the printer does not cut).
 * (The Label layout page's drag and drop editor with its live preview: label_designer.js.)
 */
import { Component, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { elementsOf, labelCode, labelRows, prepareLabelAssets, renderLabel } from "./label_render";
import { makeIdPrinter } from "./makeid_printer";

const layoutPromises = new Map();

/** The print layout of a use (read once per page; Settings changes show after a reload). */
export function getLabelLayout(orm, usage = "general") {
    if (!layoutPromises.has(usage)) {
        layoutPromises.set(usage, orm.call("bsx.label.layout", "get_print_layout", [usage]).catch((error) => {
            layoutPromises.delete(usage);
            throw error;
        }));
    }
    return layoutPromises.get(usage);
}

export function warningText(warnings) {
    const texts = {
        no_code: _t("This product has no barcode and no internal reference: add one first."),
        bad_code: _t("The code has characters a barcode can't hold."),
        barcode_too_long: _t("The code is too long: its barcode goes over the max length."),
        too_tall: _t("The content is taller than the label: use smaller text or fewer lines."),
        font_missing: _t("\"My own font\" has no font file yet: the label uses the device's font."),
    };
    return warnings.map((w) => texts[w]).filter(Boolean);
}

/**
 * Connects (asks for the printer the first time: call it from a click, before anything else waits) and prints
 * `copies` labels. assets: prepareLabelAssets(layout) when already loaded.
 */
export async function printLabelsWithLayout(layout, product, copies = 1, assets = null) {
    await makeIdPrinter.connect();
    const status = await makeIdPrinter.readStatus();
    assets = assets || (await prepareLabelAssets(layout));
    const rendered = renderLabel({ ...layout, tape_mm: Math.min(layout.tape_mm, status.headDots / 8) }, product,
                                 assets);
    const blocking = rendered.warnings.filter((w) => w === "no_code" || w === "bad_code");
    if (blocking.length) {
        throw new Error(warningText(blocking).join(" "));
    }
    const label = labelRows(rendered, status.headDots);
    const labels = Array.from({ length: Math.max(1, copies) }, () => label);
    await makeIdPrinter.printLabels(labels, { darkness: layout.darkness, gapMode: layout.gap_mode });
}

export async function printProductLabels(orm, product, copies = 1, { usage = "general" } = {}) {
    product = { ...product, name: product.label_name || product.name };
    const layout = await getLabelLayout(orm, usage);
    const placed = Object.values(elementsOf(layout)).flat();
    if (placed.some((i) => i.field === "barcode") && !labelCode(product)) {
        throw new Error(warningText(["no_code"])[0]);
    }
    await printLabelsWithLayout(layout, product, copies);
}

export class LabelPrintButton extends Component {
    static template = "printer_connector.LabelPrintButton";
    static props = {
        product: Object,
        highlight: { type: Boolean, optional: true },
        class: { type: String, optional: true },
        // e.g. a form whose code is not valid yet
        disabled: { type: Boolean, optional: true },
        // shown under the button while disabled
        disabledReason: { type: String, optional: true },
        // the layout's use (Settings › Label layout › Used for); none: "Every screen"
        usage: { type: String, optional: true },
        // a label without a barcode (e.g. a name tag): printable without a code
        noCode: { type: Boolean, optional: true },
        // the button's text (default: Print label)
        label: { type: String, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        // one label a press: the printer does not cut labels, so copies are not offered (owner, 2026-11-19)
        this.state = useState({ busy: false });
        this.printer = makeIdPrinter;
    }

    get supported() {
        return makeIdPrinter.supported;
    }

    get hasCode() {
        return Boolean(this.props.noCode || labelCode(this.props.product));
    }

    async print() {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            await makeIdPrinter.connect(); // first: the browser's printer chooser needs the click
            await printProductLabels(this.orm, this.props.product, 1, { usage: this.props.usage || "general" });
            this.notification.add(_t("Label printed."), { type: "success" });
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

