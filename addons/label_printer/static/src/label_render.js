/** @odoo-module **/
/**
 * Draws a product label from the label layout (Settings: bsx.label.layout) and turns it into printer rows.
 *
 * The label is drawn landscape, 8 dots per mm (203 dpi): width = label length along the tape, height = tape width.
 * Elements, top to bottom: barcode, its code in text, product name (1-2 lines), price (below, or right of the name).
 * Auto length: as long as the content needs, between the layout's min and max length.
 */
import { encodeCode128 } from "./code128";

export const DOTS_PER_MM = 8;

const FONT_FAMILY = "Arial, Helvetica, sans-serif";

export function labelCode(product) {
    return String(product?.barcode || product?.default_code || "").trim();
}

function fontFor(px, bold) {
    return `${bold ? "bold " : ""}${Math.round(px)}px ${FONT_FAMILY}`;
}

function measure(ctx, text, px, bold) {
    ctx.font = fontFor(px, bold);
    return ctx.measureText(text).width;
}

/** Wraps text into at most maxLines lines no wider than width; the last line gets "…" when cut. */
function wrapText(ctx, text, px, bold, width, maxLines) {
    const words = String(text || "").split(/\s+/).filter(Boolean);
    const lines = [];
    let line = "";
    let i = 0;
    while (i < words.length && lines.length < maxLines) {
        const next = line ? `${line} ${words[i]}` : words[i];
        if (measure(ctx, next, px, bold) <= width || !line) {
            line = next;
            i++;
        } else {
            lines.push(line);
            line = "";
        }
    }
    if (line && lines.length < maxLines) {
        lines.push(line);
    }
    if (i < words.length || (lines.length && measure(ctx, lines[lines.length - 1], px, bold) > width)) {
        let last = lines[lines.length - 1] || "";
        while (last && measure(ctx, `${last}…`, px, bold) > width) {
            last = last.slice(0, -1);
        }
        lines[lines.length - 1] = `${last.trimEnd()}…`;
    }
    return lines;
}

/**
 * Renders the label. layout: dict from bsx.label.layout.get_print_layout(); product: {name, barcode,
 * default_code, price_display}. Returns {canvas, widthDots (length), heightDots (tape), code, warnings[]}.
 */
