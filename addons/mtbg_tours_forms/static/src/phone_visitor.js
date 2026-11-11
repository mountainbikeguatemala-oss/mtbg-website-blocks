/** @odoo-module ignore **/
/* A page from Cloudflare's cache opened every phone field on the country of the visitor it was built for. Once the
   visitor's own session answers (window.mtbgSession, mtbg_tours_edge_cache), a field still on that default (no number
   typed, no country picked) opens on theirs. Pages Odoo builds for each visitor are already right. */
(function () {
    "use strict";
    var FIELD = '.mtbg-phone[data-mtbg-open="visitor"]';

    function apply(country) {
        if (!country) {
            return;
        }
        document.querySelectorAll(FIELD).forEach(function (field) {
            var select = field.querySelector(".mtbg-phone__select");
            var input = field.querySelector(".mtbg-phone__input");
            if (!select || select.dataset.mtbgPicked || (input && input.value.trim()) || select.value === country) {
                return;
            }
            if (window.mtbgPhoneFill) {
                window.mtbgPhoneFill(field);  // (the picker's other countries come when it is first used)
            }
            var option = select.querySelector('option[value="' + country + '"]');
            if (!option) {
                return;
            }
            select.value = country;
            var flag = field.querySelector(".mtbg-phone__flag");
            var dial = field.querySelector(".mtbg-phone__dial");
            if (flag && option.dataset.img) {
                flag.src = option.dataset.img;
                flag.alt = option.dataset.name || "";
            }
            if (dial && option.dataset.dial) {
                dial.textContent = "+" + option.dataset.dial;
            }
            select.dispatchEvent(new Event("change", {bubbles: true}));
        });
    }

    document.addEventListener("change", function (ev) {
        if (ev.isTrusted && ev.target.classList && ev.target.classList.contains("mtbg-phone__select")) {
            ev.target.dataset.mtbgPicked = "1";  // (the visitor's own choice wins)
        }
    }, true);

    function onTouch(ev) {
        if (!document.querySelector(FIELD) || !ev.target.closest || !ev.target.closest("form, .mtbg-phone, [data-mtbg-session]")) {
            return;
        }
        document.removeEventListener("focusin", onTouch, true);
        document.removeEventListener("pointerdown", onTouch, true);
        var session = window.mtbgSession;  // (none without the page cache extension)
        if (session && session.then) {
            session.then(function (data) { apply(data && data.country); });
        }
    }
    document.addEventListener("focusin", onTouch, true);
    document.addEventListener("pointerdown", onTouch, true);
    document.documentElement.dataset.mtbgPhoneVisitor = "1";  // (ready: the tests wait for it)
})();
