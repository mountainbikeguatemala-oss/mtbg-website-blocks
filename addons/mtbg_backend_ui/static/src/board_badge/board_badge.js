/**
 * A status as a pill in its stage's colour (``widget="mtbg_board_badge"``): the same colours as the board's column
 * headers, the side bar's dots and the cards' status pill (the model's ``_mtbg_board_field_colors``). A value without
 * a colour: Odoo's plain pill.
 */
import { onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { BadgeField, badgeField } from "@web/views/fields/badge/badge_field";

const colorsByModel = {};  // model -> the promise of its stages' colours (one call per model and page load)

function inkFor(color) {
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(color.slice(i, i + 2), 16));
    return 0.299 * r + 0.587 * g + 0.114 * b > 160 ? "#1b1d26" : "#ffffff";
}

export class BoardBadgeField extends BadgeField {
    static template = "mtbg_tours_core.BoardBadgeField";

    setup() {
        super.setup();
        const orm = useService("orm");
        this.boardColors = useState({ map: {} });
        onWillStart(async () => {
            const model = this.props.record.resModel;
            colorsByModel[model] ||= orm.silent.call(model, "mtbg_board_colors", []).catch(() => ({}));
            this.boardColors.map = (await colorsByModel[model])[this.props.name] || {};
        });
    }

    get boardStyle() {
        const color = this.boardColors.map[this.props.record.data[this.props.name]];
        return /^#[0-9a-f]{6}$/i.test(color || "") ? `background: ${color}; color: ${inkFor(color)};` : "";
    }
}

registry.category("fields").add("mtbg_board_badge", { ...badgeField, component: BoardBadgeField });
