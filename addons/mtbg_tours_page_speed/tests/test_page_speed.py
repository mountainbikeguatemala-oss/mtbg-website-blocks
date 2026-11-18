import re

from odoo.tests import HttpCase, TransactionCase, tagged

from odoo.addons.mtbg_tours_page_speed.models.ir_http import (
    QUIET_BG_MEDIA, _stylesheet_imports, fonts_early, logo_cached, speed_up)

HERO = (b'<html><head></head><body><main><section class="s_parallax" style="background-image: url(&#34;'
        b'/web/image/11902-6333e116/hero.jpg&#34;)"></section><img src="/web/image/5" loading="lazy"/></main>'
        b'</body></html>')


@tagged('post_install', '-at_install', 'mtbg')
class TestFontsFirst(TransactionCase):
    """The theme's font stylesheets come with the site's stylesheet, not after it (0.3.0)."""

    PAGE = (b'<html><head><link type="text/css" rel="stylesheet" href="/web/assets/1/abc/web.assets_frontend.min.css"/>'
            b'</head><body><div id="wrap"></div></body></html>')

    def test_imports_preloaded(self):
        asked = []
        imports = ['https://fonts.googleapis.com/css?family=Raleway:400&display=swap', '/web/content/7/google-font-X']
        out = fonts_early(self.PAGE, lambda url: asked.append(url) or imports)
        self.assertEqual(asked, ['/web/assets/1/abc/web.assets_frontend.min.css'])
        self.assertIn(b'<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin=""/>', out)
        self.assertIn(b'<link rel="preload" as="style" href="https://fonts.googleapis.com/css?family=Raleway:400&amp;'
                      b'display=swap" data-mtbg-fonts=""/>', out)
        self.assertIn(b'<link rel="preload" as="style" href="/web/content/7/google-font-X" data-mtbg-fonts=""/></head>',
                      out)
        self.assertEqual(fonts_early(out, lambda url: imports), out, "once (a page served again from the page cache)")

    def test_nothing_imported_or_no_stylesheet(self):
        self.assertIs(fonts_early(self.PAGE), self.PAGE)
        page = b'<html><head></head><body></body></html>'
        self.assertIs(fonts_early(page, lambda url: ['/x.css']), page)

    def test_stylesheet_not_made_yet(self):
        self.assertEqual(_stylesheet_imports(self.env)('/web/assets/1/none/web.assets_frontend.min.css'), [],
                         "a stylesheet not made yet: nothing (and asked again next time)")


