/**
 * The website chat under full-screen layers (the website blocks' shared helper since Reusable Blocks 0.11.2, for the
 * modules that need no Tours: Forms; Tours Core keeps its own for Tours' pages; owner, 2026-11-03: "every additional
 * module should utilize shared javascript in the base"): a layer (a booking sheet, a menu, a popup) hides the chat while it is open.
 * <html> carries `cfd-chat-hidden` while any layer holds it, and lists the layers holding it (data-cfd-chat-hiders), so
 * one closing never shows the chat under another still open. CFD's chat tab (and Booking Form's chat layers for Odoo's
 * own bubbles) answer the class; without them it does nothing.
 */
export function chatHidden(owner, hidden) {
    const html = document.documentElement;
    const owners = new Set((html.dataset.cfdChatHiders || "").split(" ").filter(Boolean));
    if (hidden) {
        owners.add(owner);
    } else {
        owners.delete(owner);
    }
    html.dataset.cfdChatHiders = [...owners].join(" ");
    html.classList.toggle("cfd-chat-hidden", owners.size > 0);
}

export const hideChat = (owner) => chatHidden(owner, true);
export const showChat = (owner) => chatHidden(owner, false);
