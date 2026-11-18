import base64
import gzip
import re

from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tests.common import Opener

from odoo.addons.mtbg_tours_page_speed.models import first_screen as fs, ir_http, lean

CSS = """@import url("https://fonts.googleapis.com/css?family=Raleway&display=swap");
@import url("/web/content/1/google-font-Journal");
:root{--x:1}
@font-face{font-family:Foo;src:url(foo.woff2)}
/* a comment { with braces } */
.used{color:red}
.unused{color:blue}
.used .unused, .used > p{margin:0}
.used:not(.never){padding:1px}
a[href^="http"].used::after{content:"}"}
@media (min-width:768px){.used{color:green}.unused{color:pink}}
@media print{.unused{display:none}}
@keyframes spin{from{opacity:0}to{opacity:1}}
@keyframes gone{from{opacity:0}to{opacity:1}}
@media (prefers-reduced-motion:no-preference){@keyframes gone2{to{top:0}}}
.used{animation:spin 1s}
.used, p, .used{border:0}
#hero, div#nothere{height:1px}
.esc\\:x{top:0}
"""
PAGE = (b'<html><head><title>t</title>'
        b'<link type="text/css" rel="stylesheet" href="/web/assets/1/abc/mtbg_tours_page_speed.assets_frontend_lean.min.css"/>'
        b'</head><body><div id="hero" class="used esc:x"><p>hi <a href="https://x">x</a></p></div></body></html>')


