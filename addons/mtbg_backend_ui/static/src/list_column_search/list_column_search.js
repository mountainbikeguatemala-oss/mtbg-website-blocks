/**
 * A search box in every list's column picker (the optional columns at the right of the header), Core's look for all
 * the suite's lists (owner, 2026-10-27: "since there is so many fields we should also add search to the column
 * selector dropdown Global UI"): typing keeps the columns whose name holds the words, in any order and case.
 */
import { useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";

function matches(label, words) {
    const text = (label || "").toLowerCase();
    return words.every((word) => text.includes(word));
}

patch(ListRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        this.mtbgColumnSearch = useState({ term: "" });
    },

    get optionalFieldGroups() {
        const groups = super.optionalFieldGroups;
        const words = this.mtbgColumnSearch.term.toLowerCase().split(/\s+/).filter(Boolean);
        if (!words.length) {
            return groups;
        }
        return groups
            .map((group) => matches(group.displayName, words)
                ? group
                : { ...group, optionalFields: group.optionalFields.filter((f) => matches(f.label, words)) })
            .filter((group) => group.optionalFields.length);
    },

    onMtbgColumnSearch(ev) {
        this.mtbgColumnSearch.term = ev.target.value;
    },
});
