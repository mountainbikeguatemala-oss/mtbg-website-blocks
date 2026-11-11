/**
 * The Forms page (the Forms extension's tile): one editor for every form of the site. Extensions that add a type of
 * form add their own tabs to it, shown when one of their forms is open (registry ``mtbg_form_designer_extensions``:
 * {handler, createStore(env), tabs: [{key, label, icon, Component}]}; each tab gets ``store``, ``panel`` (its key),
 * ``formId`` and ``lang``; the store keeps the extension's data and edits, saved / discarded with the designer's
 * Save / Discard: store.state.dirty, store.save() (false: not saved), store.discard(), store.refresh()). E.g. Pre-tour
 * Forms & Waivers: Who gets it, Waivers, Riders' forms.
 *
 * The Form Designer: a website form's blocks in order (drag and drop; "+" between
 * blocks adds a field, a heading, a text or a numbered step right there), each block's texts in the language picked
 * in the top bar, its width, and when it shows / is required (rules on the other answers and the visit); the form's
 * look per variant (Style) and its thank-you texts (Messages); with a live preview of the unsaved form.
 */
import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const BLOCK_TEXTS = ["label", "placeholder", "help", "content", "choices"];
const FORM_TEXTS = ["name", "thanks_title", "thanks_text", "header_title", "header_subtitle", "popup_bar_text"];
const MAX_LOGO_KB = 1024;
const PREVIEW_DELAY = 250;
const KIND_ICONS = {
    text: "fa-font", textarea: "fa-align-left", email: "fa-envelope-o", phone: "fa-mobile", number: "fa-hashtag",
    date: "fa-calendar", select: "fa-caret-square-o-down", radio: "fa-dot-circle-o", checkboxes: "fa-check-square-o",
    checkbox: "fa-check-square", step: "fa-list-ol", heading: "fa-header", html: "fa-paragraph",
    known: "fa-user-circle-o", texting: "fa-commenting-o", submit: "fa-paper-plane",
};
// what a new block of each kind starts with
const NEW_LABELS = {
    step: "New step", heading: "New heading", html: "", text: "New question", textarea: "Your answer",
    email: "Email", phone: "Mobile", number: "How many?", date: "Date", select: "Choose one",
    radio: "Choose one", checkboxes: "Choose any", checkbox: "I agree",
};
const CHOICE_KINDS = ["select", "radio", "checkboxes"];
const COLOR_TOKENS = ["bg", "text", "label", "accent", "accent_text", "input_bg", "input_text", "input_border", "step"];
const COLOR = /^#[0-9a-fA-F]{6}$/;
// the backgrounds that may also be "transparent" (a form on a coloured place, e.g. inside the phone menu)
const TRANSPARENT_TOKENS = ["bg", "input_bg"];

function slug(text) {
    return (text || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
        .replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 30) || "field";
}