@tagged('post_install', '-at_install', 'mtbg')
class TestPictures(TransactionCase):

    def test_first_img_not_lazy_and_preloaded(self):
        page = (b'<html><head><title>x</title></head><body><header><img src="/logo.png" loading="lazy"/></header>'
                b'<div id="wrap"><img src="/web/image/12/800x600" class="img" loading="lazy"/>'
                b'<img src="/web/image/13" loading="lazy"/></div></body></html>')
        out = speed_up(page)
        self.assertIn(b'<head><link rel="preload" as="image" fetchpriority="high" href="/web/image/12/800x600"/>'
                      b'<title>', out, "at the top of the head (0.7.10)")
        charset = speed_up(page.replace(b'<head>', b'<head><meta charset="utf-8"/>'))
        self.assertIn(b'<meta charset="utf-8"/><link rel="preload" as="image"', charset, "after the charset")
        self.assertEqual(speed_up(out), out, "once")
        self.assertIn(b'<img fetchpriority="high" src="/web/image/12/800x600" class="img"/>', out)
        self.assertIn(b'<img src="/logo.png" loading="lazy"/>', out, "the header's pictures as they were")
        self.assertIn(b'<img src="/web/image/13" loading="lazy"/>', out, "the others stay lazy")

    def test_first_img_preloaded_as_its_srcset(self):
        # (the tour page's cover: a srcset of its own; the phone takes the 800 copy, never the original besides it)
        page = (b'<html><head></head><body><div id="wrap"><img sizes="(min-width: 1200px) 1140px, 100vw" '
                b'fetchpriority="high" src="/web/image/2668" srcset="/web/image/2668/800x800 800w, /web/image/2668 '
                b'1920w"/></div></body></html>')
        out = speed_up(page)
        self.assertIn(b'<link rel="preload" as="image" fetchpriority="high" imagesrcset="/web/image/2668/800x800 800w, '
                      b'/web/image/2668 1920w" imagesizes="(max-width: 767.98px) 50vw, (min-width: 1200px) 1140px, 100vw" href="/web/image/2668"/>',
                      out)
        known = {77: {'width': 1920, 'height': 1080, 'size': 500000, 'copies': [(800, 42, 80000)]}}
        out = speed_up(b'<html><head></head><body><div id="wrap"><img src="/web/image/77" class="img-fluid"/>'
                       b'</div></body></html>', lambda ids: known)
        self.assertIn(b'imagesrcset="/web/image/42 800w, /web/image/77 1920w" imagesizes="(max-width: 767.98px) 50vw, (min-width: 1200px) 1140px, 100vw" href="/web/image/77"',
                      out, "the srcset given here preloaded too")

    def test_only_the_first_picture_eager(self):
        # (a row of cards: three eager photos on a computer, one on screen on a phone)
        page = (b'<html><head></head><body><div id="wrap">'
                b'<img class="mtbg-card__img" loading="eager" fetchpriority="high" src="/web/image/1/600x400"/>'
                b'<img class="mtbg-card__img" loading="eager" src="/web/image/2/600x400"/>'
                b'<img class="mtbg-card__img" loading="eager" src="/web/image/3/600x400"/>'
                b'<img class="mtbg-card__img" loading="lazy" src="/web/image/4/600x400"/></div></body></html>')
        out = speed_up(page)
        self.assertIn(b'<img class="mtbg-card__img" loading="eager" fetchpriority="high" src="/web/image/1/600x400"/>',
                      out)
        self.assertIn(b'<img class="mtbg-card__img" loading="lazy" src="/web/image/2/600x400"/>', out)
        self.assertIn(b'<img class="mtbg-card__img" loading="lazy" src="/web/image/3/600x400"/>', out)
        self.assertEqual(out.count(b'rel="preload" as="image"'), 1)

    def test_background_not_public_preloaded_as_it_is(self):
        out = speed_up(HERO)  # (no public picture known: nothing resized)
        self.assertIn(b'href="/web/image/11902-6333e116/hero.jpg"/></head>', out)
        self.assertNotIn(b'data-mtbg-bg', out)
        self.assertIn(b'<img src="/web/image/5" loading="lazy"/>', out, "after the hero: still lazy")

    def test_background_phone_and_tablet_copies(self):
        info = {'width': 1920, 'height': 1080, 'size': 600000,
                'copies': [(480, 31, 30000), (800, 32, 90000), (1280, 33, 200000)]}
        out = speed_up(HERO, lambda ids: {11902: info})
        self.assertIn(b'<section data-mtbg-bg="0" class="s_parallax"', out)
        self.assertIn(b'@media (max-width: 767.98px){[data-mtbg-bg="0"]{background-image:url("/web/image/32")'
                      b'!important}}', out)
        self.assertIn(b'url("/web/image/33")', out)
        self.assertIn(b'media="(max-width: 767.98px)" href="/web/image/32"', out, "preloaded per screen")
        self.assertIn(b'media="(min-width: 1280px)" href="/web/image/11902-6333e116/hero.jpg"', out)
        self.assertEqual(out.count(b'rel="preload"'), 3, "one per screen, never the original on a phone")

    def test_background_without_ready_or_lighter_copy_left_alone(self):
        for copies in ([], [(800, 32, 700000), (1280, 33, 900000)]):  # none, or heavier than the original
            out = speed_up(HERO, lambda ids: {11902: {'width': 1920, 'height': 1080, 'size': 600000,
                                                     'copies': copies}})
            self.assertNotIn(b'data-mtbg-bg', out)
            self.assertIn(b'href="/web/image/11902-6333e116/hero.jpg"/></head>', out, "the original, as before")

    def test_background_phone_copy_only(self):
        out = speed_up(HERO, lambda ids: {11902: {'width': 1100, 'height': 700, 'size': 300000,
                                                  'copies': [(800, 32, 90000)]}})
        self.assertIn(b'url("/web/image/32")', out)
        self.assertNotIn(b'1280px)){', out)
        self.assertIn(b'media="(min-width: 768px) and (max-width: 1279.98px), (min-width: 1280px)" '
                      b'href="/web/image/11902-6333e116/hero.jpg"', out, "tablets and computers: the original")

    def test_photo_size_and_copies(self):
        page = (b'<html><head></head><body><div id="wrap"><p>x</p>'
                b'<img src="/web/image/77/view.jpg" class="img img-fluid" loading="lazy"/>'
                b'<img src="/web/image/78" class="img-fluid" style="height: 100%" loading="lazy"/>'
                b'<img src="/web/image/79/600x400" class="img-fluid" loading="lazy"/></div></body></html>')
        known = {77: {'width': 1920, 'height': 1080, 'size': 500000,
                      'copies': [(480, 41, 30000), (800, 42, 80000), (1280, 43, 600000)]},
                 78: {'width': 1200, 'height': 800, 'size': 200000, 'copies': []}}
        out = speed_up(page, lambda ids: known)
        self.assertIn(b'width="1920" height="1080"', out)
        self.assertIn(b'srcset="/web/image/41 480w, /web/image/42 800w, /web/image/77/view.jpg 1920w" sizes="(max-width: 767.98px) 50vw, (min-width: 1200px) 1140px, 100vw"',
                      out, "the 1280 copy is heavier than the original: left out")
        self.assertNotIn(b'width="1200"', out, "a height of its own: no size added")
        self.assertNotIn(b'/web/image/78 1200w', out, "no ready copy: no srcset")
        self.assertIn(b'<img src="/web/image/79/600x400" class="img-fluid" loading="lazy"/>', out, "a sized address: as it is")

    def test_nothing_to_do(self):
        page = b'<html><head></head><body><div id="wrap"><p>text</p></div></body></html>'
        self.assertIs(speed_up(page), page)

    def test_back_button_label(self):
        self.assertIn('aria-label="Back"', self.env.ref('website.submenu').get_combined_arch())


