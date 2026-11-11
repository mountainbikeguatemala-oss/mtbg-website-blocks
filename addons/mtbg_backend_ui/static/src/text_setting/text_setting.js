/**
 * Language button for customer-facing text settings (tooltips, terms) on the extension settings pages.
 *
 * The field edits the main language; the button opens the other languages of the site. Usage:
 *   <field name="mtbg_invoice_terms_html" widget="mtbg_html_setting" options="{'key': 'mtbg_tours.invoice_terms_html'}"/>
 *   <field name="mtbg_book_tooltip" widget="mtbg_text_setting" options="{'key': 'mtbg_tours.book_tooltip'}"/>
 */
import { Component, markup, onWillStart, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { charField } from "@web/views/fields/char/char_field";
import { htmlField } from "@html_editor/fields/html_field";
import { MAIN_PLUGINS } from "@html_editor/plugin_sets";
import { Wysiwyg } from "@html_editor/wysiwyg";

export class MtbgTextSettingDialog extends Component {
    static template = "mtbg_tours_core.TextSettingDialog";
    static components = { Dialog, Wysiwyg };
    static props = {
        settingKey: String, title: String, html: Boolean, close: Function,
        allLangs: { type: Boolean, optional: true },  // the main language too (a page without its own field)
        onSaved: { type: Function, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.editors = {};
        this.state = useState({ langs: [], values: {} });
        onWillStart(async () => {
            const data = await this.orm.call("mtbg.text.setting", "mtbg_read", [this.props.settingKey]);
            this.state.langs = data.langs;
            this.state.values = data.values;
        });
    }

    get main() {
        return this.state.langs[0];
    }

    get others() {
        return this.props.allLangs ? this.state.langs : this.state.langs.slice(1);
    }

    editorConfig(code) {
        return { content: markup(this.state.values[code] || ""), Plugins: MAIN_PLUGINS, placeholder: _t("Empty: the main text") };
    }

    async save() {
        const values = {};
        for (const lang of this.others) {
            values[lang.code] = this.props.html ? this.editors[lang.code]?.getContent() ?? "" : this.state.values[lang.code];
            if (this.props.html && !this.editors[lang.code]?.getElContent().textContent.trim()) {
                values[lang.code] = "";
            }
        }
        await this.orm.call("mtbg.text.setting", "mtbg_write", [this.props.settingKey, values]);
        this.notification.add(_t("Saved"), { type: "success" });
        this.props.onSaved?.(values);
        this.props.close();
    }
}

function withLanguages(Base, html) {
    return class extends Component {
        static template = "mtbg_tours_core.TextSettingField";
        static components = { Base };
        static props = { ...Base.props, settingKey: String };

        setup() {
            this.dialog = useService("dialog");
        }

        get baseProps() {
            const { settingKey, ...props } = this.props;
            return props;
        }

        openLanguages() {
            const field = this.props.record.fields[this.props.name];
            this.dialog.add(MtbgTextSettingDialog, { settingKey: this.props.settingKey, title: field.string, html });
        }
    };
}

function descriptor(base, html) {
    return {
        ...base,
        component: withLanguages(base.component, html),
        extractProps: (fieldInfo, dynamicInfo) => ({
            ...base.extractProps(fieldInfo, dynamicInfo),
            settingKey: fieldInfo.options.key,
        }),
    };
}

registry.category("fields").add("mtbg_text_setting", descriptor(charField, false));
registry.category("fields").add("mtbg_html_setting", descriptor(htmlField, true));
