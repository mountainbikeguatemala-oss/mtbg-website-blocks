/**
 * The phone's side menu with every menu (owner, 2026-11-21: "everything that is horizontal on the main menu is in the
 * vertical (icon) menu on the mobile backend"; models/topbar.py ``phone_menu``). Odoo's side menu on a phone (the menu
 * button, top left, below 768px) lists only the open app's top bar, and a menu with its own page and menus under it
 * is a heading there (its page out of reach). With the switch on, it lists every app (the open one unfolded, a tap on
 * another unfolds it) with its whole top bar: each page a row, a menu with menus under it a heading (a tap opens its
 * own page when it has one), a menu under it that opens the same page as it left out. A computer's top bar is not
 * changed.
 */
import { useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { NavBar } from "@web/webclient/navbar/navbar";
import { topbarSettings } from "./topbar";

/** ``tree``: the menu service's tree under a menu ({id, name, xmlid, actionID, childrenTree}); the rows to show,
 * top to bottom: [{menu, depth, page (a tap opens it), heading (menus under it follow)}]. */
export function phoneMenuRows(tree, depth = 0) {
    const rows = [];
    for (const menu of tree.childrenTree || []) {
        // the same page as the menu above it (Bookings › All bookings): already its row
        if (menu.actionID && menu.actionID === tree.actionID && !(menu.childrenTree || []).length) {
            continue;
        }
        const children = phoneMenuRows(menu, depth + 1);
        if (children.length) {
            // a heading; with a page of its own, a tap on it opens that page
            rows.push({ menu, depth, heading: true, page: Boolean(menu.actionID) });
            rows.push(...children);
        } else if (menu.actionID) {
            rows.push({ menu, depth, page: true });
        }
    }
    return rows;
}

patch(NavBar.prototype, {
    setup() {
        super.setup(...arguments);
        this.mtbgTopbar = useState(topbarSettings);
        this.mtbgPhone = useState({ open: {} });
    },

    get mtbgPhoneMenu() {
        return Boolean(this.ui.isSmall && this.mtbgTopbar.phone_menu);
    },

    /** Every app with its rows (the app's own page first when it also has menus and no row opens it already: an
     * app without a page of its own opens its first menu's). */
    get mtbgPhoneApps() {
        return this.menuService.getApps().map((app) => {
            const tree = this.menuService.getMenuAsTree(app.id);
            const rows = phoneMenuRows(tree);
            if (rows.length && app.actionID && !rows.some((row) => row.page && row.menu.actionID === app.actionID)) {
                rows.unshift({ menu: app, depth: 0, page: true });
            }
            return { app, rows };
        });
    },

    mtbgPhoneIsOpen(app) {
        const open = this.mtbgPhone.open[app.id];
        return open === undefined ? this.currentApp?.id === app.id : open;
    },

    /** A tap on an app: an app with menus folds or unfolds; one without opens. */
    mtbgPhoneTapApp(entry) {
        if (!entry.rows.length) {
            return this._onMenuClicked(entry.app);
        }
        this.mtbgPhone.open[entry.app.id] = !this.mtbgPhoneIsOpen(entry.app);
    },
});