@tagged('post_install', '-at_install', 'mtbg')
class TestFirstScreenRules(TransactionCase):
    """0.7.7 (owner: "yes" to splitting the stylesheet): the rules a page can match, in their order."""

    def test_kept_rules(self):
        items, imports = fs.parse(CSS)
        self.assertEqual(imports, ['https://fonts.googleapis.com/css?family=Raleway&display=swap',
                                   '/web/content/1/google-font-Journal'])
        out = fs.kept(items, fs.page_tokens(PAGE))
        self.assertIn(':root{--x:1}', out)
        self.assertIn('@font-face', out, "at-rules kept whole")
        self.assertIn('@keyframes spin', out, "an animation a kept rule names")
        self.assertNotIn('@keyframes gone', out, "0.7.12: one no kept rule names comes with the whole stylesheet")
        self.assertNotIn('prefers-reduced-motion', out, "(its group then empty)")
        self.assertIn('.used,p{border:0}', out, "0.7.12: a selector named twice once")
        self.assertIn('@keyframes gone', fs.kept(items, fs.page_tokens(PAGE), fs.page_animations(
            b'<div style="animation: gone 2s">')), "one the page's own HTML names")
        self.assertIn('.used{color:red}', out)
        self.assertNotIn('.unused{color:blue}', out)
        self.assertIn('.used > p{margin:0}', out, "only the selectors the page can match of a list")
        self.assertNotIn('.used .unused', out)
        self.assertIn('.used:not(.never)', out, "what :not() names is not required")
        self.assertIn('content:"}"', out, "a brace in a string stays")
        self.assertIn('@media (min-width:768px){.used{color:green}}', out)
        self.assertNotIn('@media print', out, "an empty group goes")
        self.assertIn('#hero{height:1px}', out)
        self.assertIn('.esc\\:x{top:0}', out, "an escaped class name")
        self.assertNotIn('@import', out, "the imports are linked in the head instead")
        self.assertLess(out.index('.used{color:red}'), out.index('@media (min-width:768px)'), "the order stays")

    def test_page(self):
        new = fs.first_screen(PAGE, lambda url: CSS)
        self.assertNotIn(b'<link type="text/css" rel="stylesheet" href="/web/assets', new, "no longer holding the page")
        style = re.search(rb'<style data-mtbg-first-screen="">(.*?)</style>', new, re.S)
        self.assertTrue(style)
        self.assertIn(b'.used{color:red}', style.group(1))
        self.assertIn(b'<link rel="stylesheet" data-mtbg-late-href="/web/assets/1/abc/mtbg_tours_page_speed.assets_'
                      b'frontend_lean.min.css" media="print" onload="this.media=\'all\'"', new,
                      "the whole stylesheet after it, asked for once the page has loaded (0.7.10)")
        self.assertNotIn(b' href="/web/assets/1/abc/mtbg_tours_page_speed.assets_frontend_lean.min.css" media=', new,
                         "not fetched beside the first photo")
        self.assertEqual(new.count(fs.LATE_SCRIPT), 1, "one loader")
        self.assertLess(new.index(fs.LATE_SCRIPT), new.index(b'</head>'))
        self.assertIn(b'<noscript><link rel="stylesheet" href="/web/assets/1/abc/', new)
        self.assertIn(b'<link rel="stylesheet" href="https://fonts.googleapis.com/css?family=Raleway&amp;display=swap"',
                      new, "the fonts in the head")
        self.assertIn(b'<link rel="preconnect" href="https://fonts.gstatic.com"', new)
        self.assertLess(new.index(b'fonts.googleapis'), new.index(b'<style data-mtbg-first-screen'),
                        "the imports before the rules, as in the stylesheet")
        self.assertEqual(fs.first_screen(new, lambda url: CSS), new, "once")
        self.assertEqual(fs.first_screen(PAGE, lambda url: None), PAGE, "stylesheet not built yet: as it is")
        other = PAGE.replace(b'mtbg_tours_page_speed.assets_frontend_lean', b'web.assets_frontend')
        self.assertEqual(fs.first_screen(other, lambda url: CSS), other, "Odoo's own stylesheet: as it is")
        two = PAGE.replace(b'</head>', b'<link type="text/css" rel="stylesheet" href="/web/assets/1/def/x.assets_b.min.css"/>'
                                       b'<noscript><link rel="stylesheet" href="/web/assets/1/def/x.assets_c.min.css"/>'
                                       b'</noscript></head>')
        both = fs.first_screen(two, lambda url: CSS if 'lean' in url else '.used{c:3}.gone{d:4}')
        self.assertEqual(both.count(b'<style data-mtbg-first-screen'), 2, "an extension's stylesheet too, in its place")
        self.assertIn(b'<style data-mtbg-first-screen="">.used{c:3}</style><link rel="stylesheet" '
                      b'data-mtbg-late-href="/web/assets/1/def/x.assets_b.min.css" media="print"', both)
        self.assertEqual(both.count(fs.LATE_SCRIPT), 1, "one loader for both")
        self.assertIn(b'<noscript><link rel="stylesheet" href="/web/assets/1/def/x.assets_c.min.css"/>', both,
                      "a noscript stylesheet stays as it is")
        self.assertEqual(fs.bundle_of('/web/assets/1/ae4c434/mtbg_tours_booking_form.assets_booking.min.css'),
                         'mtbg_tours_booking_form.assets_booking')
        evil = CSS + '.used::before{content:"</style><script>x</script>"}'
        style = re.search(rb'<style data-mtbg-first-screen="">(.*?)</style>', fs.first_screen(PAGE, lambda url: evil),
                          re.S).group(1)
        self.assertIn(b'<\\/style><script>', style, "a stylesheet's text never closes the page's style")


