/**
 * The admin's top bar icons (Odoo's systray) in the order the Menu Designer keeps for everyone (models/topbar.py,
 * owner 2026-10-29): items by their registry key, the hidden ones left out, an item not listed (a module's new icon)
 * on the left as Odoo places it, the user menu (and the phone's menu button) always on the far right. A key of a
 * module not installed is skipped. The company switcher shows its icon only unless "Show company name" is on.
 */
import { reactive, whenReady } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";
import { NavBar } from "@web/webclient/navbar/navbar";

export const TOPBAR_PINNED = ["burger_menu", "web.user_menu"];

// what the server sent (none: a server without it, Odoo's own bar)
export const topbarSettings = reactive({ items: [], company_name: true, ...(session.mtbg_topbar || {}) });

/** ``items``: Odoo's systray items left to right ({key, ...}); returns them in the kept order. */
export function orderTopbar(items, settings) {
    const byKey = new Map(items.map((item) => [item.key, item]));
    const listed = new Set(settings.items.map((item) => item.key));
    const others = items.filter((item) => !listed.has(item.key) && !TOPBAR_PINNED.includes(item.key));
    const kept = settings.items.filter((item) => !item.hidden && byKey.has(item.key)).map((item) => byKey.get(item.key));
    const pinned = TOPBAR_PINNED.filter((key) => byKey.has(key)).map((key) => byKey.get(key));
    return [...others, ...kept, ...pinned];
}

export function applyCompanyName() {
    document.body.classList.toggle("o_mtbg_topbar_company_icon", Boolean(session.mtbg_topbar) && !topbarSettings.company_name);
}

/** New settings (the Menu Designer saved them): the top bar redrawn now, other users on their next page load. */
export function setTopbarSettings(settings) {
    Object.assign(topbarSettings, settings);
    session.mtbg_topbar = settings;
    applyCompanyName();
    registry.category("systray").trigger("UPDATE", {});
}

patch(NavBar.prototype, {
    get systrayItems() {
        const items = super.systrayItems;
        return session.mtbg_topbar ? orderTopbar(items, topbarSettings) : items;
    },
});

whenReady(applyCompanyName);
