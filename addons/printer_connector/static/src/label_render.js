/** @odoo-module **/
/**
 * Draws a label from its layout (Settings › Label layout: bsx.label.layout) and turns it into printer rows.
 *
 * The label is drawn landscape, 8 dots per mm (203 dpi): width = label length along the tape, height = tape width.
 * Its items (logo, barcode, code, name, price) in three regions: Left, Center (rows) and Right, placed with the
 * drag and drop editor (elementsOf: layouts made before it are made from their settings). Everything shrinks together
 * to fit the tape; a name is made smaller before it is cut. Auto length: as long as the content needs.
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

export const LABEL_FIELDS = ["logo", "barcode", "code", "name", "price"];
export const REGIONS = ["left", "center", "right"];

let uidSeq = 0;
export function itemUid() {
    uidSeq += 1;
    return `i${Date.now().toString(36)}${uidSeq}`;
}

/** A new item of a field, with its usual size. */
export function newItem(field, layout = {}) {
    const base = { uid: itemUid(), field, inline: false, bold: field !== "code" };
    switch (field) {
        case "logo":
            return { ...base, size: layout.logo_height_mm || 8, rotation: layout.logo_rotation || 0 };
        case "barcode":
            return { ...base, size: layout.barcode_height_mm || 7 };
        case "code":
            return { ...base, size: layout.code_font_px || 14, bold: false };
        case "name":
            return { ...base, size: layout.name_font_px || 18, bold: layout.font_bold !== false, lines: layout.name_lines || 1 };
        case "price":
            return { ...base, size: layout.price_font_px || 20 };
    }
    return base;
}

/**
 * The layout's items by region: its saved items (the drag and drop editor), else made from its settings (layouts made
 * before the editor: the same label as before).
 */
export function elementsOf(layout) {
    const e = layout.elements;
    if (e && typeof e === "object" && REGIONS.some((r) => Array.isArray(e[r]) && e[r].length)) {
        return Object.fromEntries(REGIONS.map((r) => [r, (e[r] || []).filter((i) => LABEL_FIELDS.includes(i.field))]));
    }
    const out = { left: [], center: [], right: [] };
    const logo = newItem("logo", layout);
    const pos = layout.logo_position || "left";
    if (pos === "top") {
        out.center.push(logo);
    } else {
        out[pos === "right" ? "right" : "left"].push(logo);
    }
    if (layout.show_barcode) {
        out.center.push(newItem("barcode", layout));
        if (layout.show_code) {
            const code = newItem("code", layout);
            if (layout.code_position === "right") {
                Object.assign(code, { inline: true, bold: true });
            }
            out.center.push(code);
        }
    }
    if (layout.show_name) {
        out.center.push(newItem("name", layout));
    }
    if (layout.show_price) {
        out.center.push({ ...newItem("price", layout), inline: layout.show_name && layout.price_position === "right" });
    }
    return out;
}

