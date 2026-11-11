import { onWillStart, useState } from "@odoo/owl";
import { BaseOptionComponent } from "@html_builder/core/utils";
import { Plugin } from "@html_editor/plugin";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/** Form block option: which website form it shows (the Forms page's Form Designer edits them). */
export class FormBlockOption extends BaseOptionComponent {
    static template = "mtbg_tours_forms.FormBlockOption";
    static selector = ".s_mtbg_form";

    setup() {
        super.setup();
        const orm = useService("orm");
        this.state = useState({ forms: [] });
        onWillStart(async () => {
            this.state.forms = await orm.call("mtbg.form", "mtbg_block_forms", []);
        });
    }
}

class FormBlockPlugin extends Plugin {
    static id = "mtbgFormBlock";
    /** @type {import("plugins").WebsiteResources} */
    resources = {
        builder_options: [FormBlockOption],
        // the form is drawn on each visit: only its key is saved with the page
        content_not_editable_selectors: [".s_mtbg_form_body"],
        clean_for_save_handlers: ({ root }) => {
            for (const el of root.querySelectorAll(".s_mtbg_form_body")) {
                el.replaceChildren();
            }
        },
    };
}

registry.category("website-plugins").add(FormBlockPlugin.id, FormBlockPlugin);
