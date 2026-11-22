import { registry } from "@web/core/registry";

// The phone's side menu with every menu (topbar/phone_menu.js; owner, 2026-11-21): every page of every app's top bar
// (the menus as the server sends them, the layout applied) has its row; a menu under one that opens the same page is
// left out (Bookings › All bookings). Off: Odoo's own side menu. On a computer: Odoo's top bar, no phone menu.
function check(ok, message) {
    if (!ok) {
        throw new Error(message);
    }
}

async function expectedPages() {
    const menus = await (await fetch("/web/webclient/load_menus")).json();
    const action = (menu) => menu.actionID || menu.action_id || false;
    const pages = [];
    const walk = (id) => {
        for (const child of menus[id].children) {
            const menu = menus[child];
            if (action(menu) && !(action(menu) === action(menus[id]) && !menu.children.length)) {
                pages.push(menu);
            }
            walk(child);
        }
    };
    for (const app of menus.root.children) {
        walk(app);
    }
    return pages;
}

registry.category("web_tour.tours").add("mtbg_phone_menu", {
    steps: () => [
        { content: "Open the side menu", trigger: ".o_main_navbar .o_menu_toggle", run: "click" },
        { content: "Every app listed", trigger: ".o_app_menu_sidebar .o_mtbg_phone_menu .o_mtbg_phone_app" },
        {
            content: "Unfold every app; every page of every top bar has its row",
            trigger: ".o_mtbg_phone_app.is-current .o_mtbg_phone_page",
            async run() {
                for (const head of document.querySelectorAll(".o_mtbg_phone_app_head[aria-expanded='false']")) {
                    head.click();
                    await new Promise((resolve) => setTimeout(resolve, 30));
                }
                await new Promise((resolve) => setTimeout(resolve, 300));
                const rows = new Set([...document.querySelectorAll(".o_mtbg_phone_page")].map((el) => +el.dataset.section));
                const missing = (await expectedPages()).filter((menu) => !rows.has(menu.id));
                check(rows.size > 0 && !missing.length, `pages without a row: ${missing.map((m) => m.name).join(", ")}`);
                const sidebar = document.querySelector(".o_app_menu_sidebar").getBoundingClientRect();
                check(sidebar.right <= window.innerWidth + 1, "the side menu fits the screen");
                const row = document.querySelector(".o_mtbg_phone_page").getBoundingClientRect();
                check(row.height >= 40, `rows a finger high (${row.height}px)`);
            },
        },
        {
            content: "A tap on a page opens it and closes the side menu",
            trigger: ".o_mtbg_phone_app.is-current .o_mtbg_phone_page",
            run: "click",
        },
        { content: "Closed", trigger: "body:not(:has(.o_app_menu_sidebar))" },
    ],
});

registry.category("web_tour.tours").add("mtbg_phone_menu_off", {
    steps: () => [
        { content: "Open the side menu", trigger: ".o_main_navbar .o_menu_toggle", run: "click" },
        { content: "Odoo's own: All Apps, no phone menu", trigger: ".o_app_menu_sidebar .o_sidebar_topbar a.btn-primary" },
        {
            content: "No phone menu",
            trigger: ".o_app_menu_sidebar",
            run() {
                check(!document.querySelector(".o_mtbg_phone_menu"), "the phone menu shows while off");
            },
        },
    ],
});

registry.category("web_tour.tours").add("mtbg_phone_menu_desktop", {
    steps: () => [
        {
            content: "A computer: Odoo's top bar with its menus, no phone menu",
            trigger: ".o_main_navbar .o_navbar_apps_menu",
            run() {
                check(!document.querySelector(".o_mtbg_phone_menu, .o_app_menu_sidebar"), "a phone menu on a computer");
                check(!document.querySelector(".o_main_navbar .o_menu_toggle"), "the phone's menu button on a computer");
            },
        },
    ],
});
