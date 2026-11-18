/** @odoo-module alias=@web/legacy/js/public/lazyloader default=false */
// Page Speed 0.8.0 (owner 2026-11-16, fix A: "the visitors' scripts after the first paint"): Odoo's lazyloader
// (web/static/src/legacy/js/public/lazyloader.js, the same code and the same module name) for the visitors' pages,
// except when the visitors' script bundle starts: Odoo starts it as soon as the page has loaded; here it waits, after
// the load, for a painted frame (so the cover is on screen before the bundle's long tasks), then for the whole
// stylesheets the first screen asked for (models/first_screen.py: the scripts then find every rule, menus and all),
// at most LATE_WAIT ms. A visitor's tap, click or key starts it at once. Buttons clicked before it has loaded wait
// and are pressed again once it has, as in Odoo's.
import {
    BUTTON_HANDLER_SELECTOR,
    makeAsyncHandler,
    makeButtonHandler,
} from '@web/legacy/js/public/minimal_dom';

// Track when all JS files have been lazy loaded. Will allow to unblock the
// related DOM sections when the whole JS have been loaded and executed.
let allScriptsLoadedResolve = null;
const _allScriptsLoaded = new Promise(resolve => {
    allScriptsLoadedResolve = resolve;
}).then(stopWaitingLazy);

const retriggeringWaitingProms = [];
/**
 * Function to use as an event handler to replay the incoming event after the
 * whole lazy JS has been loaded. Note that blocking the incoming event is left
 * up to the caller (i.e. a potential wrapper, @see waitLazy).
 *
 * @param {Event} ev
 * @returns {Promise}
 */
async function waitForLazyAndRetrigger(ev) {
    // Wait for the lazy JS to be loaded before re-triggering the event.
    const targetEl = ev.target;
    await _allScriptsLoaded;
    // Loaded scripts were able to add a delay to wait for before re-triggering
    // events: we wait for it here.
    await Promise.all(retriggeringWaitingProms);

    // At the end of the current execution queue, retrigger the event. Note that
    // the event is reconstructed: this is necessary in some cases, e.g. submit
    // buttons. Probably because the event was originally defaultPrevented.
    setTimeout(() => {
        // Extra safety check: the element might have been removed from the DOM
        if (targetEl.isConnected) {
            targetEl.dispatchEvent(new ev.constructor(ev.type, ev));
        }
    }, 0);
}

const loadingEffectHandlers = [];
/**
 * Adds the given event listener and saves it for later removal.
 *
 * @param {HTMLElement} el
 * @param {string} type
 * @param {Function} handler
 */
function registerLoadingEffectHandler(el, type, handler) {
    el.addEventListener(type, handler, {capture: true});
    loadingEffectHandlers.push({el, type, handler});
}

let waitingLazy = false;

/**
 * Automatically adds a loading effect on clicked buttons (that were not marked
 * with a specific class). Once the whole JS has been loaded, the events will be
 * triggered again.
 *
 * For forms, we automatically prevent submit events (since can be triggered
 * without click on a button) but we do not retrigger them (could be duplicate
 * with re-trigger of a click on a submit button otherwise). However, submitting
 * a form in any way should most of the time simulate a click on the submit
 * button if any anyway.
 *
 * @see stopWaitingLazy
 */
