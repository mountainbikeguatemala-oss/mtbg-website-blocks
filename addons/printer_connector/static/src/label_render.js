/** @odoo-module **/
/**
 * Draws a label from its layout (Settings › Label layout: bsx.label.layout) and turns it into printer rows.
 *
 * The label is drawn landscape, 8 dots per mm (203 dpi): width = label length along the tape, height = tape width.
 * A logo (left, right or above the rest, turned a little if asked) and the content: barcode (its code under it or on
 * its right), the name (1-3 lines), the price (under the name or on its right). Everything shrinks together to fit
 * the tape; a name is made smaller before it is cut. Auto length: as long as the content needs (min / max length).
 * The layout's font and logo are loaded first: prepareLabelAssets(layout) (fonts from the site, never outside).
 */
import { encodeCode128 } from "./code128";

export const DOTS_PER_MM = 8;

const FALLBACK = "Arial, Helvetica, sans-serif";
const loadedFaces = new Map();
const loadedImages = new Map();

export function labelCode(product) {
    return String(product?.barcode || product?.default_code || "").trim();
}

function loadImage(url) {
    if (!loadedImages.has(url)) {
        loadedImages.set(url, new Promise((resolve) => {
            const img = new Image();
            img.onload = () => resolve(img);
            img.onerror = () => resolve(null);
            img.src = url;
        }));
    }
    return loadedImages.get(url);
}

/** Loads the layout's font faces and logo: {family, logo (Image or null), fontMissing}. */
export async function prepareLabelAssets(layout, { logoSrc } = {}) {
    const spec = layout.font_spec || {};
    const family = spec.family || FALLBACK;
    for (const face of spec.faces || []) {
        const key = `${family}|${face.weight}|${face.url}`;
        if (!loadedFaces.has(key)) {
            loadedFaces.set(key, (async () => {
                try {
                    const font = new FontFace(family, `url("${face.url}")`, { weight: String(face.weight) });
                    await font.load();
                    document.fonts.add(font);
                    return true;
                } catch {
                    return false;
                }
            })());
        }
        await loadedFaces.get(key);
    }
    const src = logoSrc || layout.logo_url || "";
    const logo = src ? await loadImage(src) : null;
    return { family, logo, fontMissing: Boolean(spec.missing) };
}

function fontCss(family, px, bold) {
    const fam = family && family !== FALLBACK ? `"${family}", ${FALLBACK}` : FALLBACK;
    return `${bold ? "bold " : ""}${Math.round(px)}px ${fam}`;
}

