/**
 * The record card, defined once per model (``<model>.mtbg_card_data``: Core's card mixin, the model's content,
 * extensions' notices, the look set on the extension's settings page): the model's kanban, another record's page, the
 * card editor's preview. Always the same width (about a phone's). As a view widget it draws the record itself, or, with
 * ``options="{'field': 'departure_id'}"``, the record of that many2one. Cards on one screen load together.
 */
import { Component, onWillStart, onWillUpdateProps, onWillUnmount, useEffect, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

const batches = {};  // model -> the ids asked for in this tick, loaded in one call

function loadCard(orm, model, id) {
    let batch = batches[model];
    if (!batch) {
        batch = batches[model] = { ids: new Set() };
        batch.promise = Promise.resolve().then(async () => {
            delete batches[model];
            const cards = await orm.call(model, "mtbg_card_data", [[...batch.ids]]);
            return Object.fromEntries(cards.map((c) => [c.id, c]));
        });
    }
    batch.ids.add(id);
    return batch.promise.then((cards) => cards[id] || null);
}

export class RecordCard extends Component {
    static template = "mtbg_tours_core.RecordCard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.state = useState({ card: null, loaded: false, now: Date.now(), busy: false });
        // the live countdown: its pill ticks (every 30 seconds: days, hours, minutes)
        this.timer = setInterval(() => {
            if (this.card?.corner?.some((p) => p.countdown_to)) {
                this.state.now = Date.now();
            }
        }, 30000);
        onWillUnmount(() => clearInterval(this.timer));
        onWillStart(() => this.load(this.props));
        // an accent (a card's values ``accent``: a colour, e.g. a multi-day trip's day): the outline of its kanban
        // record (or of the card itself elsewhere)
        this.root = useRef("root");
        useEffect((el, accent) => {
            const box = el?.closest(".o_kanban_record");
            if (!box) {
                return;
            }
            box.classList.toggle("mtbg_rc_accented", Boolean(accent));
            if (accent) {
                box.style.setProperty("--mtbg-accent", accent);
            } else {
                box.style.removeProperty("--mtbg-accent");
            }
        }, () => [this.root.el, this.card?.accent || ""]);
        onWillUpdateProps((next) => {
            if (!next.card && this.targetKey(next) !== this.targetKey(this.props)) {
                return this.load(next);
            }
        });
    }

    /** [model, id] of the record drawn: the record itself, or its ``field``'s. */
    target(props) {
        const record = props.record;
        if (!record) {
            return [props.model, props.resId || 0];
        }
        if (props.field) {
            return [record.fields[props.field]?.relation, record.data[props.field]?.id || 0];
        }
        return [record.resModel, record.resId || 0];
    }

    targetKey(props) {
        return this.target(props).join(":");
    }

    /** The card drawn: given (the editor's preview) or loaded. */
    get card() {
        return this.props.card || this.state.card;
    }

    /** A pill's text: the live countdown to the start ("12d 04h 05m"), else its own. */
    pillText(pill) {
        if (pill.countdown_to) {
            const left = Math.max(0, Date.parse(pill.countdown_to) - this.state.now);
            if (left > 0) {
                const minutes = Math.floor(left / 60000);
                const d = Math.floor(minutes / 1440);
                const h = Math.floor((minutes % 1440) / 60);
                const m = minutes % 60;
                return d ? `${d}d ${String(h).padStart(2, "0")}h ${String(m).padStart(2, "0")}m`
                    : `${h}h ${String(m).padStart(2, "0")}m`;
            }
        }
        return pill.text || "";
    }

    /** The dropdown's grid: fixed widths per kind of column, the name taking the rest (the columns line up). */
    get detailsGrid() {
        // the small columns as wide as their widest cell (up to a limit), the name taking the rest
        const widths = { flag: "1.3rem", check: "1.6rem", pills: "fit-content(4rem)" };
        const cols = (this.card?.details?.columns || []).map((c) =>
            c.key === "slot" ? "1.2rem" : c.key === "name" ? "minmax(4rem, 1fr)" : widths[c.kind] || "fit-content(4.5rem)");
        return `grid-template-columns: ${cols.join(" ")};`;
    }

    /** A done / not done mark, drawn with the details' style (the participant lists' global icon look). */
    checkClass(value) {
        const st = this.card?.details?.check_style || {};
        return `mtbg_rc_check ${value.ok ? "is-ok" : "is-missing"} is-size-${st.size || "m"} is-mark-${st.mark_size || "s"} is-at-${st.mark_position || "br"}`;
    }

    /** Its own record in a kanban: the kanban opens it; a preview stays put. */
    get linked() {
        return !this.props.card && !(this.props.record && !this.props.field && this.env.config?.viewType === "kanban");
    }

    async load(props) {
        if (props.card) {
            this.state.loaded = true;
            return;
        }
        const [model, id] = this.target(props);
        this.state.card = model && id ? await loadCard(this.orm, model, id) : null;
        this.state.loaded = true;
    }

    open() {
        if (this.card && this.linked) {
            this.action.doAction({ type: "ir.actions.act_window", res_model: this.card.model, res_id: this.card.id,
                                   views: [[false, "form"]] });
        }
    }

    /** A card button: asked first when it has a question, then the record's method (``mtbg_card_action``); its
     * action is followed, else the card (and its kanban record) reload. */
    runAction(ev, action) {
        ev.stopPropagation();
        if (this.props.card || this.state.busy) {
            return;
        }
        const run = async () => {
            this.state.busy = true;
            try {
                const result = await this.orm.call(this.card.model, "mtbg_card_action", [[this.card.id], action.key]);
                if (result) {
                    return this.action.doAction(result);
                }
                if (this.props.record?.model?.load) {
                    await this.props.record.model.load();
                }
                this.state.card = await this.orm.call(this.card.model, "mtbg_card_data", [[this.card.id]]).then((c) => c[0] || null);
            } finally {
                this.state.busy = false;
            }
        };
        if (action.confirm) {
            this.dialog.add(ConfirmationDialog, { body: action.confirm, confirm: run, cancel: () => {} });
            return;
        }
        return run();
    }

    openLink(ev, link) {
        ev.stopPropagation();
        if (!this.props.card && link?.action) {  // e.g. the badge: the customer's saved cards
            return this.action.doAction(link.action);
        }
        if (!this.props.card && link?.model && link.id) {
            this.action.doAction({ type: "ir.actions.act_window", res_model: link.model, res_id: link.id,
                                   views: [[false, "form"]] });
        }
    }
}

registry.category("view_widgets").add("mtbg_record_card", {
    component: RecordCard,
    extractProps: ({ options }) => ({ field: options?.field || false }),
});
