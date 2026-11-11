/**
 * A model's kanban laid out by boards (``js_class="mtbg_board_kanban"``, the model inheriting ``mtbg.board.mixin``):
 * beside the view switcher the Board dropdown, the model's boards (its columns, its order top to bottom), and for
 * managers New board / Edit this board. A board may filter its records (its ``domain``, e.g. the leads only). A group-by chosen in the search applies over the board until another board
 * is picked; a sort clicked likewise. The board chosen is the viewer's (kept in this browser). The cards look as set in
 * the settings, the same on every board. A model with a side bar has it here too, on Cards and Kanban (Core's rule:
 * every view has the side bar), its chosen branch narrowing the board.
 */
import { Component, useState, useSubEnv } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatFloat, formatInteger, formatMonetary } from "@web/views/fields/formatters";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { KanbanHeader } from "@web/views/kanban/kanban_header";
import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { MtbgSidebar, useMtbgSidebar } from "@mtbg_backend_ui/sidebar_list/sidebar_list";
import { CARDS, lastBoard, readBoard, useViewModes, ViewModes, writeBoard } from "@mtbg_backend_ui/view_modes/view_modes";

export { CARDS };

/** "start_date asc, name desc" as the model's orderBy. */
function parseOrder(order) {
    return (order || "").split(",").map((part) => part.trim().split(/\s+/)).filter(([name]) => name)
        .map(([name, dir]) => ({ name, asc: (dir || "asc").toLowerCase() !== "desc" }));
}

/** A board: its name, columns and order (new, or one to change or delete). */
export class BoardDialog extends Component {
    static template = "mtbg_tours_core.BoardDialog";
    static components = { Dialog };
    static props = ["board?", "columns", "sorts", "totals", "close", "onSave", "onDelete?"];

    setup() {
        const board = this.props.board || {};
        const [sort] = parseOrder(board.order || "start_date asc");
        this.state = useState({
            name: board.name || "",
            group_by: board.group_by || this.props.columns[0]?.key || "",
            sort: sort?.name || this.props.sorts[0]?.key || "",
            asc: sort ? sort.asc : true,
            total_field: board.total_field || "",
        });
    }

    async save() {
        if (!this.state.name.trim()) {
            return;
        }
        await this.props.onSave({
            name: this.state.name.trim(),
            group_by: this.state.group_by || false,
            order: this.state.sort ? `${this.state.sort} ${this.state.asc ? "asc" : "desc"}` : false,
            total_field: this.state.total_field || false,
        });
        this.props.close();
    }

    async remove() {
        await this.props.onDelete();
        this.props.close();
    }
}

export class BoardKanbanController extends KanbanController {
    static template = "mtbg_tours_core.BoardKanbanView";
    static components = { ...KanbanController.components, Dropdown, DropdownItem, MtbgSidebar, ViewModes };

    setup() {
        super.setup();
        this.mtbgOrm = useService("orm");
        this.mtbgDialog = useService("dialog");
        this.boards = useState({ id: readBoard(this.props.resModel), list: [], columns: [], sorts: [], totals: [],
                                 colors: {}, canEdit: false, settingsAction: false, refreshed: [],
                                 hasSidebar: false });
        useSubEnv({ mtbgBoards: this.boards });
        this.viewEntries = useViewModes(this);
        this.boardsReady = this.loadBoards();
        // the search's group-by when the board was chosen: changed since, the search's applies
        this.boardGroupBy = JSON.stringify(this.env.searchModel.groupBy);
        const load = this.model.load.bind(this.model);
        // the side bar's branch narrows the search's domain, then the board lays it out
        this.mtbgSidebar = useMtbgSidebar(this, async () => (await this.boardsReady, this.boards.hasSidebar));
        this.sidebar = this.mtbgSidebar.sidebar;
        this.model.load = this.mtbgSidebar.wrapLoad(async (params = {}) => load(await this.boardParams(params)));
    }

    get hasSidebar() {
        return this.boards.hasSidebar;
    }

