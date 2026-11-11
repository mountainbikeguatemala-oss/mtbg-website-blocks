/**
 * The one Zoho setup wizard (``mtbg.zoho.setup``), opened from the Zoho section's Connection block (and from the
 * Invoices & Payments page's "Open Zoho"): sliding cards, one step each (owner, 2026-10-26): the login; one card per
 * app (Zoho Books always; the others can be skipped) with the link to where its organization ID is and the ID,
 * checked, needed to go on (Zoho Expense's filled in from Zoho Books', usually the same, a different one can be typed:
 * owner, 2026-10-26); then the permissions (copy them, paste them in Zoho's API console, the grant code back),
 * reached only once every app is set or skipped; Invoices & Payments' Zoho Books choices; Check access.
 */
import { Component, onWillStart, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { browser } from "@web/core/browser/browser";

const MODEL = "mtbg.zoho.setup";

export class ZohoSetupDialog extends Component {
    static template = "zoho_connector.ZohoSetupDialog";
    static components = { Dialog };
    static props = ["close", "onDone?"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        // the cards, left to right: the login, one per app (Zoho Books first: always), the permissions (the grant
        // code), Zoho Books' choices for Invoices & Payments, the check; each needs the one before it
        this.state = useState({ card: 0, busy: false, error: "", start: null, scopes: "", code: "", secret: "",
                                orgs: {}, listed: null, notes: [], choices: null, values: {}, langs: [], result: null });
        onWillStart(async () => {
            const start = await this.orm.call(MODEL, "mtbg_setup_start", []);
            for (const app of start.apps) {
                app.skipped = !app.always && !app.checked;
                this.state.orgs[app.code] = start.orgs[app.code] || "";
                // a different ID from its source app's only when one saved differs
                app.different = Boolean(app.same_as && start.orgs[app.code] && start.orgs[app.code] !== start.orgs[app.same_as]);
            }
            this.state.start = start;
            await this.refreshScopes();
        });
    }

    // ------------------------------------------------------------------ the cards
    get cards() {
        const apps = this.state.start.apps.map((app) => ({ key: `app:${app.code}`, title: app.label, app }));
        return [
            { key: "login", title: _t("Login") },
            ...apps,
            { key: "permissions", title: _t("Permissions") },
            // an extension's own Zoho Books choices (e.g. Invoices & Payments'), where one is installed
            ...(this.state.start.books_step ? [{ key: "books", title: _t("Invoices & Payments") }] : []),
            { key: "done", title: _t("Check access") },
        ];
    }

    get current() {
        return this.cards[this.state.card];
    }

    get dataCentre() {
        const start = this.state.start;
        return start.data_centres.find((d) => d.key === start.data_centre) || start.data_centres[0];
    }

    sameAs(app) {
        // the app whose organization ID this one uses (Zoho Expense: Zoho Books'), unless a different one is typed
        const source = app.same_as && !app.different && this.state.start.apps.find((a) => a.code === app.same_as);
        return source && !source.skipped ? source : null;
    }

    orgValue(app) {
        return (this.state.orgs[this.sameAs(app)?.code || app.code] || "").trim();
    }

    orgValid(app) {
        return new RegExp(this.state.start.org_id_pattern).test(this.orgValue(app));
    }

    setDifferent(app, different) {
        app.different = different;
    }

    sameAsText(app) {
        return _t("Usually the same as %(source)s: organization %(id)s is used.", {
            source: this.sameAs(app).label, id: this.orgValue(app) || "—" });
    }

    useSourceText(app) {
        const source = this.state.start.apps.find((a) => a.code === app.same_as);
        return _t("Use the %s organization ID", source?.label || "");
    }

    cardDone(card) {
        // what a card needs before the next one opens
        if (card.key === "login") {
            return Boolean((this.state.start.client_id || "").trim() && (this.state.secret.trim() || this.state.start.has_secret));
        }
        if (card.app) {
            return card.app.skipped || !card.app.needs_org || this.orgValid(card.app);
        }
        return false;  // the permissions and Zoho Books cards move on by their own buttons
    }

    get canNext() {
        return this.cardDone(this.current);
    }

    get appsDone() {
        return this.state.start.apps.every((app) => this.cardDone({ app }));
    }

    reachable(index) {
        // a card further on opens once every card before it is done (the permissions: every app set or skipped)
        for (let i = 0; i < index; i++) {
            const card = this.cards[i];
            if (["permissions", "books", "done"].includes(card.key)) {
                return index <= this.furthest;
            }
            if (!this.cardDone(card)) {
                return false;
            }
        }
        return true;
    }

    get furthest() {
        const keys = this.cards.map((c) => c.key);
        if (this.state.result) {
            return keys.indexOf("done");
        }
        if (this.state.choices) {
            return keys.indexOf("books");
        }
        return keys.indexOf("permissions");
    }

    go(index) {
        if (index >= 0 && index < this.cards.length && this.reachable(index)) {
            this.state.error = "";
            this.state.card = index;
        }
    }

    next() {
        if (this.canNext) {
            this.go(this.state.card + 1);
        }
    }

    back() {
        this.go(this.state.card - 1);
    }

    // ------------------------------------------------------------------ the apps
    get includedApps() {
        return this.state.start.apps.filter((a) => a.always || !a.skipped).map((a) => a.code);
    }

    async refreshScopes() {
        this.state.scopes = await this.orm.call(MODEL, "mtbg_setup_scopes", [this.includedApps]);
    }

    async skip(app, skipped) {
        app.skipped = !app.always && skipped;
        await this.refreshScopes();
        if (skipped) {
            this.next();
        }
    }

    openOrgText(app) {
        return _t("Open %s to copy the organization ID", app.label);
    }

    get permissionsLabel() {
        return _t("Permissions (for %s apps)", this.includedApps.length);
    }

    get missingGrantText() {
        // the apps chosen that the saved login was not granted (a new grant code adds them)
        const missing = this.state.start.apps.filter((a) => (a.always || !a.skipped) && !a.granted).map((a) => a.label);
        return this.state.start.connected && missing.length
            ? _t("This login does not have the permissions of %s yet: make a new grant code below to add them.", missing.join(", "))
            : "";
    }

    async copyScopes() {
        await browser.navigator.clipboard.writeText(this.state.scopes);
        this.notification.add(_t("Permissions copied: paste them into Generate Code."), { type: "success" });
    }

    // ------------------------------------------------------------------ Zoho
    async run(fn) {
        this.state.busy = true;
        this.state.error = "";
        try {
            return await fn();
        } finally {
            this.state.busy = false;
        }
    }

    checkOrgs(res) {
        // the organizations the login reaches: each one typed must be one of them (when Zoho lists them)
        this.state.notes = res.notes || [];
        for (const app of this.state.start.apps) {
            const listed = res.orgs?.[app.code]?.listed || [];
            const typed = this.orgValue(app);
            if (app.skipped || !app.needs_org || !listed.length) {
                continue;
            }
            if (!listed.some((org) => String(org.id) === typed)) {
                this.state.error = _t("%(app)s: organization %(id)s is not one this login reaches (it reaches: %(list)s).", {
                    app: app.label, id: typed, list: listed.map((o) => `${o.name} ${o.id}`).join(", ") });
                this.state.card = this.cards.findIndex((c) => c.app === app);
                return false;
            }
        }
        return true;
    }

    async saveOrgs() {
        const orgs = Object.fromEntries(this.state.start.apps.filter((a) => a.needs_org && !a.skipped)
            .map((a) => [a.code, this.orgValue(a)]));
        const res = await this.orm.call(MODEL, "mtbg_setup_save_orgs", [orgs]);
        if (!res.ok) {
            this.state.error = res.message;
            return;
        }
        this.state.choices = res;
        this.state.values = { ...(res.values || {}) };
        this.state.langs = res.langs || [];
        if (!this.state.start.books_step) {
            await this.finish();
            return;
        }
        this.go(this.cards.findIndex((c) => c.key === "books"));
    }

    connect() {
        return this.run(async () => {
            const start = this.state.start;
            const res = await this.orm.call(MODEL, "mtbg_setup_connect", [
                start.data_centre, start.client_id, this.state.secret, this.state.code, this.includedApps]);
            if (!res.ok) {
                this.state.error = res.message;
                return;
            }
            if (this.checkOrgs(res)) {
                await this.saveOrgs();
            }
        });
    }

    keepLogin() {
        return this.run(async () => {
            const res = await this.orm.call(MODEL, "mtbg_setup_orgs", []);
            if (!res.ok) {
                this.state.error = res.message;
                return;
            }
            if (this.checkOrgs(res)) {
                await this.saveOrgs();
            }
        });
    }

    finish() {
        return this.run(async () => {
            const choices = this.state.choices;
            this.state.result = await this.orm.call(MODEL, "mtbg_setup_finish", [
                this.state.values, this.state.langs, choices.contact_language?.id || false, choices.templates || []]);
            this.go(this.cards.findIndex((c) => c.key === "done"));
        });
    }

    done() {
        this.props.onDone?.();
        this.props.close();
    }
}

/** The Connection block's button: Set up Zoho (or Reconnect, once connected). */
export class ZohoSetupButton extends Component {
    static template = "zoho_connector.ZohoSetupButton";
    static props = ["*"];

    setup() {
        this.dialog = useService("dialog");
        this.action = useService("action");
    }

    open() {
        this.dialog.add(ZohoSetupDialog, { onDone: () => this.action.doAction({ type: "ir.actions.client", tag: "reload" }) });
    }
}

registry.category("view_widgets").add("mtbg_zoho_setup", { component: ZohoSetupButton });
