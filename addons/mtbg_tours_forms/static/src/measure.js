/** @odoo-module **/
/**
 * Height, weight and age as people type them (the same rules as mtbg_tours_forms/models/measure.py): height in cm,
 * weight in lb. Each returns {value, flag, error, shown}: flag = we guessed, ask "did you mean ...?";
 * shown = the reading in both units ("178 cm · 5′10″", "165 lb · 75 kg").
 */
const CM_PER_INCH = 2.54;
const LB_PER_KG = 2.20462;
const NUM = "(\\d+(?:[.,]\\d+)?)";

const number = (text) => parseFloat(text.replace(",", "."));
const none = (error) => ({ value: null, flag: false, error, shown: "" });

export function feetInches(cm) {
    const inches = Math.round(cm / CM_PER_INCH);
    return `${Math.floor(inches / 12)}′${inches % 12}″`;
}

function height(cm, flag = false) {
    cm = Math.round(cm);
    if (cm < 120 || cm > 220) {
        return none("height");
    }
    return { value: cm, flag, error: null, shown: `${cm} cm · ${feetInches(cm)}` };
}

function full(re, text) {
    return new RegExp(`^(?:${re})$`).exec(text);
}

export function parseHeight(text) {
    let t = (text || "").trim().toLowerCase()
        .replace(/[’‘′´`]/g, "'").replace(/[”“″]/g, '"').replace(/\s+/g, " ");
    if (!t) {
        return none("height");
    }
    t = t.replace(/feet|foot|pies|pie/g, "ft").replace(/inches|inch|pulgadas|pulgada/g, "in")
        .replace(/ft\./g, "ft").replace(/in\./g, "in");
    let m = full(`(\\d)\\s*(?:'|ft|-| )\\s*(\\d{1,2}(?:[.,]\\d+)?)\\s*(?:"|in|'')?`, t);
    if (m && number(m[2]) < 12) {
        return height((parseInt(m[1]) * 12 + number(m[2])) * CM_PER_INCH);
    }
    if ((m = full(`(\\d(?:[.,]\\d+)?)\\s*(?:'|ft)`, t))) {
        return height(number(m[1]) * 12 * CM_PER_INCH);
    }
    if ((m = full(`${NUM}\\s*(?:in|")`, t))) {
        return height(number(m[1]) * CM_PER_INCH);
    }
    if ((m = full(`${NUM}\\s*cm`, t))) {
        return height(number(m[1]));
    }
    if ((m = full(`${NUM}\\s*(?:m|mts?|metros?|meters?|metres?)`, t))) {
        return height(number(m[1]) * 100);
    }
    if ((m = full(NUM, t))) {
        const n = number(m[1]);
        if (n >= 100 && n <= 230) {
            return height(n);
        }
        if (n >= 1.2 && n <= 2.3) {
            return height(n * 100);
        }
        if (n >= 4 && n < 8 && /[.,]/.test(t)) {
            const [feet, inches] = m[1].replace(",", ".").split(".");
            if (parseInt(inches) < 12) {
                return height((parseInt(feet) * 12 + parseInt(inches)) * CM_PER_INCH, true);
            }
        }
        if (n >= 48 && n <= 90) {
            return height(n * CM_PER_INCH, true);
        }
    }
    return none("height");
}

function weight(lb, flag = false) {
    lb = Math.round(lb);
    if (lb < 30 || lb > 400) {
        return none("weight");
    }
    return { value: lb, flag, error: null, shown: `${lb} lb · ${Math.round(lb / LB_PER_KG)} kg` };
}

export function weightUnitForPhone(phone) {
    return (phone || "").replace(/[^\d+]/g, "").startsWith("+1") ? "lb" : "kg";
}

export function parseWeight(text, defaultUnit = "lb") {
    let t = (text || "").trim().toLowerCase().replace(/~|about|aprox/g, "").trim().replace(/\s+/g, " ");
    if (!t) {
        return none("weight");
    }
    let m = full("(\\d+)\\s*(?:st|stone)s?\\s*(?:(\\d+)\\s*(?:lbs?|pounds?)?)?", t);
    if (m) {
        return weight(parseInt(m[1]) * 14 + parseInt(m[2] || 0));
    }
    m = full(`${NUM}\\s*(?:-|–|to|a)\\s*${NUM}\\s*(lbs?|pounds?|kgs?|kilos?|kilogramos?|libras?)?`, t);
    if (m) {
        const middle = (number(m[1]) + number(m[2])) / 2;
        return parseWeight(m[3] ? `${middle} ${m[3]}` : String(middle), defaultUnit);
    }
    if ((m = full(`${NUM}\\s*(?:lbs?|pounds?|libras?|#)`, t))) {
        return weight(number(m[1]));
    }
    if ((m = full(`${NUM}\\s*(?:kgs?|kilos?|kilogramos?|kilograms?)`, t))) {
        return weight(number(m[1]) * LB_PER_KG);
    }
    if ((m = full(NUM, t))) {
        const n = number(m[1]);
        if (n >= 40 && n <= 140) {
            return weight(defaultUnit === "kg" ? n * LB_PER_KG : n, true);
        }
        if (n > 140 && n <= 400) {
            return weight(n);
        }
    }
    return none("weight");
}

export function parseAge(text) {
    const m = /\d+/.exec(text || "");
    const age = m ? parseInt(m[0]) : 0;
    return age >= 5 && age <= 90 ? { value: age, flag: false, error: null, shown: String(age) } : none("age");
}
