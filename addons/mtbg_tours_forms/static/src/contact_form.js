/** @odoo-module **/
/**
 * The newsletter popup's form (the contact forms are Form Designer forms: ./form), and the popups (contact,
 * newsletter) opening from their links with a different background picture each time. A known visitor is not asked
 * for their details again (site rule 9).
 */
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";
// the website chat hides under full-screen layers (a popup): Core's shared helper
import { chatHidden } from "@mtbg_tours_content_blocks/shared/chat";
import { checkEmail, checkName, checkPhone, showPhoneCountry } from "./fields";
import { forgetKnownContact, knownContact } from "./form";

/** The country picked in a mobile field's code picker: {code, name, dial, lengths, img}. */
export function phoneCountry(fieldEl) {
    const option = fieldEl?.querySelector(".mtbg-phone__select")?.selectedOptions[0];
    if (!option) {
        return null;
    }
    return { code: option.value, name: option.dataset.name, dial: option.dataset.dial,
             lengths: option.dataset.lengths.split(",").map(Number), img: option.dataset.img };
}

export class ContactForm extends Interaction {
    static selector = ".mtbg-newsletter-form";
    dynamicContent = {
        _root: { "t-on-submit.prevent": this.onSubmit },
        ".mtbg-phone__select": { "t-on-change": this.onPhoneCountry },
        ".mtbg-contact-form__notme": { "t-on-click.prevent": this.onNotMe },
        ".mtbg-phone__input": { "t-on-input": this.onPhoneInput },
    };

    async willStart() {
        this.known = await knownContact();
    }

    start() {
        if (this.known?.first_name) {
            this.useKnown(true);
        }
        this.onPhoneInput();
    }

    /** The SMS / WhatsApp opt-ins and their fine print only once a mobile number is typed. */
    onPhoneInput() {
        const texting = this.el.querySelector(".mtbg-contact-form__texting");
        if (!texting) {
            return;
        }
        const typed = /\d{3}/.test((this.el.querySelector(".mtbg-phone__input")?.value || "").replace(/\D/g, ""));
        const show = typed || (this.usingKnown && Boolean(this.known?.phone));
        texting.hidden = !show;
        if (!show) {
            texting.querySelectorAll("input[type=checkbox]").forEach((box) => (box.checked = false));
        }
    }

    /** A known visitor: hide their details (kept), greet them with what we have, masked. */
    useKnown(on) {
        this.usingKnown = on;
        const known = this.el.querySelector(".mtbg-contact-form__known");
        known.hidden = !on;
        this.el.querySelector(".mtbg-contact-form__who").hidden = on;
        this.onPhoneInput?.();
        if (on) {
            const reach = [this.known.phone, this.known.email].filter(Boolean).join(" · ");
            known.querySelector(".mtbg-contact-form__hello").textContent =
                _t("Hi %(name)s! We'll reply to %(reach)s.", { name: this.known.first_name, reach });
        }
    }

    onNotMe() {
        this.useKnown(false);
    }

    onPhoneCountry() {
        const field = this.el.querySelector(".mtbg-phone");
        showPhoneCountry(field, phoneCountry(field));
    }

    value(name) {
        return (this.el.querySelector(`[name="${name}"]`)?.value || "").trim();
    }

    checked(name) {
        return Boolean(this.el.querySelector(`[name="${name}"]`)?.checked);
    }

    showError(message, fieldName) {
        const box = this.el.querySelector(".mtbg-contact-form__error");
        box.textContent = message || "";
        box.hidden = !message;
        this.el.querySelectorAll(".is-invalid").forEach((el) => el.classList.remove("is-invalid"));
        if (fieldName) {
            const el = fieldName === "phone"
                ? this.el.querySelector(".mtbg-phone__input") : this.el.querySelector(`[name="${fieldName}"]`);
            el?.classList.add("is-invalid");
            el?.focus();
        }
    }

    get isNewsletter() {
        return true;
    }

    collect() {
        return this.collectNewsletter();
    }

    /** The newsletter: name and email; the mobile only with an SMS / WhatsApp opt-in (and the texting terms). */
    collectNewsletter() {
        const values = {
            sms_optin: this.checked("sms_optin"), whatsapp_optin: this.checked("whatsapp_optin"),
            sms_marketing_optin: this.checked("sms_marketing_optin"), terms: this.checked("terms"),
        };
        const opted = values.sms_optin || values.whatsapp_optin || values.sms_marketing_optin;
        if (this.usingKnown) {
            values.use_known = true;
        } else {
            if (checkName(this.value("name")).error) {
                return { error: _t("Please enter your name"), field: "name" };
            }
            const email = checkEmail(this.value("email"));
            if (email.error) {
                return { error: email.error, field: "email" };
            }
            Object.assign(values, { name: this.value("name"), email: email.value });
            const raw = this.el.querySelector(".mtbg-phone__input").value;
            if (raw.trim() || opted) {
                const country = phoneCountry(this.el.querySelector(".mtbg-phone"));
                const phone = checkPhone(country, raw);
                if (phone.error) {
                    return { error: phone.error, field: "phone" };
                }
                values.phone = phone.value;
                values.phone_country = country?.code || "";  // the contact's country (the latest they chose)
            }
        }
        if (opted && !values.terms) {
            return { error: _t("Please agree to receive text messages"), field: "terms" };
        }
        return { values };
    }

