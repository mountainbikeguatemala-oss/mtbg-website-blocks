/**
 * The backend menu designer (client action ``mtbg_menu_designer``): the admin's menus as an outline, arranged with
 * buttons and keys, like bullet points (owner, 2026-10-29: no drag and drop; design C of the Menu Designer Lab): on
 * each row ← out of its folder, → into the folder above, ↑ ↓ the order; its ⋯ moves it to any folder, renames, hides,
 * keeps it for some groups. Admin pages are added from a search. Saved for everyone; a module update does not undo it
 * (the server keeps the changes apart from the modules' menus). Reset: one menu, or everything.
 */
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { TOPBAR_PINNED, setTopbarSettings } from "../topbar/topbar";

const MODEL = "mtbg.menu.override";
const PRESETS = "mtbg.menu.preset";
const PAGE_LIMIT = 200;
const TOPBAR = "mtbg.topbar";
// the top bar icons the designer knows by name; any other one shows its registry key
const TOPBAR_ICONS = {
    cfd_inbox: ["fa-comments", () => _t("Messaging (Conversations)")],
    cfd_mailbox: ["fa-envelope", () => _t("Emails")],
    "mtbg_tours_alerts.alert_menu": ["fa-bell", () => _t("Notifications (Alerts)")],
    cfd_visitors_online: ["fa-globe", () => _t("Visits (visitors online)")],
    "mail.activity_menu": ["fa-clock-o", () => _t("Activities (the clock)")],
    SwitchCompanyMenu: ["fa-building", () => _t("Company")],
    "mail.messaging_menu": ["fa-comments-o", () => _t("Discuss")],
    "discuss.CallMenu": ["fa-phone", () => _t("Calls (shown during a call)")],
};

