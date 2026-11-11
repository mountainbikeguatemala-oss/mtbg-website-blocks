/**
 * Import / Export on a settings page: a model's records out as a spreadsheet (its list's columns), in through Odoo's
 * import (``<MtbgDataTransfer models="[{model, label}]"/>``).
 */
import { Component, useState } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { useService } from "@web/core/utils/hooks";

export class MtbgDataTransfer extends Component {
    static template = "mtbg_tours_core.DataTransfer";
    static props = { models: Array };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({ busy: null });
    }

    import(model) {
        return this.action.doAction({ type: "ir.actions.client", tag: "import", params: { model, context: {} } });
    }

    async export(model) {
        this.state.busy = model;
        try {
            const result = await this.orm.call("mtbg.data.transfer", "mtbg_export", [model]);
            browser.location.href = result.url;
            this.notification.add(`${result.count} records exported`, { type: "success" });
        } finally {
            this.state.busy = null;
        }
    }
}
