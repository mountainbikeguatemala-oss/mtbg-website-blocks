/** @odoo-module **/
/**
 * Code 128 encoder for shop labels: code set C for runs of 4+ digits (shorter bars), code set B for the rest.
 * encodeCode128(text) -> array of module widths, bar first (bar, space, bar, ...), quiet zones not included.
 */

// bar/space widths of the 107 symbols (value 0..106; 103-105 = Start A/B/C, 106 = Stop)
const PATTERNS = [
    "212222", "222122", "222221", "121223", "121322", "131222", "122213", "122312", "132212", "221213",
    "221312", "231212", "112232", "122132", "122231", "113222", "123122", "123221", "223211", "221132",
    "221231", "213212", "223112", "312131", "311222", "321122", "321221", "312212", "322112", "322211",
    "212123", "212321", "232121", "111323", "131123", "131321", "112313", "132113", "132311", "211313",
    "231113", "231311", "112133", "112331", "132131", "113123", "113321", "133121", "313121", "211331",
    "231131", "213113", "213311", "213131", "311123", "311321", "331121", "312113", "312311", "332111",
    "314111", "221411", "431111", "111224", "111422", "121124", "121421", "141122", "141221", "112214",
    "112412", "122114", "122411", "142112", "142211", "241211", "221114", "413111", "241112", "134111",
    "111242", "121142", "121241", "114212", "124112", "124211", "411212", "421112", "421211", "212141",
    "214121", "412121", "111143", "111341", "131141", "114113", "114311", "411113", "411311", "113141",
    "114131", "311141", "411131", "211412", "211214", "211232", "2331112",
];
export const CODE128_PATTERNS = PATTERNS;

const START_B = 104;
const START_C = 105;
const CODE_B = 100; // switch to B while in C
const CODE_C = 99; // switch to C while in B
const STOP = 106;

function digitRun(text, at) {
    let n = 0;
    while (at + n < text.length && text[at + n] >= "0" && text[at + n] <= "9") {
        n++;
    }
    return n;
}

/** Symbol values (start ... data ... checksum stop) for the text; throws on characters outside ASCII 32-126. */
export function code128Values(text) {
    text = String(text || "");
    if (!text) {
        throw new Error("Empty barcode");
    }
    for (const ch of text) {
        const c = ch.charCodeAt(0);
        if (c < 32 || c > 126) {
            throw new Error(`Character not allowed in a barcode: "${ch}"`);
        }
    }
    const values = [];
    let set = null;
    let i = 0;
    while (i < text.length) {
        const run = digitRun(text, i);
        // set C pays off for 4+ digits (or 2+ when the whole code is digits); keep an even count
        const useC = run >= 4 || (run >= 2 && run === text.length);
        if (useC) {
            const len = run - (run % 2);
            if (set === null) {
                values.push(START_C);
            } else if (set !== "C") {
                values.push(CODE_C);
            }
            set = "C";
            for (let k = 0; k < len; k += 2) {
                values.push(Number(text.slice(i + k, i + k + 2)));
            }
            i += len;
        } else {
            if (set === null) {
                values.push(START_B);
            } else if (set !== "B") {
                values.push(CODE_B);
            }
            set = "B";
            values.push(text.charCodeAt(i) - 32);
            i += 1;
        }
    }
    let sum = values[0];
    for (let k = 1; k < values.length; k++) {
        sum += values[k] * k;
    }
    values.push(sum % 103, STOP);
    return values;
}

/** Module widths (bar, space, bar, ...) of the whole symbol. */
export function encodeCode128(text) {
    const widths = [];
    for (const v of code128Values(text)) {
        for (const d of PATTERNS[v]) {
            widths.push(Number(d));
        }
    }
    return widths;
}
