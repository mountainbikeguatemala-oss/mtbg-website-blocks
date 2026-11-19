/** @odoo-module **/
/**
 * Draws a label from its layout (Settings › Label layout: bsx.label.layout) and turns it into printer rows.
 *
 * The label is drawn landscape, 8 dots per mm (203 dpi): width = label length along the tape, height = tape width.
 * Its items (logo, barcode, code, name, price) in rows, each row with a Left, Center and Right, placed with the drag
 * and drop editor (rowsOf: layouts made before it are made from their settings). Everything shrinks together
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
export const SLOTS = ["left", "center", "right"];
const PADS = ["pad_top", "pad_right", "pad_bottom", "pad_left"];

let uidSeq = 0;
export function itemUid() {
    uidSeq += 1;
    return `i${Date.now().toString(36)}${uidSeq}`;
}

export function newRow() {
    return { uid: itemUid(), left: [], center: [], right: [] };
}

/** A new item of a field, with its usual size. */
export function newItem(field, layout = {}) {
    const base = { uid: itemUid(), field, bold: field !== "code" };
    switch (field) {
        case "logo":
            return { ...base, size: layout.logo_height_mm || 8, rotation: layout.logo_rotation || 0,
                     pad_top: 0, pad_right: 0, pad_bottom: 0, pad_left: 0 };
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

const clean = (items) => (Array.isArray(items) ? items : []).filter((i) => i && LABEL_FIELDS.includes(i.field));

/**
 * The layout's rows, top to bottom, each with its Left, Center and Right (items side by side in each). From its saved
 * items (the drag and drop editor; 1.2.0's three regions are read too), else made from its settings (layouts made
 * before the editor: the same label as before).
 */
export function rowsOf(layout) {
    const e = layout.elements;
    if (e && typeof e === "object") {
        if (Array.isArray(e.rows)) {
            const rows = e.rows.map((r) => ({ uid: r.uid || itemUid(), left: clean(r.left), center: clean(r.center),
                                              right: clean(r.right) }));
            if (rows.length) {
                return rows;
            }
        } else if (SLOTS.some((k) => Array.isArray(e[k]) && e[k].length)) {
            // 1.2.0: Left / Center (rows: "inline" joined the one before) / Right, the sides beside every row: one row
            // per center row, the sides in the first one
            const rows = [];
            for (const item of clean(e.center)) {
                if (!rows.length || !item.inline) {
                    rows.push(newRow());
                }
                rows[rows.length - 1].center.push(item);
            }
            if (!rows.length) {
                rows.push(newRow());
            }
            rows[0].left.push(...clean(e.left));
            rows[0].right.push(...clean(e.right));
            return rows;
        }
    }
    // before the editor: from the settings
    const rows = [];
    const logo = newItem("logo", layout);
    const pos = layout.logo_position || "left";
    if (pos === "top") {
        rows.push({ ...newRow(), center: [logo] });
    }
    if (layout.show_barcode) {
        const row = { ...newRow(), center: [newItem("barcode", layout)] };
        if (layout.show_code) {
            const code = newItem("code", layout);
            if (layout.code_position === "right") {
                row.center.push({ ...code, bold: true });
            } else {
                rows.push(row);
                rows.push({ ...newRow(), center: [code] });
            }
        }
        if (!rows.includes(row)) {
            rows.push(row);
        }
    }
    if (layout.show_name || layout.show_price) {
        const row = newRow();
        if (layout.show_name) {
            row.center.push(newItem("name", layout));
        }
        if (layout.show_price) {
            if (layout.show_name && layout.price_position === "right") {
                row.right.push(newItem("price", layout));
            } else if (layout.show_name) {
                rows.push(row);
                rows.push({ ...newRow(), center: [newItem("price", layout)] });
            } else {
                row.center.push(newItem("price", layout));
            }
        }
        if (!rows.includes(row)) {
            rows.push(row);
        }
    }
    if (!rows.length) {
        rows.push(newRow());
    }
    if (pos !== "top") {
        rows[0][pos === "right" ? "right" : "left"].unshift(logo);
    }
    return rows;
}

/**
 * Renders the label. layout: dict from bsx.label.layout.get_print_layout(); product: {name, barcode,
 * default_code, price_display}; assets: prepareLabelAssets(layout) (without: the device's font, no logo).
 * Its rows top to bottom; in each, Left at the label's start, Right at its end, Center in the middle, the items of a
 * slot side by side. Everything shrinks together until it fits the tape, and a name before it is cut.
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
    const rows = rowsOf(L);

    // the barcode's bars (one encoding for every barcode item)
    let bars = null;
    if (rows.some((r) => SLOTS.some((k) => r[k].some((i) => i.field === "barcode")))) {
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
            // its spacing (mm), kept as set: around the picture, inside its box
            const [pt, pr, pb, pl] = PADS.map((k) => Math.max(0, Math.round((Number(item[k]) || 0) * DOTS_PER_MM)));
            const h = Math.max(8, Math.min(tapeDots - 2 - pt - pb, Math.round(size * DOTS_PER_MM * scale)));
            const angle = ((Number(item.rotation) || 0) * Math.PI) / 180;
            const ratio = logo.naturalWidth / logo.naturalHeight;
            const cos = Math.abs(Math.cos(angle));
            const sin = Math.abs(Math.sin(angle));
            const dh = h / (ratio * sin + cos);
            const dw = dh * ratio;
            const w = Math.round(dw * cos + dh * sin);
            return { w: w + pl + pr, h: h + pt + pb, draw: (x, y, rowH) => {
                ctx.save();
                ctx.translate(x + pl + w / 2, y + (rowH - (h + pt + pb)) / 2 + pt + h / 2);
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

    /** Every row at a scale: its slots' boxes (a name gets the room the rest of its row leaves). */
    const layoutAt = (scale) => {
        let cut = false;
        const planned = rows.map((row) => {
            const others = SLOTS.flatMap((k) => row[k]).filter((i) => i.field !== "name").map((i) => box(i, scale))
                .filter(Boolean);
            const used = others.reduce((a, b) => a + b.w, 0) + gap * others.length;
            const room = limit - 2 * margin - used;
            const slots = {};
            for (const k of SLOTS) {
                const boxes = row[k].map((i) => (i.field === "name" ? box(i, scale, room) : box(i, scale))).filter(Boolean);
                cut = cut || boxes.some((b) => b.cut);
                slots[k] = { boxes, w: boxes.reduce((a, b) => a + b.w, 0) + gap * Math.max(0, boxes.length - 1) };
            }
            const all = SLOTS.flatMap((k) => slots[k].boxes);
            const filled = SLOTS.filter((k) => slots[k].boxes.length).length;
            return { slots, h: Math.max(0, ...all.map((b) => b.h)),
                     w: 2 * margin + SLOTS.reduce((a, k) => a + slots[k].w, 0) + gap * Math.max(0, filled - 1) };
        }).filter((r) => r.h > 0);
        const h = planned.reduce((a, r) => a + r.h, 0) + rowGap * Math.max(0, planned.length - 1);
        return { rows: planned, h, w: Math.max(0, ...planned.map((r) => r.w)), cut };
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
    const drawSlot = (slot, x, y, rowH) => {
        for (const b of slot.boxes) {
            b.draw(x, y, rowH);
            x += b.w + gap;
        }
    };
    let y = Math.max(0, Math.round((tapeDots - plan.h) / 2));
    for (const row of plan.rows) {
        const { left, center, right } = row.slots;
        drawSlot(left, margin, y, row.h);
        drawSlot(right, width - margin - right.w, y, row.h);
        // the center in the middle of the label (pushed aside when a side would overlap it)
        let cx = Math.round((width - center.w) / 2);
        if (left.w) {
            cx = Math.max(cx, margin + left.w + gap);
        }
        if (right.w) {
            cx = Math.min(cx, width - margin - right.w - gap - center.w);
        }
        drawSlot(center, cx, y, row.h);
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
