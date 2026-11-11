/** @odoo-module **/
// The shared fields as components, for the forms built in the browser (e.g. the pre-tour wizard). Each reports
// what is typed through ``onChange``; checking is done with @mtbg_tours_forms/fields.
import { Component, onWillStart, useState } from "@odoo/owl";
import { phonePicker } from "./fields";

export class MtbgPhoneField extends Component {
    static template = "mtbg_tours_forms.PhoneField";
    static props = { onChange: Function, placeholder: { type: String, optional: true } };

    setup() {
        this.state = useState({ code: "", raw: "", countries: [] });
        onWillStart(async () => {
            const picker = await phonePicker();
            Object.assign(this.state, { countries: picker.countries, code: picker.default });
            this.report();
        });
    }

    get country() {
        return this.state.countries.find((c) => c.code === this.state.code) || null;
    }

    report() {
        this.props.onChange({ country: this.country, raw: this.state.raw });
    }
}
