from odoo.tests import HttpCase, tagged

WAIT = """
const selectors = %r;
const wait = () => new Promise((ok, ko) => {
    let n = 0;
    const timer = setInterval(() => {
        const missing = selectors.filter((selector) => !document.querySelector(selector));
        if (!missing.length) { clearInterval(timer); ok(); }
        else if (++n > 150) { clearInterval(timer); ko(new Error("not shown: " + missing.join(", "))); }
    }, 100);
});
wait().then(() => console.log("test successful")).catch((error) => console.error(error.message));
"""


@tagged('post_install', '-at_install')
class TestCrmRulesPage(HttpCase):
    """0.3.0: the Contact Rules page (its own, without Tours) opens with its rules."""

    def test_page_opens(self):
        self.env['mtbg.crm.rule']._mtbg_sync_sources()
        self.browser_js('/odoo/action-mtbg_tours_crm_rules.action_crm_rules_page',
                        WAIT % ['.mtbg_crm_page .nav-link.active > .fa-magic', '.mtbg_crm_page .mtbg_ap_rules'],
                        "odoo.isReady", login='admin')
