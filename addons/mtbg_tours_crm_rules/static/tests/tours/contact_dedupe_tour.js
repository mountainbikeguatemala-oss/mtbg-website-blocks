import { registry } from "@web/core/registry";

// De-duplicate (2026-11-21): the contact's gear menu has no Duplicate, its De-duplicate opens Odoo's merge dialog
// with the contact and its duplicate (test_contact_dedupe.TestContactDedupeBrowser)
registry.category("web_tour.tours").add("mtbg_contact_dedupe", {
    steps: () => [
        { trigger: ".o_form_view .o_cp_action_menus button", run: "click" },
        {
            trigger: ".o-dropdown--menu .o-dropdown-item:contains(De-duplicate)",
            run() {
                const items = [...document.querySelectorAll(".o-dropdown--menu .o-dropdown-item")];
                if (items.some((item) => item.textContent.trim() === "Duplicate")) {
                    throw new Error("Duplicate is still in the contact's gear menu");
                }
            },
        },
        { trigger: ".o-dropdown--menu .o-dropdown-item:contains(De-duplicate)", run: "click" },
        {
            trigger: ".modal .o_partner_merge_wizard .o_data_row",
            run() {
                const dialog = document.querySelector(".modal .o_partner_merge_wizard");
                const text = dialog.textContent;
                for (const name of ["Ellie Tourtest", "Ellie Tourtest (copy)"]) {
                    if (!text.includes(name)) {
                        throw new Error("not in the merge dialog: " + name);
                    }
                }
                if (dialog.querySelectorAll(".o_data_row").length !== 2) {
                    throw new Error("the merge dialog should list the two contacts");
                }
            },
        },
    ],
});