@tagged('post_install', '-at_install', 'mtbg')
class TestTourCoverFirst(TransactionCase):
    """0.9.1 (owner 2026-11-17, www speed log: a tour page's LCP 9.6 s on a phone): the cover is the page's one urgent
    picture, asked for as a phone shows it; the page's background tile waits; the logo is kept at Cloudflare's edge."""

    TOUR = (b'<html><head><meta charset="utf-8"/><meta http-equiv="X-UA-Compatible" content="IE=edge"/>'
            b'<meta name="viewport" content="width=device-width, initial-scale=1"/><title>t</title></head><body>'
            b'<header><a href="/" class="navbar-brand logo"><span><img src="/web/image/website/1/logo/Example%20Tours'
            b'?unique=9f8fb93" class="img img-fluid" width="95" height="40" alt="Example Tours"/></span></a></header>'
            b'<main><div id="wrap" class="mtbg-tour-page has-page-bg" style="--mtbg-page-bg: url(/web/image/8471-195b305b);'
            b' background-image: url(/web/image/8471-195b305b)"><div class="container"><img class="mtbg-tour-cover '
            b'img-fluid w-100" sizes="(min-width: 1200px) 1140px, 100vw" fetchpriority="high" src="/web/image/3121" '
            b'srcset="/web/image/3121/800x800 800w, /web/image/3121/1280x1280 1280w, /web/image/3121 1920w"/>'
            b'</div></div></main></body></html>')

    def test_cover_urgent_background_not(self):
        out = speed_up(self.TOUR)
        head = out[:out.index(b'</head>')]
        preloads = re.findall(rb'<link rel="preload"[^>]*>', head)
        self.assertEqual(len(preloads), 2)
        cover = next(p for p in preloads if b'3121' in p)
        tile = next(p for p in preloads if b'8471' in p)
        self.assertIn(b'fetchpriority="high"', cover, "the cover: the page's one urgent picture")
        self.assertNotIn(b'fetchpriority', tile, "the background tile: never urgent")
        self.assertIn(b'media="%s"' % QUIET_BG_MEDIA, tile, "computers only (phones paint it below the top section)")
        self.assertEqual(out.count(b'fetchpriority="high"'), 2, "the cover's preload and the cover itself, nothing else")

    def test_preload_after_the_viewport(self):
        out = speed_up(self.TOUR)
        # (read before the viewport, a phone took the page as 980 px wide: its imagesizes chose the 1920 original)
        self.assertLess(out.index(b'name="viewport"'), out.index(b'rel="preload"'))
        self.assertLess(out.index(b'rel="preload"'), out.index(b'<title>'), "still at the top of the head")
        self.assertLess(out.index(b'<meta charset="utf-8"/>'), 1024)
        self.assertIn(b'imagesizes="(max-width: 767.98px) 50vw, (min-width: 1200px) 1140px, 100vw"', out,
                      "the cover as a phone shows it: its ~800 px copy (0.7.1)")
        bare = self.TOUR.replace(b'<meta name="viewport" content="width=device-width, initial-scale=1"/>', b'')
        self.assertIn(b'<meta charset="utf-8"/><link rel="preload"', speed_up(bare), "no viewport: after the charset")

    def test_background_alone_stays_urgent(self):
        page = self.TOUR.replace(b'<div class="container"><img', b'<div class="container"><i').replace(
            b'srcset=', b'data-x=')
        out = speed_up(page)
        self.assertIn(b'<link rel="preload" as="image" fetchpriority="high" href="/web/image/8471-195b305b"/>', out,
                      "without a photo after it the background is the first picture, as before")

    def test_page_background_copy_for_phones(self):
        known = {8471: {'width': 1920, 'height': 1080, 'size': 600000, 'copies': [(800, 32, 90000)]}}
        out = speed_up(self.TOUR, lambda ids: known)
        self.assertIn(b'background-image:url("/web/image/32")!important;--mtbg-page-bg:url("/web/image/32")!important',
                      out, "a tour's phone layer paints the phone copy too")
        self.assertNotIn(b'href="/web/image/32"', out, "not preloaded ahead of the cover")

    def test_logo_at_an_address_cloudflare_keeps(self):
        out = logo_cached(self.TOUR, b'svg')
        self.assertIn(b'src="/web/image/website/1/logo/logo.svg?unique=9f8fb93"', out)
        self.assertEqual(logo_cached(self.TOUR, None), self.TOUR, "a logo of another type: as it is")
        self.assertEqual(logo_cached(out, b'svg'), out, "once")


