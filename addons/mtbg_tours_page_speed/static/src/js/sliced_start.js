/**
 * Page Speed 0.11.0 (desktop INP, 2026-11-21): the page's interactions start in short slices on the visitors' pages.
 *
 * Odoo starts every interaction of the page (Odoo's and the extensions': menus, sliders, forms, galleries...) in one
 * go once its scripts have loaded: on a tour page that was one task of half a second at a slow computer's speed, and
 * a click then waited for it. Here the page's first start (the whole page, ``#wrapwrap``) starts them in the same
 * order (each interaction class in the registry's order, its elements in the page's order), but gives the page its
 * turn (a click, a frame) whenever SLICE_MS have passed; so does a bundle loaded later that adds its interactions to
 * a part of the page (``activate``, e.g. the booking form's on a tour page). Every other start (a part of the page
 * started again, the editor's) is Odoo's own. Only in the visitors' copy of the script bundle (models/lean.py): logged-in users and the
 * full pages keep Odoo's start.
 */
import { registry } from "@web/core/registry";
import { yieldToPage } from "@web/legacy/js/public/lazyloader";
import "@web/public/interaction_service";

const SLICE_MS = 30;

/** A few turns of the promises: an interaction's own start (after its willStart) runs inside the slice. */
async function settle() {
    for (let i = 0; i < 4; i++) {
        await null;
    }
}

/** The service's first start of the whole page, a slice at a time (the same checks and order as Odoo's). */
async function startInSlices(service, el, { thenOdoo = false } = {}) {
    const proms = [];
    let sliceStart = performance.now();
    for (const I of service.Interactions) {
        if (I.selector === "") {
            throw new Error(
                `The selector should be defined as a static property on the class ${I.name}, not on the instance`
            );
        }
        if (I.dynamicContent) {
            throw new Error(
                `The dynamic content object should be defined on the instance, not on the class (${I.name})`
            );
        }
        let targets;
        try {
            targets = el.matches(I.selector) ? [el, ...el.querySelectorAll(I.selector)] : el.querySelectorAll(I.selector);
            if (I.selectorHas) {
                targets = [...targets].filter((target) => !!target.querySelector(I.selectorHas));
            }
            if (I.selectorNotHas) {
                targets = [...targets].filter((target) => !target.querySelector(I.selectorNotHas));
            }
        } catch {
            const has = I.selectorHas ? ` or selectorHas: '${I.selectorHas}'` : "";
            const notHas = I.selectorNotHas ? ` or selectorNotHas: '${I.selectorNotHas}'` : "";
            proms.push(Promise.reject(new Error(
                `Could not start interaction ${I.name} (invalid selector: '${I.selector}'${has}${notHas})`
            )));
            continue;
        }
        for (const target of targets) {
            if (!el.isConnected) {
                break;
            }
            service._startInteraction(target, I, proms);
            await settle();
            if (performance.now() - sliceStart > SLICE_MS) {
                await yieldToPage();
                sliceStart = performance.now();
            }
        }
    }
    if (el === service.el) {
        service.isActive = true;
    }
    if (thenOdoo && el.isConnected) {
        // the class's own start after the slices: it finds them all running already, and starts what the public root
        // adds to it (the page's legacy widgets in that part)
        proms.push(Object.getPrototypeOf(service).startInteractions.call(service, el));
    }
    return Promise.all(proms);
}

const services = registry.category("services");
const odooService = services.get("public.interactions");
services.add("public.interactions", {
    ...odooService,
    async start(env) {
        const service = await odooService.start(env);
        let first = true;
        // (the service's first start comes once every service has started: env.isReady, after this one; any other
        // start is the class's own, as patched later by the public root: its widgets start with the interactions)
        service.startInteractions = function (el = this.el) {
            if (!first || el !== this.el || !el.isConnected) {
                return Object.getPrototypeOf(this).startInteractions.call(this, el);
            }
            first = false;
            const prom = startInSlices(this, el);
            this.proms.push(prom);
            return prom;
        };
        // a bundle loaded later registering more interactions (e.g. the booking form's on a tour page) starts them on
        // its part of the page: in slices too
        service.activate = function (Interactions, target) {
            if (!target || target === this.el) {
                return Object.getPrototypeOf(this).activate.call(this, Interactions, target);
            }
            this.Interactions = Interactions;
            this.proms.push(this.env.isReady.then(() => startInSlices(this, target, { thenOdoo: true })));
        };
        return service;
    },
}, { force: true });
