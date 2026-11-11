/**
 * Settings › Google: a card per Google app (like the Zoho extension's): what it does, its version and status, its
 * Google account; On and Writes allowed switches; its settings; Install when its module is not installed yet.
 */
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

export class GoogleConnectorCards extends Component {
    static template = "google_connector.Cards";
    static props = { ...standardWidgetProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ cards: [] });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.cards = await this.orm.call("google.connector.app", "google_card_data", []);
    }

    async toggle(card, field) {
        const values = { [field]: !card[field] };
        if (field === "on" && card.on) {
            values.writes_allowed = false;  // off: no writes either
        }
        await this.orm.write("google.connector.app", [card.id], values);
        await this.load();
    }

    async openSettings(card) {
        const action = await this.orm.call("google.connector.app", "action_open_settings", [[card.id]]);
        if (action) {
            this.action.doAction(action);
        }
    }

    async install(card) {
        const [module] = await this.orm.searchRead("ir.module.module", [["name", "=", card.module]], ["id"]);
        if (module) {
            await this.action.doAction(await this.orm.call("ir.module.module", "button_immediate_install", [[module.id]]));
        }
    }
}

registry.category("view_widgets").add("google_connector_cards", { component: GoogleConnectorCards });
