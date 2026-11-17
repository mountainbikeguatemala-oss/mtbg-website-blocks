import { registry } from "@web/core/registry";

// The admin on a phone (owner, 2026-11-16): a form in a dialog has finger-sized fields and buttons below 768px wide;
// on a desktop the fields keep Odoo's size; inside the Staff App (mtbg_sa) nothing changes.
function size(el) {
    const style = getComputedStyle(el);
    return { height: el.getBoundingClientRect().height, font: parseFloat(style.fontSize) };
}
function check(ok, message) {
    if (!ok) {
        throw new Error(message);
    }
}

registry.category("web_tour.tours").add("mtbg_backend_ui_mobile_fields", {
    steps: () => [
        {
            content: "Open a contact's form in a dialog",
            trigger: ".o_action_manager .o_view_controller, .o_action_manager .o_action",
            run() {
                odoo.__WOWL_DEBUG__.root.env.services.action.doAction({
                    type: "ir.actions.act_window", res_model: "res.partner", name: "Mobile fields",
                    views: [[false, "form"]], target: "new",
                });
            },
        },
        {
            content: "The fields, the label and the buttons measured",
            trigger: ".modal .o_form_view .o_field_widget[name='email'] input",
            run() {
                const small = window.innerWidth < 768;
                const input = this.anchor;
                const button = document.querySelector(".modal .modal-footer .btn-primary");
                const label = document.querySelector(".modal .o_form_label");
                const i = size(input), b = size(button), l = size(label);
                console.log(`mtbg mobile fields: width ${window.innerWidth} input ${i.height}px/${i.font}px ` +
                            `button ${b.height}px/${b.font}px label ${l.font}px`);
                if (small) {
                    check(i.height >= 44, `phone: the input is ${i.height}px high (44 at least)`);
                    check(i.font >= 16, `phone: the input's text is ${i.font}px (16 at least)`);
                    check(b.height >= 44, `phone: the dialog button is ${b.height}px high (44 at least)`);
                    check(l.font >= 16, `phone: the label is ${l.font}px (16 at least)`);
                    check(getComputedStyle(button.closest(".modal-footer")).position === "sticky",
                          "phone: the dialog's buttons stay in reach (sticky footer)");
                    // the Staff App on screen: its own styles, nothing of these
                    const sa = document.createElement("div");
                    sa.className = "mtbg_sa";
                    document.body.appendChild(sa);
                    const inSa = size(input);
                    sa.remove();
                    check(inSa.height < 44, `Staff App on screen: the input is still ${inSa.height}px high`);
                } else {
                    check(i.height <= 40, `desktop: the input is ${i.height}px high (Odoo's size, 40 at most)`);
                    check(i.font < 16, `desktop: the input's text is ${i.font}px (Odoo's size)`);
                }
            },
        },
    ],
});
