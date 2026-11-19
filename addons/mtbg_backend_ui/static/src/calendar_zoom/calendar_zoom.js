/**
 * Every calendar's Day and Week view zooms sideways (owner, 2026-11-18: "Calendar week view should allow horizontal
 * pinch zoom across the entire suite of extensions"): a two-finger pinch (or Ctrl + wheel / a trackpad pinch on a
 * computer) widens the day columns, from the screen's width (Odoo's look, the smallest) to about one day per screen;
 * the grid then scrolls sideways with the day header, the hours stay pinned on the left. The time scale is not
 * touched. The zoom is kept per model and view (day / week) on each device (the browser's local storage).
 *
 * A patch of Odoo's CalendarCommonRenderer, so every calendar built on it (Odoo's calendar view for any model, the
 * suite's own calendars that extend it) gets it. FullCalendar's own column width option (dayMinWidth) needs its paid
 * scroll grid, so the calendar's view harness is made wider instead (CSS variable ``--mtbg-cal-zoom``) and FullCalendar
 * lays itself out for that width.
 */
import { onWillUnmount, useEffect } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { patch } from "@web/core/utils/patch";
import { CalendarCommonRenderer } from "@web/views/calendar/calendar_common/calendar_common_renderer";

export const ZOOM_SCALES = ["day", "week"];
const KEY_PREFIX = "mtbg_backend_ui.calendar_zoom";
const EPSILON = 0.001;

/** The local storage key: one zoom per model and view (day / week), per device. */
export function zoomKey(resModel, scale) {
    return `${KEY_PREFIX}.${resModel || "_"}.${scale}`;
}

/** The widest zoom: about one day column per screen width (the hours column stays outside it). */
export function maxZoom(columns, width, axisWidth = 0) {
    if (!columns || !width || width <= axisWidth) {
        return 1;
    }
    return Math.max(1, (columns * (width - axisWidth) + axisWidth) / width);
}

export function clampZoom(zoom, max) {
    if (!Number.isFinite(zoom)) {
        return 1;
    }
    return Math.min(Math.max(zoom, 1), Math.max(1, max));
}

/** The scroll that keeps the point under ``anchorX`` (px from the scroller's left) in place when the width changes. */
export function anchoredScroll(scrollLeft, anchorX, oldWidth, newWidth) {
    if (!oldWidth) {
        return scrollLeft;
    }
    return Math.max(0, ((scrollLeft + anchorX) / oldWidth) * newWidth - anchorX);
}

/** The zoom a pinch has reached: its start zoom times how far the fingers spread. */
export function pinchZoom(startZoom, startDistance, distance, max) {
    if (!startDistance) {
        return clampZoom(startZoom, max);
    }
    return clampZoom(startZoom * (distance / startDistance), max);
}

export function readZoom(key) {
    try {
        const value = parseFloat(browser.localStorage.getItem(key));
        return Number.isFinite(value) && value >= 1 ? value : 1;
    } catch {
        return 1;
    }
}

export function writeZoom(key, zoom) {
    try {
        if (zoom <= 1 + EPSILON) {
            browser.localStorage.removeItem(key);
        } else {
            browser.localStorage.setItem(key, zoom.toFixed(3));
        }
    } catch {
        // private window or storage blocked: the zoom just isn't remembered
    }
}

function distance(t1, t2) {
    return Math.hypot(t1.clientX - t2.clientX, t1.clientY - t2.clientY);
}

/**
 * The zoom of one calendar renderer (its FullCalendar element ``component.fc.el``).
 * Returns ``{ zoom, setZoom(zoom, anchorX) }``.
 */
