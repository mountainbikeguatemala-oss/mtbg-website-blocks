/** A receipt file as the expense form sends it (moved from the Staff App, 2026-11-07): a picture made a JPEG of at most
 *  MAX_SIDE px (fast on a tour's signal), a PDF as it is. Resolves {name, mimetype, data (base64), preview}. */
import { _t } from "@web/core/l10n/translation";

export const MAX_SIDE = 1600;

export function readReceipt(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onerror = () => reject(new Error(_t("The file could not be read.")));
        reader.onload = () => {
            const dataUrl = String(reader.result);
            if (file.type === "application/pdf") {
                resolve({ name: file.name, mimetype: file.type, data: dataUrl.split(",")[1], preview: "" });
                return;
            }
            const image = new Image();
            image.onerror = () => reject(new Error(_t("This photo could not be opened: take it again or pick a JPG.")));
            image.onload = () => {
                const scale = Math.min(1, MAX_SIDE / Math.max(image.width, image.height));
                const canvas = document.createElement("canvas");
                canvas.width = Math.round(image.width * scale);
                canvas.height = Math.round(image.height * scale);
                canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
                const jpeg = canvas.toDataURL("image/jpeg", 0.82);
                const name = (file.name || "receipt").replace(/\.[^.]+$/, "") + ".jpg";
                resolve({ name, mimetype: "image/jpeg", data: jpeg.split(",")[1], preview: jpeg });
            };
            image.src = dataUrl;
        };
        reader.readAsDataURL(file);
    });
}
