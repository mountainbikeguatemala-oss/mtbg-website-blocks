/**
 * One expense input form for the whole suite (owner, 2026-11-07: "you two should share the same input form for
 * expenses"): the Staff App's phone form and the back office's Add Expense (a departure, a unit, the Expenses page).
 * What it records comes from its target's server side (mtbg.expense.form, models/expense_form.py): the fields, their
 * order, choices, conditions, the values, the save. This component only draws and sends them.
 *
 *   <MtbgExpenseForm target="'staff'" params="{ departure_id: 3 }" onDone="..." onCancel="..."/>
 *
 * or a button returning env['mtbg.expense.form']._mtbg_action(target, params): the client action
 * "mtbg_expense_form" in a dialog.
 *
 * A new expense may start with its receipt (receipt.first, the phone's flow, owner 2026-11-05): a dialog to take or
 * upload the photo, then the details under it; the photo stays on top while they are entered.
 */
import { Component, onMounted, onWillStart, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { readReceipt } from "./receipt";

const MODEL = "mtbg.expense.form";

/** A value as conditions compare it: a typeahead's id, "" for nothing, else its text. */
function norm(value) {
    if (value && typeof value === "object" && "value" in value) {
        value = value.value;
    }
    return value === false || value === null || value === undefined ? "" : String(value);
}

/**
 * A typed number read (owner, 2026-11-15: "if you put a decimal and enter slowly the decimal disappears"): the box
 * keeps exactly what was typed ("12.", "12,5") and it is read only here, on save. A comma is the decimal point too
 * ("12,5"); with both, the comma groups thousands ("1,234.5"). Nothing typed: null; not a number: NaN.
 */
export function readNumber(value) {
    if (value === false || value === null || value === undefined) {
        return null;
    }
    if (typeof value === "number") {
        return value;
    }
    let text = String(value).replace(/[\s\u00a0]/g, "");
    if (!text) {
        return null;
    }
    text = text.includes(".") ? text.replace(/,/g, "") : text.replace(",", ".");
    return /^[-+]?(\d+\.?\d*|\.\d+)$/.test(text) ? parseFloat(text) : NaN;
}

/** {field: value | [values] | {not: [values]}}: every key holds. */
export function holds(cond, values) {
    if (!cond || cond === true) {
        return true;
    }
    for (const [key, want] of Object.entries(cond)) {
        const value = norm(values[key]);
        if (Array.isArray(want)) {
            if (!want.map(norm).includes(value)) {
                return false;
            }
        } else if (want && typeof want === "object" && "not" in want) {
            if (want.not.map(norm).includes(value)) {
                return false;
            }
        } else if (norm(want) !== value) {
            return false;
        }
    }
    return true;
}

export class MtbgExpenseForm extends Component {
    static template = "mtbg_backend_ui.ExpenseForm";
    static props = {
        target: String,
        params: { type: Object, optional: true },
        onDone: { type: Function, optional: true },
        onCancel: { type: Function, optional: true },
        orm: { type: Object, optional: true },
    };

    setup() {
        this.orm = this.props.orm || useService("orm");
        this.camera = useRef("camera");
        this.file = useRef("file");
        this.pick = useRef("pick");
        this.thenSelect = useRef("thenSelect");
        this.state = useState({
            schema: null, values: {}, photos: [], removed: [], busy: false, error: "", confirm: false, zoom: false,
            search: null, typeahead: {}, picking: false, more: false, unfolded: {},
        });
        onWillStart(() => this.load());
        onMounted(() => {
            if (this.state.picking) {
                this.openPicker();  // straight to the phone's chooser (camera, gallery); cancelled, the dialog stays
            }
        });
    }

    async load() {
        const schema = await this.orm.call(MODEL, "mtbg_load", [this.props.target, this.props.params || {}]);
        this.state.schema = schema;
        this.state.values = { ...schema.values };
        this.initial = { ...schema.values };
        this.state.picking = Boolean(schema.receipt.first && !schema.record_id && !schema.readonly);
    }

    // ------------------------------------------------------------------ what shows
    /** The phone's form (the Staff App's ``app`` params, or the schema's ``touch``): big, touch-friendly fields. */
    get touch() {
        return Boolean(this.state.schema?.touch || this.props.params?.app);
    }

    /** Every field shown, the ``top`` ones (drawn above the receipt) included. */
    get allFields() {
        const s = this.state.schema;
        // drawn inside another: an amount's currency, a choice's follow-up select ("then")
        const inline = new Set([...s.fields.filter((f) => f.currency_field).map((f) => f.currency_field),
                                ...s.fields.filter((f) => f.then).map((f) => f.then)]);
        return s.fields.filter((f) => !inline.has(f.name) && this.isVisible(f));
    }

    /** Above the receipt (owner, 2026-11-16: "Big buttons should show above the fold"): ``'top': True`` fields. */
    get topFields() {
        return this.allFields.filter((f) => f.top);
    }

    get fields() {
        return this.allFields.filter((f) => !f.top);
    }

    /**
     * As few at once as can be (owner, 2026-11-09: "no one is going to fill it out if there are 12+ fields"): the one
     * order's (lead), one that must be filled in and wasn't given, one kept with its own ("with"), an expense's own
     * extras already filled in; the others fold under More details.
     */
    isMain(field, depth = 0) {
        if (field.main || field.lead) {
            return true;
        }
        if (field.more) {
            return false;
        }
        const anchor = field.with && this.fieldOf(field.with);
        if (anchor && depth < 5) {
            return this.isVisible(anchor) && this.isMain(anchor, depth + 1);
        }
        const given = this.initial?.[field.name];
        if (this.isRequired(field)) {
            return this.isEmpty(field, given);
        }
        return Boolean(this.state.schema.record_id) && field.kind !== "check" && !this.isEmpty(field, given);
    }

    get mainFields() {
        return this.fields.filter((f) => this.isMain(f));
    }

    get moreFields() {
        return this.fields.filter((f) => !this.isMain(f));
    }

    get shownFields() {
        return this.state.more ? this.fields : this.mainFields;
    }

    toggleMore() {
        this.state.more = !this.state.more;
    }

    /** A choice's smaller options (``'minor': True``) wait under More details on the phone. */
    get hasHiddenMinor() {
        return this.touch && this.allFields.some((f) => f.kind === "choice" && this.minorOptionsOf(f).length);
    }

    get moreLabel() {
        const labels = this.moreFields.map((f) => f.label);
        if (this.hasHiddenMinor) {
            labels.unshift(_t("Other type"));
        }
        return labels.join(", ");
    }

    /** A choice's big buttons; its ``minor`` options are small ones (never a big button). */
    bigOptionsOf(field) {
        return this.optionsOf(field).filter((o) => !o.minor);
    }

    minorOptionsOf(field) {
        return this.optionsOf(field).filter((o) => o.minor);
    }

    /**
     * Set by another (``'fold': {condition}``, owner 2026-11-16: "hitting a big button should select and hide the
     * expense category so you don't have to do it twice"): one line with its value and "Change" while the condition
     * holds, it has a value and it wasn't opened.
     */
    isFolded(field) {
        return Boolean(field.fold) && holds(field.fold, this.state.values) && !this.state.unfolded[field.name]
            && !this.isEmpty(field, this.state.values[field.name]);
    }

    foldedLabel(field) {
        const value = this.state.values[field.name];
        const option = (field.options || []).find((o) => this.same(o.value, value));
        return option ? option.label : (value && value.label) || "";
    }

    unfold(field) {
        this.state.unfolded[field.name] = true;
    }

    /**
     * Read only: the field's own ``readonly``, or one option left with ``'lock_single': True`` (owner, 2026-11-16: an
     * expense paid through a GTQ account "should automatically select and lock the currency").
     */
    isLocked(field) {
        if (field.readonly) {
            return true;
        }
        return Boolean(field.lock_single) && this.optionsOf(field).length === 1;
    }

    /** A ``tags`` field's value: the ids picked (several). */
    tagsOf(field) {
        const value = this.state.values[field.name];
        return Array.isArray(value) ? value : [];
    }

    hasTag(field, value) {
        return this.tagsOf(field).some((v) => this.same(v, value));
    }

    toggleTag(field, value) {
        const current = this.tagsOf(field);
        this.set(field, this.hasTag(field, value) ? current.filter((v) => !this.same(v, value)) : [...current, value]);
    }

    fieldOf(name) {
        return this.state.schema.fields.find((f) => f.name === name);
    }

    isVisible(field) {
        return holds(field.visible, this.state.values);
    }

    isRequired(field) {
        return field.required === true || (field.required && typeof field.required === "object"
            && holds(field.required, this.state.values));
    }

    isEmpty(field, value) {
        if (field.kind === "typeahead") {
            return !value || (!value.value && !(field.create && (value.label || "").trim()));
        }
        if (field.kind === "money" || field.kind === "number") {
            return !(readNumber(value) > 0);
        }
        if (field.kind === "tags") {
            return !Array.isArray(value) || !value.length;
        }
        if (field.kind === "check" || field.kind === "info") {
            return false;
        }
        return value === undefined || value === null || value === false || value === "";
    }

    /** Two values the same (an option's and the field's: ids may come as text from the page). */
    same(a, b) {
        return norm(a) === norm(b);
    }

    optionsOf(field) {
        return (field.options || []).filter((o) => !o.only || holds(o.only, this.state.values));
    }

    get readonly() {
        return Boolean(this.state.schema.readonly) || this.state.busy;
    }

    get receipt() {
        return this.state.schema.receipt || {};
    }

    /** The receipts shown: those kept, then the new ones. */
    get shownReceipts() {
        const kept = (this.receipt.existing || []).filter((r) => !this.state.removed.includes(r.id))
            .map((r) => ({ ...r, key: `old${r.id}` }));
        const fresh = this.state.photos.map((p, i) => ({
            key: `new${i}`, index: i, url: p.preview, name: p.name, is_pdf: p.mimetype === "application/pdf",
        }));
        return [...kept, ...fresh];
    }

    // ------------------------------------------------------------------ input
    set(field, value) {
        this.state.values[field.name] = value;
        // a choice that hides options of a select: a value no longer offered is cleared
        for (const other of this.state.schema.fields) {
            if (other.kind === "select" && other.options?.some((o) => o.only)) {
                const current = norm(this.state.values[other.name]);
                if (current && !this.optionsOf(other).some((o) => norm(o.value) === current)) {
                    const offered = this.optionsOf(other);
                    this.state.values[other.name] = offered.length === 1 ? offered[0].value : false;
                }
            }
        }
    }

    /** A choice's button: set; its follow-up select ("then") taken when one option is left, else its list opened. */
    async pickChoice(field, value) {
        this.set(field, value);
        // what the option sets with it (``'sets': {field: value}``: a type's button, its Category)
        const option = (field.options || []).find((o) => this.same(o.value, value));
        for (const [name, other] of Object.entries(option?.sets || {})) {
            const target = this.fieldOf(name);
            if (target) {
                this.set(target, other);
                delete this.state.unfolded[name];  // set again: folded again
            }
        }
        const then = field.then && this.fieldOf(field.then);
        if (!then) {
            return;
        }
        const offered = this.optionsOf(then);
        if (offered.length === 1) {
            this.set(then, offered[0].value);
            return;
        }
        if (offered.some((o) => this.same(o.value, this.state.values[then.name]))) {
            return;  // still a good one: kept
        }
        // once drawn under the buttons (the tap still counts as the person's: the browser lets the list open)
        await new Promise((resolve) => requestAnimationFrame(() => setTimeout(resolve)));
        const select = this.thenSelect.el;
        if (!select) {
            return;
        }
        select.focus();
        try {
            select.showPicker();
        } catch {
            // an older browser: focused, a tap opens it
        }
    }

    onSelect(field, ev) {
        const raw = ev.target.value;
        if (raw === "__search__") {
            ev.target.value = norm(this.state.values[field.name]);
            this.state.search = { field: field.name, term: "", results: [] };
            this.runSearch();
            return;
        }
        const option = (field.options || []).find((o) => norm(o.value) === raw);
        this.set(field, option ? option.value : false);
    }

    async runSearch() {
        const search = this.state.search;
        if (!search) {
            return;  // picked (or cancelled) before the wait was over
        }
        const found = await this.orm.call(MODEL, "mtbg_search", [this.props.target, this.props.params || {},
                                                                  search.field, search.term]);
        if (this.state.search === search) {
            search.results = found;
        }
    }

    onSearchTerm(ev) {
        if (!this.state.search) {
            return;
        }
        this.state.search.term = ev.target.value;
        clearTimeout(this.searchTimer);
        this.searchTimer = setTimeout(() => this.runSearch(), 200);
    }

    pickFound(option) {
        const search = this.state.search;
        this.state.search = null;
        if (!option) {
            return;
        }
        const field = this.fieldOf(search.field);
        if (!(field.options || []).some((o) => norm(o.value) === norm(option.value))) {
            field.options = [...(field.options || []), option];
        }
        this.set(field, option.value);
    }

    // a search box (owner, 2026-11-05: never the whole list on the phone): what matches, or the recent ones
    typeaheadOf(field) {
        return this.state.typeahead[field.name] || { open: false, results: [] };
    }

    onTypeaheadInput(field, ev) {
        this.set(field, { value: false, label: ev.target.value });
        clearTimeout(this.typeTimer);
        this.typeTimer = setTimeout(() => this.loadTypeahead(field), 200);
    }

    async loadTypeahead(field) {
        const term = this.state.values[field.name]?.label || "";
        const found = await this.orm.call(MODEL, "mtbg_search", [this.props.target, this.props.params || {},
                                                                  field.name, term]);
        if ((this.state.values[field.name]?.label || "") === term) {
            this.state.typeahead[field.name] = { open: true, results: found };
        }
    }

    onTypeaheadFocus(field) {
        this.state.typeahead[field.name] = { ...this.typeaheadOf(field), open: true };
        this.loadTypeahead(field);
    }

    onTypeaheadBlur(field) {
        setTimeout(() => {
            this.state.typeahead[field.name] = { ...this.typeaheadOf(field), open: false };
        }, 200);  // after a tap on a suggestion
    }

    pickTypeahead(field, option) {
        this.set(field, { value: option.value, label: option.label });
        this.state.typeahead[field.name] = { open: false, results: [] };
    }

    /** "New: …": the typed name is not one of the suggestions. */
    typeaheadIsNew(field) {
        const value = this.state.values[field.name];
        const typed = (value?.label || "").trim().toLowerCase();
        return Boolean(field.create && typed && !value.value
            && !this.typeaheadOf(field).results.some((r) => r.label.trim().toLowerCase() === typed));
    }

    currencyLabel(field) {
        const currency = field.currency_field && this.fieldOf(field.currency_field);
        if (!currency) {
            return field.symbol || "";
        }
        const option = (currency.options || []).find((o) => norm(o.value) === norm(this.state.values[currency.name]));
        return option ? option.label : "";
    }

    // ------------------------------------------------------------------ the receipt
    openPicker() {
        const open = () => this.pick.el?.click();
        if (this.pick.el) {
            open();
        } else {
            setTimeout(open, 60);
        }
    }

    takePhoto() {
        this.camera.el?.click();
    }

    uploadPhoto() {
        this.file.el?.click();
    }

    async onPhoto(ev) {
        const files = [...(ev.target.files || [])];
        ev.target.value = "";
        if (!files.length) {
            return;
        }
        this.state.error = "";
        try {
            const read = await Promise.all(files.map((f) => readReceipt(f)));
            if (this.receipt.multiple) {
                this.state.photos.push(...read);
            } else {
                this.state.photos = [read[0]];
                this.state.removed = (this.receipt.existing || []).map((r) => r.id);
            }
            this.state.picking = false;
        } catch (error) {
            this.state.error = error.message;
        }
    }

    removeReceipt(item) {
        if (item.key.startsWith("new")) {
            this.state.photos.splice(item.index, 1);
        } else {
            this.state.removed.push(item.id);
        }
    }

    toggleZoom() {
        this.state.zoom = !this.state.zoom;
    }

    // ------------------------------------------------------------------ save, delete, cancel
    async save() {
        const s = this.state.schema;
        this.state.error = "";
        const values = {};
        for (const field of s.fields) {
            if (field.kind === "info" || !this.isVisible(field)) {
                continue;
            }
            const value = this.state.values[field.name];
            if (this.isRequired(field) && this.isEmpty(field, value)) {
                if (!this.isMain(field)) {
                    this.state.more = true;  // the one missing is folded: shown
                }
                this.state.error = field.kind === "typeahead" && !field.create
                    ? _t("Choose %s from the list.", field.label) : _t("%s is needed.", field.label);
                return;
            }
            if (field.kind === "money" || field.kind === "number") {
                const number = readNumber(value);
                if (Number.isNaN(number)) {
                    if (!this.isMain(field)) {
                        this.state.more = true;
                    }
                    this.state.error = _t("%s is not a number.", field.label);
                    return;
                }
                values[field.name] = number === null ? false : number;
            } else if (field.kind === "check") {
                values[field.name] = Boolean(value);
            } else {
                values[field.name] = value ?? false;
            }
        }
        const kept = (this.receipt.existing || []).filter((r) => !this.state.removed.includes(r.id));
        if (this.receipt.required && !this.state.photos.length && !kept.length) {
            this.state.error = _t("Add a photo of the receipt.");
            return;
        }
        values.photos = this.state.photos.map(({ name, mimetype, data }) => ({ name, mimetype, data }));
        values.photos_removed = this.state.removed;
        this.state.busy = true;
        try {
            const result = await this.orm.call(MODEL, "mtbg_save", [this.props.target, this.props.params || {}, values]);
            this.props.onDone?.({ ...result, created: !s.record_id });
        } catch (error) {
            this.state.error = error.data?.message || error.message || _t("Not saved.");
        } finally {
            this.state.busy = false;
        }
    }

    async remove() {
        if (!this.state.confirm) {
            this.state.confirm = true;  // asked first (no browser pop-up): a second tap deletes
            return;
        }
        this.state.busy = true;
        try {
            await this.orm.call(MODEL, "mtbg_delete", [this.props.target, this.props.params || {},
                                                       this.state.schema.record_id]);
            this.props.onDone?.({ id: this.state.schema.record_id, deleted: true });
        } catch (error) {
            this.state.error = error.data?.message || error.message || _t("Not deleted.");
        } finally {
            this.state.busy = false;
            this.state.confirm = false;
        }
    }

    cancel() {
        this.props.onCancel?.();
    }
}

/** The back office's Add Expense: the form in a dialog (a button returns env['mtbg.expense.form']._mtbg_action). */
export class MtbgExpenseFormAction extends Component {
    static template = "mtbg_backend_ui.ExpenseFormAction";
    static components = { MtbgExpenseForm };
    static props = ["*"];

    setup() {
        this.action = useService("action");
        this.notification = useService("notification");
    }

    get params() {
        return this.props.action?.params || {};
    }

    done(result) {
        this.notification.add(result.deleted ? _t("Expense deleted.") : result.message
            || (result.created ? _t("Expense recorded.") : _t("Expense saved.")), { type: "success" });
        return this.action.doAction({ type: "ir.actions.act_window_close" });
    }

    close() {
        return this.action.doAction({ type: "ir.actions.act_window_close" });
    }
}

registry.category("actions").add("mtbg_expense_form", MtbgExpenseFormAction);
