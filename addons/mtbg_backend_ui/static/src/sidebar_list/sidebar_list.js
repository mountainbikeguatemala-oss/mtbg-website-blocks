/**
 * A list with a side bar (``js_class="mtbg_sidebar_list"``, the model inheriting ``mtbg.sidebar.mixin``), as the
 * Resources & Equipment page has: the model's records as a tree with their counts (e.g. tours and their departures),
 * following the search. A click on a branch shows its records only; again, or All, every one. Filters and groups are
 * the search's (its Filters and Group By); the folding is the side bar's, so the list's groups stay open. The cog opens
 * the model's settings page (Import / Export there).
 *
 * Core's rule (owner, 2026-10-27): every view of a model with a side bar has it, List, Cards and Kanban alike
 * (``useMtbgSidebar``: the board kanban uses it too); the branch chosen stays chosen when switching views.
 */
import { Component, reactive, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";
import { useViewModes, ViewModes } from "@mtbg_backend_ui/view_modes/view_modes";

/** The side bar hidden or shown, the same on every page, kept in this browser (owner, 2026-10-27: "vertical sidebar
 * should have expand / hide control"). */
const HIDDEN_KEY = "mtbg_tours.sidebar.hidden";

function readHidden() {
    try {
        return window.localStorage.getItem(HIDDEN_KEY) === "1";
    } catch {
        return false;
    }
}

export const sidebarDisplay = reactive({ hidden: readHidden() });

export function toggleSidebarHidden() {
    sidebarDisplay.hidden = !sidebarDisplay.hidden;
    try {
        window.localStorage.setItem(HIDDEN_KEY, sidebarDisplay.hidden ? "1" : "0");
    } catch {
        // the choice lasts this page only
    }
}

/** The side bar: sections, their branches (folding), the one chosen; hidden to a thin strip and shown again. */
export class MtbgSidebar extends Component {
    static template = "mtbg_tours_core.Sidebar";
    static props = ["sidebar", "onSelect"];

    setup() {
        this.state = useState({ folded: {}, open: {} });
        this.display = useState(sidebarDisplay);
    }

    toggleHidden() {
        toggleSidebarHidden();
    }

    /** A section is open unless folded; a branch with children closed unless opened (or holding the choice). */
    isOpen(node, isSection = false) {
        if (isSection) {
            return !this.state.folded[node.key];
        }
        if (node.key in this.state.open) {
            return this.state.open[node.key];
        }
        const chosen = this.props.sidebar.selected?.key;
        return !!chosen && (node.children || []).some((c) => c.key === chosen);
    }

    toggle(node, isSection = false) {
        if (isSection) {
            this.state.folded[node.key] = !this.state.folded[node.key];
        } else {
            this.state.open[node.key] = !this.isOpen(node);
        }
    }

    isChosen(node) {
        return this.props.sidebar.selected?.key === node.key;
    }
}

/** The branch chosen on a model's page, kept while switching its views (this tab only). */
const chosenKey = (model, context) => `mtbg_tours.sidebar.${model}.${context?.mtbg_scope || ""}`;

function readChosen(model, context) {
    try {
        return JSON.parse(window.sessionStorage.getItem(chosenKey(model, context)) || "null");
    } catch {
        return null;
    }
}

function writeChosen(model, context, node) {
    try {
        window.sessionStorage.setItem(chosenKey(model, context), JSON.stringify(node));
    } catch {
        // the choice lasts this view only
    }
}

/** The branches' keys, at every level. */
function sidebarKeys(sections) {
    const keys = new Set();
    const walk = (nodes) => (nodes || []).forEach((n) => {
        keys.add(n.key);
        walk(n.children);
    });
    sections.forEach((section) => walk(section.nodes));
    return keys;
}

/**
 * A view's side bar, in its controller's setup (the list's and the board kanban's): its state, its load following
 * the search, the chosen branch's records only. ``enabled()``: whether the model has one. Returns the state; the
 * controller's model loads through ``wrapLoad``.
 */
export function useMtbgSidebar(controller, enabled = () => true) {
    const orm = useService("orm");
    const { resModel, context } = controller.props;
    const sidebar = useState({ sections: [], total: 0, selected: readChosen(resModel, context),
                               settingsAction: false, ready: false });
    let base = controller.props.domain || [];

    async function load(domain) {
        if (!(await enabled())) {
            sidebar.selected = null;
            return;
        }
        // the page's context: a page of the model (``mtbg_scope``) has its own side bar
        const result = await orm.call(resModel, "mtbg_sidebar", [domain], { context });
        Object.assign(sidebar, { sections: result.sections, total: result.total,
                                 settingsAction: result.settings_action || false, ready: true });
    }

    return {
        sidebar,
        /** The model's load: the search's domain, narrowed to the chosen branch; the side bar counted alongside. */
        wrapLoad(load_) {
            return async (params = {}) => {
                if ("domain" in params) {
                    base = params.domain || [];
                }
                const node = sidebar.selected;
                const domain = node ? [...base, ...node.domain] : base;
                const [result] = await Promise.all([load_({ ...params, domain }), load(base)]);
                // a branch kept from another view, gone here: everything again
                if (node && sidebar.ready && !sidebarKeys(sidebar.sections).has(node.key)) {
                    sidebar.selected = null;
                    writeChosen(resModel, context, null);
                    return load_({ ...params, domain: base });
                }
                return result;
            };
        },
        get base() {
            return base;
        },
        load,
        /** A branch chosen (again: all). */
        choose(node) {
            sidebar.selected = !node || sidebar.selected?.key === node.key
                ? null : { key: node.key, domain: node.domain, label: node.label };
            writeChosen(resModel, context, sidebar.selected);
        },
    };
}

export class SidebarListController extends ListController {
    static template = "mtbg_tours_core.SidebarListView";
    static components = { ...ListController.components, MtbgSidebar, ViewModes };

    setup() {
        super.setup();
        this.mtbgAction = useService("action");
        this.mtbgSidebar = useMtbgSidebar(this, () => this.hasSidebar);
        this.sidebar = this.mtbgSidebar.sidebar;
        this.viewEntries = useViewModes(this);  // List · Cards · Kanban
        this.model.load = this.mtbgSidebar.wrapLoad(this.model.load.bind(this.model));
    }

    get sidebarBase() {
        return this.mtbgSidebar.base;
    }

    /** The groups (the search's Group By) always open: the folding is the side bar's. */
    get modelParams() {
        const params = super.modelParams;
        params.config = { ...params.config, openGroupsByDefault: true };
        return params;
    }

    /** Whether this list has a side bar (a list class shared with a model without one: override). */
    get hasSidebar() {
        return true;
    }

    loadSidebar(domain) {
        return this.mtbgSidebar.load(domain);
    }

    /** A branch chosen (again: all). */
    chooseSidebar(node) {
        this.mtbgSidebar.choose(node);
        return this.model.load({ domain: this.sidebarBase });
    }

    openSettings() {
        return this.mtbgAction.doAction(this.sidebar.settingsAction);
    }
}

export const sidebarListView = { ...listView, Controller: SidebarListController };

registry.category("views").add("mtbg_sidebar_list", sidebarListView);
