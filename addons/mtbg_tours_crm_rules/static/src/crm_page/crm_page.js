/**
 * The Contact Rules page (0.3.0: the extension's own, for a site without Tours; with Tours the same tabs are on the
 * Alert Feed's page, Rules & Alerts): its Contact rules tab and its Changes tab.
 */
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { crmRulesMethods, crmRulesState } from "../crm_tab/crm_tab";

export class CrmRulesPage extends Component {
    static template = "mtbg_tours_crm_rules.CrmRulesPage";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({ tab: this.props.action?.params?.tab === "changes" ? "changes" : "crm",
                                ...crmRulesState() });
        onWillStart(() => this.setTab(this.state.tab));
    }

    async setTab(tab) {
        this.state.tab = tab;
        if (tab === "changes") {
            await this.loadCrmChanges();
        } else {
            await this.loadCrm();
        }
    }
}
Object.assign(CrmRulesPage.prototype, crmRulesMethods);

registry.category("actions").add("mtbg_crm_rules_page", CrmRulesPage);
