import re

from odoo.tests import HttpCase, tagged
from odoo.tests.common import Opener

from odoo.addons.mtbg_tours_page_speed.models import lean

IMPORT = re.compile(r'''from\s+["'](@[^"']+)["']''')


def _name(url):
    found = re.match(r'/([^/]+)/static/src/(.+?)(\.js)?$', url)
    return found and '@%s/%s' % (found.group(1), found.group(2))


@tagged('post_install', '-at_install', 'mtbg')
class TestLean(HttpCase):
    """0.5.0 (owner: "the trim odoo extras should be an option in the optimizer extension itself on/off")."""

    def _switch(self, on):
        self.env['ir.config_parameter'].sudo().set_param(lean.PARAM, 'True' if on else 'False')
        self.env['mtbg.page.speed.lean']._mtbg_sync()

    def _files(self, bundle):
        return {a.url: a for a in self.env['ir.qweb']._get_asset_bundle(bundle, css=False, js=True).javascripts}

    def test_bundle_without_extras_and_whole(self):
        self._switch(True)
        full, lean_files = self._files('web.assets_frontend_lazy'), self._files(lean.BUNDLE)
        gone = set(full) - set(lean_files)
        self.assertTrue(any(u.startswith('/web_tour/') for u in gone), "the onboarding tours left out")
        self.assertTrue(any(u.startswith('/html_editor/static/src/main/media/') for u in gone), "the media dialog")
        # 0.7.12: the back end's own widgets
        for folder in ('tree_editor', 'domain_selector', 'model_field_selector', 'barcode', 'effects', 'debug'):
            self.assertFalse([u for u in lean_files if u.startswith('/web/static/src/core/%s/' % folder)], folder)
        self.assertTrue(any(u.startswith('/web/static/src/core/dropdown/') for u in lean_files), "what pages use stays")
        self.assertFalse(set(lean_files) - set(full), "nothing added")
        self.assertTrue(any(u.startswith('/website/static/src/') for u in lean_files), "the website's own code stays")
        if 'mtbg.edge.cache' in self.env:  # (Cloudflare Connector's page cache: its session script)
            self.assertTrue(any(u.startswith('/cloudflare_connector/') for u in lean_files), "our own code stays")
        # nothing kept imports what was left out (the module loader would stop every script)
        gone_names = {_name(u) for u in gone}
        broken = sorted('%s <- %s' % (imp, url) for url, asset in lean_files.items() if url.endswith('.js')
                        for imp in IMPORT.findall(asset.content or '') if imp in gone_names)
        self.assertFalse(broken, "kept files import left-out ones: %s" % broken[:5])
        self._switch(False)
        self.assertFalse(self.env['ir.asset'].search([('bundle', '=', lean.BUNDLE), ('directive', '=', 'remove')]),
                         "off: no removals")

    def _css(self, bundle):
        """The bundle's stylesheet, compiled (an SCSS error shows in it as Odoo's error banner)."""
        return b''.join(a.raw for a in self.env['ir.qweb']._get_asset_bundle(bundle, css=True, js=False).css()).decode()

    def test_stylesheet_without_extras(self):
        """0.6.0: the visitors' stylesheet leaves out the editor's and the back end's styles; the background shapes
        come late, their base rules stay in place."""
        self._switch(True)
        full, slim, late = self._css('web.assets_frontend'), self._css(lean.CSS_BUNDLE), self._css(lean.LATE_CSS_BUNDLE)
        for css in (slim, late):
            self.assertNotIn('A css error occured', css)
        self.assertLess(len(slim), len(full) - 50000, "lighter by the shapes at least")
        shape = '.o_we_shape.o_html_builder_'
        if shape in full:
            self.assertNotIn(shape, slim, "the shapes are not in the page's stylesheet")
            self.assertIn(shape, late, "they come late")
        self.assertIn('.o_we_bg_filter', slim, "the backgrounds' base rules stay")
        self.assertIn('.o_we_shape', slim)
        self.assertIn('o_cc', slim, "the website's own styles stay")
        if self.env['ir.module.module'].search_count([('name', '=', 'web_tour'), ('state', '=', 'installed')]):
            self.assertNotIn('o_tour_pointer', slim)
        self._switch(False)
        self.assertFalse(self.env['ir.asset'].search([('name', '=like', 'Page speed: %')]), "off: no records")

    def test_chat_brings_the_bus(self):
        """0.6.0: where CFD's chat tab loads the chat on its own, the bus leaves the visitors' scripts for the chat's
        bundle (Odoo's chat needs it)."""
        if not self.env['ir.module.module'].search_count([('name', '=', lean.CHAT), ('state', '=', 'installed')]):
            self.skipTest('no chat tab')
        self._switch(True)
        page = {a.url for a in self.env['ir.qweb']._get_asset_bundle(lean.BUNDLE, css=False).javascripts}
        chat = {a.url for a in self.env['ir.qweb']._get_asset_bundle(lean.CHAT_BUNDLE, css=False).javascripts}
        self.assertFalse([u for u in page if u.startswith('/bus/')], "no bus in the visitors' scripts")
        self.assertIn('/bus/static/src/services/bus_service.js', chat, "the chat brings it")
        self.assertNotIn('/bus/static/src/workers/bus_worker_script.js', chat)
        # 0.7.12: the chat's widgets too, with their templates; the emojis themselves still when wanted
        self.assertFalse([u for u in page if u.startswith('/web/static/src/core/emoji_picker/')], "not in the page's")
        for url in ('/web/static/src/core/emoji_picker/emoji_picker.js', '/web/static/src/core/color_picker/color_picker.js',
                    '/web/static/src/views/fields/file_handler.js'):
            self.assertIn(url, chat)
        templates = {a.url for a in self.env['ir.qweb']._get_asset_bundle(lean.CHAT_BUNDLE, css=False).templates}
        self.assertIn('/web/static/src/core/emoji_picker/emoji_picker.xml', templates, "with its templates")
        self.assertNotIn('/web/static/src/core/emoji_picker/emoji_data.js', chat)
        # nothing the chat's code imports is missing from the page's and the chat's scripts together
        assets = [a for bundle in ('web.assets_frontend_minimal', lean.BUNDLE, lean.CHAT_BUNDLE)
                  for a in self.env['ir.qweb']._get_asset_bundle(bundle, css=False).javascripts]
        names = {_name(a.url) for a in assets}
        missing = sorted({imp for a in assets if a.url.endswith('.js') for imp in IMPORT.findall(a.content or '')
                          if imp.startswith('@web/core/') and imp not in names and imp + '/index' not in names})
        self.assertFalse(missing, "the chat imports what neither bundle has: %s" % missing[:5])
        self._switch(False)
        chat = {a.url for a in self.env['ir.qweb']._get_asset_bundle(lean.CHAT_BUNDLE, css=False).javascripts}
        self.assertNotIn('/bus/static/src/services/bus_service.js', chat, "off: the chat's bundle as it was")

    def test_who_gets_which(self):
        self._switch(True)
        self.opener = Opener(self)
        for path, slim in (('/contactus', True), ('/', True), ('/my', False), ('/shop', False),
                           ('/web/login', False)):
            response = self.url_open(path, allow_redirects=False)
            if response.status_code != 200:  # (a redirect, or a page this site does not have)
                continue
            self.assertEqual('assets_frontend_lazy_lean' in response.text, slim, path)
            self.assertEqual('assets_frontend_lean.min.css' in response.text, slim, path)
            self.assertEqual('web.assets_frontend.min.css' in response.text, not slim, path)
            self.assertEqual('type="speculationrules"' in response.text, slim, path + ": instant pages (0.7.12)")
        self.authenticate('admin', 'admin')
        page = self.url_open('/contactus').text
        self.assertNotIn('assets_frontend_lazy_lean', page, "logged in: Odoo's own")
        self.assertNotIn('assets_frontend_lean', page, "logged in: Odoo's own stylesheet")
        self.assertNotIn('assets_frontend_late', page)
        self.assertNotIn('speculationrules', page, "logged in: no pages fetched ahead")
        self._switch(False)
        self.opener = Opener(self)
        page = self.url_open('/contactus').text
        self.assertNotIn('assets_frontend_lazy_lean', page, "off: Odoo's own")
        self.assertNotIn('assets_frontend_lean', page, "off: Odoo's own stylesheet")

    def test_visitor_page_runs(self):
        """In a real browser, the visitor's page with the copy loads every script without an error."""
        self._switch(True)
        code = """
const lean = [...document.scripts].some((s) => (s.src || '').includes('assets_frontend_lazy_lean'));
const css = [...document.querySelectorAll('link[rel=stylesheet]')].some((l) => l.href.includes('assets_frontend_lean'));
const errors = odoo.loader.findErrors();
if (!lean || !css) { console.error('test failed: not the visitors copy'); }
else if (Object.keys(errors).length) { console.error('test failed: modules missing ' + JSON.stringify(errors)); }
else { console.log('test successful'); }
"""
        self.browser_js('/contactus', code, ready="odoo.loader && odoo.loader.modules.size > 300", login=None)

    def test_icon_font_in_two_files(self):
        """0.7.11 (owner: "trim font awesome"): the visitors' stylesheet has Font Awesome's icons in two files, the
        site's icons and Odoo's whole font for the others; every icon has one of them. The back end keeps Odoo's."""
        from odoo.tools.misc import file_open
        self._switch(True)
        slim, full = self._css(lean.CSS_BUNDLE), self._css('web.assets_frontend')
        self.assertIn('font_awesome_visitors.woff2', slim)
        self.assertNotIn('font_awesome_visitors', full, "logged-in users and the back end: Odoo's")
        self.assertNotIn('font_awesome_visitors', self._css('web.assets_backend'))
        odoo_css = file_open(lean.FONT_AWESOME).read()
        ours = file_open(lean.FONT_AWESOME_VISITORS).read()
        face = re.compile(r'@font-face\s*\{[^}]*\}')
        # (the same icons, sizes and animations as Odoo's: only the font's files differ)
        bare = lambda css: re.sub(r'/\*.*?\*/', '', face.sub('', css), flags=re.S).split()  # noqa: E731
        self.assertEqual(bare(ours), bare(odoo_css),
                         "Odoo's font-awesome.css changed: run tools/font_awesome_visitors.py again")
        covered = []
        for rule in face.findall(ours):
            points = set()
            for a, b in re.findall(r'U\+([0-9A-F]+)(?:-([0-9A-F]+))?', rule.split('unicode-range:')[1]):
                points.update(range(int(a, 16), int(b or a, 16) + 1))
            covered.append(points)
        small, whole = covered
        self.assertFalse(small & whole, "one file per icon")
        icons = {int(cp, 16) for cp in re.findall(r':before\s*\{\s*content:\s*"\\([0-9a-f]+)"', odoo_css)}
        self.assertFalse(icons - small - whole, "every icon has a file")
        for icon in (0xf005, 0xf206, 0xf041, 0xf232):  # (star, bicycle, map marker, WhatsApp: on the site's pages)
            self.assertIn(icon, small)
        self.assertEqual(self.url_open('/mtbg_tours_page_speed/static/src/fonts/font_awesome_visitors.woff2').status_code,
                         200)
        self._switch(False)
        self.assertNotIn('font_awesome_visitors', self._css(lean.CSS_BUNDLE), "off: Odoo's")

    def test_icon_font_fetched_as_needed(self):
        """In a real browser: a page drawing the site's icons fetches the small file only; an icon it does not have
        brings Odoo's whole font, and draws."""
        self._switch(True)
        code = """
const files = () => performance.getEntriesByType('resource').map((r) => r.name).filter((n) => n.includes('.woff'));
const draw = async (cls) => {
    const i = document.createElement('i');
    i.className = 'fa ' + cls;
    document.body.append(i);
    // (the page's whole stylesheet comes after the page has loaded: until then only its first screen's rules)
    for (let n = 0; n < 100 && getComputedStyle(i, '::before').content === 'none'; n++) {
        await new Promise((r) => setTimeout(r, 100));
    }
    await document.fonts.load('14px FontAwesome', getComputedStyle(i, '::before').content.slice(1, -1));
    return i.getBoundingClientRect().width;
};
(async () => {
    await document.fonts.ready;
    const before = files();  // (the page's own icons)
    const star = await draw('fa-star');
    const first = files();
    const glass = await draw('fa-glass');
    const after = files();
    const small = (l) => l.some((n) => n.includes('font_awesome_visitors.woff2'));
    const whole = (l) => l.some((n) => n.includes('fontawesome-webfont'));
    if (!small(first) || (whole(first) && !whole(before))) { console.error('test failed: the site icon fetched ' + first); }
    else if (!whole(after)) { console.error('test failed: no whole font for another icon ' + after); }
    else if (!(star > 0 && glass > 0)) { console.error('test failed: not drawn ' + star + ' ' + glass); }
    else { console.log('test successful'); }
})();
"""
        self.browser_js('/contactus', code, ready="document.readyState === 'complete'", login=None)

    def test_instant_pages_rules(self):
        """0.7.12: the rules leave out Odoo's back end, the portal, checkout, the token pages, with or without the
        language, and the links with a query string."""
        import json
        rules = json.loads(self.env['mtbg.page.speed.lean'].mtbg_speculation_rules())['prefetch'][0]
        self.assertEqual(rules['eagerness'], 'moderate', "on hover or touch, not every link of the page")
        where = rules['where']['and']
        pattern = where[1]['not']['href_matches']
        self.assertTrue(pattern.startswith('{/:lang}?/(') and pattern.endswith('){/*}?'), pattern)
        for path in ('web', 'my', 'shop', 'pretour', 'i', 'website', 'sitemap\\.xml'):
            self.assertIn('|%s|' % path, '|' + pattern[11:-6] + '|')
        self.assertIn('a[href*="?"]', where[2]['not']['selector_matches'])
        excluded = re.compile('^(?:/[a-z]{2}(?:_[A-Za-z]{2,4})?)?(?:%s)(?:[/.]|$)'
                              % self.env['mtbg.page.speed.lean'].mtbg_prefetch_excluded())
        for path in ('/web/login', '/my', '/es/my/orders', '/shop/cart', '/i/abc', '/web/session/logout'):
            self.assertTrue(excluded.match(path), path)
        for path in ('/', '/tours', '/es/tours/a-ride', '/blog/journal-1', '/website-terms', '/myths'):
            self.assertFalse(excluded.match(path), path)