export function renderLabel(layout, product) {
    const L = layout;
    const warnings = [];
    const tapeDots = Math.round(L.tape_mm * DOTS_PER_MM);
    const margin = Math.round(L.margin_mm * DOTS_PER_MM);
    const minLen = Math.round(L.min_length_mm * DOTS_PER_MM);
    const maxLen = Math.max(minLen, Math.round(L.max_length_mm * DOTS_PER_MM));
    const fixedLen = L.length_mm > 0 ? Math.round(L.length_mm * DOTS_PER_MM) : 0;
    const bold = Boolean(L.font_bold);
    const code = labelCode(product);
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");

    // --- barcode
    let bars = null;
    let module = Math.max(1, Math.round(L.bar_module_dots || 2));
    if (L.show_barcode) {
        if (!code) {
            warnings.push("no_code");
        } else {
            try {
                bars = encodeCode128(code);
            } catch {
                warnings.push("bad_code");
            }
        }
    }
    const barsModules = bars ? bars.reduce((a, b) => a + b, 0) : 0;
    // the printer leaves its own ~1.5 mm blank border around every label, so a small quiet zone scans fine
    const quiet = () => Math.max(margin, 2 * module);
    const limit = fixedLen || maxLen;
    const barsMax = Math.round((L.barcode_max_mm || 40) * DOTS_PER_MM);
    const fits = () => barsModules * module <= barsMax && barsModules * module + 2 * quiet() <= limit;
    while (bars && module > 1 && !fits()) {
        module -= 1;
    }
    if (bars && !fits()) {
        warnings.push("barcode_too_long");
    }
    const barcodeWidth = bars ? barsModules * module + 2 * quiet() : 0;

    // --- text sizes; shrink everything together until it fits the tape
    let scale = 1;
    let blocks;
    let contentWidth;
    const priceText = L.show_price ? String(product?.price_display || "") : "";
    for (let attempt = 0; attempt < 12; attempt++) {
        const codePx = L.code_font_px * scale;
        const namePx = L.name_font_px * scale;
        const pricePx = L.price_font_px * scale;
        const barH = bars ? Math.max(16, Math.round(L.barcode_height_mm * DOTS_PER_MM * Math.max(scale, 0.6))) : 0;
        const priceRight = Boolean(priceText) && L.price_position === "right";
        const textArea = (fixedLen || maxLen) - 2 * margin;
        const priceW = priceText ? measure(ctx, priceText, pricePx, true) : 0;
        const nameArea = priceRight ? Math.max(40, textArea - priceW - 3 * DOTS_PER_MM) : textArea;
        const nameLines = L.show_name ? wrapText(ctx, product?.name || "", namePx, bold, nameArea, L.name_lines) : [];
        blocks = [];
        if (bars) {
            blocks.push({ kind: "bars", h: barH });
        }
        if (L.show_code && code) {
            blocks.push({ kind: "text", text: code, px: codePx, bold: false, h: Math.ceil(codePx * 1.05) });
        }
        if (priceRight && nameLines.length) {
            blocks.push({ kind: "namePrice", lines: nameLines, px: namePx, pricePx,
                          h: Math.ceil(Math.max(nameLines.length * namePx * 1.1, pricePx * 1.1)) });
        } else {
            for (const line of nameLines) {
                blocks.push({ kind: "text", text: line, px: namePx, bold, h: Math.ceil(namePx * 1.1) });
            }
            if (priceText) {
                blocks.push({ kind: "text", text: priceText, px: pricePx, bold: true, h: Math.ceil(pricePx * 1.1) });
            }
        }
        const gap = Math.round(0.4 * DOTS_PER_MM);
        const totalH = blocks.reduce((a, b) => a + b.h, 0) + gap * Math.max(0, blocks.length - 1);
        contentWidth = barcodeWidth;
        for (const b of blocks) {
            if (b.kind === "text") {
                contentWidth = Math.max(contentWidth, measure(ctx, b.text, b.px, b.bold) + 2 * margin);
            } else if (b.kind === "namePrice") {
                const nw = Math.max(...b.lines.map((t) => measure(ctx, t, b.px, bold)));
                contentWidth = Math.max(contentWidth, nw + 3 * DOTS_PER_MM + priceW + 2 * margin);
            }
        }
        blocks.gap = gap;
        blocks.totalH = totalH;
        if (totalH <= tapeDots - 2 || scale < 0.45) {
            if (totalH > tapeDots) {
                warnings.push("too_tall");
            }
            break;
        }
        scale *= 0.92;
    }

    const width = fixedLen || Math.min(maxLen, Math.max(minLen, Math.ceil(contentWidth)));
    canvas.width = width;
    canvas.height = tapeDots;
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, width, tapeDots);
    ctx.fillStyle = "#000";
    ctx.textBaseline = "middle";
    let y = Math.max(0, Math.round((tapeDots - blocks.totalH) / 2));
    for (const b of blocks) {
        if (b.kind === "bars") {
            let x = Math.round((width - barsModules * module) / 2);
            bars.forEach((w, i) => {
                if (i % 2 === 0) {
                    ctx.fillRect(x, y, w * module, b.h);
                }
                x += w * module;
            });
        } else if (b.kind === "text") {
            ctx.font = fontFor(b.px, b.bold);
            ctx.textAlign = "center";
            ctx.fillText(b.text, width / 2, y + b.h / 2);
        } else if (b.kind === "namePrice") {
            ctx.textAlign = "left";
            ctx.font = fontFor(b.px, bold);
            const lineH = b.px * 1.1;
            const top = y + (b.h - b.lines.length * lineH) / 2;
            b.lines.forEach((t, i) => ctx.fillText(t, margin, top + lineH * (i + 0.5)));
            ctx.font = fontFor(b.pricePx, true);
            ctx.textAlign = "right";
            ctx.fillText(priceText, width - margin, y + b.h / 2);
        }
        y += b.h + blocks.gap;
    }
    // hard black / white: thermal dots are on or off
    const img = ctx.getImageData(0, 0, width, tapeDots);
    const d = img.data;
    for (let i = 0; i < d.length; i += 4) {
        const v = d[i] * 0.3 + d[i + 1] * 0.59 + d[i + 2] * 0.11 < 150 ? 0 : 255;
        d[i] = d[i + 1] = d[i + 2] = v;
        d[i + 3] = 255;
    }
    ctx.putImageData(img, 0, 0);
    return { canvas, widthDots: width, heightDots: tapeDots, code, warnings };
}

/**
 * Printer rows of a rendered label: one row per dot along the tape (the label's right end first, as the
 * MakeID app sends it), headDots across, 1 bit per dot, first dot in the top bit, the tape centred on the head.
 */
export function labelRows(rendered, headDots) {
    const { canvas, widthDots, heightDots } = rendered;
    const data = canvas.getContext("2d").getImageData(0, 0, widthDots, heightDots).data;
    const bytesPerRow = Math.ceil(headDots / 8);
    const offset = Math.max(0, Math.floor((headDots - heightDots) / 2));
    const out = new Uint8Array(widthDots * bytesPerRow);
    for (let r = 0; r < widthDots; r++) {
        const col = widthDots - 1 - r;
        for (let y = 0; y < heightDots; y++) {
            const dot = y + offset;
            if (dot >= headDots) {
                break;
            }
            if (data[(y * widthDots + col) * 4] < 128) {
                out[r * bytesPerRow + (dot >> 3)] |= 0x80 >> (dot & 7);
            }
        }
    }
    return { rows: out, rowCount: widthDots, bytesPerRow };
}
