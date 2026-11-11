/**
 * The Zoho page's sub-extension cards (``mtbg.zoho.subextension``): one per Zoho integration, at the top of its block
 * on the settings page (``<widget name="mtbg_zoho_card" card="unit_expenses"/>``), or every card without a block of
 * its own (``card="others"``). Name, what it does, versions, status, its Zoho app's On / Writes allowed, Sync now, its
 * pages, Install / Update through the updater.
 */
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const MODEL = "mtbg.zoho.subextension";
// one load for every card of the page (and a switch changes them all: an app is shared by its cards)
const shared = { data: null, promise: null, loadedAt: 0, listeners: new Set() };
const FRESH_MS = 3000;  // the cards of one page share a load; the page opened again loads anew

export class ZohoCard extends Component {
    static template = "zoho_connector.ZohoCard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({ data: shared.data, busy: false });
        const listener = (data) => { this.state.data = data; };
        shared.listeners.add(listener);
        onWillUnmount(() => shared.listeners.delete(listener));
        onWillStart(() => this.load());
    }

    async load(force = false) {
        if (force || !shared.promise || Date.now() - shared.loadedAt > FRESH_MS) {
            shared.loadedAt = Date.now();
            shared.promise = this.orm.call(MODEL, "mtbg_cards", []);
        }
        this.publish(await shared.promise);
    }

    publish(data) {
        shared.data = data;
        for (const listener of shared.listeners) {
            listener(data);
        }
    }

    get cards() {
        const cards = this.state.data?.cards || [];
        if (this.props.card === "others") {
            return cards.filter((card) => !card.block);
        }
        return cards.filter((card) => card.key === this.props.card);
    }

    statusLabel(card) {
        return {
            built_in: _t("Built in"), installed: _t("Installed"), available: _t("Available"),
            needs: _t("Needs %s", card.needs.map((n) => n.title).join(", ")), unknown: _t("Not on this server"),
        }[card.status];
    }

    versionText(card) {
        if (card.version && card.newest) {
            return _t("Version %(version)s · on GitHub %(newest)s", { version: card.version, newest: card.newest });
        }
        return card.version ? _t("Version %s", card.version) : card.newest ? _t("On GitHub %s", card.newest) : "";
    }

    errorsText(card) {
        return _t("%s sync error(s)", card.errors);
    }

    onLabel(card) {
        return _t("%s: On", card.app_label);
    }

    sharedText(card) {
        return _t("(shared by every %s integration)", card.app_label);
    }

    needsText(card) {
        return _t("Installs itself once %s is switched on.", card.needs.map((n) => n.title).join(", "));
    }

    statusClass(card) {
        return { built_in: "text-bg-success", installed: "text-bg-success", available: "text-bg-info",
                 needs: "text-bg-secondary", unknown: "text-bg-light" }[card.status];
    }

    async run(promise) {
        this.state.busy = true;
        try {
            return await promise;
        } finally {
            this.state.busy = false;
        }
    }

    async setSwitch(card, which, value) {
        this.publish(await this.run(this.orm.call(MODEL, "mtbg_card_switch", [card.app, which, value])));
    }

    async sync(card) {
        const res = await this.run(this.orm.call(MODEL, "mtbg_card_sync", [card.key]));
        this.publish({ ...this.state.data, cards: res.cards });
        this.notification.add(res.message, { type: "success" });
    }

    async install(card, kind) {
        const action = await this.run(this.orm.call(MODEL, "mtbg_card_install", [card.key, kind]));
        return this.action.doAction(action);
    }

    async open(card, link) {
        return this.action.doAction(await this.orm.call(MODEL, "mtbg_card_link", [card.key, link.index]));
    }

    async errors(card) {
        return this.action.doAction(await this.orm.call(MODEL, "mtbg_section_action", ["refs", card.app]));
    }
}

/** The section's own pages: the sync log and the references (the Zoho ids of Odoo records). */
export class ZohoSection extends Component {
    static template = "zoho_connector.ZohoSection";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
    }

    async open(what) {
        return this.action.doAction(await this.orm.call(MODEL, "mtbg_section_action", [what]));
    }
}

registry.category("view_widgets").add("mtbg_zoho_card", {
    component: ZohoCard,
    extractProps: ({ attrs }) => ({ card: attrs.card }),
});
registry.category("view_widgets").add("mtbg_zoho_section", { component: ZohoSection });
