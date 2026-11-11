import { BaseOptionComponent, useDomState } from "@html_builder/core/utils";
import { onWillStart } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";

const IDS = /^ids:([\d,]*)$/;
const RECORD = /^([a-z][a-z0-9_]*):(\d+|page|)$/;

// the record galleries a block can show (other modules', e.g. Tours' "A tour's gallery": mtbg.gallery
// _mtbg_gallery_sources), asked once per editor
let sources = null;
let loaded = [];

/** The record galleries offered: [{kind, model, domain, label, record_label, search_label, add, add_label, help}]. */
export function loadSources() {
    sources ||= rpc("/mtbg_tours_gallery/sources").then((list) => (loaded = list || []));
    return sources;
}

/** The sources already known (empty until loadSources() answered). */
export function knownSources() {
    return loaded;
}

/** The id of the record of a source's kind the page holding a block shows (data-mtbg-<kind>, or the record whose HTML
 * field is edited), else "". */
export function pageRecordId(el, source) {
    return el.closest(`[data-mtbg-${source.kind}]`)?.getAttribute(`data-mtbg-${source.kind}`)
        || el.closest(`[data-oe-model="${source.model}"]`)?.dataset.oeId || "";
}

/** The picture ids of a block showing pictures chosen in the editor ("ids:12,14"), else null. */
export function pickedIds(value) {
    const match = (value || "").match(IDS);
    return match ? match[1].split(",").filter(Boolean) : null;
}

/** The record source a block shows ("<kind>:<id>", "<kind>:page", "<kind>:" still to choose), else null. */
export function blockSource(el) {
    const match = (el.dataset.gallery || "").match(RECORD);
    return (match && match[1] !== "ids" && loaded.find((s) => s.kind === match[1])) || null;
}

/** The id of the record whose gallery a block shows ("tour:12", or "tour:page": the page's), else "". */
export function blockRecordId(el) {
    const source = blockSource(el);
    if (!source) {
        return "";
    }
    const value = el.dataset.gallery.split(":")[1];
    return value === "page" ? pageRecordId(el, source) : value;
}

/** Tiled Gallery block: corners, the photos (a record's gallery, the page's own record first, or pictures chosen
 * here). */
export class TiledGalleryOption extends BaseOptionComponent {
    static template = "mtbg_tours_gallery.TiledGalleryOption";
    static selector = ".s_mtbg_gallery";

    setup() {
        super.setup();
        onWillStart(() => loadSources());
        this.domState = useDomState((editingElement) => {
            const current = editingElement.dataset.gallery || "";
            const ids = pickedIds(current);
            const source = blockSource(editingElement);
            return {
                current,
                picked: !!ids,
                count: ids ? ids.length : 0,
                source,
                record: blockRecordId(editingElement),
                pageRecords: Object.fromEntries(knownSources().map((s) => [s.kind, pageRecordId(editingElement, s)])),
            };
        });
    }

    get sources() {
        return knownSources();
    }

    /** A record source's choice: the record already shown, else the page's own record, else one still to search. */
    sourceValue(source) {
        if (this.domState.source?.kind === source.kind) {
            return this.domState.current;
        }
        return this.domState.pageRecords[source.kind] ? `${source.kind}:page` : `${source.kind}:`;
    }

    /** "Pictures I choose": keeps the pictures already chosen. */
    get pickValue() {
        return this.domState.picked ? this.domState.current : "ids:";
    }
}
