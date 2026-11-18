/**
 * The Contact rules tabs (templates mtbg_tours_crm_rules.CrmRulesTab and CrmChangesTab): a Contact rules tab (the
 * rules by the records they look at: on/off, their days, a dry run) and a Changes tab (what the rules changed, undo).
 * Their methods, for the page that shows them: this extension's own page (crm_page) or, with Tours, the Alert Feed's
 * ("Rules & Alerts", its patch). The page has this.orm, this.action, this.notification and this.state with crm,
 * crmChanges and crmDry.
 */
import { _t } from "@web/core/l10n/translation";

export const RULE = "mtbg.crm.rule";

export const crmRulesState = () => ({ crm: null, crmChanges: null, crmDry: {} });

export const crmRulesMethods = {
    // ------------------------------------------------------------------
    // Contact rules
    // ------------------------------------------------------------------
    async loadCrm(data = null) {
        this.state.crm = data || (await this.orm.call(RULE, "mtbg_get_crm_rules", []));
    },

    async saveCrmRule(rule, values) {
        await this.loadCrm(await this.orm.call(RULE, "mtbg_save_crm_rule", [rule.id, values]));
    },

    setCrmDays(rule, value) {
        const days = parseInt(value);
        if (Number.isNaN(days) || days < 0) {
            this.notification.add(_t("The days are a number from 0."), { type: "warning" });
            return;
        }
        return this.saveCrmRule(rule, { days });
    },

    async dryRun(rule) {
        this.state.crmDry[rule.id] = { loading: true };
        try {
            this.state.crmDry[rule.id] = await this.orm.call(RULE, "mtbg_crm_dry_run", [rule.id]);
        } catch (error) {
            delete this.state.crmDry[rule.id];
            throw error;
        }
    },

    closeDry(rule) {
        delete this.state.crmDry[rule.id];
    },

    // ------------------------------------------------------------------
    // Changes
    // ------------------------------------------------------------------
    async loadCrmChanges(data = null) {
        this.state.crmChanges = data || (await this.orm.call(RULE, "mtbg_get_crm_changes", []));
    },

    async undoChange(change) {
        await this.loadCrmChanges(await this.orm.call(RULE, "mtbg_undo_crm_changes", [[change.id]]));
        this.notification.add(_t("Put back."), { type: "success" });
    },

    async resolveChange(change) {
        await this.loadCrmChanges(await this.orm.call(RULE, "mtbg_resolve_crm_alert", [change.id]));
    },

    openRecord(change) {
        return this.action.doAction({ type: "ir.actions.act_window", res_model: change.res_model,
                                      res_id: change.res_id, views: [[false, "form"]] });
    },
};