@tagged('post_install', '-at_install', 'mtbg')
class TestFirstScreenPages(HttpCase):
    """Who gets the first screen first: visitors on the lean pages only, on by default, off by its switch."""

    def _set(self, lean_on, first=None):
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param(lean.PARAM, 'True' if lean_on else 'False')
        if first is None:
            ICP.search([('key', '=', lean.FIRST_SCREEN_PARAM)]).unlink()
        else:
            ICP.set_param(lean.FIRST_SCREEN_PARAM, 'True' if first else 'False')
        self.env['mtbg.page.speed.lean']._mtbg_sync()

    def _page(self, path):
        response = self.url_open(path, allow_redirects=False)
        return response.status_code, response.text

    def test_who_gets_it(self):
        self._set(True)
        self.opener = Opener(self)
        self._page('/contactus')  # (the stylesheet built by the first visit)
        code, page = self._page('/contactus')
        self.assertEqual(code, 200)
        style = re.search(r'<style data-mtbg-first-screen="">(.*?)</style>', page, re.S)
        self.assertTrue(style, "a visitor: the page's rules in its head")
        self.assertIn('media="print" onload="this.media=\'all\'" data-mtbg-first-screen=""', page)
        self.assertIn('data-mtbg-late-href="/web/assets/', page)
        self.assertNotRegex(page, r'<link type="text/css" rel="stylesheet" href="[^"]*assets_frontend_lean')
        href = re.search(r'href="(/web/assets/[^"]*assets_frontend_lean\.min\.css)"', page).group(1)
        whole = self.url_open(href).content
        self.assertLess(len(gzip.compress(style.group(1).encode())), len(gzip.compress(whole)) / 2,
                        "the page's rules are a small part of the stylesheet")
        for path in ('/my', '/shop', '/web/login'):
            code, page = self._page(path)
            if code == 200:
                self.assertNotIn('data-mtbg-first-screen', page, path)
        self.authenticate('admin', 'admin')
        self.assertNotIn('data-mtbg-first-screen', self._page('/contactus')[1], "logged in: Odoo's own")
        self.opener = Opener(self)
        self._set(True, first=False)
        self.assertNotIn('data-mtbg-first-screen', self._page('/contactus')[1], "switched off")
        self._set(False, first=True)
        self.assertNotIn('data-mtbg-first-screen', self._page('/contactus')[1], "without the lean pages: nothing")

    def test_first_visit_stylesheet_not_stored(self):
        """The very first visitor after an update: Odoo has not stored the stylesheet yet and the page's transaction
        is read-only: the page still gets its first screen (compiled in memory), nothing written, no error."""
        self._set(True)
        self.opener = Opener(self)
        self.env['ir.attachment'].sudo().search([('url', '=like', '/web/assets/%assets_frontend_lean%')]).unlink()
        ir_http._compiled.clear()
        fs._parsed.clear()
        fs._kept.clear()
        code, page = self._page('/')
        self.assertEqual(code, 200)
        self.assertIn('<style data-mtbg-first-screen="">', page)
        self.assertIn('Contact', self._page('/contactus')[1], "the next page works too")

    def test_settings_switch(self):
        self._set(True)
        page = self.env['mtbg.page.speed.settings'].create({'lean': True, 'first_screen': False})
        page.action_save()
        self.assertFalse(self.env['mtbg.page.speed.lean']._mtbg_first_screen_on())
        page = self.env['mtbg.page.speed.settings'].create({})
        self.assertFalse(page.first_screen)
        page.write({'first_screen': True})
        page.action_save()
        self.assertTrue(self.env['mtbg.page.speed.lean']._mtbg_first_screen_on())

    def test_visitor_page_runs(self):
        """In a real browser, the visitor's page gets the whole stylesheet after it, and every script loads."""
        self._set(True)
        self.opener = Opener(self)
        self._page('/contactus')
        code = """
const first = document.querySelector('style[data-mtbg-first-screen]');
const whole = [...document.querySelectorAll('link[rel=stylesheet]')].find((l) => l.href.includes('assets_frontend_lean'));
const errors = odoo.loader.findErrors();
(async () => {
    // (it is asked for once the page has loaded: a few moments for it to arrive)
    for (let n = 0; n < 100 && whole && whole.media !== 'all'; n++) { await new Promise((r) => setTimeout(r, 100)); }
    if (!first || !whole) { console.error('test failed: not the first screen first'); }
    else if (whole.media !== 'all') { console.error('test failed: the whole stylesheet never applied: ' + whole.media); }
    else if (Object.keys(errors).length) { console.error('test failed: modules missing ' + JSON.stringify(errors)); }
    else { console.log('test successful'); }
})();
"""
        self.browser_js('/contactus', code, ready="odoo.loader && odoo.loader.modules.size > 300", login=None)