/**
 * Renders the label. layout: dict from bsx.label.layout.get_print_layout(); product: {name, barcode,
 * default_code, price_display}; assets: prepareLabelAssets(layout) (without: the device's font, no logo).
 * The items: Left and Right stack top to bottom beside the rest; Center is rows (an item "inline" joins the row
 * before it). Everything shrinks together until it fits the tape, and a name before it is cut.
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
    const limit = fixedLen || maxLen;
    const code = labelCode(product);
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    const measureWith = (px, b) => (text) => {
        ctx.font = fontCss(family, px, b);
        return ctx.measureText(text).width;
    };
    const gap = Math.round(0.6 * DOTS_PER_MM);
    const rowGap = Math.round(0.4 * DOTS_PER_MM);
    const logo = assets.logo && assets.logo.naturalWidth ? assets.logo : null;
    const priceText = String(product?.price_display || "");
    const regions = elementsOf(L);

    // the barcode's bars (one encoding for every barcode item)
    let bars = null;
    const wantsBars = REGIONS.some((r) => regions[r].some((i) => i.field === "barcode"));
    if (wantsBars) {
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
    const barsMax = Math.round((L.barcode_max_mm || 40) * DOTS_PER_MM);
    let module = Math.max(1, Math.round(L.bar_module_dots || 2));

    /** An item's box at a scale: {w, h, draw(x, y, rowH)}; null: nothing to show (no logo, empty text). */
    const box = (item, scale, room) => {
        const size = Number(item.size) || 0;
        if (item.field === "logo") {
            if (!logo) {
                return null;
            }
            const h = Math.max(8, Math.min(tapeDots - 2, Math.round(size * DOTS_PER_MM * scale)));
            const angle = ((Number(item.rotation) || 0) * Math.PI) / 180;
            const ratio = logo.naturalWidth / logo.naturalHeight;
            const cos = Math.abs(Math.cos(angle));
            const sin = Math.abs(Math.sin(angle));
            const dh = h / (ratio * sin + cos);
            const dw = dh * ratio;
            const w = Math.round(dw * cos + dh * sin);
            return { w, h, draw: (x, y, rowH) => {
                ctx.save();
                ctx.translate(x + w / 2, y + rowH / 2);
                ctx.rotate(angle);
                ctx.drawImage(logo, -dw / 2, -dh / 2, dw, dh);
                ctx.restore();
            } };
        }
        if (item.field === "barcode") {
            if (!bars) {
                return null;
            }
            const h = Math.max(16, Math.round(size * DOTS_PER_MM * Math.max(scale, 0.6)));
            const w = barsModules * module + 2 * module;
            return { w, h, draw: (x, y, rowH) => {
                let bx = x + module;
                const top = y + (rowH - h) / 2;
                bars.forEach((bw, i) => {
                    if (i % 2 === 0) {
                        ctx.fillRect(bx, top, bw * module, h);
                    }
                    bx += bw * module;
                });
            } };
        }
        const text = item.field === "code" ? code : item.field === "price" ? priceText : String(product?.name || "");
        if (!text) {
            return null;
        }
        const px = Math.max(6, size * scale);
        const bold = Boolean(item.bold);
        const measure = measureWith(px, bold);
        const lines = item.field === "name" && room !== undefined
            ? wrapText(measure, text, Math.max(20, room), Math.max(1, Math.min(3, item.lines || 1)))
            : { lines: [text], cut: false };
        const lineH = Math.ceil(px * 1.1);
        const w = Math.ceil(Math.max(...lines.lines.map(measure)));
        return { w, h: lineH * lines.lines.length, cut: lines.cut, draw: (x, y, rowH) => {
            ctx.font = fontCss(family, px, bold);
            ctx.textAlign = "left";
            const top = y + (rowH - lineH * lines.lines.length) / 2;
            lines.lines.forEach((t, i) => ctx.fillText(t, x, top + lineH * (i + 0.5)));
        } };
    };

    /** A side region (left / right): its items stacked; a center: its rows. */
    const layoutAt = (scale) => {
        const side = (items) => {
            const boxes = items.map((i) => box(i, scale)).filter(Boolean);
            const h = boxes.reduce((a, b) => a + b.h, 0) + rowGap * Math.max(0, boxes.length - 1);
            return { boxes, w: Math.max(0, ...boxes.map((b) => b.w)), h };
        };
        const left = side(regions.left);
        const right = side(regions.right);
        const centerRoom = limit - 2 * margin - (left.w ? left.w + gap : 0) - (right.w ? right.w + gap : 0);
        const rows = [];
        for (const item of regions.center) {
            if (!rows.length || !item.inline) {
                rows.push([]);
            }
            rows[rows.length - 1].push(item);
        }
        let cut = false;
        const rowBoxes = rows.map((row) => {
            // the name gets the room the rest of its row leaves
            const others = row.filter((i) => i.field !== "name").map((i) => box(i, scale)).filter(Boolean);
            const used = others.reduce((a, b) => a + b.w, 0) + gap * others.length;
            const boxes = row.map((i) => (i.field === "name" ? box(i, scale, centerRoom - used) : box(i, scale)))
                .filter(Boolean);
            cut = cut || boxes.some((b) => b.cut);
            return { boxes, w: boxes.reduce((a, b) => a + b.w, 0) + gap * Math.max(0, boxes.length - 1),
                     h: Math.max(0, ...boxes.map((b) => b.h)) };
        }).filter((r) => r.boxes.length);
        const centerH = rowBoxes.reduce((a, r) => a + r.h, 0) + rowGap * Math.max(0, rowBoxes.length - 1);
        const centerW = Math.max(0, ...rowBoxes.map((r) => r.w));
        return { left, right, rows: rowBoxes, centerW, centerH, cut,
                 h: Math.max(left.h, right.h, centerH),
                 w: 2 * margin + centerW + (left.w ? left.w + gap : 0) + (right.w ? right.w + gap : 0) };
    };

    // the bars as wide as the tape lets them be (down to one dot), then everything smaller until it fits
    if (bars) {
        while (module > 1 && (barsModules * module > barsMax || layoutAt(1).w > limit)) {
            module -= 1;
        }
        if (barsModules * module > barsMax || layoutAt(1).w > limit) {
            warnings.push("barcode_too_long");
        }
    }
    let scale = 1;
    let plan = layoutAt(scale);
    for (let attempt = 0; attempt < 16; attempt++) {
        const fitsTape = plan.h <= tapeDots - 2;
        if ((fitsTape && !plan.cut && plan.w <= limit) || scale < 0.4) {
            if (!fitsTape) {
                warnings.push("too_tall");
            }
            break;
        }
        scale *= 0.92;
        plan = layoutAt(scale);
    }

    // the canvas
    const width = fixedLen || Math.min(maxLen, Math.max(minLen, Math.ceil(plan.w)));
    canvas.width = width;
    canvas.height = tapeDots;
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, width, tapeDots);
    ctx.fillStyle = "#000";
    ctx.textBaseline = "middle";
    const drawStack = (region, x) => {
        let y = Math.max(0, Math.round((tapeDots - region.h) / 2));
        for (const b of region.boxes) {
            b.draw(x + (region.w - b.w) / 2, y, b.h);
            y += b.h + rowGap;
        }
    };
    if (plan.left.w) {
        drawStack(plan.left, margin);
    }
    if (plan.right.w) {
        drawStack(plan.right, width - margin - plan.right.w);
    }
    const x0 = margin + (plan.left.w ? plan.left.w + gap : 0);
    const x1 = width - margin - (plan.right.w ? plan.right.w + gap : 0);
    let y = Math.max(0, Math.round((tapeDots - plan.centerH) / 2));
    for (const row of plan.rows) {
        let x = Math.round((x0 + x1) / 2 - row.w / 2);
        for (const b of row.boxes) {
            b.draw(x, y, row.h);
            x += b.w + gap;
        }
        y += row.h + rowGap;
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
