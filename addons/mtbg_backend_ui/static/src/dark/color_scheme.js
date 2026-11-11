/** @odoo-module **/
/**
 * Dark mode for the whole admin: a switch in the user menu. The choice is a cookie (``color_scheme``, as Odoo's own
 * dark bundle expects); the page reloads in the other bundle. The settings pages' Light / Dark switches open in the
 * admin's scheme and flip only their preview, for the visit (unsaved changes kept: no reload).
 */
import { browser } from "@web/core/browser/browser";
import { cookie } from "@web/core/browser/cookie";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";

const ONE_YEAR = 365 * 24 * 60 * 60;

/** The admin in dark (the user menu's switch): the editors' light / dark previews start from it. */
export function adminIsDark() {
    return cookie.get("color_scheme") === "dark";
}

export function darkModeItem() {
    const dark = adminIsDark();
    return {
        type: "switch",
        id: "mtbg_color_scheme",
        description: _t("Dark mode"),
        isChecked: dark,
        callback: () => {
            cookie.set("color_scheme", dark ? "light" : "dark", ONE_YEAR);
            browser.location.reload();
        },
        sequence: 35,
    };
}

registry.category("user_menuitems").add("mtbg_color_scheme", darkModeItem);
