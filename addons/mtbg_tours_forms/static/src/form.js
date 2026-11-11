/** @odoo-module **/
/**
 * Form Designer forms on the website (mtbg_tours_forms.form): each block shown and required by its rules as the
 * visitor types, the shared field checks (./fields), a known visitor only answers what we do not know yet (site
 * rule 9), and the answers sent to /mtbg_forms/submit/<form>, where the server checks the same rules again.
 *
 * ``evaluate`` is models/form.py's ``evaluate``: keep them the same.
 */
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";
import { checkEmail, checkName, checkPhone, showPhoneCountry } from "./fields";
import { Stepper } from "./stepper";

const FIELDS = new Set(["text", "textarea", "email", "phone", "number", "date", "select", "radio", "checkboxes", "checkbox"]);
// a known visitor in the designer's preview (never real details)
const PREVIEW_KNOWN = { first_name: "Ana", phone: "•••• 1234", email: "a•••@example.com" };

let knownPromise = null;
export function knownContact() {
    knownPromise ||= rpc("/mtbg_forms/contact/known", {}).catch(() => ({}));
    return knownPromise;
}
export function forgetKnownContact() {
    knownPromise = null;
}

function digits(value) {
    return String(value ?? "").replace(/\D/g, "").length;
}

function number(value) {
    const n = parseFloat(String(value ?? "").replace(",", "."));
    return Number.isNaN(n) ? null : n;
}

function test(condition, answers, ctx) {
    const subject = condition.subject || "";
    const op = condition.op || "";
    const expected = condition.value;
    if (subject.startsWith("field:")) {
        const value = answers[subject.slice(6)];
        const text = Array.isArray(value) ? value.join(" ") : value === undefined || value === null || value === false ? "" : String(value);
        const ticked = value === true || (Array.isArray(value) && value.length > 0);
        switch (op) {
            case "filled": return Boolean(text.trim()) && value !== false;
            case "empty": return !text.trim() || value === false;
            case "checked": return ticked;
            case "unchecked": return !ticked;
            case "is":
            case "is_not": {
                const same = Array.isArray(value)
                    ? value.includes(String(expected))
                    : text.trim().toLowerCase() === String(expected ?? "").trim().toLowerCase();
                return op === "is" ? same : !same;
            }
            case "contains": return text.toLowerCase().includes(String(expected ?? "").toLowerCase());
            case "min_digits": return digits(text) >= (number(expected) || 0);
            case "gte":
            case "lte": {
                const n = number(text);
                const limit = number(expected);
                if (n === null || limit === null) {
                    return false;
                }
                return op === "gte" ? n >= limit : n <= limit;
            }
            default: return false;
        }
    }
    // a fact of the visit (known, known_phone, variant, lang, tour; a form type's own: booker, rental...)
    if (op === "yes" || op === "no") {
        return Boolean(ctx[subject]) === (op === "yes");
    }
    if (op === "is" || op === "is_not") {
        const same = String(ctx[subject] ?? "") === String(expected ?? "");
        return op === "is" ? same : !same;
    }
    return false;
}

/** Does a rule hold for these answers and this visit? An empty rule holds. */
export function evaluate(rule, answers, ctx) {
    const conditions = rule?.conditions || [];
    if (!conditions.length) {
        return true;
    }
    const results = conditions.map((c) => test(c, answers, ctx));
    return rule.match === "any" ? results.some(Boolean) : results.every(Boolean);
}

/** Shown / required by a block's [mode, rule] (always, never, when, unless). */
export function byMode([mode, rule], answers, ctx, fallback) {
    if (mode === "always" || mode === "never" || !mode) {
        return mode ? mode === "always" : fallback;
    }
    const held = evaluate(rule, answers, ctx);
    return mode === "when" ? held : !held;
}

/** The country picked in a mobile field's code picker: {code, name, dial, lengths, img}. */
function phoneCountry(fieldEl) {
    const option = fieldEl?.querySelector(".mtbg-phone__select")?.selectedOptions[0];
    if (!option) {
        return null;
    }
    return { code: option.value, name: option.dataset.name, dial: option.dataset.dial,
             lengths: option.dataset.lengths.split(",").map(Number), img: option.dataset.img };
}

export class MtbgForm extends Interaction {
    static selector = "form.mtbg-form";
    dynamicContent = {
        _root: {
            "t-on-submit.prevent": this.onSubmit,
            "t-on-input": this.apply,
            "t-on-change": this.apply,
        },
        ".mtbg-phone__select": { "t-on-change": this.onPhoneCountry },
        ".mtbg-contact-form__notme": { "t-on-click.prevent": this.onNotMe },
    };

    setup() {
        this.defs = JSON.parse(this.el.dataset.defs || "[]");
        this.els = {};
        for (const el of this.el.querySelectorAll("[data-block]")) {
            this.els[el.dataset.block] = el;
        }
        this.usingKnown = false;
        // the designer's preview: the facts it is switched to (a known visitor, a tour page...)
        const { known, known_phone, ...facts } = JSON.parse(this.el.dataset.previewCtx || "{}");
        this.previewFacts = facts;  // (a known visitor: the preview's switch, then "Not you?")
    }