    /** A branch chosen (again: all). */
    chooseSidebar(node) {
        this.mtbgSidebar.choose(node);
        return this.model.load({ domain: this.mtbgSidebar.base });
    }

    /** Each column sums every number a board can total (Core names them on the kanban: ``mtbg_totals``). */
    get progressBarAggregateFields() {
        const names = (this.props.arch?.getAttribute?.("mtbg_totals") || "").split(",").filter(Boolean);
        const own = super.progressBarAggregateFields;
        return [...own, ...names.map((name) => this.props.fields[name]).filter((f) => f && !own.includes(f))];
    }

    /** The first load waits for the board (its columns), so the kanban opens laid out. */
    get modelOptions() {
        return { ...super.modelOptions, lazy: false };
    }

    async loadBoards() {
        // the page's context: a page of the model (``mtbg_scope``) has its own boards
        const settings = await this.mtbgOrm.call(this.props.resModel, "mtbg_board_settings", [],
                                                 { context: this.props.context });
        Object.assign(this.boards, { list: settings.boards, columns: settings.columns, sorts: settings.sorts,
                                     totals: settings.totals, colors: settings.colors, canEdit: settings.can_edit,
                                     settingsAction: settings.settings_action || false,
                                     refreshed: settings.refreshed || [], hasSidebar: !!settings.has_sidebar });
        if (this.boards.id !== CARDS && !settings.boards.some((b) => b.id === this.boards.id)) {
            this.boards.id = settings.boards[0]?.id || 0;
        }
    }

    get board() {
        if (this.boards.id === CARDS) {
            return { id: CARDS, name: _t("Cards"), group_by: "", order: "", domain: [], cards: true };
        }
        return this.boards.list.find((b) => b.id === this.boards.id) || null;
    }

    /** The load's group-by and order: the board's, unless the search says otherwise. */
    async boardParams(params) {
        await this.boardsReady;
        const board = this.board;
        if (!board) {
            return params;
        }
        // the server folds the empty columns of a board only
        const result = { ...params, context: { ...(params.context || this.props.context), mtbg_board: true } };
        // the board's filter (e.g. the leads only), over the search's
        if (board.domain?.length) {
            result.domain = [...(params.domain || this.props.domain || []), ...board.domain];
        }
        const searchGroupBy = this.env.searchModel.groupBy;
        if (board.cards && JSON.stringify(searchGroupBy) === this.boardGroupBy) {
            result.groupBy = [];  // the cards in a grid
        } else if (board.group_by && JSON.stringify(searchGroupBy) === this.boardGroupBy) {
            result.groupBy = [board.group_by];
        }
        if (board.order && !this.env.searchModel.orderBy.length) {
            result.orderBy = parseOrder(board.order);
        }
        // the columns kept up to date as a board loads (the model's ``_mtbg_board_refreshed``)
        const refresh = (result.groupBy || []).map((g) => g.split(":")[0])
            .filter((g) => this.boards.refreshed.includes(g));
        if (refresh.length) {
            await this.mtbgOrm.call(this.props.resModel, "mtbg_board_refresh",
                                    [result.domain || params.domain || this.props.domain || [], refresh]);
        }
        return result;
    }

    reloadBoard() {
        this.boardGroupBy = JSON.stringify(this.env.searchModel.groupBy);
        const { context, groupBy, orderBy } = this.props;
        return this.model.load({ domain: this.mtbgSidebar.base, context, groupBy, orderBy });
    }

    /** The cog: the model's settings page (Import / Export there), not Odoo's menu. */
    openSettings() {
        return this.actionService.doAction(this.boards.settingsAction);
    }

    chooseBoard(id) {
        this.boards.id = id;
        writeBoard(this.props.resModel, id);
        return this.reloadBoard();
    }

    /** List · Cards · Kanban: Cards and Kanban are this kanban's boards (Kanban: the one chosen last). */
    get viewMode() {
        return this.boards.id === CARDS ? "cards" : "kanban";
    }

