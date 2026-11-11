/**
 * Each user's screen choices on the server (models/user_prefs.py), for every page of the suite (owner, 2026-11-09:
 * "permanent across sessions"): loaded with the session, saved as they change. Browser storage is lost on another
 * browser, a cleared cache or a private window; these follow the user.
 *
 *     import { getUserPref, setUserPref } from "@mtbg_backend_ui/user_prefs/user_prefs";
 *     const open = getUserPref("fold:booking.invoice_preview", false);
 *     setUserPref("fold:booking.invoice_preview", true);
 */
import { rpc } from "@web/core/network/rpc";
import { session } from "@web/session";

const prefs = session.mtbg_user_prefs || {};
const timers = {};

/** The user's choice ``key``, else ``fallback`` (undefined: none saved). */
export function getUserPref(key, fallback = undefined) {
    return key in prefs ? prefs[key] : fallback;
}

export function hasUserPref(key) {
    return key in prefs;
}

/** The user's choice ``key`` set to ``value`` (null: forgotten): at once here, on the server a moment later. */
export function setUserPref(key, value) {
    if (value === null || value === undefined) {
        delete prefs[key];
    } else {
        prefs[key] = value;
    }
    clearTimeout(timers[key]);
    timers[key] = setTimeout(() => {
        delete timers[key];
        rpc("/web/dataset/call_kw/mtbg.user.pref/mtbg_set_pref", {
            model: "mtbg.user.pref", method: "mtbg_set_pref", args: [key, value ?? null], kwargs: {},
        }).catch(() => {});  // offline or signed out: kept for this page
    }, 300);
}