    async willStart() {
        // the designer's preview: known only when its "Known visitor" switch is on (never the person designing)
        this.known = this.el.dataset.preview ? (this.el.dataset.previewKnown ? PREVIEW_KNOWN : {}) : await knownContact();
    }

    start() {
        if (this.known?.first_name && this.defs.some((d) => d.kind === "known")) {
            this.useKnown(true);
        } else {
            this.apply();
        }
        if (this.el.dataset.steps) {
            this.stepper = new Stepper(this.el);  // one step at a time
        }
    }

    get ctx() {
        return {
            variant: this.el.dataset.source || "page",
            lang: (document.documentElement.lang || "").replace("-", "_"),
            tour: Boolean(this.el.dataset.tourId),
            known: this.usingKnown,
            known_phone: this.usingKnown && Boolean(this.known?.phone),
            ...this.previewFacts,
        };
    }

    /** {key: answer}: text, true / false (a checkbox), [values] (several choices). */
    answers() {
        const answers = {};
        this.defs.forEach((def, index) => {
            if (!FIELDS.has(def.kind) || !def.key) {
                return;
            }
            const el = this.els[index];
            if (!el) {
                return;
            }
            if (def.kind === "phone") {
                answers[def.key] = el.querySelector(".mtbg-phone__input")?.value || "";
            } else if (def.kind === "checkbox") {
                answers[def.key] = Boolean(el.querySelector("input")?.checked);
            } else if (def.kind === "checkboxes") {
                answers[def.key] = [...el.querySelectorAll("input:checked")].map((i) => i.value);
            } else if (def.kind === "radio") {
                answers[def.key] = el.querySelector("input:checked")?.value || "";
            } else {
                answers[def.key] = (el.querySelector("[name]")?.value || "").trim();
            }
        });
        return answers;
    }

    /** Show / hide and mark required every block by its rules (a step hides its whole section). */
    apply() {
        const answers = this.answers();
        const ctx = this.ctx;
        this.state = { shown: {}, required: {} };
        let stepShown = true;
        this.defs.forEach((def, index) => {
            const shown = byMode(def.show, answers, ctx, true);
            const el = this.els[index];
            if (def.kind === "step") {
                stepShown = shown;
            }
            this.state.shown[index] = shown && (def.kind === "step" || stepShown);
            this.state.required[index] = byMode(def.require, answers, ctx, false);
            if (!el) {
                return;
            }
            if (this.el.dataset.showAll) {
                el.classList.toggle("mtbg-rule-off", !shown);  // the designer's preview: shown, marked
            } else if (el.hidden !== !shown) {
                el.hidden = !shown;
                if (!shown) {
                    // hidden choices are not sent: the texting opt-ins untick as before
                    el.querySelectorAll("input[type=checkbox]").forEach((box) => (box.checked = false));
                }
            }
            el.classList.toggle("is-required", this.state.required[index]);
        });
        this.numberSteps();
        this.stepper?.refresh();
    }

    /** The visible steps numbered 1, 2, 3... */
    numberSteps() {
        let n = 0;
        this.defs.forEach((def, index) => {
            if (def.kind === "step" && this.state.shown[index]) {
                const num = this.els[index]?.querySelector(".mtbg-form__step-num");
                if (num) {
                    num.textContent = String(++n);
                }
            }
        });
    }

    /** A known visitor: their details are kept (the rules hide those fields), greeted with what we have, masked. */
    useKnown(on) {
        this.usingKnown = on;
        for (const box of this.el.querySelectorAll(".mtbg-contact-form__known")) {
            box.hidden = !on;
            if (on) {
                const reach = [this.known.phone, this.known.email].filter(Boolean).join(" · ");
                box.querySelector(".mtbg-contact-form__hello").textContent =
                    _t("Hi %(name)s! We'll reply to %(reach)s.", { name: this.known.first_name, reach });
            }
        }
        this.apply();
    }

    onNotMe() {
        this.useKnown(false);
    }

    onPhoneCountry(ev) {
        const field = ev.currentTarget.closest(".mtbg-phone");
        showPhoneCountry(field, phoneCountry(field));
    }

    showError(message, key) {
        const box = this.el.querySelector(".mtbg-contact-form__error");
        if (box) {
            box.textContent = message || "";
            box.hidden = !message;
        }
        this.el.querySelectorAll(".is-invalid").forEach((el) => el.classList.remove("is-invalid"));
        if (key) {
            const block = this.el.querySelector(`.mtbg-form__block[data-key="${key}"]`);
            const input = block?.querySelector(".mtbg-phone__input, [name]");
            this.stepper?.reveal(input);
            input?.classList.add("is-invalid");
            input?.focus();
        }
    }

