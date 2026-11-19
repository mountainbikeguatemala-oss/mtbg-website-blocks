/** @odoo-module **/
/**
 * MakeID label printers (E1 and the other "new protocol" models) over Web Bluetooth: Chrome on Android, Windows,
 * macOS, Linux and ChromeOS (not iPhone / iPad). Protocol worked out from the MakeID-Life app and checked on the
 * shop's E1: status 66 06 00 10 00 84; one 0x1B frame per chunk of rows; the printer answers every frame with
 * its status. See docs in the module description.
 */
import { _t } from "@web/core/l10n/translation";

const SERVICE = "0000abf0-0000-1000-8000-00805f9b34fb";
const WRITE = "0000abf1-0000-1000-8000-00805f9b34fb";
const NOTIFY = "0000abf2-0000-1000-8000-00805f9b34fb";
const OLD_SERVICE = "49535343-fe7d-4ae5-8fa9-9fafd205e455";
const OLD_WRITE = "49535343-8841-43f4-a8d4-ecbe34729bb3";
const OLD_NOTIFY = "49535343-1e4d-4bd9-ba61-23c647249616";

const WRITE_SIZE = 20; // ATT payload at the default MTU; works everywhere
const STATUS_CMD = withChecksum([0x66, 0x06, 0x00, 0x10, 0x00]);

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function checksum(bytes, end = bytes.length) {
    let s = 0;
    for (let i = 0; i < end; i++) {
        s = (s - bytes[i]) & 0xff;
    }
    return s;
}

function withChecksum(bytes) {
    const out = new Uint8Array(bytes.length + 1);
    out.set(bytes);
    out[bytes.length] = checksum(bytes);
    return out;
}

/** LZO1X stream holding the data as one literal run (valid for the printer's LZO1X decompressor). */
function lzoLiteral(data) {
    const head = [];
    const t = data.length;
    if (t <= 238) {
        head.push(17 + t);
    } else {
        head.push(0);
        let tt = t - 18;
        while (tt > 255) {
            head.push(0);
            tt -= 255;
        }
        head.push(tt);
    }
    const out = new Uint8Array(head.length + t + 3);
    out.set(head, 0);
    out.set(data, head.length);
    out.set([0x11, 0x00, 0x00], head.length + t);
    return out;
}

export class PrinterError extends Error {
    constructor(code, message) {
        super(message);
        this.code = code;
    }
}

/** Status reply -> plain object. */
export function parseStatus(r) {
    if (!r || r.length < 6 || r[0] !== 0x66 || r[3] !== 0x10) {
        return null;
    }
    const s = {
        raw: r,
        state: r[4],
        error: r[4] & 0x3f,
        wait: Boolean(r[4] & 0x80),
        resend: Boolean(r[4] & 0x40),
        printing: r.length > 35 ? Boolean(r[35] & 0x80) : false,
        model: r.length > 11 ? String.fromCharCode(...r.slice(10, 12)).replace(/\0/g, "") : "",
        version: r.length > 37 ? `${r[36]}.${r[37]}` : "",
        headDots: 96,
        maxRows: 170,
        swap: false,
    };
    if (r.length >= 43 && r[36] * 100 + r[37] >= 130) {
        s.swap = Boolean((r[38] >> 2) & 1);
        s.headDots = ((r[39] | (r[40] << 8)) || 12) * 8;
        s.maxRows = (r[41] | (r[42] << 8)) || 170;
    }
    return s;
}

class MakeIdPrinter {
    constructor() {
        this.device = null;
        this.write = null;
        this.notify = null;
        this.buffer = [];
        this.waiter = null;
        this.status = null;
        this.onNotify = this.onNotify.bind(this);
        this.busy = false;
    }

    get supported() {
        return Boolean(globalThis.navigator?.bluetooth);
    }

    get connected() {
        return Boolean(this.device?.gatt?.connected && this.write);
    }

    get name() {
        return this.device?.name || "";
    }

    /** Must run from a click (the browser's printer chooser needs it); asks only the first time. */
    async connect({ forceChoose = false } = {}) {
        if (!this.supported) {
            throw new PrinterError("unsupported", _t("This browser has no Bluetooth printing: use Chrome on Android, Windows or Mac."));
        }
        if (this.connected && !forceChoose) {
            return;
        }
        if (!this.device || forceChoose) {
            this.device = await navigator.bluetooth.requestDevice({
                filters: [{ namePrefix: "E1" }, { services: [SERVICE] }, { namePrefix: "MakeID" }],
                optionalServices: [SERVICE, OLD_SERVICE],
            });
            this.device.addEventListener("gattserverdisconnected", () => {
                this.write = null;
                this.notify = null;
            });
        }
        let server = null;
        for (let attempt = 0; attempt < 3 && !server; attempt++) {
            try {
                server = await this.device.gatt.connect();
            } catch (error) {
                if (attempt === 2) {
                    throw new PrinterError("connect", _t("The printer did not connect: is it on and close by? (%s)", error.message));
                }
                await sleep(400);
            }
        }
        let service;
        let ids = [WRITE, NOTIFY];
        try {
            service = await server.getPrimaryService(SERVICE);
        } catch {
            service = await server.getPrimaryService(OLD_SERVICE);
            ids = [OLD_WRITE, OLD_NOTIFY];
        }
        this.write = await service.getCharacteristic(ids[0]);
        this.notify = await service.getCharacteristic(ids[1]);
        this.notify.removeEventListener("characteristicvaluechanged", this.onNotify);
        this.notify.addEventListener("characteristicvaluechanged", this.onNotify);
        await this.notify.startNotifications();
    }