export function useCalendarZoom(component) {
    const scale = component.props.model.scale;
    if (!ZOOM_SCALES.includes(scale)) {
        return null;
    }
    const key = zoomKey(component.props.model.resModel, scale);
    const zoom = { value: readZoom(key) };
    let frame = null;
    let pending = null;
    let saveTimeout = null;
    let pinch = null;  // the pinch under way: { startZoom, startDistance, max }
    let pinchedThisGesture = false;  // until every finger is up: the gesture is ours (no swipe to next week)

    const el = () => component.fc.el;
    const harness = () => el()?.querySelector(":scope > .fc-view-harness");

    function currentMax() {
        const root = el();
        const columns = root.querySelectorAll(".fc-col-header-cell").length;
        const axis = root.querySelector(".fc-col-header .fc-timegrid-axis");
        return maxZoom(columns, root.clientWidth, axis ? axis.getBoundingClientRect().width : 0);
    }

    function syncAxis() {
        const root = el();
        root.style.setProperty("--mtbg-cal-x", `${root.scrollLeft}px`);
    }

    function apply(value, anchorX = null) {
        const root = el();
        const box = harness();
        if (!root || !box) {
            return;
        }
        const next = clampZoom(value, currentMax());
        const oldWidth = box.getBoundingClientRect().width;
        const zoomed = next > 1 + EPSILON;
        zoom.value = zoomed ? next : 1;
        root.classList.toggle("o_mtbg_cal_zoomed", zoomed);
        if (zoomed) {
            root.style.setProperty("--mtbg-cal-zoom", String(next));
        } else {
            root.style.removeProperty("--mtbg-cal-zoom");
        }
        const newWidth = box.getBoundingClientRect().width;
        if (Math.abs(newWidth - oldWidth) > 0.5) {
            component.fc.api?.updateSize();
        }
        if (!zoomed) {
            root.scrollLeft = 0;
        } else if (anchorX !== null) {
            root.scrollLeft = anchoredScroll(root.scrollLeft, anchorX, oldWidth, newWidth);
        }
        syncAxis();
    }

    /** At most one layout per frame while the fingers move. */
    function schedule(value, anchorX) {
        pending = { value, anchorX };
        if (frame === null) {
            frame = browser.requestAnimationFrame(() => {
                frame = null;
                const { value, anchorX } = pending;
                apply(value, anchorX);
            });
        }
    }

    function save() {
        browser.clearTimeout(saveTimeout);
        saveTimeout = browser.setTimeout(() => writeZoom(key, zoom.value), 300);
    }

    /** Opened zoomed: today's column in view (else the week's first day). */
    function scrollToToday() {
        const root = el();
        const today = root.querySelector(".fc-col-header-cell.fc-day-today");
        if (!today || !root.classList.contains("o_mtbg_cal_zoomed")) {
            return;
        }
        const axis = root.querySelector(".fc-col-header .fc-timegrid-axis");
        const axisWidth = axis ? axis.getBoundingClientRect().width : 0;
        const left = today.getBoundingClientRect().left - root.getBoundingClientRect().left + root.scrollLeft;
        root.scrollLeft = Math.max(0, left - axisWidth);
        syncAxis();
    }

    function anchorOf(clientX) {
        return clientX - el().getBoundingClientRect().left;
    }

    function onTouchStart(ev) {
        if (ev.touches.length >= 2) {
            pinchedThisGesture = true;
            pinch = {
                startZoom: zoom.value,
                startDistance: distance(ev.touches[0], ev.touches[1]),
                max: currentMax(),
            };
            ev.stopPropagation();
        } else if (!pinchedThisGesture) {
            pinch = null;
        }
    }

    function onTouchMove(ev) {
        if (!pinchedThisGesture) {
            return;
        }
        // the gesture is a pinch: not the calendar's swipe to the next / previous week
        ev.stopPropagation();
        if (pinch && ev.touches.length >= 2) {
            ev.preventDefault();
            const [t1, t2] = ev.touches;
            const value = pinchZoom(pinch.startZoom, pinch.startDistance, distance(t1, t2), pinch.max);
            schedule(value, anchorOf((t1.clientX + t2.clientX) / 2));
        }
    }

    function onTouchEnd(ev) {
        if (!pinchedThisGesture) {
            return;
        }
        ev.stopPropagation();
        if (ev.touches.length < 2 && pinch) {
            pinch = null;
            save();
        }
        if (ev.touches.length === 0) {
            pinchedThisGesture = false;
        }
    }

    function onWheel(ev) {
        if (!ev.ctrlKey) {
            return;
        }
        // Ctrl + wheel, or a trackpad pinch (the browser sends it as Ctrl + wheel): the columns, not the page
        ev.preventDefault();
        const value = clampZoom(zoom.value * Math.exp(-ev.deltaY * 0.01), currentMax());
        schedule(value, anchorOf(ev.clientX));
        save();
    }

    useEffect(
        (root) => {
            if (!root) {
                return;
            }
            root.classList.add("o_mtbg_cal_zoomable");
            const opts = { passive: false };
            root.addEventListener("touchstart", onTouchStart, opts);
            root.addEventListener("touchmove", onTouchMove, opts);
            root.addEventListener("touchend", onTouchEnd, opts);
            root.addEventListener("touchcancel", onTouchEnd, opts);
            root.addEventListener("wheel", onWheel, opts);
            root.addEventListener("scroll", syncAxis, { passive: true });
            if (zoom.value > 1 + EPSILON) {
                apply(zoom.value);
                scrollToToday();
            }
            return () => {
                root.removeEventListener("touchstart", onTouchStart, opts);
                root.removeEventListener("touchmove", onTouchMove, opts);
                root.removeEventListener("touchend", onTouchEnd, opts);
                root.removeEventListener("touchcancel", onTouchEnd, opts);
                root.removeEventListener("wheel", onWheel, opts);
                root.removeEventListener("scroll", syncAxis);
            };
        },
        () => [component.fc.el]
    );
    onWillUnmount(() => {
        if (frame !== null) {
            browser.cancelAnimationFrame(frame);
        }
        if (saveTimeout !== null) {
            browser.clearTimeout(saveTimeout);
            writeZoom(key, zoom.value);
        }
    });

    return {
        get zoom() {
            return zoom.value;
        },
        setZoom(value, anchorX = null) {
            apply(value, anchorX);
            writeZoom(key, zoom.value);
        },
    };
}

patch(CalendarCommonRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        this.mtbgZoom = useCalendarZoom(this);
    },
});