    async onSubmit() {
        const { values, error, field } = this.collect();
        this.showError(error, field);
        if (error || this.sending) {
            return;
        }
        this.sending = true;
        const button = this.el.querySelector(".mtbg-contact-form__send");
        button.disabled = true;
        try {
            const route = this.isNewsletter ? "/mtbg_forms/newsletter" : "/mtbg_forms/contact";
            const result = await this.waitFor(rpc(route, { values, website_hp: this.value("website_hp") }));
            if (!result.ok) {
                const [key, message] = Object.entries(result.errors || {})[0] || [];
                this.showError(message || _t("Something went wrong, please try again."), key);
                return;
            }
            this.el.querySelector(".mtbg-contact-form__body").hidden = true;
            const thanks = this.el.querySelector(".mtbg-contact-form__thanks");
            thanks.querySelector(".mtbg-contact-form__thanks-name").textContent =
                result.first_name ? `, ${result.first_name}` : "";
            thanks.hidden = false;
            forgetKnownContact(); // now they are known
        } catch {
            this.showError(_t("Something went wrong, please try again."));
        } finally {
            this.sending = false;
            button.disabled = false;
        }
    }
}

/**
 * The popups: the newsletter (the footer's "Subscribe to our Newsletter", .signupbutton, #newsletter,
 * data-mtbg-newsletter) and the contact form (#contact, data-mtbg-contact), with the next background picture each
 * time one opens.
 */
const POPUP_TRIGGERS = {
    mtbg_newsletter_popup: '.signupbutton, a[href="#newsletter"], [data-mtbg-newsletter]',
    // on tour pages, the description's "contact us" links open it too
    mtbg_contact_popup: 'a[href="#contact"], a[href="#contact-us"], [data-mtbg-contact], ' +
        '.mtbg-tour-page a[href$="/contactus"], .mtbg-tour-page a[href$="/contact-us"], ' +
        '.mtbg-tour-page a[href*="request-a-call"]',
};

const AUTO_KEY = "mtbg-newsletter-auto-shown";
const AUTO_DELAY = 180000; // 3 minutes, as the original

export class ContactPopup extends Interaction {
    static selector = "#mtbg_contact_popup, #mtbg_newsletter_popup, #mtbg_form_popup";
    dynamicContent = {
        _document: { "t-on-click": this.onDocumentClick, "t-on-mouseout": this.onMouseOut },
        // the website chat (bubble and window) hides while a popup is open (the owner): Website Chat reads the class
        _root: {
            "t-on-show.bs.modal": () => chatHidden(this.el.id || "contact-popup", true),
            "t-on-hidden.bs.modal": () => chatHidden(this.el.id || "contact-popup", false),
        },
    };

    setup() {
        this.backgrounds = (this.el.dataset.backgrounds || "").split(",").filter(Boolean);
        this.last = -1;
        // a popup form (Form Designer > Popup): opens by itself; a newsletter one also from the newsletter links
        this.isFormPopup = this.el.id === "mtbg_form_popup";
        this.isNewsletter = this.el.id === "mtbg_newsletter_popup" || (this.isFormPopup && !!this.el.dataset.newsletter);
        this.trigger = this.isFormPopup ? (this.isNewsletter ? POPUP_TRIGGERS.mtbg_newsletter_popup : null)
            : POPUP_TRIGGERS[this.el.id];
        // its pictures turn (one per opening), else it keeps the first
        this.rotate = !this.isFormPopup || !!this.el.dataset.rotate;
    }

    async willStart() {
        this.known = this.isNewsletter ? await knownContact() : {};
    }

    start() {
        if (this.autoAllowed()) {
            this.waitForTimeout(() => this.openAutomatically(), AUTO_DELAY);
        }
    }

    /** Once a visit; a newsletter popup never for someone already subscribed (we ask once). */
    autoAllowed() {
        if (!(this.isNewsletter || this.el.dataset.auto) || (this.isNewsletter && this.known?.newsletter)) {
            return false;
        }
        try {
            return sessionStorage.getItem(AUTO_KEY) !== "1";
        } catch {
            return false;
        }
    }