FOLD_CSS = """:root{--used:1px;--chain:var(--used);--unused:2px;--page:3px}
.above{margin:var(--chain)}
.below{color:red}
.offcanvas{visibility:hidden}
.offcanvas .inmenu{color:blue}
[data-theme-x="dark"]{color:white}
[data-here]{top:0}
"""


def _page(filler=20000):
    return (b'<html><head><link type="text/css" rel="stylesheet" href="/web/assets/1/abc/mtbg_tours_page_speed.'
            b'assets_frontend_lean.min.css"/><link rel="preload" as="image" fetchpriority="high" href="/web/image/9"/>'
            b'</head><body><div id="wrapwrap"><header id="top"><a href="/" class="navbar-brand logo"><span>'
            b'<img src="/logo.png" width="95" height="40"/></span></a>'
            b'<div class="offcanvas offcanvas-end" id="phone_menu"><ul>' + b'<li class="inmenu">a menu entry</li>' * 80
            + b'</ul></div><div class="dropdown-menu o_mega_menu">' + b'<p class="inmenu">mega</p>' * 80 + b'</div>'
            b'<div class="dropdown-menu"><script>var x = "<div>";</script>' + b'<p>x</p>' * 300 + b'</div>'
            b'</header><main><div id="wrap" data-here="1" style="padding:var(--page)"><img class="cover" src="/web/image/9"/>'
            b'<p class="above">first screen</p>' + b'<p>text</p>' * (filler // 11) + b'<p class="below">far</p>'
            b'</div></main><footer><p class="below">footer</p></footer></div></body></html>')


@tagged('post_install', '-at_install', 'mtbg')
class TestFirstScreenOnly(TransactionCase):
    """0.8.0 (owner 2026-11-16, fix A): the first screen's rules only, the menus' content after the page's content, the
    header logo at low priority."""

    def test_rules_of_the_first_screen(self):
        page = _page()
        tokens = fs.page_tokens(fs.first_screen_html(page))
        self.assertIn('.above', tokens)
        self.assertNotIn('.below', tokens, "after the content's first screen")
        self.assertIn('.offcanvas', tokens, "a hidden element's own rules (they hide it)")
        self.assertNotIn('.inmenu', tokens, "not its content's")
        self.assertIn('[data-here', tokens)
        out = fs.kept(fs.parse(FOLD_CSS)[0], tokens, (), fs.page_vars(page))
        self.assertIn('.above{margin:var(--chain)}', out)
        self.assertNotIn('.below', out)
        self.assertIn('.offcanvas{visibility:hidden}', out)
        self.assertNotIn('inmenu', out)
        self.assertNotIn('data-theme-x', out, "an attribute no element has")
        self.assertIn('[data-here]{top:0}', out)
        self.assertIn('--chain:var(--used)', out)
        self.assertIn('--used:1px', out, "a custom property a kept one uses")
        self.assertIn('--page:3px', out, "one the page's own HTML uses")
        self.assertNotIn('--unused', out)
        self.assertIn('.above', fs.page_tokens(fs.first_screen_html(_page(filler=100))))
        self.assertIn('.below', fs.page_tokens(fs.first_screen_html(_page(filler=100))), "a short page: all of it")
        shown = fs.page_tokens(fs.first_screen_html(b'<body><main><div class="d-none d-lg-block"><p class="desk"></p></div>'
                               b'<div class="d-none"><p class="never"></p></div><div hidden=""><p class="later"></p>'
                               b'</div><svg class="ico"><path class="p1"/></svg></main></body>'))
        self.assertIn('.desk', shown, "shown on a computer")
        self.assertNotIn('.never', shown)
        self.assertNotIn('.later', shown)
        self.assertIn('.p1', shown, "an icon's drawing")

    def test_menus_after_the_content(self):
        whole = FOLD_CSS + ''.join('.other-%d{color:red}' % n for n in range(200))  # (a stylesheet's other rules)
        page = fs.first_screen(_page(), lambda url: whole)
        self.assertIn(b'<style data-mtbg-first-screen="">', page)
        cover = page.index(b'class="cover"')
        self.assertLess(cover, page.index(b'a menu entry'), "the cover before the phone menu's content")
        self.assertLess(cover, page.index(b'<p class="inmenu">mega'), "and before the mega menu's")
        self.assertLess(page.index(b'<p>x</p>'), cover, "a menu with a script of its own stays")
        self.assertIn(b'<div class="offcanvas offcanvas-end" id="phone_menu"><template data-mtbg-slot="0"></template>'
                      b'</div>', page, "the menu's own element stays in its place")
        self.assertEqual(page.count(b'<template data-mtbg-later='), 2)
        self.assertLess(page.index(b'</main>'), page.index(fs.LATER_SCRIPT))
        self.assertLess(page.index(fs.LATER_SCRIPT), page.index(b'<footer>'), "put back right after the content")
        self.assertIn(b'<img fetchpriority="low" src="/logo.png"', page, "the logo after the cover")
        self.assertNotIn(b'fetchpriority="low" class="cover"', page)
        self.assertEqual(fs.menus_later(page), page, "once")


@tagged('post_install', '-at_install', 'mtbg')
class TestFirstScreenTourPage(HttpCase):
    """0.8.0: a rendered tour page: its first screen's rules within bounds, its cover before the menus' content, and,
    in a browser, every menu back in its place, the scripts loaded and the booking form opening, without an error."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if 'mtbg.tour' not in cls.env or 'mtbg.tour.media' not in cls.env:
            return
        ICP = cls.env['ir.config_parameter'].sudo()
        ICP.set_param(lean.PARAM, 'True')
        ICP.search([('key', '=', lean.FIRST_SCREEN_PARAM)]).unlink()
        cls.env['mtbg.page.speed.lean']._mtbg_sync()
        cls.tour = cls.env['mtbg.tour'].create({'name': 'Speed Ride', 'slug': 'speed-ride-fs', 'base_price': 90,
                                               'is_published': True})
        att = cls.env['ir.attachment'].create({
            'name': 'speed-cover.png', 'public': True, 'mimetype': 'image/png',
            'raw': base64.b64decode(b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')})
        folder = cls.env['mtbg.tours.media.folder'].create({'name': 'Speed Ride'})
        cls.env['mtbg.tour.media'].create({'tour_id': cls.tour.id, 'folder_id': folder.id, 'media_type': 'image',
                                           'name': 'Cover', 'attachment_id': att.id, 'is_cover': True})

    def setUp(self):
        super().setUp()
        if not getattr(self, 'tour', None):
            self.skipTest('no tour pages here')
        self.opener = Opener(self)

    def test_tour_page_first_screen(self):
        path = '/tours/speed-ride-fs'
        self.url_open(path)
        page = self.url_open(path).content
        styles = re.findall(rb'<style data-mtbg-first-screen="">(.*?)</style>', page, re.S)
        self.assertTrue(styles, "the first screen's rules")
        size = sum(map(len, styles))
        # (0.9.1: ~57 KB on www's tour pages before, ~49 KB now: hover and focus states, closed menus' content,
        # fonts no kept rule names, transitions, print and lists nested deeper than the page's come later)
        self.assertLess(size, 60000, "the first screen's rules, not the whole page's (156 KB before 0.8.0)")
        rules = b''.join(styles)
        self.assertIn(b'.navbar', rules, "the header's rules")
        self.assertIn(b'.mtbg-tour-cover', rules, "the cover's")
        self.assertNotIn(b':hover{', rules, "no hover states")
        head = page[:page.index(b'</head>')]
        self.assertLess(head.index(b'name="viewport"'), head.index(b'rel="preload" as="image"'),
                        "the cover's preload read at the phone's width")
        cover = page.index(b'mtbg-tour-cover img-fluid')
        self.assertLess(cover, len(page) * 0.6)
        for menu in (b'offcanvas-body', b'<template data-mtbg-later='):
            if menu in page:
                self.assertLess(cover, page.index(menu), "the cover before the menus' content")

    def test_tour_page_in_a_browser(self):
        path = '/tours/speed-ride-fs'
        self.url_open(path)
        code = """
(async () => {
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));
    for (let n = 0; n < 150 && document.body.classList.contains('o_lazy_js_waiting'); n++) { await wait(100); }
    const errors = odoo.loader.findErrors();
    const late = [...document.querySelectorAll('link[rel=stylesheet][data-mtbg-first-screen]')].filter((l) => l.media === 'print');
    if (document.querySelector('template[data-mtbg-later], template[data-mtbg-slot]')) {
        console.error('test failed: a menu was not put back');
    } else if (Object.keys(errors).length) {
        console.error('test failed: modules missing ' + JSON.stringify(errors));
    } else if (late.length) {
        console.error('test failed: the whole stylesheets never applied');
    } else if (!document.querySelector('#top_menu .o_mega_menu, #top_menu_collapse_mobile .offcanvas-body, #top_menu')) {
        console.error('test failed: no menu');
    } else {
        const book = document.querySelector('#mtbg-book-now');
        if (book) { book.click(); await wait(800); }
        console.log('test successful');
    }
})();
"""
        self.browser_js(path, code, ready="odoo.loader && odoo.loader.modules.size > 300", login=None)


CRITICAL_CSS = """:root{--hero-h:300px;--menu-c:red}
@font-face{font-family:'Icons';src:url(old.woff2)}
@font-face{font-family:'Icons';src:url(new.woff2)}
@font-face{font-family:"Unused Face";src:url(u.woff2)}
@font-face{font-family:Title;src:url(t.woff2)}
.navbar{display:flex;transition:all .3s;cursor:pointer;--nav-x:1}
.navbar a:hover{color:red}
.navbar a:not(:hover){color:blue}
.navbar a:focus-visible,.navbar a{text-decoration:none}
.offcanvas{position:fixed;visibility:hidden;background:var(--menu-c);color:green}
.offcanvas .nav-link{color:var(--menu-c)}
.offcanvas + .nav-link{margin:0}
.nav-link{padding:2px}
.fa{font-family:'Icons'}
h1{font:700 2rem/1.2 Title,serif}
ul ul{margin:0}
ul{padding:0}
.hero{height:var(--hero-h)}
@media print{.hero{display:none}}
"""


def _critical_page(content=b''):
    return (b'<html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>'
            b'<link type="text/css" rel="stylesheet" href="/web/assets/1/abc/mtbg_tours_page_speed.'
            b'assets_frontend_lean.min.css"/></head><body><header><nav class="navbar"><a class="nav-link" href="/">'
            b'<i class="fa"></i> Home</a><ul><li>x</li></ul>'
            b'<div class="offcanvas"><a class="nav-link" href="/x">menu</a></div></nav></header>'
            b'<main><div id="wrap"><div class="hero"><h1>Title</h1></div>' + content + b'</div></main></body></html>')


@tagged('post_install', '-at_install', 'mtbg')
class TestCriticalRules(TransactionCase):
    """0.9.1 (owner 2026-11-17: "inline only the CSS the first screen needs", ~30 KB): what a visitor does, what is
    inside a closed menu, fonts no kept rule names, lists nested deeper than the page's, transitions and long
    attribute values never make the first screen's rules bigger."""

    def _out(self, page=None, css=CRITICAL_CSS):
        page = page or _critical_page()
        new = fs.first_screen(page, lambda url: css)
        return re.search(rb'<style data-mtbg-first-screen="">(.*?)</style>', new, re.S).group(1).decode()

    def test_only_what_the_first_screen_draws(self):
        out = self._out()
        self.assertIn('.navbar{display:flex', out, "the header's rules")
        self.assertIn('.hero{height:var(--hero-h)}', out, "the hero's")
        self.assertIn('--hero-h:300px', out)
        self.assertNotIn(':hover{', out, "a hover's rule comes with the whole stylesheet")
        self.assertIn('.navbar a:not(:hover){color:blue}', out, "not hovered: drawn at once")
        self.assertIn('.navbar a{text-decoration:none}', out, "a list's other selectors stay")
        self.assertNotIn('focus-visible', out)
        self.assertNotIn('transition', out, "no transition starts when the whole stylesheet comes")
        self.assertNotIn('cursor', out)
        self.assertIn('.offcanvas{position:fixed;visibility:hidden}', out, "a closed menu: what places and hides it")
        self.assertNotIn('.offcanvas .nav-link', out, "nothing for what is inside it")
        self.assertIn('.offcanvas + .nav-link{margin:0}', out, "its sibling is not inside it")
        self.assertIn('.nav-link{padding:2px}', out, "the header's own links")
        self.assertNotIn('--menu-c', out, "a custom property only the closed menu used")
        self.assertIn("url(new.woff2)", out, "a font a kept rule names: its last @font-face")
        self.assertNotIn("url(old.woff2)", out, "the same face twice: the browser keeps the last")
        self.assertIn("url(t.woff2)", out, "a family named in a 'font' shorthand")
        self.assertNotIn('Unused Face', out, "a font no kept rule names")
        self.assertNotIn('ul ul', out, "a list in a list: the first screen has none")
        self.assertIn('ul{padding:0}', out)
        self.assertNotIn('@media print', out)
        self.assertIn('ul ul{margin:0}', self._out(_critical_page(b'<ul><li><ul><li>y</li></ul></li></ul>')),
                      "one where the first screen has a list in a list")
        self.assertTrue(fs.acted('.a:hover') and fs.acted('.a:focus-within .b') and not fs.acted('.a:not(:hover)'))
        self.assertFalse(fs.acted('.a:hovered'), "a word starting so is not the state")

    def test_long_attribute_values_do_not_fill_the_fold(self):
        icon = b'<span class="stat" style="--icon:url(data:image/png;base64,' + b'A' * 30000 + b')"></span>'
        screen = fs.first_screen_html(_critical_page(icon + b'<p class="next">after the icon</p>'))
        self.assertIn('.next', fs.page_tokens(screen), "a 30 KB inlined icon is not 30 KB of the first screen")
        self.assertNotIn(b'AAAA', screen)
        far = fs.first_screen_html(_critical_page(b'<p>text</p>' * 2000 + b'<p class="far">far</p>'))
        self.assertNotIn('.far', fs.page_tokens(far), "the first screen ends where it did")

    def test_cached_per_stylesheet_version_and_page(self):
        fs._kept.clear()
        page = _critical_page()
        first = fs.first_screen(page, lambda url: CRITICAL_CSS)
        self.assertEqual(len(fs._kept), 1)
        self.assertEqual(fs.first_screen(page, lambda url: CRITICAL_CSS), first)
        self.assertEqual(len(fs._kept), 1, "the same stylesheet and page shape: worked out once")
        newer = page.replace(b'/abc/', b'/def/')
        out = fs.first_screen(newer, lambda url: CRITICAL_CSS.replace('display:flex', 'display:grid'))
        self.assertEqual(len(fs._kept), 2, "a new stylesheet version: worked out again")
        self.assertIn(b'.navbar{display:grid', out)
        fs.first_screen(_critical_page(b'<p class="nav-link">x</p>'), lambda url: CRITICAL_CSS)
        self.assertEqual(len(fs._kept), 3, "another page shape")