    /** {values} to send, or {error, key}: the server's checks, in the form's order. */
    collect() {
        this.apply();
        const answers = this.answers();
        const values = {
            source: this.el.dataset.source, tour_id: this.el.dataset.tourId || false,
            use_known: this.usingKnown || undefined,
        };
        for (const [index, def] of this.defs.entries()) {
            if (!FIELDS.has(def.kind) || !def.key || !this.state.shown[index]) {
                continue;
            }
            const required = this.state.required[index];
            let value = answers[def.key];
            const label = def.label || def.key;
            const empty = Array.isArray(value) ? !value.length : value === false || !String(value ?? "").trim();
            if (empty) {
                if (required) {
                    return {
                        key: def.key,
                        error: def.kind === "checkbox" ? _t('Please tick "%s"', label)
                            : ["radio", "select", "checkboxes"].includes(def.kind) ? _t('Please choose "%s"', label)
                                : _t('Please fill in "%s"', label),
                    };
                }
                values[def.key] = value;
                continue;
            }
            if (def.kind === "email") {
                const email = checkEmail(value);
                if (email.error) {
                    return { key: def.key, error: email.error };
                }
                value = email.value;
            } else if (def.kind === "phone") {
                const country = phoneCountry(this.els[index]);
                const phone = checkPhone(country, value);
                if (phone.error) {
                    return { key: def.key, error: phone.error };
                }
                value = phone.value;
                // the country picked with it: the contact's country (the latest they chose)
                values[`${def.key}_country`] = country?.code || "";
            } else if (def.kind === "number" && number(value) === null) {
                return { key: def.key, error: _t('"%s" needs a number', label) };
            }
            values[def.key] = value;
        }
        // the texting opt-ins (SMS, WhatsApp, promotions): each box ticked is sent, with its wording kept by the server
        for (const box of this.el.querySelectorAll(".mtbg-contact-form__texting input[type=checkbox]")) {
            if (box.checked && !box.closest("[hidden]")) {
                values[box.name] = true;
            }
        }
        // a new contact needs a name (one Name field, or first and last together)
        const nameKeys = this.defs.map((d, i) => [d, i]).filter(([d, i]) =>
            ["name", "first_name", "last_name"].includes(d.key) && this.state.shown[i]);
        if (nameKeys.length) {
            const name = checkName(answers.name || [answers.first_name, answers.last_name].filter(Boolean).join(" "));
            if (name.error) {
                return { key: nameKeys.at(-1)[0].key, error: name.error };
            }
        }
        return { values };
    }

    async onSubmit() {
        const { values, error, key } = this.collect();
        this.showError(error, key);
        if (error || this.sending) {
            return;
        }
        this.sending = true;
        const button = this.el.querySelector(".mtbg-contact-form__send");
        if (button) {
            button.disabled = true;
        }
        try {
            const hp = this.el.querySelector('[name="website_hp"]')?.value || "";
            const result = await this.waitFor(rpc(`/mtbg_forms/submit/${this.el.dataset.form}`, { values, website_hp: hp }));
            if (!result.ok) {
                const [errorKey, message] = Object.entries(result.errors || {})[0] || [];
                this.showError(message || _t("Something went wrong, please try again."), errorKey);
                return;
            }
            this.el.querySelector(".mtbg-contact-form__body").hidden = true;
            const thanks = this.el.querySelector(".mtbg-contact-form__thanks");
            const name = thanks.querySelector(".mtbg-contact-form__thanks-name");
            if (name) {
                name.textContent = result.first_name ? `, ${result.first_name}` : "";
            }
            thanks.hidden = false;
            forgetKnownContact(); // now they are known
        } catch {
            this.showError(_t("Something went wrong, please try again."));
        } finally {
            this.sending = false;
            if (button) {
                button.disabled = false;
            }
        }
    }
}

/**
 * The Form Designer's preview (/mtbg_forms/designer/preview): the designer sends the form rendered with its unsaved
 * blocks and look (``mtbg_form_preview`` event, or ``window.mtbgFormPreview`` before this starts).
 */
export class MtbgFormPreview extends Interaction {
    static selector = "[data-mtbg-form-preview]";
    dynamicContent = {
        _document: { "t-on-mtbg_form_preview": (ev) => this.apply(ev.detail) },
    };

    start() {
        if (window.mtbgFormPreview) {
            this.apply(window.mtbgFormPreview);
        }
    }

    apply({ html }) {
        if (html === undefined) {
            return;
        }
        const interactions = this.services["public.interactions"];
        for (const child of [...this.el.children]) {
            interactions.stopInteractions(child);
        }
        this.el.innerHTML = html;
        for (const child of [...this.el.children]) {
            interactions.startInteractions(child);
        }
    }
}

registry.category("public.interactions").add("mtbg_tours_forms.form", MtbgForm);
registry.category("public.interactions").add("mtbg_tours_forms.form_preview", MtbgFormPreview);
