/**
 * A pipeline in the stages' colours (``<widget name="mtbg_stage_colors" options="{'field': 'stage'}"/>``,
 * anywhere on the page): Odoo's status bar of that field takes the same colours as the board's column headers and
 * the badges (the model's ``_mtbg_board_field_colors``): the current stage filled, the others tinted. A stage without
 * a colour: Odoo's own.
 */
import { Component, onWillStart, onWillUnmount, useEffect } from "@odoo/owl";
import { registry } from "@web/core/registry";

const colorsByModel = {};  // model -> the promise of its stages' colours (one call per model and page load)

function inkFor(color) {
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(color.slice(i, i + 2), 16));
    return 0.299 * r + 0.587 * g + 0.114 * b > 160 ? "#1b1d26" : "#ffffff";
}

export class BoardStatusbarColors extends Component {
    static template = "mtbg_tours_core.BoardStatusbarColors";
    static props = ["*"];

    setup() {
        this.map = {};
        onWillStart(async () => {
            const model = this.props.record.resModel;
            // shared by every widget of the page: the service itself, not this component's (a component's calls
            // never answer once it is gone, and the page redraws its widgets while it loads)
            colorsByModel[model] ||= this.env.services.orm.silent.call(model, "mtbg_board_colors", []).catch(() => ({}));
            this.map = (await colorsByModel[model])[this.props.field] || {};
        });
        // the rules go in the page's head (one style element per field), gone with the page
        this.style = document.createElement("style");
        useEffect(() => {
            this.style.textContent = this.css;
            document.head.appendChild(this.style);
        }, () => []);
        onWillUnmount(() => this.style.remove());
    }

    get css() {
        const bar = `.o_field_widget[name="${this.props.field}"] .o_statusbar_status`;
        return Object.entries(this.map)
            .filter(([value, color]) => /^#[0-9a-f]{6}$/i.test(color || "") && /^[\w-]+$/.test(value))
            .map(([value, color]) =>
                // over Odoo's own (the current stage is a disabled button)
                `${bar} .o_arrow_button[data-value="${value}"] { background-color: ${color}2e !important; color: var(--bs-body-color) !important; }
${bar} .o_arrow_button.o_arrow_button_current[data-value="${value}"] { background-color: ${color} !important; color: ${inkFor(color)} !important; opacity: 1 !important; }`)
            .join("\n");
    }
}

registry.category("view_widgets").add("mtbg_stage_colors", {
    component: BoardStatusbarColors,
    extractProps: ({ options }) => ({ field: options?.field || "state" }),
});
