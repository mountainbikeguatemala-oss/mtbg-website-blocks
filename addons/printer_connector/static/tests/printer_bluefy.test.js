import { beforeEach, describe, expect, mockUserAgent, test } from "@odoo/hoot";
import { click, queryFirst } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import { mountWithCleanup, patchTranslations } from "@web/../tests/web_test_helpers";
import { PrinterUnsupportedNote } from "@printer_connector/label_print";
import {
    BLUEFY_APP_STORE_URL,
    isIOS,
    makeIdPrinter,
    requestOptions,
    unsupportedMessage,
    valueBytes,
} from "@printer_connector/makeid_printer";

describe.current.tags("desktop");

// the messages are _t() strings: plain English here
beforeEach(() => patchTranslations());

const SERVICE = "0000abf0-0000-1000-8000-00805f9b34fb";
const IPHONE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    + "CriOS/131.0.6778.73 Mobile/15E148 Safari/604.1";
const IPAD_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    + "Version/18.1 Safari/605.1.15";

/** A fresh printer (not the page's shared one) with a stubbed Web Bluetooth. */
function newPrinter(bluetooth = null) {
    const printer = new makeIdPrinter.constructor();
    Object.defineProperty(printer, "bluetooth", { get: () => bluetooth, configurable: true });
    return printer;
}

test("printer_connector_bluefy: iPhone and iPad (iPadOS says MacIntel) are iOS; Mac, Android are not", () => {
    expect(isIOS({ userAgent: IPHONE_UA, platform: "iPhone", maxTouchPoints: 5 })).toBe(true);
    expect(isIOS({ userAgent: IPAD_UA, platform: "MacIntel", maxTouchPoints: 5 })).toBe(true);
    expect(isIOS({ userAgent: "Mozilla/5.0 (iPad; CPU OS 12_0 like Mac OS X)", platform: "iPad" })).toBe(true);
    expect(isIOS({ userAgent: IPAD_UA, platform: "MacIntel", maxTouchPoints: 0 })).toBe(false);
    expect(isIOS({ userAgent: "Mozilla/5.0 (Linux; Android 14; Pixel 8)", platform: "Linux armv8l",
                   maxTouchPoints: 5 })).toBe(false);
    expect(isIOS(null)).toBe(false);
});

test("printer_connector_bluefy: the unsupported message sends iOS to Bluefy, others to Chrome", () => {
    expect(unsupportedMessage({ userAgent: IPHONE_UA, platform: "iPhone" })).toMatch(/Bluefy/);
    expect(unsupportedMessage({ userAgent: IPHONE_UA, platform: "iPhone" })).toMatch(/App Store/);
    const other = unsupportedMessage({ userAgent: "Mozilla/5.0 (X11; Linux x86_64) Firefox/133.0", platform: "Linux" });
    expect(other).toBe("This browser has no Bluetooth printing: use Chrome on Android, Windows or Mac.");
    expect(BLUEFY_APP_STORE_URL).toBe("https://apps.apple.com/app/id1492822055");
});

test("printer_connector_bluefy: the chooser filters by name on iOS, adds the service elsewhere", () => {
    const ios = requestOptions({ ios: true });
    expect(ios.filters).toEqual([{ namePrefix: "E1" }, { namePrefix: "MakeID" }]);
    expect(ios.filters.some((f) => f.services)).toBe(false);
    expect(ios.optionalServices).toInclude(SERVICE);
    const chrome = requestOptions({ ios: false });
    expect(chrome.filters).toEqual([{ namePrefix: "E1" }, { services: [SERVICE] }, { namePrefix: "MakeID" }]);
    const all = requestOptions({ acceptAll: true });
    expect(all.acceptAllDevices).toBe(true);
    expect("filters" in all).toBe(false);
    expect(all.optionalServices).toInclude(SERVICE);
});

test("printer_connector_bluefy: filters rejected (TypeError): the chooser again with every device", async () => {
    const calls = [];
    const device = { name: "E1-1234", addEventListener() {} };
    const printer = newPrinter({
        async requestDevice(options) {
            calls.push(options);
            if (options.filters) {
                throw new TypeError("Unsupported filter");
            }
            return device;
        },
    });
    expect(await printer.requestDevice()).toBe(device);
    expect(calls.length).toBe(2);
    expect(calls[1].acceptAllDevices).toBe(true);
});

