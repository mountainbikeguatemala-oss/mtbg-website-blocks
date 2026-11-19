import { beforeEach, describe, expect, getFixture, test } from "@odoo/hoot";
import { animationFrame, runAllTimers } from "@odoo/hoot-mock";
import { queryFirst } from "@odoo/hoot-dom";
import { mountWithCleanup, patchWithCleanup, preloadBundle } from "@web/../tests/web_test_helpers";
import { FAKE_MODEL } from "@web/../tests/views/calendar/calendar_test_helpers";
import { browser } from "@web/core/browser/browser";
import { CallbackRecorder } from "@web/search/action_hook";
import { CalendarCommonRenderer } from "@web/views/calendar/calendar_common/calendar_common_renderer";
import {
    anchoredScroll,
    clampZoom,
    maxZoom,
    pinchZoom,
    readZoom,
    writeZoom,
    zoomKey,
} from "@mtbg_backend_ui/calendar_zoom/calendar_zoom";

describe.current.tags("desktop");

const FAKE_PROPS = {
    model: FAKE_MODEL,
    createRecord() {},
    deleteRecord() {},
    editRecord() {},
    callbackRecorder: new CallbackRecorder(),
    onSquareSelection() {},
    cleanSquareSelection() {},
};

async function start(scale) {
    const target = document.createElement("div");
    target.style.cssText = "width: 400px; height: 600px; display: flex; flex-direction: column;";
    getFixture().append(target);
    const renderer = await mountWithCleanup(CalendarCommonRenderer, {
        props: { ...FAKE_PROPS, model: { ...FAKE_MODEL, scale } },
        target,
    });
    await animationFrame();
    return renderer;
}

function touch(el, x, y, id) {
    return new Touch({ identifier: id, target: el, clientX: x, clientY: y });
}

preloadBundle("web.fullcalendar_lib");
beforeEach(() => {
    luxon.Settings.defaultZone = "UTC+1";
});

test("mtbg_calendar_zoom: the zoom's arithmetic", () => {
    // 7 days on a 400px screen with a 40px hours column: one day per screen at (7 * 360 + 40) / 400
    expect(maxZoom(7, 400, 40)).toBe(6.4);
    expect(maxZoom(1, 400, 40)).toBe(1);
    expect(maxZoom(0, 400, 40)).toBe(1);
    expect(clampZoom(0.5, 6.4)).toBe(1);
    expect(clampZoom(9, 6.4)).toBe(6.4);
    expect(clampZoom(NaN, 6.4)).toBe(1);
    expect(pinchZoom(1, 100, 250, 6.4)).toBe(2.5);
    expect(pinchZoom(2, 100, 10, 6.4)).toBe(1);
    // the point under the fingers stays put: 200px in at 400px wide = 400px in at 800px wide
    expect(anchoredScroll(0, 200, 400, 800)).toBe(200);
    expect(anchoredScroll(100, 0, 400, 200)).toBe(50);
    expect(zoomKey("res.partner", "week")).toBe("mtbg_backend_ui.calendar_zoom.res.partner.week");
});

test("mtbg_calendar_zoom: kept per device, survives blocked storage", () => {
    const key = zoomKey("x.model", "week");
    writeZoom(key, 2.5);
    expect(readZoom(key)).toBe(2.5);
    writeZoom(key, 1);
    expect(browser.localStorage.getItem(key)).toBe(null);
    expect(readZoom(key)).toBe(1);
    patchWithCleanup(browser.localStorage, {
        getItem() {
            throw new Error("blocked");
        },
        setItem() {
            throw new Error("blocked");
        },
    });
    expect(readZoom(key)).toBe(1);
    writeZoom(key, 2);  // no error: just not remembered
});

test("mtbg_calendar_zoom: Ctrl + wheel widens the week, the hours stay", async () => {
    const renderer = await start("week");
    const root = queryFirst(".o_calendar_widget.fc");
    expect(root).toHaveClass("o_mtbg_cal_zoomable");
    expect(root).not.toHaveClass("o_mtbg_cal_zoomed");
    const harness = root.querySelector(".fc-view-harness");
    const before = harness.getBoundingClientRect().width;

    root.dispatchEvent(
        new WheelEvent("wheel", { ctrlKey: true, deltaY: -100, clientX: 200, bubbles: true, cancelable: true })
    );
    await animationFrame();
    expect(root).toHaveClass("o_mtbg_cal_zoomed");
    expect(renderer.mtbgZoom.zoom).toBeGreaterThan(2);
    expect(harness.getBoundingClientRect().width).toBeGreaterThan(before * 2);
    expect(root.scrollLeft).toBeGreaterThan(0);
    // the hours column follows the scroll
    expect(root.style.getPropertyValue("--mtbg-cal-x")).toBe(`${root.scrollLeft}px`);
    await runAllTimers();
    expect(readZoom(zoomKey("event", "week"))).toBe(Number(renderer.mtbgZoom.zoom.toFixed(3)));

    // never wider than about one day per screen, never narrower than the screen
    renderer.mtbgZoom.setZoom(100);
    expect(renderer.mtbgZoom.zoom).toBeLessThan(7.01);
    renderer.mtbgZoom.setZoom(0.2);
    expect(renderer.mtbgZoom.zoom).toBe(1);
    expect(root).not.toHaveClass("o_mtbg_cal_zoomed");
    expect(readZoom(zoomKey("event", "week"))).toBe(1);
});

test("mtbg_calendar_zoom: a two-finger pinch zooms, the swipe to next week does not run", async () => {
    const renderer = await start("week");
    const root = queryFirst(".o_calendar_widget.fc");
    let reachedParent = 0;
    const count = () => reachedParent++;
    root.parentElement.addEventListener("touchmove", count);
    root.parentElement.addEventListener("touchend", count);

    const start1 = [touch(root, 150, 300, 1), touch(root, 250, 300, 2)];
    root.dispatchEvent(new TouchEvent("touchstart", { touches: start1, bubbles: true, cancelable: true }));
    const moved = [touch(root, 50, 300, 1), touch(root, 350, 300, 2)];
    root.dispatchEvent(new TouchEvent("touchmove", { touches: moved, bubbles: true, cancelable: true }));
    await animationFrame();
    root.dispatchEvent(new TouchEvent("touchend", { touches: [], bubbles: true, cancelable: true }));

    expect(renderer.mtbgZoom.zoom).toBe(3);
    expect(root).toHaveClass("o_mtbg_cal_zoomed");
    expect(reachedParent).toBe(0);
    await runAllTimers();
    expect(readZoom(zoomKey("event", "week"))).toBe(3);
});

test("mtbg_calendar_zoom: opened again at the kept zoom; Month is left as it is", async () => {
    writeZoom(zoomKey("event", "week"), 2);
    let renderer = await start("week");
    expect(renderer.mtbgZoom.zoom).toBe(2);
    expect(".o_calendar_widget.fc").toHaveClass("o_mtbg_cal_zoomed");

    renderer = await start("month");
    expect(renderer.mtbgZoom).toBe(null);
});
