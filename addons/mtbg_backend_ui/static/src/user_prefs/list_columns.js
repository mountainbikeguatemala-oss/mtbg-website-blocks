/**
 * Every list's picked columns (the optional-columns toggle) kept per user on the server (owner, 2026-11-09: "the filter
 * for column selection should be permanent across sessions"), lists inside a record page (a booking's Participants)
 * too. One choice per list: its model, view and, for a list inside a page, the page's model and field. Odoo's own
 * browser key also holds the list's field names, so a column an extension adds started the choice over: this one stays.
 * A column the user has never seen in that list starts as the list says (shown or hidden); browser storage only counts
 * while the server has nothing for that list.
 */
import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";
import { getUserPref, hasUserPref, setUserPref } from "./user_prefs";

patch(ListRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        this.mtbgColumnsKey = this.mtbgListKey();
    },

    /** The list's key: "list:" model, view type, view id, the page's field, the sub-view (no field names), and the
     * list's class when it has one (two lists of one field on a page: a booking's Participants and Rider bikes). */
    mtbgListKey() {
        const nested = this.props.nestedKeyOptionalFieldsData;
        const parts = nested
            ? [nested.model, nested.viewMode, this.env.config?.viewId, nested.field, "list"]
            : [this.props.list.resModel, "list", this.env.config?.viewId];
        if (this.props.archInfo?.className) {
            parts.push(this.props.archInfo.className);
        }
        return "list:" + parts.map((part) => (part === undefined || part === null ? "" : part)).join(",");
    },

    computeOptionalActiveFields() {
        if (!hasUserPref(this.mtbgColumnsKey)) {
            return super.computeOptionalActiveFields(...arguments);
        }
        const saved = getUserPref(this.mtbgColumnsKey) || {};
        const shown = new Set(saved.shown || []);
        const known = new Set(saved.known || []);
        const active = {};
        for (const col of this.allColumns) {
            if (col.type === "field" && col.optional) {
                active[col.name] = known.has(col.name) ? shown.has(col.name) : col.optional === "show";
            }
        }
        return active;
    },

    saveOptionalActiveFields() {
        super.saveOptionalActiveFields(...arguments);
        const optional = this.allColumns.filter((col) => col.type === "field" && col.optional).map((col) => col.name);
        const saved = getUserPref(this.mtbgColumnsKey) || {};
        // columns of this list not drawn this time (another page's extension) keep their choice
        const known = new Set([...(saved.known || []), ...optional]);
        const shown = new Set((saved.shown || []).filter((name) => !optional.includes(name)));
        for (const name of optional) {
            if (this.optionalActiveFields[name]) {
                shown.add(name);
            }
        }
        setUserPref(this.mtbgColumnsKey, { shown: [...shown], known: [...known] });
    },
});
