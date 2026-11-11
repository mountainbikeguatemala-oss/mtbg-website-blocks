/**
 * Coloured choice buttons for a selection (owner, 2026-11-07: an expense's type, Initial Cost / Upgrades / Maintenance
 * / Fuel): in a form, one button per choice in its tone and icon (the one picked filled); read only (a list), the
 * value as a pill in its tone. The tones are Core's palette (light and dark):
 *
 *   <field name="cost_type" widget="mtbg_choice_buttons"
 *          options="{'tones': {'initial': 'slate', 'fuel': 'green'}, 'icons': {'initial': 'fa-tag', 'fuel': 'fa-tint'}}"/>
 *
 * Tones: slate, purple, orange, green, blue, red, teal, grey.
 */
import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class MtbgChoiceButtons extends Component {
    static template = "mtbg_tours_core.ChoiceButtons";
    static props = { ...standardFieldProps, tones: { type: Object, optional: true }, icons: { type: Object, optional: true } };

    get choices() {
        const field = this.props.record.fields[this.props.name];
        return (field.selection || []).map(([value, label]) => ({
            value, label, tone: this.props.tones?.[value] || "grey", icon: this.props.icons?.[value] || "",
        }));
    }

    get current() {
        return this.choices.find((c) => c.value === this.props.record.data[this.props.name]) || null;
    }

    pick(value) {
        if (!this.props.readonly) {
            this.props.record.update({ [this.props.name]: value });
        }
    }
}

registry.category("fields").add("mtbg_choice_buttons", {
    component: MtbgChoiceButtons,
    supportedTypes: ["selection"],
    extractProps: ({ options }) => ({ tones: options.tones || {}, icons: options.icons || {} }),
});