@tagged('post_install', '-at_install', 'mtbg')
class TestPicturesPages(HttpCase):

    def test_icon_font_not_before_the_text(self):
        page = self.url_open('/contactus').text
        self.assertNotIn('fontawesome-webfont.woff2?v=4.7.0" as="font"', page)
        css = re.search(r'href="(/web/assets/[^"]*(?:web\.assets_frontend|assets_frontend_lean)\.min\.css)"', page).group(1)
        if '@import' in self.url_open(css).text[:20000]:  # (the theme's fonts, when it has any)
            again = self.url_open('/contactus').text
            # (0.7.7: with the first screen first, the fonts are linked in the head instead of preloaded)
            self.assertTrue('data-mtbg-fonts=""' in again or 'fonts.googleapis.com/css' in again.split('</head>')[0]
                            and 'data-mtbg-first-screen' in again, "the theme's fonts asked for early")

    def test_logo_address(self):
        logo = self.env['website'].get_current_website().logo
        page = self.url_open('/').text
        if logo and 'navbar-brand' in page:
            self.assertRegex(page, r'/web/image/website/\d+/logo/logo\.(svg|png|webp|jpg|gif)\?unique=[0-9a-f]+"',
                             "the logo at an address ending in its type (Cloudflare keeps such files)")
            found = re.search(r'(/web/image/website/\d+/logo/logo\.\w+\?unique=[0-9a-f]+)"', page).group(1)
            self.assertEqual(self.url_open(found).status_code, 200, "the same logo")

    def test_anonymous_page_once_and_logged_in_untouched(self):
        page = self.url_open('/').text
        self.assertLessEqual(page.count('as="image" fetchpriority="high" href'), 3)
        self.authenticate('admin', 'admin')
        self.assertNotIn('rel="preload" as="image" fetchpriority="high"', self.url_open('/').text)
