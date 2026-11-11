/**
 * Form block (website editor > Contact & Forms > Form): draws the website form the block names (data-form) from
 * /mtbg_forms/block, then starts it (form.js). Also in the website editor; the form is emptied before saving.
 */
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

export class FormBlock extends Interaction {
    static selector = ".s_mtbg_form";

    setup() {
        this.body = this.el.querySelector(".s_mtbg_form_body");
    }

    async willStart() {
        const key = this.el.dataset.form;
        const variant = this.el.dataset.variant || "page"; // the server keeps it only when the form has that variant
        this.html = key ? await this.waitFor(rpc("/mtbg_forms/block", { key, variant })).then((r) => r.html).catch(() => "") : "";
    }

    start() {
        if (!this.body) {
            return;
        }
        const interactions = this.services["public.interactions"];
        this.body.innerHTML = this.html;
        for (const child of [...this.body.children]) {
            interactions.startInteractions(child);
        }
        this.registerCleanup(() => {
            for (const child of [...this.body.children]) {
                interactions.stopInteractions(child);
            }
        });
    }
}

registry.category("public.interactions").add("mtbg_tours_forms.form_block", FormBlock);
registry.category("public.interactions.edit").add("mtbg_tours_forms.form_block", { Interaction: FormBlock });