    setViewMode(mode) {
        if (mode === "cards") {
            return this.chooseBoard(CARDS);
        }
        const last = lastBoard(this.props.resModel);
        return this.chooseBoard(this.boards.list.some((b) => b.id === last) ? last : this.boards.list[0]?.id || 0);
    }

    editBoard(board = null) {
        this.mtbgDialog.add(BoardDialog, {
            board,
            columns: this.boards.columns,
            sorts: this.boards.sorts,
            totals: this.boards.totals,
            onSave: async (values) => {
                let id = board?.id;
                if (id) {
                    await this.mtbgOrm.write("mtbg.board", [id], values);
                } else {
                    [id] = await this.mtbgOrm.create("mtbg.board", [{ ...values, res_model: this.props.resModel,
                                                                      scope: this.props.context?.mtbg_scope || false,
                                                                      sequence: 100 }]);
                }
                await this.loadBoards();
                await this.chooseBoard(id);
            },
            onDelete: board && (async () => {
                await this.mtbgOrm.unlink("mtbg.board", [board.id]);
                await this.loadBoards();
                await this.reloadBoard();
            }),
        });
    }
}

/** A column's header: its stage's colour, its total (the board's number summed over its cards), a fold button. */
export class BoardKanbanHeader extends KanbanHeader {
    static template = "mtbg_tours_core.BoardKanbanHeader";

    setup() {
        super.setup();
        this.mtbgBoards = this.env.mtbgBoards ? useState(this.env.mtbgBoards) : null;
    }

    get mtbgBoard() {
        const boards = this.mtbgBoards;
        return boards && (boards.list.find((b) => b.id === boards.id) || null);
    }

    /** The column's colour (its stage's), when the columns are a field with colours. */
    get mtbgColor() {
        const field = this.group.groupByField?.name;
        const colors = (field && this.mtbgBoards?.colors?.[field]) || {};
        const value = Array.isArray(this.group.value) ? this.group.value[0] : this.group.value;
        return colors[this.group.serverValue] || colors[value] || "";
    }

    /** The header in its colour, its text dark or light to read on it. */
    get mtbgStyle() {
        const color = this.mtbgColor;
        if (!/^#[0-9a-f]{6}$/i.test(color)) {
            return "";
        }
        const [r, g, b] = [1, 3, 5].map((i) => parseInt(color.slice(i, i + 2), 16));
        const ink = (0.299 * r + 0.587 * g + 0.114 * b) > 160 ? "#1b1d26" : "#ffffff";
        return `--mtbg-board-color: ${color}; --mtbg-board-ink: ${ink};`;
    }

    /** The column's total: {label, text}, or null. */
    get mtbgTotal() {
        const name = this.mtbgBoard?.total_field;
        if (name === "__count") {  // the records in the column
            const label = this.mtbgBoards.totals.find((t) => t.key === name)?.label || "";
            return { label, text: formatInteger(this.group.count) };
        }
        const field = name && this.props.list.fields[name];
        if (!field || !this.group.aggregates || !(name in this.group.aggregates)) {
            return null;
        }
        const value = this.group.aggregates[name] || 0;
        let text;
        if (field.type === "monetary") {
            const currencies = this.group.aggregates[field.currency_field];
            const currencyId = Array.isArray(currencies) ? (currencies.length === 1 ? currencies[0] : false) : currencies;
            text = formatMonetary(value, { currencyId, digits: [false, 0] });
        } else if (field.type === "integer") {
            text = formatInteger(value);
        } else {
            text = formatFloat(value, { digits: [false, 1] });
        }
        const label = this.mtbgBoards.totals.find((t) => t.key === name)?.label || field.string;
        return { label, text };
    }
}

export class BoardKanbanRenderer extends KanbanRenderer {
    static components = { ...KanbanRenderer.components, KanbanHeader: BoardKanbanHeader };
}

export const boardKanbanView = { ...kanbanView, Controller: BoardKanbanController, Renderer: BoardKanbanRenderer };

registry.category("views").add("mtbg_board_kanban", boardKanbanView);
