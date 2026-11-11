import { Plugin } from "@html_editor/plugin";
import { registry } from "@web/core/registry";
import { BuilderAction } from "@html_builder/core/builder_action";
import { rpc } from "@web/core/network/rpc";
import { blockRecordId, blockSource, knownSources, loadSources, pageRecordId, pickedIds, TiledGalleryOption } from "./gallery_option";

/** The attachment ids of the pictures chosen in the media dialog ([] if closed). */
async function chooseImages(media) {
    let images = [];
    await new Promise((resolve) => {
        const onClose = media.openMediaDialog({
            onlyImages: true,
            multiImages: true,
            save: (selected) => {
                images = selected;
                resolve();
            },
        });
        onClose.then(resolve);
    });
    return images.map((img) => img.dataset.attachmentId).filter(Boolean);
}

/** Pictures chosen in the media dialog, added after the block's own. */
class MtbgGalleryAddPicturesAction extends BuilderAction {
    static id = "mtbgGalleryAddPictures";
    static dependencies = ["media"];

    load() {
        return chooseImages(this.dependencies.media);
    }
    apply({ editingElement, loadResult }) {
        const ids = pickedIds(editingElement.dataset.gallery) || [];
        for (const id of loadResult || []) {
            if (!ids.includes(String(id))) {
                ids.push(String(id));
            }
        }
        editingElement.dataset.gallery = `ids:${ids.join(",")}`;
    }
}

/** Pictures chosen in the media dialog, added to the gallery of the record the block shows (e.g. a tour's Media
 * Library). */
class MtbgGalleryAddToRecordAction extends BuilderAction {
    static id = "mtbgGalleryAddToRecord";
    static dependencies = ["media"];

    async load({ editingElement }) {
        const ids = await chooseImages(this.dependencies.media);
        const source = blockSource(editingElement);
        if (ids.length && source) {
            await rpc("/mtbg_tours_gallery/record_add", {
                kind: source.kind, res_id: Number(blockRecordId(editingElement)), attachment_ids: ids.map(Number),
            });
        }
        return ids.length;
    }
    apply({ editingElement, loadResult }) {
        if (loadResult) {
            // the tiles are fetched again (the attribute is never saved)
            editingElement.dataset.mtbgRefresh = String(Date.now());
        }
    }
}

/** A source's record picker (searchable): its value is {"id": record}; the page's own record is saved as
 * "<kind>:page" (e.g. the tour page's gallery, shared by every tour page, each showing its own tour). */
class MtbgGalleryRecordAction extends BuilderAction {
    static id = "mtbgGalleryRecord";

    getValue({ editingElement }) {
        const id = blockRecordId(editingElement);
        return id ? JSON.stringify({ id: Number(id) }) : undefined;
    }
    apply({ editingElement, value }) {
        const source = blockSource(editingElement);
        if (!source) {
            return;
        }
        const { id } = JSON.parse(value);
        editingElement.dataset.gallery = String(id) === String(pageRecordId(editingElement, source))
            ? `${source.kind}:page` : `${source.kind}:${id}`;
    }
}

class MtbgGalleryRemovePicturesAction extends BuilderAction {
    static id = "mtbgGalleryRemovePictures";

    apply({ editingElement }) {
        editingElement.dataset.gallery = "ids:";
    }
}

class MtbgGalleryOptionPlugin extends Plugin {
    static id = "mtbgGalleryOption";

    setup() {
        loadSources(); // the record galleries offered (asked once), for the options and the drop below
    }
    /** @type {import("plugins").WebsiteResources} */
    resources = {
        builder_options: [TiledGalleryOption],
        builder_actions: {
            MtbgGalleryAddPicturesAction, MtbgGalleryAddToRecordAction, MtbgGalleryRemovePicturesAction, MtbgGalleryRecordAction,
        },
        // dropped on a record's page (e.g. a tour page): that record's gallery
        on_snippet_dropped_handlers: ({ snippetEl }) => {
            if (snippetEl.matches(".s_mtbg_gallery") && !snippetEl.dataset.gallery) {
                const source = knownSources().find((s) => pageRecordId(snippetEl, s));
                if (source) {
                    snippetEl.dataset.gallery = `${source.kind}:page`;
                }
            }
        },
        // droppable next to content in sections and columns, and in page areas / HTML fields
        so_content_addition_selector: [".s_mtbg_gallery"],
        so_snippet_addition_selector: [".s_mtbg_gallery"],
        // only the block and what it shows are saved, never the tiles
        clean_for_save_handlers: ({ root }) => {
            for (const el of root.querySelectorAll(".o_mtbg_gallery_generated")) {
                el.remove();
            }
            for (const el of root.querySelectorAll(".s_mtbg_gallery_placeholder.d-none")) {
                el.classList.remove("d-none");
            }
            for (const el of root.querySelectorAll(".s_mtbg_gallery[data-mtbg-refresh]")) {
                delete el.dataset.mtbgRefresh;
            }
        },
    };
}

registry.category("website-plugins").add(MtbgGalleryOptionPlugin.id, MtbgGalleryOptionPlugin);
