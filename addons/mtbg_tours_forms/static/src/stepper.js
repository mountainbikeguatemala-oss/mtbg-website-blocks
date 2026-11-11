/** @odoo-module **/
/**
 * A Form Designer form one step at a time (the form's "One step at a time", and the designer's full preview): the
 * steps' progress on top (each step's number and title: done, current, to come), Back / Next under the form, the
 * form's own buttons (Send, Submit) on the last step. A step its rules hide is skipped; ``refresh`` after the rules
 * run, ``reveal`` to open the step of an element (e.g. the first error); ``check`` (the form's): Next only once the
 * step it leaves passes it.
 */
import { _t } from "@web/core/l10n/translation";

const SECTIONS = ":is(.mtbg-pt__section, .mtbg-form__section)";
const TITLES = ".mtbg-pt__step-title, .mtbg-form__step-title";

export class Stepper {
    /**
     * @param {HTMLElement} form
     * @param {{ last?: string, check?: (section: HTMLElement) => boolean }} options ``last``: what shows on the last
     *     step only (the form's own buttons); ``check``: does this step let the customer go on (it shows why not)?
     */
    constructor(form, { last = "", check = null } = {}) {
        this.form = form;
        this.last = last;
        this.check = check;
        this.index = 0;
        const first = form.querySelector(SECTIONS);
        if (!first) {
            return;
        }
        this.body = first.parentElement;
        this.progress = document.createElement("ol");
        this.progress.className = "mtbg-steps";
        this.progress.setAttribute("aria-label", _t("Steps"));
        this.body.insertBefore(this.progress, first);
        this.nav = document.createElement("div");
        this.nav.className = "mtbg-steps__nav";
        this.nav.innerHTML = `<button type="button" class="btn mtbg-steps__back"></button>` +
            `<button type="button" class="btn mtbg-steps__next"></button>`;
        this.nav.querySelector(".mtbg-steps__back").textContent = `‹ ${_t("Back")}`;
        this.nav.querySelector(".mtbg-steps__next").textContent = `${_t("Next")} ›`;
        this.body.appendChild(this.nav);
        this.nav.querySelector(".mtbg-steps__back").addEventListener("click", () => this.go(this.index - 1));
        this.nav.querySelector(".mtbg-steps__next").addEventListener("click", () => {
            if (!this.check || this.check(this.sections[this.index])) {
                this.go(this.index + 1);
            }
        });
        this.progress.addEventListener("click", (ev) => {
            const item = ev.target.closest("[data-step]");
            if (item && Number(item.dataset.step) < this.index) {
                this.go(Number(item.dataset.step));  // back to a step done
            }
        });
        form.classList.add("mtbg-stepped");
        this.go(0, false);
    }

    get sections() {
        return [...this.form.querySelectorAll(SECTIONS)].filter((s) => !s.hidden);
    }

    /** The steps as the rules show them now (the current one kept where it is). */
    refresh() {
        if (this.body) {
            this.go(Math.min(this.index, this.sections.length - 1), false);
        }
    }

    reveal(el) {
        const section = el?.closest(SECTIONS);
        const index = this.sections.indexOf(section);
        if (this.body && index >= 0 && index !== this.index) {
            this.go(index, false);
        }
    }

    go(index, scroll = true) {
        const sections = this.sections;
        if (!sections.length) {
            return;
        }
        this.index = Math.max(0, Math.min(index, sections.length - 1));
        const lastStep = this.index === sections.length - 1;
        this.form.querySelectorAll(SECTIONS).forEach((s) => s.classList.add("mtbg-steps-off"));
        sections[this.index].classList.remove("mtbg-steps-off");
        if (this.last) {
            this.form.querySelectorAll(this.last).forEach((el) => el.classList.toggle("mtbg-steps-off", !lastStep));
        }
        this.progress.hidden = sections.length < 2;
        this.nav.querySelector(".mtbg-steps__back").hidden = this.index === 0;
        this.nav.querySelector(".mtbg-steps__next").hidden = lastStep;
        this.progress.replaceChildren(...sections.map((section, i) => {
            const item = document.createElement("li");
            item.dataset.step = String(i);
            item.className = i < this.index ? "is-done" : i === this.index ? "is-current" : "";
            if (i === this.index) {
                item.setAttribute("aria-current", "step");
            }
            const dot = document.createElement("span");
            dot.className = "mtbg-steps__dot";
            dot.textContent = String(i + 1);
            const title = document.createElement("span");
            title.className = "mtbg-steps__title";
            title.textContent = section.querySelector(TITLES)?.textContent.trim() || _t("Start");
            item.append(dot, title);
            return item;
        }));
        if (scroll) {
            this.form.scrollIntoView({ block: "start", behavior: "smooth" });
        }
    }
}