    disconnect() {
        try {
            this.device?.gatt?.disconnect();
        } catch {
            // already gone
        }
    }

    onNotify(event) {
        let data = new Uint8Array(event.target.value.buffer.slice(0));
        if (data.length > 4 && data[0] === 0x23 && data[1] === 0x23) {
            data = data.slice(4);
        }
        this.buffer.push(...data);
        const b = this.buffer;
        if (this.waiter && b.length >= 3 && b.length >= (b[1] | (b[2] << 8))) {
            const reply = new Uint8Array(b);
            this.buffer = [];
            const w = this.waiter;
            this.waiter = null;
            w(reply);
        }
    }

    /** Sends one packet and waits for the printer's answer (null after the timeout). */
    async request(packet, timeout = 8000) {
        this.buffer = [];
        const answer = new Promise((resolve) => {
            this.waiter = resolve;
            setTimeout(() => {
                if (this.waiter === resolve) {
                    this.waiter = null;
                    resolve(null);
                }
            }, timeout);
        });
        for (let i = 0; i < packet.length; i += WRITE_SIZE) {
            const part = packet.slice(i, i + WRITE_SIZE);
            if (this.write.writeValueWithoutResponse) {
                await this.write.writeValueWithoutResponse(part);
            } else {
                await this.write.writeValue(part);
            }
            await sleep(4);
        }
        return answer;
    }

    async readStatus() {
        const status = parseStatus(await this.request(STATUS_CMD, 5000));
        if (!status) {
            throw new PrinterError("no_answer", _t("The printer does not answer."));
        }
        this.status = status;
        return status;
    }

    static errorMessage(status) {
        return _t("The printer reports a problem (code %s): check the labels and that the lid is closed.", status.error);
    }

    async waitReady(maxMs = 30000) {
        const until = Date.now() + maxMs;
        for (;;) {
            const s = await this.readStatus();
            if (s.error) {
                throw new PrinterError(s.error, MakeIdPrinter.errorMessage(s));
            }
            if (!s.wait) {
                return s;
            }
            if (Date.now() > until) {
                throw new PrinterError("busy", _t("The printer stays busy."));
            }
            await sleep(300);
        }
    }

    /**
     * Prints labels. labels: [{rows: Uint8Array, rowCount}] (rows built for this.status.headDots);
     * options: {darkness 1-31, gapMode "gap"|"continuous"}.
     */
    async printLabels(labels, { darkness = 15, gapMode = "gap" } = {}) {
        if (this.busy) {
            throw new PrinterError("busy", _t("Already printing."));
        }
        this.busy = true;
        try {
            const status = await this.waitReady();
            const total = labels.length;
            for (let n = 0; n < total; n++) {
                const { rows, rowCount } = labels[n];
                const bytesPerRow = rows.length / rowCount;
                const maxRows = status.maxRows;
                const chunks = Math.ceil(rowCount / maxRows);
                for (let c = 0; c < chunks; c++) {
                    const first = c * maxRows;
                    const count = Math.min(maxRows, rowCount - first);
                    let data = rows.slice(first * bytesPerRow, (first + count) * bytesPerRow);
                    if (status.swap) {
                        data = data.slice();
                        for (let i = 0; i + 1 < data.length; i += 2) {
                            [data[i], data[i + 1]] = [data[i + 1], data[i]];
                        }
                    }
                    const frame = this.frame(lzoLiteral(data), {
                        darkness, gapMode, total, number: n + 1, rowCount, count, remaining: chunks - 1 - c,
                    });
                    let tries = 0;
                    for (;;) {
                        const s = parseStatus(await this.request(frame, 15000));
                        if (!s) {
                            throw new PrinterError("no_answer", _t("The printer stopped answering."));
                        }
                        if (s.error) {
                            throw new PrinterError(s.error, MakeIdPrinter.errorMessage(s));
                        }
                        if (s.resend && tries++ < 3) {
                            await sleep(200);
                            continue;
                        }
                        if (s.wait) {
                            await this.waitReady();
                        }
                        break;
                    }
                }
            }
        } finally {
            this.busy = false;
        }
    }

    frame(payload, { darkness, gapMode, total, number, rowCount, count, remaining }) {
        const length = 17 + payload.length + 1;
        const f = new Uint8Array(length);
        const dk = Math.min(31, Math.max(1, Math.round(darkness))) | (gapMode === "continuous" ? 0xe0 : 0x20);
        f.set([
            0x66, length & 0xff, length >> 8, 0x1b, dk, 0x03,
            total & 0xff, total >> 8, number & 0xff, number >> 8, 0x01,
            rowCount & 0xff, rowCount >> 8, count & 0xff, count >> 8, remaining & 0xff, 0x00,
        ]);
        f.set(payload, 17);
        f[length - 1] = checksum(f, length - 1);
        return f;
    }
}

/** One printer connection for the whole page (every screen shares it). */
export const makeIdPrinter = new MakeIdPrinter();