test("printer_connector_bluefy: a closed chooser (NotFoundError) is not asked again", async () => {
    let calls = 0;
    const printer = newPrinter({
        async requestDevice() {
            calls++;
            throw new DOMException("User cancelled", "NotFoundError");
        },
    });
    await expect(printer.requestDevice()).rejects.toThrow(/User cancelled/);
    expect(calls).toBe(1);
});

test("printer_connector_bluefy: no Web Bluetooth: connect says why, nothing asked", async () => {
    const printer = newPrinter(null);
    expect(printer.supported).toBe(false);
    await expect(printer.connect()).rejects.toThrow(/Bluetooth printing|Bluefy/);
});

test("printer_connector_bluefy: a notification read from its DataView's own bytes (offset, bigger buffer)", async () => {
    // a status reply (66 len=6 00 10 state check) inside a bigger buffer, after 3 other bytes
    const reply = [0x66, 0x06, 0x00, 0x10, 0x00, 0x84];
    const big = new Uint8Array([0xaa, 0xbb, 0xcc, ...reply, 0xdd, 0xee]);
    const view = new DataView(big.buffer, 3, reply.length);
    expect([...valueBytes(view)]).toEqual(reply);
    expect([...valueBytes(new Uint8Array(reply).buffer)]).toEqual(reply);
    expect(valueBytes(null).length).toBe(0);

    const printer = newPrinter();
    let got = null;
    printer.waiter = (r) => (got = r);
    printer.onNotify({ target: { value: view } });
    expect([...got]).toEqual(reply);

    // no event target (a partial Web Bluetooth): the characteristic's value
    got = null;
    printer.waiter = (r) => (got = r);
    printer.notify = { value: new DataView(big.buffer, 3, reply.length) };
    printer.onNotify({});
    expect([...got]).toEqual(reply);
});

test("printer_connector_bluefy: write without response fails once: writeValue for the rest of the session", async () => {
    const printer = newPrinter();
    const log = [];
    printer.device = { gatt: { connected: true } };
    printer.write = {
        async writeValueWithoutResponse() {
            log.push("without");
            throw new DOMException("GATT operation not permitted", "NotSupportedError");
        },
        async writeValue(part) {
            log.push(`with:${part.length}`);
        },
    };
    await printer.writePart(new Uint8Array(20));
    await printer.writePart(new Uint8Array(5));
    expect(log).toEqual(["without", "with:20", "with:5"]);
    expect(printer.noWriteWithoutResponse).toBe(true);
});

test("printer_connector_bluefy: write without response where it works; no writeValue: writeValueWithResponse", async () => {
    const printer = newPrinter();
    const log = [];
    printer.device = { gatt: { connected: true } };
    printer.write = { async writeValueWithoutResponse() { log.push("without"); } };
    await printer.writePart(new Uint8Array(3));
    expect(log).toEqual(["without"]);

    printer.write = { async writeValueWithResponse() { log.push("withResponse"); } };
    await printer.writePart(new Uint8Array(3));
    expect(log).toEqual(["without", "withResponse"]);
});

test("printer_connector_bluefy: disconnected during a write: the error is passed on (no silent fallback)", async () => {
    const printer = newPrinter();
    printer.device = { gatt: { connected: false } };
    printer.write = {
        async writeValueWithoutResponse() {
            throw new DOMException("GATT Server is disconnected.", "NetworkError");
        },
        async writeValue() {},
    };
    await expect(printer.writePart(new Uint8Array(3))).rejects.toThrow(/disconnected/);
    expect(printer.noWriteWithoutResponse).toBe(false);
});

test("printer_connector_bluefy: on an iPhone the note says Bluefy, Copy link copies the page", async () => {
    mockUserAgent("ios");
    await mountWithCleanup(PrinterUnsupportedNote);
    const note = queryFirst(".bsx_print_unsupported");
    expect(note).toHaveText(/Bluefy/);
    expect(".bsx_print_bluefy").toHaveAttribute("href", BLUEFY_APP_STORE_URL);
    await click(".bsx_print_copy");
    await animationFrame();
    expect(".bsx_print_copied").toHaveText(/Link copied/);
    expect(await navigator.clipboard.readText()).toBe(window.location.href);
});

test("printer_connector_bluefy: elsewhere the note keeps the Chrome message, no Bluefy buttons", async () => {
    mockUserAgent("linux");
    await mountWithCleanup(PrinterUnsupportedNote);
    expect(".bsx_print_unsupported").toHaveText(
        "This browser has no Bluetooth printing: use Chrome on Android, Windows or Mac."
    );
    expect(".bsx_print_copy").toHaveCount(0);
    expect(".bsx_print_bluefy").toHaveCount(0);
});
