/**
 * The Counter block (s_mtbg_counter), and any number marked data-mtbg-count (e.g. <p data-mtbg-count="60"
 * data-mtbg-count-suffix="+">60+</p> in a tour's description): counts up from 0 to the number once it is scrolled
 * into view. Options on the element: data-mtbg-count (the number), data-mtbg-count-prefix / -suffix,
 * data-mtbg-count-decimals, data-count-ms (how long, ms) and data-count-ease (the speed curve, as the Reviews blocks:
 * linear, smooth, slow, slower, log). The page's text stays the final value (search engines, no script).
 */
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

import { counterText, countOptions, countUp } from "../../js/count_up";

export class MtbgCounter extends Interaction {
    static selector = "[data-mtbg-count]";

    start() {
        const target = parseFloat(this.el.dataset.mtbgCount);
        if (Number.isNaN(target)) {
            return;
        }
        const original = this.el.textContent;
        const decimals = Math.max(0, Math.min(4, parseInt(this.el.dataset.mtbgCountDecimals) || 0));
        this.registerCleanup(countUp(this.el, target, {
            ...countOptions(this.el), decimals, format: (n) => counterText(this.el, n),
        }));
        this.registerCleanup(() => (this.el.textContent = original));
    }
}

registry.category("public.interactions").add("website_review_sync.counter", MtbgCounter);
