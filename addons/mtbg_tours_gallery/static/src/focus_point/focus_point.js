/**
 * Focus point (widget ``mtbg_focus_point`` on a media's focus_x): click the photo where the subject is; the tiled
 * galleries crop the photo around that point. Two previews show the crop in a wide tile and in a tall one.
 */
import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class FocusPointField extends Component {
    static template = "mtbg_tours_gallery.FocusPointField";
    static props = { ...standardFieldProps };

    get attachmentId() {
        const value = this.props.record.data.attachment_id;
        return Array.isArray(value) ? value[0] : value?.id;
    }

    get src() {
        return `/web/image/${this.attachmentId}`;
    }

    get x() {
        return this.props.record.data.focus_x ?? 50;
    }

    get y() {
        return this.props.record.data.focus_y ?? 50;
    }

    get position() {
        return `${this.x}% ${this.y}%`;
    }

    get isPicture() {
        return this.attachmentId && this.props.record.data.media_type === "image";
    }

    onClick(ev) {
        if (this.props.readonly) {
            return;
        }
        const rect = ev.currentTarget.getBoundingClientRect();
        const clamp = (v) => Math.round(Math.min(100, Math.max(0, v)));
        this.props.record.update({
            focus_x: clamp(((ev.clientX - rect.left) / rect.width) * 100),
            focus_y: clamp(((ev.clientY - rect.top) / rect.height) * 100),
        });
    }

    reset() {
        this.props.record.update({ focus_x: 50, focus_y: 50 });
    }
}

registry.category("fields").add("mtbg_focus_point", {
    component: FocusPointField,
    supportedTypes: ["integer"],
    fieldDependencies: [
        { name: "attachment_id", type: "many2one", relation: "ir.attachment" },
        { name: "focus_y", type: "integer" },
        { name: "media_type", type: "selection" },
    ],
});