function waitLazy() {
    if (waitingLazy) {
        return;
    }
    waitingLazy = true;

    document.body.classList.add('o_lazy_js_waiting');

    // TODO should probably find the wrapwrap another way but in future versions
    // the element will be gone anyway.
    const mainEl = document.getElementById('wrapwrap') || document.body;
    const loadingEffectButtonEls = [...mainEl.querySelectorAll(BUTTON_HANDLER_SELECTOR)]
        // We target all buttons but...
        .filter(el => {
            // ... we allow to disable the effect by adding a specific class if
            // needed. Note that if some non-lazy loaded code is adding an event
            // handler on some buttons, it means that if they do not have that
            // class, they will show a loading effect and not do anything until
            // lazy JS is loaded anyway. This is not ideal, especially since
            // this was added as a stable fix/imp, but this is a compromise: on
            // next page visits, the cache should limit to effect of the lazy
            // loading anyway.
            return !el.classList.contains('o_no_wait_lazy_js')
                // ... we also allow do not consider links with a href which is
                // not "#". They could be linked to handlers that prevent their
                // default behavior but we consider that following the link
                // should still be relevant in that case.
                && !(el.nodeName === 'A' && el.href && el.getAttribute('href') !== '#');
        });
    // Note: this is a limitation/a "risk" to only block and retrigger those
    // specific event types.
    const loadingEffectEventTypes = ['mouseover', 'mouseenter', 'mousedown', 'mouseup', 'click', 'mouseout', 'mouseleave'];
    for (const buttonEl of loadingEffectButtonEls) {
        for (const eventType of loadingEffectEventTypes) {
            const loadingEffectHandler = eventType === 'click'
                ? makeButtonHandler(waitForLazyAndRetrigger, true, true, true)
                : makeAsyncHandler(waitForLazyAndRetrigger, true, true, true);
            registerLoadingEffectHandler(buttonEl, eventType, loadingEffectHandler);
        }
    }

    for (const formEl of document.querySelectorAll('form:not(.o_no_wait_lazy_js)')) {
        registerLoadingEffectHandler(formEl, 'submit', ev => {
            ev.preventDefault();
            ev.stopImmediatePropagation();
        });
    }
}
/**
 * Undo what @see waitLazy did.
 */
function stopWaitingLazy() {
    if (!waitingLazy) {
        return;
    }
    waitingLazy = false;

    document.body.classList.remove('o_lazy_js_waiting');

    for (const { el, type, handler } of loadingEffectHandlers) {
        el.removeEventListener(type, handler, {capture: true});
    }
}

// Start waiting for lazy loading as soon as the DOM is available
if (document.readyState !== 'loading') {
    waitLazy();
} else {
    document.addEventListener('DOMContentLoaded', function () {
        waitLazy();
    });
}

const LATE_WAIT = 3000;
let started = false;
function _start() {
    if (started) {
        return;
    }
    started = true;
    for (const type of ["pointerdown", "keydown", "touchstart"]) {
        document.removeEventListener(type, _start, true);
    }
    setTimeout(_loadScripts, 0);
}
for (const type of ["pointerdown", "keydown", "touchstart"]) {
    document.addEventListener(type, _start, { capture: true, passive: true });
}
function _painted() {
    // (two frames: the first one after the load is painted; a hidden tab paints none, hence the timer)
    return new Promise((resolve) => {
        const timer = setTimeout(resolve, 250);
        requestAnimationFrame(() => requestAnimationFrame(() => {
            clearTimeout(timer);
            resolve();
        }));
    });
}
function _lateSheets() {
    const waiting = [...document.querySelectorAll("link[rel=stylesheet][data-mtbg-first-screen]")].filter(
        (link) => link.media === "print"
    );
    return Promise.race([
        Promise.all(waiting.map((link) => new Promise((resolve) => {
            link.addEventListener("load", resolve, { once: true });
            link.addEventListener("error", resolve, { once: true });
        }))),
        new Promise((resolve) => setTimeout(resolve, LATE_WAIT)),
    ]);
}
function _afterLoad() {
    // (the first screen's stylesheets are asked for on the same load: models/first_screen.py LATE_SCRIPT)
    setTimeout(() => _painted().then(_lateSheets).then(_start), 0);
}
if (document.readyState === 'complete') {
    _afterLoad();
} else {
    window.addEventListener('load', _afterLoad);
}

/**
 * @param {DOMElement[]} scripts
 * @param {integer} index
 */
function _loadScripts(scripts, index) {
    if (scripts === undefined) {
        scripts = document.querySelectorAll('script[data-src]');
    }
    if (index === undefined) {
        index = 0;
    }
    if (index >= scripts.length) {
        allScriptsLoadedResolve();
        return;
    }
    const script = scripts[index];
    script.addEventListener('load', _loadScripts.bind(this, scripts, index + 1));
    script.setAttribute('defer', 'defer'); // See LAZY_LOAD_DEFER
    script.src = script.dataset.src;
    script.removeAttribute('data-src');
}

export default {
    loadScripts: _loadScripts,
    allScriptsLoaded: _allScriptsLoaded,
    registerPageReadinessDelay: retriggeringWaitingProms.push.bind(retriggeringWaitingProms),
};