export class FormDesigner extends Component {
    static template = "mtbg_tours_forms.FormDesigner";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.frame = useRef("frame");
        this.walkFrame = useRef("walkFrame");
        this.stage = useRef("stage");
        this.logoInput = useRef("logoInput");
        this.popupInput = useRef("popupInput");
        this.state = useState({
            data: null, blocks: [], texts: {}, style: {}, headerLook: {}, popup: { on: false, newsletter: false, settings: {} }, dirty: false, saving: false, lang: null, tab: "blocks",
            open: null, adding: null, dragging: null, armed: null, variant: "page", styleVariant: "page",
            known: false, device: "desktop", frameKey: 1, scale: 1, stageHeight: 600, logo: "", facts: {},
            showAll: false, walk: null, lookPart: {}, dark: false, currency: "base",
        });
        this.newId = 0;
        this.previewTimer = null;
        this.previewSeq = 0;
        // opened for one form (e.g. from the Pre-tour Forms & Waivers page): {form_id, handler}
        this.params = this.props.action?.params || {};
        // the extensions' tabs, each extension with the store of its data and edits
        this.extensions = registry.category("mtbg_form_designer_extensions").getEntries().map(([key, ext]) => {
            const store = ext.createStore ? ext.createStore(this.env) : null;
            return { key, ...ext, store, state: store ? useState(store.state) : null };
        });
        onWillStart(() => this.load(null, this.params.form_id || null));
        onMounted(() => {
            this.resizer = new ResizeObserver(() => this.fitPreview());
            if (this.stage.el) {
                this.resizer.observe(this.stage.el);
            }
            this.fitPreview();
        });
        onWillUnmount(() => {
            this.resizer?.disconnect();
            clearTimeout(this.previewTimer);
        });
    }

    async load(page = null, formId = null) {
        const data = page || (await this.orm.call("mtbg.form.designer", "mtbg_get_page", [formId, this.params.handler || null]));
        this.state.data = data;
        const form = data.form || { texts: {}, style: {}, variants: ["page"] };
        const formTexts = [...FORM_TEXTS, ...(form.extra_texts || []).map((t) => t.name)];
        this.state.texts = Object.fromEntries(formTexts.map((f) => [f, { ...(form.texts[f] || {}) }]));
        this.state.style = JSON.parse(JSON.stringify(form.style || {}));
        this.state.logo = form.logo || "";
        this.state.stepByStep = Boolean(form.step_by_step);
        this.state.headerLook = { ...(form.header_look || {}) };
        this.state.popup = { on: Boolean(form.popup), newsletter: Boolean(form.newsletter),
                             settings: JSON.parse(JSON.stringify(form.popup_settings || {})) };  // a data URL (as saved), a new upload (base64) or false (removed)
        this.state.blocks = data.blocks.map((b) => ({
            ...b, uid: String(b.id), texts: Object.fromEntries(BLOCK_TEXTS.map((f) => [f, { ...(b.texts[f] || {}) }])),
            show_rule: { match: b.show_rule.match || "all", conditions: [...(b.show_rule.conditions || [])] },
            require_rule: { match: b.require_rule.match || "all", conditions: [...(b.require_rule.conditions || [])] },
            look: JSON.parse(JSON.stringify(b.look || {})),
        }));
        this.state.dirty = false;
        // an extension's tab only for that extension's forms
        if (this.state.tab.includes(":") && !this.extTabs.some((tab) => tab.id === this.state.tab)) {
            this.state.tab = "blocks";
        }
        if (!form.variants.includes(this.state.variant)) {
            this.state.variant = form.variants[0];
        }
        if (!form.variants.includes(this.state.styleVariant)) {
            this.state.styleVariant = form.variants[0];
        }
        if (!this.state.lang || !data.langs.some((l) => l.code === this.state.lang)) {
            this.state.lang = data.langs[0]?.code;
        }
        // the preview's facts (the booker's form, a tour page...): each one's default, until switched
        const facts = {};
        for (const subject of this.previewFactSubjects) {
            facts[subject.key] = subject.key in this.state.facts ? this.state.facts[subject.key] : Boolean(subject.preview);
        }
        this.state.facts = facts;
    }

    /** The yes / no facts the preview can be switched to (not the known visitor: its own switch). */
    get previewFactSubjects() {
        return (this.state.data?.form?.visit_subjects || []).filter(
            (s) => s.ops === "bool" && !["known", "known_phone"].includes(s.key));
    }

    setFact(key, value) {
        this.state.facts[key] = value;
        this.reloadPreview();
    }

    setStepByStep(value) {
        this.state.stepByStep = value;
        this.changed();
    }

    setShowAll(value) {
        this.state.showAll = value;
        this.reloadPreview();
    }

    // ------------------------------------------------------------------
    // What the page shows
    // ------------------------------------------------------------------
    get form() {
        return this.state.data.form;
    }

    get mainLang() {
        return this.state.data.langs[0]?.code;
    }

    get langInfo() {
        return this.state.data.langs.find((l) => l.code === this.state.lang) || this.state.data.langs[0];
    }

    get isTranslating() {
        return this.state.lang !== this.mainLang;
    }

    get variants() {
        const labels = { page: _t("Page"), popup: _t("Popup"), sidebar: _t("Tour sidebar"), menu: _t("Phone menu"), pretour: _t("Pre-tour form") };
        return (this.form?.variants || ["page"]).map((key) => ({ key, label: labels[key] || key }));
    }

    kindOf(key) {
        return this.state.data.kinds.find((k) => k.key === key) || { key, label: key };
    }

    isField(block) {
        return this.kindOf(block.kind).field;
    }

    icon(block) {
        return this.kindIcon(block.kind);
    }

    kindIcon(kind) {
        return KIND_ICONS[kind] || "fa-square-o";
    }

    get addGroups() {
        const kinds = this.state.data.kinds;
        return [
            { label: _t("Layout"), kinds: kinds.filter((k) => ["step", "heading", "html"].includes(k.key)) },
            { label: _t("Fields"), kinds: kinds.filter((k) => k.field) },
        ];
    }

    /** The blocks as the list shows them: each with its step number and whether it sits in a step. */
    get rows() {
        let step = 0;
        let inStep = false;
        return this.state.blocks.map((block, index) => {
            if (block.kind === "step") {
                step += 1;
                inStep = true;
                return { block, index, number: step, inStep: false };
            }
            return { block, index, inStep };
        });
    }

    text(item, field, texts = item.texts) {
        return texts[field]?.[this.state.lang] || "";
    }

    placeholderOf(item, field, texts = item.texts) {
        const main = texts[field]?.[this.mainLang];
        return this.isTranslating && main ? main : "";
    }

    title(block) {
        const texts = block.texts;
        const label = texts.label?.[this.state.lang] || texts.label?.[this.mainLang];
        if (label) {
            return label;
        }
        if (block.kind === "html") {
            const html = texts.content?.[this.state.lang] || texts.content?.[this.mainLang] || "";
            return html.replace(/<[^>]+>/g, " ").trim().slice(0, 60) || this.kindOf(block.kind).label;
        }
        return this.kindOf(block.kind).label;
    }

    /** The answers a rule can look at: the other fields, and the form's own answers: [{key, label, kind, choices}]. */
    fieldSubjects(except) {
        const own = (this.form?.known_answers || []).map((a) => ({ ...a, key: `field:${a.key}` }));
        return [...this.state.blocks.filter((b) => b !== except && this.isField(b) && b.key).map((b) => ({
            key: `field:${b.key}`, label: `${this.title(b)} (${b.key})`, kind: b.kind,
            choices: (b.texts.choices?.[this.mainLang] || "").split("\n").map((c) => c.trim()).filter(Boolean),
        })), ...own];
    }

    /** The facts of the visit this form type knows (a known visitor, the page variant, the booker...). */
    get visitSubjects() {
        return this.form?.visit_subjects || [];
    }

    opsFor(subject, block) {
        const visit = this.visitSubjects.find((s) => s.key === subject);
        if (visit) {
            return visit.ops === "bool"
                ? [{ key: "yes", label: _t("is true") }, { key: "no", label: _t("is not") }]
                : [{ key: "is", label: _t("is") }, { key: "is_not", label: _t("is not") }];
        }
        const field = this.fieldSubjects(block).find((f) => f.key === subject);
        if (!field) {
            return [];
        }
        if (["checkbox"].includes(field.kind)) {
            return [{ key: "checked", label: _t("is ticked") }, { key: "unchecked", label: _t("is not ticked") }];
        }
        const ops = [
            { key: "filled", label: _t("is filled in") }, { key: "empty", label: _t("is empty") },
            { key: "is", label: _t("is") }, { key: "is_not", label: _t("is not") },
        ];
        if (["text", "textarea", "email"].includes(field.kind)) {
            ops.push({ key: "contains", label: _t("contains") });
        }
        if (field.kind === "phone") {
            ops.push({ key: "min_digits", label: _t("has at least … digits") });
        }
        if (field.kind === "number") {
            ops.push({ key: "gte", label: _t("is at least") }, { key: "lte", label: _t("is at most") });
        }
        if (field.kind === "checkboxes") {
            return [{ key: "checked", label: _t("has any ticked") }, { key: "unchecked", label: _t("has none ticked") },
                    { key: "is", label: _t("includes") }, { key: "is_not", label: _t("does not include") }];
        }
        return ops;
    }

    needsValue(op) {
        return !["filled", "empty", "checked", "unchecked", "yes", "no"].includes(op);
    }

    /** The values a condition can pick from (a choice field, the variants, the languages), or null: typed. */
    valueChoices(condition, block) {
        const visit = this.visitSubjects.find((s) => s.key === condition.subject);
        if (visit?.ops === "variant") {
            return this.variants.map((v) => ({ key: v.key, label: v.label }));
        }
        if (visit?.ops === "lang") {
            return this.state.data.langs.map((l) => ({ key: l.code, label: l.name }));
        }
        if (visit?.choices) {
            return visit.choices;
        }
        const field = this.fieldSubjects(block).find((f) => f.key === condition.subject);
        if (field && CHOICE_KINDS.includes(field.kind)) {
            // (a form's own answers come with {key, label} choices)
            return field.choices.map((c) => (typeof c === "string" ? { key: c, label: c } : c));
        }
        return null;
    }

    /** A short summary of when a block shows / is required (its row's badge). */
    ruleBadge(block) {
        const badges = [];
        if (block.show_mode !== "always") {
            badges.push(block.show_mode === "when" ? _t("Shows when…") : _t("Hidden when…"));
        }
        if (this.isField(block)) {
            badges.push({ always: _t("Required"), never: "", when: _t("Required when…"), unless: _t("Required unless…") }[block.require_mode]);
        }
        return badges.filter(Boolean);
    }

    // ------------------------------------------------------------------
    // Edits
    // ------------------------------------------------------------------
    changed() {
        this.state.dirty = true;
        this.schedulePreview();
    }

    setText(item, field, value, texts = item.texts) {
        texts[field] ||= {};
        texts[field][this.state.lang] = value;
        this.changed();
    }

    setField(item, key, value) {
        item[key] = value;
        this.changed();
    }

    // a block's text: its colour is the light pages' or the dark pages' (the preview's light / dark switch says which)
    get textColorKey() {
        return this.state.dark ? "text_color_dark" : "text_color";
    }

    blockColor(block) {
        return block[this.textColorKey] || "";
    }

    setBlockColor(block, value) {
        value = (value || "").trim();
        if (value && !value.startsWith("#")) {
            value = `#${value}`;
        }
        if (!value || COLOR.test(value)) {
            this.setField(block, this.textColorKey, value);
        }
    }

    /** Blocks with text of their own to size and colour (not the button, the opt-ins' consent or the greeting). */
    hasTextLook(block) {
        return !["submit", "known"].includes(block.kind);
    }

    /** The header's title (Messages tab): its level, size, colour (per page look), bold, uppercase, alignment. */
    setHeaderLook(key, value) {
        if (key === "color") {
            key = this.state.dark ? "color_dark" : "color";
        }
        this.state.headerLook = { ...this.state.headerLook, [key]: value };
        this.changed();
    }

    // ------------------------------------------------------------------
    // The form as a website popup (Popup tab): its look, pictures, bar, pages; the popups' order
    // ------------------------------------------------------------------
    setPopup(key, value) {
        this.state.popup[key] = value;
        this.changed();
        this.queuePopupPreview();
    }

    setPopupSetting(key, value) {
        this.state.popup.settings = { ...this.state.popup.settings, [key]: value };
        this.changed();
        this.queuePopupPreview();
    }

    /** The popup's look changed: the preview (on the popup) draws it again, a moment after the last change. */
    queuePopupPreview() {
        if (this.state.variant !== "popup") {
            return;
        }
        clearTimeout(this.popupTimer);
        this.popupTimer = setTimeout(() => this.reloadPreview(), 500);
    }

    get popupBackdrop() {
        const value = this.state.popup.settings.backdrop;
        return value === undefined || value === null || value === "" ? 80 : value;
    }

    /** The popup's space between fields: the Style tab's own setting, for the popup look (light pages). */
    get popupGap() {
        return this.state.style.popup?.gap ?? "";
    }

    setPopupGap(value) {
        this.state.style.popup ||= {};
        this.state.style.popup.gap = value;
        this.changed();
        this.queuePopupPreview();
    }

    /** "Preview the popup": the preview shows the form in its popup. */
    previewPopup() {
        if (!this.form.variants.includes("popup")) {
            this.form.variants = [...this.form.variants, "popup"];
        }
        this.setVariant("popup");
    }

    /** A page rule's kinds (include / exclude): ticked or not. */
    togglePopupKind(which, kind) {
        const rule = { kinds: [], words: [], ...(this.state.popup.settings[which] || {}) };
        rule.kinds = rule.kinds.includes(kind) ? rule.kinds.filter((k) => k !== kind) : [...rule.kinds, kind];
        this.setPopupSetting(which, rule);
    }

    setPopupWords(which, value) {
        const rule = { kinds: [], words: [], ...(this.state.popup.settings[which] || {}) };
        rule.words = value.split(",").map((w) => w.trim().toLowerCase()).filter(Boolean);
        this.setPopupSetting(which, rule);
    }

    popupRule(which) {
        return { kinds: [], words: [], ...(this.state.popup.settings[which] || {}) };
    }

    movePopupImage(index, step) {
        const images = [...(this.state.popup.settings.images || [])];
        const to = index + step;
        if (to < 0 || to >= images.length) {
            return;
        }
        [images[index], images[to]] = [images[to], images[index]];
        this.setPopupSetting("images", images);
    }

    removePopupImage(index) {
        this.setPopupSetting("images", (this.state.popup.settings.images || []).filter((_, i) => i !== index));
    }

    pickPopupFile(target) {
        this.popupTarget = target;
        this.popupInput.el?.click();
    }

    async onPopupFileChosen(ev) {
        const file = ev.target.files?.[0];
        ev.target.value = "";
        if (!file) {
            return;
        }
        const data = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result).split(",")[1]);
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
        const url = await this.orm.call("mtbg.form.designer", "mtbg_popup_upload", [file.name, data]);
        if (this.popupTarget === "logo") {
            this.setPopupSetting("logo", url);
        } else {
            this.setPopupSetting("images", [...(this.state.popup.settings.images || []), url]);
        }
    }

    async movePopup(index, step) {
        const ids = this.state.data.popups.map((p) => p.id);
        const to = index + step;
        if (to < 0 || to >= ids.length) {
            return;
        }
        [ids[index], ids[to]] = [ids[to], ids[index]];
        this.state.data.popups = await this.orm.call("mtbg.form.designer", "mtbg_popups_order", [ids]);
    }

    /** A step's title style: bold, uppercase, alignment. */
    setStepStyle(block, key, value) {
        this.setField(block, { bold: "text_bold", upper: "text_upper", align: "text_align" }[key], value);
    }

    get headerColor() {
        return this.state.headerLook[this.state.dark ? "color_dark" : "color"] || "";
    }

    setKey(block, value) {
        block.key = slug(value);
        this.changed();
    }

    toggleOpen(block) {
        this.state.open = this.state.open === block.uid ? null : block.uid;
        this.state.adding = null;
    }

    alwaysOn(block) {
        return Boolean(this.kindOf(block.kind).always_on);
    }

    toggleActive(block) {
        if (this.alwaysOn(block)) {
            return;
        }
        block.active = !block.active;
        this.changed();
    }

    /** "+" between blocks: the palette opens there (index: the new block's place). */
    openAdd(index) {
        this.state.adding = this.state.adding === index ? null : index;
    }

    uniqueKey(base) {
        const keys = new Set(this.state.blocks.map((b) => b.key));
        let key = base;
        let n = 2;
        while (keys.has(key)) {
            key = `${base}_${n++}`;
        }
        return key;
    }

    addBlock(kind, index) {
        this.newId++;
        const label = NEW_LABELS[kind] ?? "";
        const isField = this.kindOf(kind).field;
        const texts = Object.fromEntries(BLOCK_TEXTS.map((f) => [f, {}]));
        if (label) {
            texts.label[this.mainLang] = label;
        }
        if (kind === "html") {
            texts.content[this.mainLang] = `<p>${_t("Some text for your visitors.")}</p>`;
        }
        if (CHOICE_KINDS.includes(kind)) {
            texts.choices[this.mainLang] = [_t("Option 1"), _t("Option 2")].join("\n");
        }
        const block = {
            id: `new_${this.newId}`, uid: `new_${this.newId}`, kind, key: isField ? this.uniqueKey(slug(label)) : "",
            width: "full", system: false, active: true, show_mode: "always", show_rule: { match: "all", conditions: [] },
            require_mode: "never", require_rule: { match: "all", conditions: [] }, texts,
            text_size: 0, text_color: "", text_color_dark: "", heading_level: "h3",
        };
        const blocks = [...this.state.blocks];
        blocks.splice(index, 0, block);
        this.state.blocks = blocks;
        this.state.adding = null;
        this.state.open = block.uid;
        this.changed();
    }

    remove(block) {
        if (block.system) {
            return;
        }
        this.state.blocks = this.state.blocks.filter((b) => b !== block);
        this.changed();
    }

    // rules
    setMode(block, which, mode) {
        block[`${which}_mode`] = mode;
        const rule = block[`${which}_rule`];
        if (["when", "unless"].includes(mode) && !rule.conditions.length) {
            this.addCondition(block, which);
            return;
        }
        this.changed();
    }

    addCondition(block, which) {
        const field = this.fieldSubjects(block)[0];
        const subject = field ? field.key : "known";
        block[`${which}_rule`].conditions.push({ subject, op: this.opsFor(subject, block)[0]?.key || "is", value: "" });
        this.changed();
    }

    setCondition(block, condition, key, value) {
        condition[key] = value;
        if (key === "subject") {
            condition.op = this.opsFor(value, block)[0]?.key || "is";
            condition.value = this.valueChoices(condition, block)?.[0]?.key || "";
        }
        this.changed();
    }

    removeCondition(block, which, condition) {
        const rule = block[`${which}_rule`];
        rule.conditions = rule.conditions.filter((c) => c !== condition);
        this.changed();
    }

    // a block's own look (a form type's block with settings, e.g. the pre-tour Fitness / Technical cards)
    lookSchema(block) {
        return this.kindOf(block.kind).look || null;
    }

    isLinked(block) {
        return block.look?.linked !== false;
    }

    /** The part edited now (linked: the first; else the one picked). */
    lookPart(block) {
        const parts = this.lookSchema(block).parts;
        return (!this.isLinked(block) && this.state.lookPart[block.uid]) || parts[0].key;
    }

    lookValue(block, field) {
        const part = this.lookPart(block);
        const own = block.look?.parts?.[part]?.[field.key];
        return own ?? this.lookSchema(block).defaults?.[part]?.[field.key] ?? field.default;
    }

    setLook(block, field, value) {
        const schema = this.lookSchema(block);
        block.look = { linked: this.isLinked(block), parts: { ...(block.look?.parts || {}) } };
        const parts = this.isLinked(block) ? schema.parts.map((p) => p.key) : [this.lookPart(block)];
        for (const part of parts) {
            block.look.parts[part] = { ...(block.look.parts[part] || {}), [field.key]: value };
        }
        this.changed();
    }

    /** Linked: one look for every part (the part shown goes to the others); not linked: each part its own. */
    toggleLinked(block) {
        const schema = this.lookSchema(block);
        const linked = !this.isLinked(block);
        const current = this.lookPart(block);
        const values = Object.fromEntries(schema.fields.map((f) => [f.key, this.lookValue(block, f)]));
        block.look = { linked, parts: { ...(block.look?.parts || {}) } };
        if (linked) {
            for (const part of schema.parts) {
                block.look.parts[part.key] = { ...values };
            }
        } else {
            this.state.lookPart[block.uid] = current;
        }
        this.changed();
    }

    setLookPart(block, part) {
        this.state.lookPart[block.uid] = part;
    }

    resetLook(block) {
        block.look = { linked: true, parts: {} };
        this.changed();
    }

    // the header's logo (forms with a header of their own)
    get logoSrc() {
        const logo = this.state.logo;
        if (!logo) {
            return "";
        }
        return logo.startsWith("data:") ? logo : `data:image/png;base64,${logo}`;
    }

    pickLogo() {
        this.logoInput.el?.click();
    }

    async onLogoChosen(ev) {
        const file = ev.target.files?.[0];
        ev.target.value = "";
        if (!file) {
            return;
        }
        if (file.size > MAX_LOGO_KB * 1024) {
            this.notification.add(_t("The logo is larger than %s KB.", MAX_LOGO_KB), { type: "danger" });
            return;
        }
        const url = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result));
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
        this.state.logo = url.split(",")[1];
        this.changed();
    }

    removeLogo() {
        this.state.logo = false;
        this.changed();
    }

    // style: a Light and a Dark look per variant (Dark: "<variant>:dark", for dark pages); the preview's page look
    // (light / dark) says which one the Style tab edits
    get styleKey() {
        return this.state.dark ? `${this.state.styleVariant}:dark` : this.state.styleVariant;
    }

    styleOf(token) {
        return this.state.style[this.styleKey]?.[token] ?? "";
    }

    setStyle(token, value) {
        const variant = this.styleKey;
        this.state.style[variant] ||= {};
        if (value === "" || value === null) {
            delete this.state.style[variant][token];
        } else {
            this.state.style[variant][token] = value;
        }
        this.changed();
    }

    /** The colour picker's value: the token's colour (white when it has none, or is "transparent"). */
    colorValue(token) {
        const value = this.styleOf(token);
        return COLOR.test(value) ? value : "#ffffff";
    }

    setColor(token, value) {
        value = (value || "").trim();
        if (value.toLowerCase() === "transparent") {
            if (TRANSPARENT_TOKENS.includes(token)) {
                this.setStyle(token, "transparent");
            }
            return;
        }
        if (value && !value.startsWith("#")) {
            value = `#${value}`;
        }
        if (!value || COLOR.test(value)) {
            this.setStyle(token, value);
        }
    }

    resetStyle() {
        delete this.state.style[this.styleKey];
        this.changed();
    }


    get colorTokens() {
        const labels = {
            bg: _t("Background"), text: _t("Text"), label: _t("Labels and titles"), accent: _t("Button"),
            accent_text: _t("Button text"), input_bg: _t("Field background"), input_text: _t("Field text"),
            input_border: _t("Field border"), step: _t("Step number"),
        };
        return COLOR_TOKENS.map((key) => ({ key, label: labels[key] }));
    }

    get sizeTokens() {
        return [
            { key: "radius", label: _t("Corner radius"), min: 0, max: 24, step: 1, unit: "px", fallback: 6 },
            { key: "gap", label: _t("Space between fields"), min: 0, max: 2, step: 0.1, unit: "rem", fallback: 0.6 },
            { key: "padding", label: _t("Padding"), min: 0, max: 40, step: 2, unit: "px", fallback: 0 },
            { key: "font_scale", label: _t("Text size"), min: 80, max: 130, step: 5, unit: "%", fallback: 100 },
        ];
    }

    // ------------------------------------------------------------------
    // Order: drag a block by its grip (or focus the grip and use the arrow keys)
    // ------------------------------------------------------------------
    arm(block) {
        this.state.armed = block.uid;
    }

    disarm() {
        if (!this.state.dragging) {
            this.state.armed = null;
        }
    }

    onDragStart(ev, block) {
        this.state.dragging = block.uid;
        this.state.adding = null;
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", block.uid);
    }

    onDragOver(ev, block) {
        const dragged = this.state.blocks.find((b) => b.uid === this.state.dragging);
        if (!dragged) {
            return;
        }
        ev.preventDefault();
        if (dragged === block) {
            return;
        }
        const rect = ev.currentTarget.getBoundingClientRect();
        this.moveTo(dragged, block, ev.clientY > rect.top + rect.height / 2);
    }

    onDragEnd() {
        this.state.dragging = null;
        this.state.armed = null;
    }

    moveTo(dragged, target, after) {
        const order = this.state.blocks.filter((b) => b !== dragged);
        order.splice(order.indexOf(target) + (after ? 1 : 0), 0, dragged);
        if (order.map((b) => b.uid).join() !== this.state.blocks.map((b) => b.uid).join()) {
            this.state.blocks = order;
            this.changed();
        }
    }

    onGripKey(ev, block) {
        const step = { ArrowUp: -1, ArrowDown: 1 }[ev.key];
        if (!step) {
            return;
        }
        ev.preventDefault();
        const index = this.state.blocks.indexOf(block) + step;
        if (index < 0 || index >= this.state.blocks.length) {
            return;
        }
        this.moveTo(block, this.state.blocks[index], step > 0);
        const target = ev.currentTarget;
        setTimeout(() => target?.focus());
    }

    // ------------------------------------------------------------------
    // Save / discard / forms
    // ------------------------------------------------------------------
    get payload() {
        return {
            texts: this.state.texts,
            style: this.state.style,
            logo: this.state.logo === "" ? undefined : this.state.logo,
            step_by_step: this.state.stepByStep,
            header_look: this.state.headerLook,
            ...(this.state.data?.form?.is_website ? { popup: this.state.popup.on, newsletter: this.state.popup.newsletter,
                                                      popup_settings: this.state.popup.settings } : {}),
            blocks: this.state.blocks.map((b) => ({
                id: b.id, kind: b.kind, key: b.key, width: b.width, active: b.active, show_mode: b.show_mode,
                show_rule: b.show_rule, require_mode: b.require_mode, require_rule: b.require_rule, texts: b.texts,
                text_size: b.text_size || 0, text_color: b.text_color || "", text_color_dark: b.text_color_dark || "",
                heading_level: b.heading_level || "h3",
                text_bold: Boolean(b.text_bold), text_upper: Boolean(b.text_upper), text_align: b.text_align || "",
                line_height: b.line_height || 0,
                ...(this.lookSchema(b) ? { look: b.look } : {}),
            })),
        };
    }

    /** Unsaved changes: the form's, or an extension tab's (who gets a pre-tour form, the waivers...). */
    get isDirty() {
        return this.state.dirty || this.extensions.some((ext) => ext.state?.dirty);
    }

    /** The open form's extension tabs: [{id, key, label, icon, Component, store}]. */
    get extTabs() {
        return this.extensions.filter((ext) => ext.handler === this.form?.handler).flatMap((ext) =>
            ext.tabs.map((tab) => ({ ...tab, id: `${ext.key}:${tab.key}`, store: ext.store })));
    }

    async save() {
        const unnamed = this.state.dirty && this.state.blocks.find((b) => this.isField(b) && !b.key);
        if (unnamed) {
            this.state.tab = "blocks";
            this.state.open = unnamed.uid;
            this.notification.add(_t("Every field needs a name."), { type: "danger" });
            return;
        }
        this.state.saving = true;
        try {
            if (this.state.dirty) {
                await this.orm.call("mtbg.form.designer", "mtbg_save", [this.form.id, this.payload]);
                this.state.dirty = false;
            }
            for (const ext of this.extensions) {
                if (ext.state?.dirty && !(await ext.store.save())) {
                    return;  // (the extension said why)
                }
            }
            // (the form may be gone: deleted in an extension's tab)
            await this.load(null, this.form?.id);
            this.reloadPreview();
            this.notification.add(_t("Saved."), { type: "success" });
        } finally {
            this.state.saving = false;
        }
    }

    async discard() {
        for (const ext of this.extensions) {
            if (ext.state?.dirty) {
                await ext.store.discard();
            }
        }
        await this.load(null, this.form?.id);
        this.state.open = null;
        this.reloadPreview();
    }

    /** The forms of the list, by type (the website's, then each extension's), each type with its "+ New ...". */
    get formGroups() {
        return this.state.data.form_types.map((type) => ({
            key: type.key, label: type.group, newLabel: type.new_label,
            forms: this.state.data.forms.filter((f) => f.type === type.key),
        }));
    }

    /** The form list: open the form picked, or make a new one of a type (its "+ New ..." entry). */
    async onFormPick(ev) {
        const value = ev.target.value;
        if (!value.startsWith("new:")) {
            return this.switchForm(value);
        }
        ev.target.value = String(this.form?.id || "");  // back on the open form until the new one is made
        if (this.state.dirty) {
            this.notification.add(_t("Save (or discard) your changes first."), { type: "warning" });
            return;
        }
        const kind = value.slice(4);
        const page = await this.orm.call("mtbg.form.designer", "mtbg_new_form", [kind, this.form?.id || null]);
        await this.load(page);
        this.state.open = null;
        this.state.tab = "blocks";
        for (const ext of this.extensions) {
            ext.store?.refresh();  // its tabs know the new form too (a new pre-tour form...)
        }
        this.reloadPreview();
        this.notification.add(kind === "website"
            ? _t("New website form: name it next to the list, change its blocks and save. It shows where its Form " +
                 "block is dropped (website editor > Contact & Forms).")
            : _t("New form: name it next to the list, change its blocks and save; then choose who gets it."),
            { type: "success" });
    }

    async switchForm(id) {
        await this.load(null, parseInt(id));
        this.state.open = null;
        this.reloadPreview();
    }

    setLang(code) {
        this.state.lang = code;
        this.reloadPreview();
    }

    // ------------------------------------------------------------------
    // Preview
    // ------------------------------------------------------------------
    get previewUrl() {
        const lang = this.langInfo ? `/${this.langInfo.url_code}` : "";
        return `${lang}/mtbg_forms/designer/preview?form=${this.form?.id || 0}&variant=${this.state.variant}` +
            `&known=${this.state.known ? 1 : 0}&facts=${encodeURIComponent(JSON.stringify(this.state.facts))}` +
            `&all=${this.state.showAll ? 1 : 0}&v=${this.state.frameKey}` + this.popupPreviewParam;
    }

    /** A popup form previewed as its popup: its unsaved popup settings (pictures, overlay, logo, dark bar). */
    get popupPreviewParam() {
        if (this.state.variant !== "popup" || !this.form?.is_website || !this.state.popup.on) {
            return "";
        }
        const barText = this.text(null, "popup_bar_text", this.state.texts) || "";
        return `&popup=${encodeURIComponent(JSON.stringify({ ...this.state.popup.settings, on: true, bar_text: barText }))}`;
    }

    get frameStyle() {
        if (this.state.device === "mobile") {
            return "";
        }
        const s = this.state.scale;
        return `width: 1100px; height: ${Math.round(this.state.stageHeight / s)}px; transform: scale(${s});`;
    }

    fitPreview() {
        const el = this.stage.el;
        if (!el) {
            return;
        }
        this.state.scale = Math.min(1, el.clientWidth / 1100) || 1;
        this.state.stageHeight = el.clientHeight || 600;
    }

    reloadPreview() {
        this.state.frameKey++;
    }

    setVariant(variant) {
        this.state.variant = variant;
        this.state.styleVariant = variant;
        this.reloadPreview();
    }

    setKnown(known) {
        this.state.known = known;
        this.reloadPreview();
    }

    /** The preview's page look: light / dark (the site's dark page look) or currency (base / alt). */
    setPreviewLook(key, value) {
        this.state[key] = value;
        this.applyLook(this.frame);
        this.applyLook(this.walkFrame);
    }

    /** Put the page look and the currency in a preview (same site: its document is reachable). */
    applyLook(frame) {
        const doc = frame.el?.contentDocument;
        const wrap = doc?.getElementById("wrap");
        if (!wrap) {
            return;
        }
        wrap.classList.add("mtbg-tour-page");
        wrap.classList.toggle("mtbg-theme-dark", this.state.dark);
        wrap.classList.toggle("mtbg-theme-light", !this.state.dark);
        doc.dispatchEvent(new CustomEvent("mtbg_currency", { detail: { alt: this.state.currency === "alt" } }));
    }

    setDevice(device) {
        this.state.device = device;
        setTimeout(() => this.fitPreview());
    }

    schedulePreview() {
        clearTimeout(this.previewTimer);
        this.previewTimer = setTimeout(() => this.refreshPreview(), PREVIEW_DELAY);
    }

    async refreshPreview() {
        const seq = ++this.previewSeq;
        let html;
        try {
            html = await this.orm.call("mtbg.form.designer", "mtbg_preview",
                [this.form.id, this.payload, this.state.variant, this.state.lang, this.state.known, 0, this.state.facts,
                 this.state.showAll]);
        } catch {
            return; // e.g. a field without a name yet: the preview waits for a valid form
        }
        if (seq === this.previewSeq) {
            this.push({ html });
        }
    }

    push(detail, frame = this.frame) {
        const win = frame.el?.contentWindow;
        if (!win) {
            return;
        }
        win.mtbgFormPreview = detail;
        win.document.dispatchEvent(new CustomEvent("mtbg_form_preview", { detail }));
    }

    onFrameLoad() {
        this.applyLook(this.frame);
        if (this.state.dirty) {
            this.refreshPreview();
        }
        // a click on a block of the preview opens it here
        const doc = this.frame.el?.contentDocument;
        if (doc) {
            doc.body.classList.add("mtbg-designer-pick");
            doc.addEventListener("click", (ev) => this.onPreviewClick(ev), true);
        }
    }

    /** The block clicked in the preview, opened in the list (its index: the block's place in the form). */
    onPreviewClick(ev) {
        const el = ev.target.closest?.("[data-block]");
        if (!el || ev.target.closest("input, select, textarea, button, a, canvas, label")) {
            return;  // the fields work as on the website (the rules react as you type)
        }
        const block = this.state.blocks.filter((b) => b.active)[Number(el.dataset.block)];
        if (!block) {
            return;
        }
        ev.preventDefault();
        this.state.tab = "blocks";
        this.state.open = block.uid;
        this.state.adding = null;
        el.ownerDocument.querySelectorAll(".mtbg-designer-picked").forEach((x) => x.classList.remove("mtbg-designer-picked"));
        el.classList.add("mtbg-designer-picked");
        setTimeout(() => document.querySelector(".mtbg_fd_row.is-open")?.scrollIntoView({ block: "center", behavior: "smooth" }));
    }

    // ------------------------------------------------------------------
    // Full preview: the form as a customer goes through it, one step at a time (the steps' progress on top, Back /
    // Next under the form: stepper.js), a made-up answer in every field
    // ------------------------------------------------------------------
    get walkUrl() {
        return this.previewUrl.replace(/&all=\d/, "&all=0") + "&sample=1&walk=1";
    }

    openWalk() {
        this.state.walk = { device: this.state.device };
    }

    closeWalk() {
        this.state.walk = null;
    }

    onWalkKey(ev) {
        if (ev.key === "Escape") {
            this.closeWalk();
        }
    }

    setWalkDevice(device) {
        this.state.walk.device = device;
    }

    async onWalkLoad() {
        this.applyLook(this.walkFrame);
        const doc = this.walkFrame.el?.contentDocument;
        if (!doc || !this.state.walk) {
            return;
        }
        doc.addEventListener("keydown", (ev) => this.onWalkKey(ev));
        if (this.state.dirty) {
            try {
                const html = await this.orm.call("mtbg.form.designer", "mtbg_preview",
                    [this.form.id, this.payload, this.state.variant, this.state.lang, this.state.known, 0,
                     this.state.facts, false, true, true]);
                this.push({ html }, this.walkFrame);
            } catch {
                // (a field without a name yet: the saved form shows)
            }
        }
    }
}

registry.category("actions").add("mtbg_form_designer", FormDesigner);