    openAutomatically() {
        if (!this.autoAllowed() || document.querySelector(".modal.show")) {
            return;
        }
        try {
            sessionStorage.setItem(AUTO_KEY, "1");
        } catch {
            // storage blocked: it may show again on the next page
        }
        this.open();
    }

    /** Leaving the page on a desktop (the pointer goes off the top): the original "exit intent". */
    onMouseOut(ev) {
        if (!ev.relatedTarget && ev.clientY <= 0 && window.matchMedia("(hover: hover) and (pointer: fine)").matches) {
            this.openAutomatically();
        }
    }

    onDocumentClick(ev) {
        if (!this.trigger || !ev.target.closest?.(this.trigger)) {
            return;
        }
        ev.preventDefault();
        this.open();
    }

    open() {
        const picture = this.el.querySelector(".mtbg-contact-popup__picture");
        if (this.backgrounds.length && this.rotate) {
            let index = Math.floor(Math.random() * this.backgrounds.length);
            if (this.backgrounds.length > 1 && index === this.last) {
                index = (index + 1) % this.backgrounds.length; // never the same picture twice in a row
            }
            this.last = index;
            picture.style.backgroundImage = `url("${this.backgrounds[index]}")`;
        }
        // how it opens (a popup form's animation; the others fly up, as since 2025)
        const animation = this.el.dataset.animation || "fly";
        const box = this.el.querySelector(".modal-content");
        box.classList.remove("mtbg-fly-up", "mtbg-anim-fade", "mtbg-anim-zoom", "mtbg-anim-slide");
        void box.offsetWidth; // restart the entrance
        if (animation !== "none") {
            box.classList.add(animation === "fly" ? "mtbg-fly-up" : `mtbg-anim-${animation}`);
        }
        window.Modal.getOrCreateInstance(this.el).show();
        // how dark the page behind it gets (the popup's setting): the backdrop Bootstrap has just made
        if (this.el.dataset.backdrop) {
            requestAnimationFrame(() => {
                const backdrop = [...document.querySelectorAll(".modal-backdrop")].at(-1);
                backdrop?.style.setProperty("--bs-backdrop-opacity", this.el.dataset.backdrop);
            });
        }
    }
}

/** "Live chat" links (#livechat, data-mtbg-livechat): open the website chat. */
export class LivechatLink extends Interaction {
    static selector = "#wrapwrap";
    dynamicContent = {
        _document: { "t-on-click": this.onDocumentClick },
    };

    onDocumentClick(ev) {
        if (!ev.target.closest?.('a[href="#livechat"], [data-mtbg-livechat]')) {
            return;
        }
        ev.preventDefault();
        if (!openWebsiteChat()) {
            // no chat on this page (switched off, or no operator available): the contact popup instead
            const popup = document.getElementById("mtbg_contact_popup");
            if (popup) {
                window.Modal.getOrCreateInstance(popup).show();
            }
        }
    }
}

/**
 * Open the website chat, wherever it stands (it lives in the chat's own shadow DOM): a chat window already open gets the
 * focus, a folded chat (its bubble) opens, else the chat button starts one. False when the page has no chat at all.
 */
function openWebsiteChat() {
    for (const host of document.querySelectorAll("body > div")) {
        const root = host.shadowRoot;
        if (!root) {
            continue;
        }
        const composer = root.querySelector(".o-mail-ChatWindow .o-mail-Composer-input");
        if (composer) {
            composer.focus();
            return true;
        }
        const bubble = root.querySelector(".o-mail-ChatBubble:not(.o-mail-ChatHub-compact)") ||
            root.querySelector(".o-mail-ChatHub-compact");
        const button = root.querySelector(".o-livechat-LivechatButton");
        const target = bubble || button;
        if (target) {
            target.click();
            return true;
        }
    }
    return false;
}

/** The chat page (/chat, for links in emails): the website chat opens by itself as soon as it is there (it loads after
 * the page); none within a few seconds (no chat, no operator): the contact popup. */
export class ChatPage extends Interaction {
    static selector = ".mtbg-chat-page";

    start() {
        let tries = 0;
        const attempt = () => {
            if (openWebsiteChat()) {
                this.el.querySelector(".mtbg-chat-page__status")?.classList.add("d-none");
                return;
            }
            if (++tries < 16) {
                this.waitForTimeout(attempt, 500);
                return;
            }
            const popup = document.getElementById("mtbg_contact_popup");
            if (popup) {
                window.Modal.getOrCreateInstance(popup).show();
            }
        };
        this.waitForTimeout(attempt, 300);
    }
}

registry.category("public.interactions").add("mtbg_tours_forms.contact_form", ContactForm);
registry.category("public.interactions").add("mtbg_tours_forms.chat_page", ChatPage);
registry.category("public.interactions").add("mtbg_tours_forms.contact_popup", ContactPopup);
registry.category("public.interactions").add("mtbg_tours_forms.livechat_link", LivechatLink);
