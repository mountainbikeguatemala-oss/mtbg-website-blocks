import os
from unittest.mock import patch

from odoo.tests import HttpCase, tagged

from odoo.addons.mtbg_tours_page_speed.models import lean

# a slow computer (4x slower than this one): the speed Google's desktop measures stand for
THROTTLE = '4'
# no task longer than this while the visitors' scripts start (Google: a click answered within 200 ms is good)
BUDGET_MS = 200

# installed as soon as the page starts loading (the ready check runs from the start): every long task, and every long
# animation frame (a task with the page's styles and layout after it: what a click waits for), with its scripts
WATCH = """(() => {
    if (!window.__mtbgInp) {
        const inp = window.__mtbgInp = { tasks: [], frames: [] };
        const watch = (type, push) => {
            try {
                new PerformanceObserver((list) => list.getEntries().forEach(push)).observe({ type, buffered: true });
            } catch {}
        };
        watch('longtask', (e) => inp.tasks.push(Math.round(e.duration)));
        watch('long-animation-frame', (e) => inp.frames.push([Math.round(e.duration),
            (e.scripts || []).map((s) => `${s.invoker} ${Math.round(s.duration)}`).join('; ').slice(0, 300)]));
    }
    return document.readyState !== 'loading';
})()"""


@tagged('post_install', '-at_install', 'mtbg')
class TestInp(HttpCase):
    """0.11.0 (desktop INP, 2026-11-21: Google rated every computer page poor, 575 ms): the visitors' scripts start in
    short slices, a click is answered between two; at a slow computer's speed no task is long. (A timer's delay does
    not tell: the slices' continuations come before timers, not before a click.)"""

    def setUp(self):
        super().setUp()
        self.env['ir.config_parameter'].sudo().set_param(lean.PARAM, 'True')
        self.env['mtbg.page.speed.lean']._mtbg_sync()

    def _run(self, code):
        # (the runbot's own variable: throttled without the warning meant for a developer's run)
        with patch.dict(os.environ, {'ODOO_BROWSER_CPU_THROTTLING': THROTTLE}):
            self.browser_js('/contactus', code, ready=WATCH, login=None, timeout=120)

    def test_no_long_task_while_scripts_start(self):
        """At 4x slower, the page's scripts start (modules and interactions) without one task, or one frame with its
        styles and layout, over the budget."""
        code = """
(async () => {
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));
    for (let n = 0; n < 600 && document.body.getAttribute('is-ready') !== 'true'; n++) { await wait(100); }
    await wait(500);
    const inp = window.__mtbgInp;
    const lean = [...document.scripts].some((s) => (s.src || '').includes('assets_frontend_lazy_lean'));
    const longest = Math.max(0, ...inp.tasks);
    const frame = inp.frames.reduce((a, f) => (f[0] > a[0] ? f : a), [0, '']);
    console.log('mtbg inp: long tasks ' + JSON.stringify(inp.tasks) + ', longest frame ' + JSON.stringify(frame));
    if (!lean) { console.error('test failed: not the visitors copy'); }
    else if (document.body.getAttribute('is-ready') !== 'true') { console.error('test failed: the page never started'); }
    else if (document.body.classList.contains('o_lazy_js_waiting')) { console.error('test failed: still waiting'); }
    else if (longest > %(budget)s) { console.error('test failed: a task of ' + longest + ' ms'); }
    else if (frame[0] > %(budget)s) { console.error('test failed: a frame of ' + frame[0] + ' ms: ' + frame[1]); }
    else { console.log('test successful'); }
})();
""" % {'budget': BUDGET_MS}
        self._run(code)

    def test_modules_and_interactions_all_started(self):
        """The slices change when, not what: every module of the bundle starts (none waiting, none failed), the
        interactions start once each, the legacy widgets with them, and a part of the page started again later is
        Odoo's own start."""
        code = """
(async () => {
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));
    for (let n = 0; n < 600 && document.body.getAttribute('is-ready') !== 'true'; n++) { await wait(100); }
    const loader = odoo.loader;
    const errors = loader.findErrors();
    const service = odoo.__WOWL_DEBUG__ && odoo.__WOWL_DEBUG__.root.env.services['public.interactions'];
    const started = service ? service.interactions.map((i) => i.interaction.constructor.name + '|' + [...document.querySelectorAll('*')].indexOf(i.el)) : [];
    if (loader.addJob !== Object.getPrototypeOf(loader).addJob) { console.error('test failed: the loader still holds the modules'); }
    else if (Object.keys(errors).length) { console.error('test failed: modules not started ' + JSON.stringify(errors)); }
    else if (!service || !service.isActive || !started.length) { console.error('test failed: interactions not started'); }
    else if (new Set(started).size !== started.length) { console.error('test failed: an interaction started twice'); }
    else {
        // a part of the page again: Odoo's own start, synchronous as Odoo's
        const header = document.querySelector('header') || document.querySelector('#wrapwrap > *');
        service.stopInteractions(header);
        const before = service.interactions.length;
        service.startInteractions(header);
        if (service.interactions.length < before) { console.error('test failed: the restart lost interactions'); }
        else { console.log('test successful'); }
    }
})();
"""
        self._run(code)
