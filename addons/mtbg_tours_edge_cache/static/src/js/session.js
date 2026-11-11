/** @odoo-module ignore **/
/* A page from Cloudflare's cache is the same for every visitor: its form token is nobody's. The visitor's own token
   (and their country, for the phone field) comes from /mtbg/session when they start filling a form.
   window.mtbgSession: a promise of {csrf_token, country} (country null on a page Odoo built for this visitor). */
(function () {
    "use strict";
    var cached = !!document.querySelector('meta[name="mtbg-cached"]');
    var promise = null;

    function load() {
        if (promise) {
            return promise;
        }
        if (!cached) {
            promise = Promise.resolve({csrf_token: window.odoo && window.odoo.csrf_token, country: null});
            return promise;
        }
        promise = window.fetch("/mtbg/session", {credentials: "same-origin", cache: "no-store"})
            .then(function (response) { return response.json(); })
            .then(function (data) {
                if (data.csrf_token) {
                    if (window.odoo) {
                        window.odoo.csrf_token = data.csrf_token;
                    }
                    document.querySelectorAll('input[name="csrf_token"]').forEach(function (input) {
                        input.value = data.csrf_token;
                    });
                }
                return data;
            })
            .catch(function () {
                promise = null;  // (tried again on the next use)
                return {csrf_token: window.odoo && window.odoo.csrf_token, country: null};
            });
        return promise;
    }

    Object.defineProperty(window, "mtbgSession", {get: load, configurable: true});
    if (!cached) {
        return;
    }
    // the first touch of a form (or anything marked data-mtbg-session) loads it, before it is sent
    function onTouch(ev) {
        if (ev.target && ev.target.closest && ev.target.closest("form, [data-mtbg-session], .mtbg-phone")) {
            load();
            document.removeEventListener("focusin", onTouch, true);
            document.removeEventListener("pointerdown", onTouch, true);
        }
    }
    document.addEventListener("focusin", onTouch, true);
    document.addEventListener("pointerdown", onTouch, true);
})();
