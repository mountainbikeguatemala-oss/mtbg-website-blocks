/** The marketing engine's picture (owner, 2026-11-22: "the marketing template preview should be GLOBAL"): a story or
 * post drawing as a thumbnail (a queue's list or board, a template's live preview); a click shows it as the phone
 * shows it (a story's bars, the account, the reply box), full size. Works on an image field (binary) or a picture
 * address (char). */
import { Component } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { isBinarySize } from "@web/core/utils/binary";
import { imageUrl } from "@web/core/utils/urls";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class MarketingPhoneDialog extends Component {
    static template = "meta_connector.MarketingPhoneDialog";
    static components = { Dialog };
    static props = { src: String, shape: { type: String, optional: true }, title: { type: String, optional: true },
                     close: Function };
}

export class MarketingPictureField extends Component {
    static template = "meta_connector.MarketingPictureField";
    static props = {
        ...standardFieldProps,
        width: { type: Number, optional: true },
        height: { type: Number, optional: true },
        shapeField: { type: String, optional: true },
        shape: { type: String, optional: true },
    };

    setup() {
        this.dialog = useService("dialog");
    }

    get value() {
        return this.props.record.data[this.props.name];
    }

    get src() {
        const value = this.value;
        if (!value) {
            return "";
        }
        if (this.props.record.fields[this.props.name].type === "char") {
            return value;
        }
        if (isBinarySize(value)) {
            return imageUrl(this.props.record.resModel, this.props.record.resId, this.props.name, {
                unique: this.props.record.data.write_date,
            });
        }
        const mime = value.startsWith("/9j/") ? "jpeg" : "png";
        return `data:image/${mime};base64,${value}`;
    }

    get shape() {
        const field = this.props.shapeField;
        const value = field && this.props.record.data[field];
        if (value === "square" || value === "vertical") {
            return value;
        }
        return this.props.shape || "vertical";
    }

    get style() {
        const parts = [];
        if (this.props.width) {
            parts.push(`max-width: ${this.props.width}px`);
        }
        if (this.props.height) {
            parts.push(`max-height: ${this.props.height}px`);
        }
        return parts.join("; ");
    }

    openPhone(ev) {
        ev.stopPropagation();
        ev.preventDefault();
        if (!this.src) {
            return;
        }
        this.dialog.add(MarketingPhoneDialog, {
            src: this.src,
            shape: this.shape,
            title: this.props.record.data.display_name || _t("Preview"),
        });
    }
}

export const marketingPictureField = {
    component: MarketingPictureField,
    displayName: _t("Marketing picture"),
    supportedTypes: ["binary", "char"],
    fieldDependencies: [{ name: "write_date", type: "datetime" }],
    extractProps: ({ options }) => ({
        width: options.size && options.size[0] ? options.size[0] : undefined,
        height: options.size && options.size[1] ? options.size[1] : undefined,
        shapeField: options.shape_field,
        shape: options.shape,
    }),
};

registry.category("fields").add("mtbg_marketing_picture", marketingPictureField);