/** Wraps text into at most maxLines lines no wider than width: {lines, cut} (cut: "…" on the last line). */
function wrapText(measure, text, width, maxLines) {
    const words = String(text || "").split(/\s+/).filter(Boolean);
    const lines = [];
    let line = "";
    let i = 0;
    while (i < words.length && lines.length < maxLines) {
        const next = line ? `${line} ${words[i]}` : words[i];
        if (measure(next) <= width || !line) {
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
    let cut = false;
    if (i < words.length || (lines.length && measure(lines[lines.length - 1]) > width)) {
        let last = lines[lines.length - 1] || "";
        while (last && measure(`${last}…`) > width) {
            last = last.slice(0, -1);
        }
        lines[lines.length - 1] = `${last.trimEnd()}…`;
        cut = true;
    }
    return { lines, cut };
}

/**
 * Renders the label. layout: dict from bsx.label.layout.get_print_layout(); product: {name, barcode,
 * default_code, price_display}; assets: prepareLabelAssets(layout) (without: the device's font, no logo).
 * Returns {canvas, widthDots (length), heightDots (tape), code, warnings[]}.
 */
export function renderLabel(layout, product, assets = {}) {
    const L = layout;
    const warnings = [];
    if (assets.fontMissing) {
        warnings.push("font_missing");
    }
    const family = assets.family || FALLBACK;
    const tapeDots = Math.round(L.tape_mm * DOTS_PER_MM);
    const margin = Math.round(L.margin_mm * DOTS_PER_MM);
    const minLen = Math.round(L.min_length_mm * DOTS_PER_MM);
    const maxLen = Math.max(minLen, Math.round(L.max_length_mm * DOTS_PER_MM));
    const fixedLen = L.length_mm > 0 ? Math.round(L.length_mm * DOTS_PER_MM) : 0;
    const bold = Boolean(L.font_bold);
    const code = labelCode(product);
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    const measureWith = (px, b) => (text) => {
        ctx.font = fontCss(family, px, b);
        return ctx.measureText(text).width;
    };
    const gap = Math.round(0.6 * DOTS_PER_MM);

    // --- logo: its box (left / right: across the tape; above: on top of the content)
    const logo = assets.logo && assets.logo.naturalWidth ? assets.logo : null;
    const logoPos = L.logo_position || "left";
    // logoW / logoH: the box it takes (turned: the turned picture's box); drawW / drawH: the picture itself
    let logoH = 0;
    let logoW = 0;
    let drawW = 0;
    let drawH = 0;
    const angle = ((L.logo_rotation || 0) * Math.PI) / 180;
    if (logo) {
        const want = Math.round((L.logo_height_mm || 8) * DOTS_PER_MM);
        logoH = Math.min(want, logoPos === "top" ? Math.max(8, tapeDots - 24) : tapeDots - 2);
        const ratio = logo.naturalWidth / logo.naturalHeight;
        const cos = Math.abs(Math.cos(angle));
        const sin = Math.abs(Math.sin(angle));
        drawH = logoH / (ratio * sin + cos);
        drawW = drawH * ratio;
        logoW = Math.round(drawW * cos + drawH * sin);
    }
    const sideLogo = logo && logoPos !== "top";
    const contentH = logo && logoPos === "top" ? tapeDots - logoH - gap : tapeDots;
    const limit = fixedLen || maxLen;
    const contentLimit = limit - (sideLogo ? logoW + gap : 0);

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
    const codeRight = Boolean(bars && L.show_code && code && L.code_position === "right");
    const barsMax = Math.round((L.barcode_max_mm || 40) * DOTS_PER_MM);
    const codeRoom = codeRight ? measureWith(L.code_font_px, true)(code) + gap : 0;
    const fits = () => barsModules * module <= barsMax && barsModules * module + 2 * quiet() + codeRoom <= contentLimit;
    while (bars && module > 1 && !fits()) {
        module -= 1;
    }
    if (bars && !fits()) {
        warnings.push("barcode_too_long");
    }

    // --- the content's rows; everything shrinks together until it fits the tape (and a name before it is cut)
    let scale = 1;
    let blocks;
    let contentWidth;
    const priceText = L.show_price ? String(product?.price_display || "") : "";
    for (let attempt = 0; attempt < 16; attempt++) {
        const codePx = L.code_font_px * scale;
        const namePx = L.name_font_px * scale;
        const pricePx = L.price_font_px * scale;
        const barH = bars ? Math.max(16, Math.round(L.barcode_height_mm * DOTS_PER_MM * Math.max(scale, 0.6))) : 0;
        const priceRight = Boolean(priceText) && L.price_position === "right";
        const textArea = contentLimit - 2 * margin;
        const priceW = priceText ? measureWith(pricePx, true)(priceText) : 0;
        const nameArea = priceRight ? Math.max(40, textArea - priceW - 3 * DOTS_PER_MM) : textArea;
        const wrapped = L.show_name ? wrapText(measureWith(namePx, bold), product?.name || "", nameArea, L.name_lines)
            : { lines: [], cut: false };
        const nameLines = wrapped.lines;
        blocks = [];
        if (bars) {
            const rowCodePx = codeRight ? Math.min(codePx, barH * 0.9) : 0;
            const codeW = codeRight ? measureWith(rowCodePx, true)(code) : 0;
            blocks.push({ kind: "bars", h: barH, codePx: rowCodePx, codeW,
                          w: barsModules * module + (codeRight ? gap + codeW : 0) });
        }
        if (L.show_code && code && !codeRight) {
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
        const rowGap = Math.round(0.4 * DOTS_PER_MM);
        const totalH = blocks.reduce((a, b) => a + b.h, 0) + rowGap * Math.max(0, blocks.length - 1);
        contentWidth = 0;
        for (const b of blocks) {
            if (b.kind === "bars") {
                contentWidth = Math.max(contentWidth, b.w + 2 * quiet());
            } else if (b.kind === "text") {
                contentWidth = Math.max(contentWidth, measureWith(b.px, b.bold)(b.text) + 2 * margin);
            } else if (b.kind === "namePrice") {
                const nw = Math.max(...b.lines.map((t) => measureWith(b.px, bold)(t)));
                contentWidth = Math.max(contentWidth, nw + 3 * DOTS_PER_MM + priceW + 2 * margin);
            }
        }
        blocks.gap = rowGap;
        blocks.totalH = totalH;
        const fitsTape = totalH <= contentH - 2;
        if ((fitsTape && !wrapped.cut) || scale < 0.4) {
            if (!fitsTape) {
                warnings.push("too_tall");
            }
            break;
        }
        scale *= 0.92;
    }

    // --- the canvas
    const needed = sideLogo ? contentWidth + logoW + gap + margin
        : Math.max(contentWidth, logo ? logoW + 2 * margin : 0);
    const width = fixedLen || Math.min(maxLen, Math.max(minLen, Math.ceil(needed)));
    canvas.width = width;
    canvas.height = tapeDots;
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, width, tapeDots);
    ctx.fillStyle = "#000";
    ctx.textBaseline = "middle";

    // the content's area (the logo's side taken off), its rows centred in it
    let x0 = 0;
    let x1 = width;
    let y0 = 0;
    if (logo) {
        let lx;
        let ly;
        if (logoPos === "top") {
            lx = Math.round((width - logoW) / 2);
            ly = Math.max(0, Math.round((tapeDots - logoH - gap - blocks.totalH) / 2));
            y0 = ly + logoH + gap;
        } else {
            ly = Math.round((tapeDots - logoH) / 2);
            if (logoPos === "right") {
                lx = width - margin - logoW;
                x1 = lx - gap + margin;
            } else {
                lx = margin;
                x0 = lx + logoW + gap - margin;
            }
        }
        ctx.save();
        ctx.translate(lx + logoW / 2, ly + logoH / 2);
        ctx.rotate(angle);
        ctx.drawImage(logo, -drawW / 2, -drawH / 2, drawW, drawH);
        ctx.restore();
    }
    const cx = (x0 + x1) / 2;
    let y = logo && logoPos === "top" ? y0 : Math.max(0, Math.round((tapeDots - blocks.totalH) / 2));
    for (const b of blocks) {
        if (b.kind === "bars") {
            let x = Math.round(cx - b.w / 2);
            bars.forEach((w, i) => {
                if (i % 2 === 0) {
                    ctx.fillRect(x, y, w * module, b.h);
                }
                x += w * module;
            });
            if (b.codePx) {
                ctx.font = fontCss(family, b.codePx, true);
                ctx.textAlign = "left";
                ctx.fillText(code, x + gap, y + b.h / 2);
            }
        } else if (b.kind === "text") {
            ctx.font = fontCss(family, b.px, b.bold);
            ctx.textAlign = "center";
            ctx.fillText(b.text, cx, y + b.h / 2);
        } else if (b.kind === "namePrice") {
            ctx.textAlign = "left";
            ctx.font = fontCss(family, b.px, bold);
            const lineH = b.px * 1.1;
            const top = y + (b.h - b.lines.length * lineH) / 2;
            b.lines.forEach((t, i) => ctx.fillText(t, x0 + margin, top + lineH * (i + 0.5)));
            ctx.font = fontCss(family, b.pricePx, true);
            ctx.textAlign = "right";
            ctx.fillText(priceText, x1 - margin, y + b.h / 2);
        }
        y += b.h + blocks.gap;
    }
    // hard black / white: thermal dots are on or off (a logo's transparent parts are white)
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
