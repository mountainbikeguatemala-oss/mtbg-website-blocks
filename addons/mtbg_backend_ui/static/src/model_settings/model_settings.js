/**
 * A model's settings page (client action ``mtbg_model_settings``, params {model, title?}): the page every board's and
 * list's cog opens (Core's rule, docs/architecture/core-ui.md). Its tabs: the record card (Core's card editor, with
 * its preview and Import / Export) and the boards (the kanban's templates: each extension ships its own, people add
 * theirs; what each shows, its columns, order and total), then the extensions' own tabs for the model (registry
 * category ``mtbg_tours.settings_tabs``: {model, label, icon, Component, sequence}, e.g. Communications' Engagement)
 * and, at the end, a link to the module's own settings page (params ``more``: {label, xmlid}).
 */
import { Component, onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { BoardDialog } from "@mtbg_backend_ui/board_kanban/board_kanban";
import { CardEditor } from "@mtbg_backend_ui/card_editor/card_editor";

export const settingsTabs = registry.category("mtbg_tours.settings_tabs");

export class ModelSettings extends Component {
    static template = "mtbg_tours_core.ModelSettings";
    static components = { CardEditor };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        const params = this.props.action?.params || {};
        this.model = params.model;
        this.title = params.title || this.props.action?.name || _t("Settings");
        this.cardAction = { name: params.card_title || _t("Card"), params: { model: this.model } };
        this.more = params.more || null;  // the module's own settings page ({label, xmlid}), a link at the end
        this.action = useService("action");
        this.state = useState({ tab: params.tab || "card", boards: null });
        this.extraTabs = settingsTabs.getEntries().filter(([_key, tab]) => tab.model === this.model)
            .map(([key, tab]) => ({ key, ...tab })).sort((a, b) => (a.sequence || 10) - (b.sequence || 10));
        onWillStart(() => this.loadBoards());
    }

    async loadBoards() {
        try {
            this.state.boards = await this.orm.call(this.model, "mtbg_board_settings", []);
        } catch {
            this.state.boards = null;  // a model without boards: the card tab only
        }
    }

    openMore() {
        return this.action.doAction(this.more.xmlid);
    }

    get extraTab() {
        return this.extraTabs.find((t) => t.key === this.state.tab) || null;
    }

    label(list, key) {
        return (list || []).find((c) => c.key === key)?.label || key || "";
    }

    orderLabel(order) {
        const [name, dir] = (order || "").split(",")[0].trim().split(/\s+/);
        return name ? `${this.label(this.state.boards.sorts, name)} ${dir === "desc" ? "↓" : "↑"}` : "";
    }

    editBoard(board = null) {
        const settings = this.state.boards;
        this.dialog.add(BoardDialog, {
            board, columns: settings.columns, sorts: settings.sorts, totals: settings.totals,
            onSave: async (values) => {
                if (board) {
                    await this.orm.write("mtbg.board", [board.id], values);
                } else {
                    await this.orm.create("mtbg.board", [{ ...values, res_model: this.model, sequence: 100 }]);
                }
                await this.loadBoards();
            },
            onDelete: board && (async () => {
                await this.orm.unlink("mtbg.board", [board.id]);
                await this.loadBoards();
            }),
        });
    }
}

registry.category("actions").add("mtbg_model_settings", ModelSettings);
