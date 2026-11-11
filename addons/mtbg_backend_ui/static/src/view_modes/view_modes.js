/**
 * The view switcher of Core's pages (Core's rule, docs/architecture/core-ui.md): List · Cards · Kanban, in that order,
 * on every side bar list and every board kanban; Cards is the kanban with no columns (the built-in Cards board),
 * Kanban the board chosen last (its dropdown to the right). The action's other views (calendar, pivot...) follow.
 */
import { Component, useSubEnv } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

export const CARDS = -1;  // the built-in "Cards" board: no columns, every card in a grid
const boardKey = (model) => `mtbg_tours.board.${model}`;
const lastKey = (model) => `mtbg_tours.board_last.${model}`;

function read(key) {
    try {
        return Number(window.localStorage.getItem(key)) || 0;
    } catch {
        return 0;
    }
}

/** The board shown on the model's kanban (CARDS, a board's id, or 0: the first). */
export function readBoard(model) {
    return read(boardKey(model));
}

/** The kanban board last chosen (not Cards). */
export function lastBoard(model) {
    return read(lastKey(model));
}

export function writeBoard(model, id) {
    try {
        window.localStorage.setItem(boardKey(model), String(id));
        if (id !== CARDS) {
            window.localStorage.setItem(lastKey(model), String(id));
        }
    } catch {
        // the choice lasts this page only
    }
}

/** In a controller's setup: the action's views, with Odoo's own switcher hidden (ours draws them). */
export function useViewModes(component) {
    const entries = component.env.config.viewSwitcherEntries || [];
    const config = Object.create(component.env.config);
    config.viewSwitcherEntries = [];
    useSubEnv({ config });
    return entries;
}

export class ViewModes extends Component {
    static template = "mtbg_tours_core.ViewModes";
    static props = { mode: String, resModel: String, entries: Array, onMode: { type: Function, optional: true } };

    setup() {
        this.action = useService("action");
    }

    get has() {
        const types = this.props.entries.map((e) => e.type);
        return { list: types.includes("list"), kanban: types.includes("kanban") };
    }

    get modes() {
        const modes = [];
        if (this.has.list) {
            modes.push({ key: "list", label: _t("List"), icon: "oi oi-view-list" });
        }
        if (this.has.kanban) {
            modes.push({ key: "cards", label: _t("Cards"), icon: "fa fa-th-large" },
                       { key: "kanban", label: _t("Kanban"), icon: "oi oi-view-kanban" });
        }
        return modes;
    }

    /** The action's other views (calendar, pivot, graph...), after the three. */
    get others() {
        return this.props.entries.filter((e) => !["list", "kanban"].includes(e.type));
    }

    choose(mode) {
        if (mode === this.props.mode) {
            return;
        }
        if (this.props.onMode && mode !== "list") {
            return this.props.onMode(mode);  // the kanban: Cards and Kanban are its boards
        }
        if (mode === "cards") {
            writeBoard(this.props.resModel, CARDS);
        } else if (mode === "kanban" && readBoard(this.props.resModel) === CARDS) {
            writeBoard(this.props.resModel, lastBoard(this.props.resModel));
        }
        return this.action.switchView(mode === "list" ? "list" : "kanban");
    }

    switchTo(type) {
        return this.action.switchView(type);
    }
}