export class MenuDesigner extends Component {
    static template = "mtbg_tours_content_blocks.MenuDesigner";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.menuService = useService("menu");
        this.state = useState({
            nodes: {}, pages: [], groups: [], saved: "", deleted: [], open: {}, editing: null, groupsFor: null,
            groupSearch: "", search: "", module: "", segment: "out", treeSearch: "",
            viewAs: "", saving: false, barApp: null, barOpen: null, selected: null,
            presets: [], presetsOpen: false, presetName: "", viewAsOpen: false, viewAsSearch: "",
            menuFor: null, moveFor: null, moveSearch: "", addTo: undefined, note: null,
            topbar: null, topbarSaving: false,
        });
        this.newId = 0;
        onWillUnmount(() => clearTimeout(this.noteTimer));
        onWillStart(async () => {
            this.load(await this.orm.call(MODEL, "mtbg_designer_data", []));
            try {
                this.state.presets = await this.orm.call(PRESETS, "mtbg_presets", []);
            } catch (error) {
                console.warn("Menu presets:", error);  // the designer works on without them (e.g. a server not updated yet)
            }
            try {
                this.state.topbar = await this.orm.call(TOPBAR, "mtbg_topbar_settings", []);
            } catch (error) {
                console.warn("Top bar icons:", error);
            }
        });
    }

    load(data) {
        const nodes = {};
        for (const node of data.nodes) {
            nodes[node.id] = node;
        }
        this.state.nodes = nodes;
        this.state.pages = data.pages;
        this.state.groups = data.groups;
        this.state.deleted = [];
        this.state.groupsFor = null;
        this.state.menuFor = null;
        this.state.editing = null;
        this.state.saved = this.snapshot();
        for (const node of this.children(false)) {
            this.state.open[node.id] ??= false;
        }
        if (!this.state.nodes[this.state.barApp]) {
            this.state.barApp = this.children(false).find((n) => this.hasChildren(n))?.id || null;
            this.state.barOpen = null;
        }
    }

    // ------------------------------------------------------------------ the app's top bar (horizontal)
    get apps() {
        return this.children(false);
    }

    get barMenus() {
        return this.state.barApp ? this.children(this.state.barApp) : [];
    }

    get barOpenNode() {
        return this.state.barOpen ? this.state.nodes[this.state.barOpen] : null;
    }

    selectInBar(node) {
        // a menu picked in the tree: the top bar shows its app, with its menu of the bar open
        const path = [];
        let current = node;
        const seen = new Set();
        while (current && !seen.has(current.id)) {
            seen.add(current.id);
            path.unshift(current);
            current = current.parent ? this.state.nodes[current.parent] : null;
        }
        this.state.barApp = path[0]?.id ?? null;
        this.state.barOpen = path.length > 1 ? path[1].id : null;
        this.state.selected = node.id;
    }

    toggleBarMenu(node) {
        this.state.barOpen = this.state.barOpen === node.id ? null : node.id;
    }

    snapshot() {
        return JSON.stringify([Object.values(this.state.nodes).map((n) =>
            [n.id, n.parent, n.sequence, n.name, n.hidden, n.removed, n.group_ids]), this.state.deleted]);
    }

    get dirty() {
        return this.snapshot() !== this.state.saved;
    }

    // ------------------------------------------------------------------ the tree
    children(parent) {
        return Object.values(this.state.nodes)
            .filter((n) => (n.parent || false) === (parent || false) && !n.removed)
            .sort((a, b) => a.sequence - b.sequence || String(a.id).localeCompare(String(b.id)));
    }

    hasChildren(node) {
        return Object.values(this.state.nodes).some((n) => n.parent === node.id && !n.removed);
    }

    isInside(id, ancestor) {
        let current = this.state.nodes[id];
        const seen = new Set();
        while (current && current.parent && !seen.has(current.id)) {
            seen.add(current.id);
            if (current.parent === ancestor) {
                return true;
            }
            current = this.state.nodes[current.parent];
        }
        return false;
    }

    matches(node) {
        const text = this.state.treeSearch.trim().toLowerCase();
        if (!text) {
            return true;
        }
        const self = (n) => n.name.toLowerCase().includes(text) || (n.action_name || "").toLowerCase().includes(text);
        return self(node) || Object.values(this.state.nodes).some((n) => this.isInside(n.id, node.id) && self(n));
    }

    toggle(node) {
        this.state.open[node.id] = !this.state.open[node.id];
    }

    expandAll(open) {
        for (const node of Object.values(this.state.nodes)) {
            if (this.hasChildren(node)) {
                this.state.open[node.id] = open;
            }
        }
    }

    resequence(parent) {
        this.children(parent).forEach((n, index) => (n.sequence = (index + 1) * 10));
    }

    // ------------------------------------------------------------------ the moves (buttons and keys, no dragging)
    canMove(node, step) {
        const list = this.children(node.parent || false);
        const to = list.findIndex((n) => n.id === node.id) + step;
        return to >= 0 && to < list.length;
    }

    move(node, step) {
        if (!this.canMove(node, step)) {
            return;
        }
        const list = this.children(node.parent || false);
        const from = list.findIndex((n) => n.id === node.id);
        [list[from], list[from + step]] = [list[from + step], list[from]];
        list.forEach((n, index) => (n.sequence = (index + 1) * 10));
        this.picked(node);
    }

    /** The folder just above a row (its previous sibling, not a page): → puts the row in it, last. */
    folderAbove(node) {
        const list = this.children(node.parent || false);
        const previous = list[list.findIndex((n) => n.id === node.id) - 1];
        return previous && !previous.action ? previous : null;
    }

    /** ← out of its folder: one level up, right after the folder (an app's menu: an app of its own). */
    moveOut(node) {
        const folder = node.parent ? this.state.nodes[node.parent] : null;
        if (!folder) {
            return;
        }
        node.parent = folder.parent || false;
        node.sequence = folder.sequence + 5;
        this.resequence(node.parent);
        this.resequence(folder.id);
        this.picked(node);
    }

    moveInto(node) {
        const folder = this.folderAbove(node);
        if (folder) {
            this.moveTo(node, folder.id);
        }
    }

    /** Into any folder (``parent``), last; false: the main menu (an app of its own). */
    moveTo(node, parent) {
        const oldParent = node.parent || false;
        node.parent = parent || false;
        node.sequence = 100000;
        this.resequence(node.parent);
        if (oldParent !== node.parent) {
            this.resequence(oldParent);
        }
        if (parent) {
            this.state.open[parent] = true;
        }
        this.state.moveFor = null;
        this.picked(node);
    }

    path(node) {
        const names = [];
        let current = node;
        const seen = new Set();
        while (current && !seen.has(current.id)) {
            seen.add(current.id);
            names.unshift(current.name);
            current = current.parent ? this.state.nodes[current.parent] : null;
        }
        return names.join(" › ");
    }

    /** Removed, or inside a removed menu (not a place to move to). */
    isRemoved(node) {
        let current = node;
        const seen = new Set();
        while (current && !seen.has(current.id)) {
            seen.add(current.id);
            if (current.removed) {
                return true;
            }
            current = current.parent ? this.state.nodes[current.parent] : null;
        }
        return false;
    }

    whereText(node) {
        return node.parent ? this.path(this.state.nodes[node.parent]) : this.mainMenuLabel;
    }

    get mainMenuLabel() {
        return _t("Main menu (an app of its own)");
    }

    /** Move to…: the main menu and every folder (not the row itself or what is inside it), by path. */
    get moveTargets() {
        const node = this.state.nodes[this.state.moveFor];
        if (!node) {
            return [];
        }
        const text = this.state.moveSearch.trim().toLowerCase();
        const folders = Object.values(this.state.nodes)
            .filter((n) => !n.action && !this.isRemoved(n) && n.id !== node.id && !this.isInside(n.id, node.id))
            .map((n) => ({ id: n.id, label: this.path(n) }))
            .sort((a, b) => a.label.localeCompare(b.label));
        return [{ id: false, label: this.mainMenuLabel }, ...folders]
            .filter((t) => !text || t.label.toLowerCase().includes(text))
            .map((t) => ({ ...t, key: String(t.id), here: t.id === (node.parent || false) }));
    }

    get moveTitle() {
        return _t("Move “%s” to…", this.state.nodes[this.state.moveFor]?.name || "");
    }

    get moveWhere() {
        const node = this.state.nodes[this.state.moveFor];
        return node ? _t("Now in: %s", this.whereText(node)) : "";
    }

    openMove(node) {
        this.state.menuFor = null;
        this.state.moveSearch = "";
        this.state.moveFor = node.id;
    }

    /** A row chosen (clicked, or just moved): selected, its app shown in the top bar. */
    picked(node) {
        this.selectInBar(node);
        let current = node.parent ? this.state.nodes[node.parent] : null;
        while (current) {
            this.state.open[current.id] = true;
            current = current.parent ? this.state.nodes[current.parent] : null;
        }
    }

    toggleMenu(node) {
        this.state.menuFor = this.state.menuFor === node.id ? null : node.id;
    }

    /** The rows as shown, top to bottom (↑ ↓ pick the next one). */
    visibleRows() {
        const rows = [];
        const walk = (parent) => {
            for (const node of this.children(parent)) {
                if (!this.matches(node)) {
                    continue;
                }
                rows.push(node);
                if (this.state.open[node.id] || this.state.treeSearch.trim()) {
                    walk(node.id);
                }
            }
        };
        walk(false);
        return rows;
    }

    focusRow(id) {
        // after the render: the row keeps the keyboard
        setTimeout(() => document.querySelector(`.mtbg_md_row[data-node="${id}"]`)?.focus());
    }

    onRowKey(ev, node) {
        if (ev.target.closest("input, .mtbg_md_menu")) {
            return;
        }
        const run = (fn) => {
            ev.preventDefault();
            fn();
            this.focusRow(node.id);
        };
        if (ev.key === "Tab" && ev.shiftKey) {
            run(() => this.moveOut(node));
        } else if (ev.key === "Tab") {
            run(() => this.moveInto(node));
        } else if (ev.altKey && ev.key === "ArrowUp") {
            run(() => this.move(node, -1));
        } else if (ev.altKey && ev.key === "ArrowDown") {
            run(() => this.move(node, 1));
        } else if (ev.key === "ArrowUp" || ev.key === "ArrowDown") {
            ev.preventDefault();
            const rows = this.visibleRows();
            const next = rows[rows.findIndex((n) => n.id === node.id) + (ev.key === "ArrowUp" ? -1 : 1)];
            if (next) {
                this.picked(next);
                this.focusRow(next.id);
            }
        } else if (ev.key === "ArrowRight" && this.hasChildren(node)) {
            run(() => (this.state.open[node.id] = true));
        } else if (ev.key === "ArrowLeft" && this.hasChildren(node)) {
            run(() => (this.state.open[node.id] = false));
        } else if (ev.key === "F2") {
            run(() => (this.state.editing = node.id));
        } else if (ev.key === "Delete") {
            ev.preventDefault();
            this.removeMenu(node);
        }
    }

    // ------------------------------------------------------------------ the items
    addNode(values) {
        const id = `new-${++this.newId}`;
        const node = Object.assign({
            id, name: _t("New folder"), module_name: "", xmlid: "", parent: false, module_parent: false, sequence: 0,
            hidden: false, removed: false, group_ids: [], module_group_ids: [], designer: true, action: false, action_name: "",
            protected: false, changed: true,
        }, values);
        this.state.nodes[id] = node;
        return node;
    }

    newFolder(parent) {
        this.state.menuFor = null;
        const node = this.addNode({ parent: parent ? parent.id : false, sequence: 100000 });
        this.resequence(node.parent);
        this.picked(node);
        this.state.editing = node.id;
    }

    rename(node, value) {
        value = (value || "").trim();
        node.name = value || node.module_name || node.name;
        this.state.editing = null;
    }

    onRenameKey(ev, node) {
        if (ev.key === "Enter") {
            this.rename(node, ev.target.value);
        } else if (ev.key === "Escape") {
            this.state.editing = null;
        }
    }

    toggleHidden(node) {
        if (!node.protected) {
            node.hidden = !node.hidden;
        }
    }

    /** Out of the menus (owner, 2026-10-28: "remove an item from the menu not just hide it"): an added folder or
     * page is deleted; a module's menu (an update would bring it back) goes to the Removed list, to put back. */
    removeMenu(node) {
        this.state.menuFor = null;
        if (node.protected) {
            return;
        }
        if (node.designer) {
            this.remove(node);
        } else {
            node.removed = true;
            if (this.state.barOpen === node.id) {
                this.state.barOpen = null;
            }
        }
    }

    restore(node) {
        node.removed = false;
    }

    /** The modules' menus removed (each with what was inside it), to put back. */
    get removedNodes() {
        return Object.values(this.state.nodes).filter((n) => n.removed)
            .sort((a, b) => a.name.localeCompare(b.name));
    }

    remove(node) {
        // an added folder or page: its added children go with it, the modules' menus go back to their place
        const stack = [node.id];
        while (stack.length) {
            const id = stack.pop();
            for (const child of Object.values(this.state.nodes).filter((n) => n.parent === id)) {
                if (child.designer) {
                    stack.push(child.id);
                } else {
                    child.parent = child.module_parent;
                }
            }
            if (typeof id === "number") {
                this.state.deleted.push(id);
            }
            const action = this.state.nodes[id]?.action;
            delete this.state.nodes[id];
            if (action && !Object.values(this.state.nodes).some((n) => n.action === action)) {
                const page = this.state.pages.find((p) => p.action === action);
                if (page) {
                    page.in_menu = false;
                }
            }
        }
    }

    groupNames(node) {
        return node.group_ids.map((id) => this.state.groups.find((g) => g.id === id)?.name).filter(Boolean).join(", ");
    }

    get groupChoices() {
        const text = this.state.groupSearch.trim().toLowerCase();
        return this.state.groups.filter((g) => !text || g.name.toLowerCase().includes(text)).slice(0, 40);
    }

    toggleGroup(node, group) {
        node.group_ids = node.group_ids.includes(group.id)
            ? node.group_ids.filter((id) => id !== group.id) : [...node.group_ids, group.id];
    }

    // ------------------------------------------------------------------ check what a group sees
    memberOf(groupId) {
        return new Set(this.state.groups.find((g) => g.id === Number(groupId))?.member_of || []);
    }

    seenBy(node, member) {
        // shown to a member of the group: not hidden, its groups (the designer's, else the module's) among theirs,
        // and so for every menu above it
        let current = node;
        const seen = new Set();
        while (current && !seen.has(current.id)) {
            seen.add(current.id);
            const groups = current.group_ids.length ? current.group_ids : current.module_group_ids;
            if (current.hidden || (groups.length && !groups.some((id) => member.has(id)))) {
                return false;
            }
            current = current.parent ? this.state.nodes[current.parent] : null;
        }
        return true;
    }

    hiddenFor(node) {
        return Boolean(this.state.viewAs) && !this.seenBy(node, this.memberOf(this.state.viewAs));
    }

    pageHiddenFor(page) {
        if (!this.state.viewAs || !page.group_ids.length) {
            return false;
        }
        const member = this.memberOf(this.state.viewAs);
        return !page.group_ids.some((id) => member.has(id));
    }

    get viewAsName() {
        return this.state.groups.find((g) => g.id === Number(this.state.viewAs))?.name || "";
    }

    get viewAsPlaceholder() {
        return _t("Check visibility as…");
    }

    get viewAsChoices() {
        const text = this.state.viewAsSearch.trim().toLowerCase();
        return this.state.groups.filter((g) => !text || g.name.toLowerCase().includes(text)).slice(0, 60);
    }

    pickViewAs(id) {
        this.state.viewAs = id ? String(id) : "";
        this.state.viewAsOpen = false;
    }

    get viewAsNote() {
        return _t("Greyed, with a ⊘: not shown to %s.", this.viewAsName);
    }

    moreText(count) {
        return _t("%s more: search to narrow them down.", count);
    }

    // ------------------------------------------------------------------ the pages (left)
    get modules() {
        const seen = new Map();
        for (const page of this.state.pages) {
            if (page.module) {
                seen.set(page.module, page.module_name || page.module);
            }
        }
        return [...seen.entries()].sort((a, b) => a[1].localeCompare(b[1]));
    }

    get pageList() {
        const text = this.state.search.trim().toLowerCase();
        const segment = this.state.segment;
        return this.state.pages.filter((p) =>
            (!this.state.module || p.module === this.state.module)
            && (segment === "all" || (segment === "in") === p.in_menu)
            && (!text || p.name.toLowerCase().includes(text) || p.model.toLowerCase().includes(text))
        );
    }

    get segmentCounts() {
        const base = this.state.pages.filter((p) => !this.state.module || p.module === this.state.module);
        return { all: base.length, in: base.filter((p) => p.in_menu).length, out: base.filter((p) => !p.in_menu).length };
    }

    get shownPages() {
        return this.pageList.slice(0, PAGE_LIMIT);
    }

    /** + Page: the admin pages, searched, added into ``parent`` (false: the main menu). */
    openAdd(parent) {
        this.state.menuFor = null;
        this.state.search = "";
        this.state.addTo = parent ? parent.id : false;
    }

    get addTitle() {
        const parent = this.state.nodes[this.state.addTo];
        return _t("Add a page to %s", parent ? this.path(parent) : this.mainMenuLabel);
    }

    addPage(page) {
        const node = this.addNode({ name: page.name, action: page.action, action_name: page.name,
                                    parent: this.state.addTo || false, sequence: 100000 });
        this.resequence(node.parent);
        page.in_menu = true;
        this.state.addTo = undefined;
        this.picked(node);
    }

    /** What just happened, in the page's own head (not a toast: toasts sat over the Presets button, www 2026-10-29). */
    say(text, type = "success") {
        this.state.note = { text, type };
        clearTimeout(this.noteTimer);
        this.noteTimer = setTimeout(() => (this.state.note = null), 5000);
    }

    // ------------------------------------------------------------------ the top bar icons (saved as soon as changed)
    /** The icons left to right: the kept order, then the ones not in it yet (they show on the left: first here). */
    get topbarRows() {
        if (!this.state.topbar) {
            return [];
        }
        const present = registry.category("systray").getEntries().map(([key]) => key).reverse()
            .filter((key) => !TOPBAR_PINNED.includes(key));
        const kept = this.state.topbar.items;
        const keys = [...present.filter((key) => !kept.some((item) => item.key === key)), ...kept.map((item) => item.key)];
        return keys.map((key) => {
            const [icon, label] = TOPBAR_ICONS[key] || ["fa-circle-o", () => key];
            return { key, icon, label: label(), hidden: kept.find((item) => item.key === key)?.hidden || false,
                     present: present.includes(key) };
        });
    }

    get hideText() {
        return _t("Hide it from the top bar");
    }

    get showText() {
        return _t("Show it in the top bar");
    }

    async saveTopbar(items, companyName) {
        this.state.topbarSaving = true;
        try {
            const settings = await this.orm.call(TOPBAR, "mtbg_topbar_save", [], {
                items: items?.map((row) => ({ key: row.key, hidden: row.hidden })), company_name: companyName,
            });
            this.state.topbar = settings;
            setTopbarSettings(settings);
            this.say(_t("The top bar is saved, for everyone."));
        } finally {
            this.state.topbarSaving = false;
        }
    }

    topbarMove(row, step) {
        const rows = this.topbarRows;
        const index = rows.findIndex((r) => r.key === row.key);
        const to = index + step;
        if (index < 0 || to < 0 || to >= rows.length) {
            return;
        }
        [rows[index], rows[to]] = [rows[to], rows[index]];
        this.saveTopbar(rows).then(() => requestAnimationFrame(() => this.focusTopbar(row.key)));
    }

    topbarToggle(row) {
        this.saveTopbar(this.topbarRows.map((r) => (r.key === row.key ? { ...r, hidden: !r.hidden } : r)));
    }

    topbarCompanyName(ev) {
        this.saveTopbar(undefined, ev.target.checked);
    }

    focusTopbar(key) {
        document.querySelector(`.mtbg_md_topbar_icons [data-key="${CSS.escape(key)}"]`)?.focus();
    }

    onTopbarKey(ev, row) {
        const rows = this.topbarRows;
        const index = rows.findIndex((r) => r.key === row.key);
        if (ev.altKey && (ev.key === "ArrowUp" || ev.key === "ArrowDown")) {
            this.topbarMove(row, ev.key === "ArrowUp" ? -1 : 1);
        } else if (ev.key === "ArrowUp" || ev.key === "ArrowDown") {
            const next = rows[index + (ev.key === "ArrowUp" ? -1 : 1)];
            if (next) {
                this.focusTopbar(next.key);
            }
        } else {
            return;
        }
        ev.preventDefault();
    }

    resetTopbar() {
        this.dialog.add(ConfirmationDialog, {
            body: _t("Put the top bar icons back in the default order, all shown, the company name off?"),
            confirm: async () => {
                const settings = await this.orm.call(TOPBAR, "mtbg_topbar_reset", []);
                this.state.topbar = settings;
                setTopbarSettings(settings);
                this.say(_t("The top bar is saved, for everyone."));
            },
            cancel: () => {},
        });
    }

    // ------------------------------------------------------------------ save, discard, reset
    async save() {
        this.state.saving = true;
        try {
            const nodes = Object.values(this.state.nodes).map((n) => ({
                id: n.id, parent: n.parent || false, sequence: n.sequence, name: n.name, hidden: n.hidden, removed: n.removed,
                group_ids: n.group_ids, action: n.designer ? n.action : undefined,
            }));
            this.load(await this.orm.call(MODEL, "mtbg_designer_save", [nodes, this.state.deleted]));
            await this.menuService.reload();
            this.say(_t("The menus are saved, for everyone."));
        } finally {
            this.state.saving = false;
        }
    }

    async discard() {
        this.load(await this.orm.call(MODEL, "mtbg_designer_data", []));
    }

    resetOne(node) {
        this.dialog.add(ConfirmationDialog, {
            body: _t("Put “%s” back as its module has it (name, place, order, visibility)? Unsaved changes are lost.", node.name),
            confirm: async () => {
                this.load(await this.orm.call(MODEL, "mtbg_designer_reset", [[node.id]]));
                await this.menuService.reload();
            },
            cancel: () => {},
        });
    }

    // ------------------------------------------------------------------ presets
    applyPreset(preset) {
        this.state.presetsOpen = false;
        this.dialog.add(ConfirmationDialog, {
            body: _t("Use the preset “%s” for everyone? It replaces the menus' layout now (unsaved changes are lost).", preset.name),
            confirm: async () => {
                this.load(await this.orm.call(PRESETS, "mtbg_preset_apply", [preset.key]));
                await this.menuService.reload();
                this.say(_t("The preset “%s” is in use.", preset.name));
            },
            cancel: () => {},
        });
    }

    async savePreset() {
        const name = this.state.presetName.trim();
        if (!name) {
            return;
        }
        if (this.dirty) {
            this.say(_t("Save your changes first: a preset keeps the saved layout."), "warning");
            return;
        }
        this.state.presets = await this.orm.call(PRESETS, "mtbg_preset_save", [name]);
        this.state.presetName = "";
        this.say(_t("The layout is kept as the preset “%s”.", name));
    }

    deletePreset(preset) {
        this.dialog.add(ConfirmationDialog, {
            body: _t("Delete the preset “%s”? The menus in use stay as they are.", preset.name),
            confirm: async () => {
                this.state.presets = await this.orm.call(PRESETS, "mtbg_preset_delete", [preset.key]);
            },
            cancel: () => {},
        });
    }

    resetAll() {
        this.dialog.add(ConfirmationDialog, {
            body: _t("Put every menu back as the modules have them? The folders and pages added here are removed."),
            confirm: async () => {
                this.load(await this.orm.call(MODEL, "mtbg_designer_reset", [[]]));
                await this.menuService.reload();
            },
            cancel: () => {},
        });
    }
}

registry.category("actions").add("mtbg_menu_designer", MenuDesigner);
