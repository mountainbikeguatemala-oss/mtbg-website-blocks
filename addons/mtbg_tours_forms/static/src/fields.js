/** @odoo-module **/
/**
 * The customer fields every form on the site shares (booking form, website chat, pre-tour form): one way to ask,
 * one way to check. The server checks the same things (mtbg.form.fields). Site rule 9: we ask once.
 *
 * Checks return {value} or {error}. A phone country is {code, name, dial, lengths: [n, ...], img}.
 */
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";

export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** A mobile field shows the country picked: its flag (named for screen readers and search engines) and dial code. */
export function showPhoneCountry(fieldEl, country) {
    const flag = fieldEl.querySelector(".mtbg-phone__flag");
    if (flag) {
        flag.src = country.img;
        flag.alt = country.name || "";
    }
    fieldEl.querySelector(".mtbg-phone__dial").textContent = `+${country.dial}`;
}

/** The country's flag as an emoji. */
export function flag(code) {
    return (code || "").toUpperCase().replace(/./g, (c) => String.fromCodePoint(127397 + c.charCodeAt(0)));
}

/** Today as YYYY-MM-DD (local). */
export function todayIso() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

let pickerPromise = null;
/** The mobile field's countries and the one it opens on: {default, countries: [country...]}. */
export function phonePicker() {
    pickerPromise ||= rpc("/mtbg_forms/phone_picker", {}).then((picker) => ({
        default: picker.default,
        countries: picker.countries.map((c) => ({ ...c, lengths: String(c.lengths).split(",").map(Number) })),
    })).catch(() => {
        pickerPromise = null;
        return { default: "US", countries: [] };
    });
    return pickerPromise;
}

/**
 * The mobile's national digits when their count fits the country (its own +code typed in front and a leading
 * trunk 0 are dropped), else "".
 */
export function nationalNumber(country, raw) {
    raw = (raw || "").trim();
    let digits = raw.replace(/\D/g, "");
    if (/^(\+|00)/.test(raw)) {
        digits = digits.replace(/^00/, "");
        if (!digits.startsWith(country.dial)) {
            return "";
        }
        digits = digits.slice(country.dial.length);
    }
    if (!country.lengths.includes(digits.length) && digits.startsWith("0")) {
        digits = digits.slice(1);
    }
    return country.lengths.includes(digits.length) ? digits : "";
}

export function checkName(text) {
    const name = (text || "").trim().replace(/\s+/g, " ");
    return name.length >= 2 ? { value: name } : { error: _t("Please enter your name") };
}

export function checkEmail(text) {
    const email = (text || "").trim().toLowerCase();
    return EMAIL_RE.test(email) ? { value: email } : { error: _t("Please enter a valid email") };
}

/** {value: "+502 55551234"} for the number typed with the picked country, or {error}. */
export function checkPhone(country, raw) {
    if (!(raw || "").trim()) {
        return { error: _t("Please enter your phone number") };
    }
    if (!country) {
        return { error: _t("Please pick your country") };
    }
    const digits = nationalNumber(country, raw);
    if (!digits) {
        return {
            error: _t("Please enter a valid %(country)s mobile number (%(digits)s digits after +%(dial)s)", {
                country: country.name, digits: country.lengths.join(" / "), dial: country.dial,
            }),
        };
    }
    return { value: `+${country.dial} ${digits}` };
}
