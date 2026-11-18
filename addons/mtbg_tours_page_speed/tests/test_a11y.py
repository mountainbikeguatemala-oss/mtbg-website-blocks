import io
from unittest.mock import patch

from PIL import Image

from odoo.tests import HttpCase, TransactionCase, tagged

from odoo.addons.mtbg_tours_page_speed.models import a11y, lighten

PAGE = (b'<html><head><title>Lake Atitlan Ride | Example Tours</title></head><body><header>'
        b'<a href="/" class="navbar-brand logo"><img src="/web/image/website/1/logo" alt="Example Tours" loading="lazy"/>'
        b'</a></header><main><img src="/web/image/12-abc/lake-atitlan-sunset_2-1024x683.jpg"/>'
        b'<img src="/web/image/13/800x600"/><img src="/web/image/14/IMG_1234.JPG" loading="lazy"/>'
        b'<img src="/deco.png" alt=""/>'
        b'<a href="https://maps.app.goo.gl/x"><img src="/web/image/15" alt=""/></a>'
        b'<a href="/web/image/16"><span class="tile"></span></a>'
        b'<img width="125" alt="" src="/mtbg_tours/bike_type_icon/4" title="Bring your own bike"/>'
        b'<img alt="" src="/web/image/17" class="o_flag icon"/><a href="https://maps.app.goo.gl/y"><i class="fa fa-map"/></a>'
        b'<a href="/what-level-am-i/">Learn more</a><a href="/tours" aria-label="All tours"><i class="fa fa-x"/></a>'
        b'<a href="/contactus">Contact us</a><a href="#top"><i class="fa fa-up" aria-label="Back to top"/></a>'
        b'</main></body></html>')


@tagged('post_install', '-at_install', 'mtbg')
class TestAccessible(TransactionCase):
    """0.4.0: what screen readers and search engines read, at render time (nothing stored is changed)."""

    def test_page(self):
        out = a11y.accessible(PAGE, {13: 'tecpan-xc-trail.webp'}, 'Example Tours')
        self.assertIn(b'<img alt="Lake atitlan sunset" src="/web/image/12-abc/', out, "its file's name in words")
        self.assertIn(b'<img alt="Tecpan xc trail" src="/web/image/13/800x600"/>', out, "its attachment's name")
        self.assertIn(b'<img alt="Lake Atitlan Ride" src="/web/image/14/IMG_1234.JPG"', out, "a camera's name: the title")
        self.assertIn(b'<img src="/deco.png" alt=""/>', out, "a decoration stays one")
        self.assertNotIn(b'logo" loading="lazy"', out.replace(b'alt="Example Tours" loading', b''))
        self.assertIn(b'alt="Example Tours"/></a></header>', out, "the logo is not lazy")
        self.assertIn(b'<a href="https://maps.app.goo.gl/x"><img src="/web/image/15" alt="Lake Atitlan Ride"/></a>', out,
                      "a photo with alt=\"\" (the editor's): the title; its link is named by it")
        self.assertIn(b'<a aria-label="Open photo" href="/web/image/16">', out)
        self.assertIn(b'<img width="125" alt="Bring your own bike" src="/mtbg_tours/bike_type_icon/4"', out, "its title")
        self.assertIn(b'<img alt="" src="/web/image/17" class="o_flag icon"/>', out, "an icon stays a decoration")
        self.assertIn(b'<a aria-label="Open the map" href="https://maps.app.goo.gl/y">', out)
        self.assertIn(b'<a aria-label="Learn more: What level am i" href="/what-level-am-i/">', out)
        self.assertIn(b'<a href="/tours" aria-label="All tours">', out, "named already")
        self.assertIn(b'<a href="/contactus">Contact us</a>', out)
        self.assertIn(b'<a href="#top"><i class="fa fa-up" aria-label="Back to top"/></a>', out)
        self.assertEqual(a11y.accessible(out, {}, 'x'), out, "once")

    def test_own_site_links_by_the_sites_address(self):
        """A link to the site's own address is one of its pages (named by its path), another site's by its host: the
        address comes from the request, never a business's domain in the code."""
        page = b'<html><body><a href="https://www.own-example.com/tours/">Learn more</a> <a href="https://other.org/x">Learn more</a></body></html>'
        out = a11y.accessible(page, {}, 'x', ('own-example.com',))
        self.assertIn(b'aria-label="Learn more: Tours"', out)
        self.assertIn(b'aria-label="Learn more: other.org"', out)

    def test_file_words(self):
        for name, words in (('lake-atitlan-sunset_2-1024x683.jpg', 'Lake atitlan sunset'), ('IMG_1234.JPG', ''),
                            ('DSC0042.jpg', ''), ('20230512_101010.jpg', ''), ('Tecpan%20XC%20trail.jpg', 'Tecpan XC trail')):
            self.assertEqual(a11y.words_of_file(name), words, name)


@tagged('post_install', '-at_install', 'mtbg')
class TestAccessiblePages(HttpCase):

    def test_anonymous_page(self):
        response = self.url_open('/contactus')
        self.assertEqual(response.status_code, 200)
        self.assertNotRegex(response.text, r'<img(?![^>]*\salt=)[^>]*>', "every picture has an alt")
        self.assertNotRegex(response.text, r'navbar-brand[^>]*>\s*<img[^>]*loading="lazy"', "the logo is not lazy")


def _webp(width, height, quality=95):
    image = Image.effect_noise((width, height), 60).convert('RGB')
    out = io.BytesIO()
    image.save(out, 'WEBP', quality=quality)
    return out.getvalue()


@tagged('post_install', '-at_install', 'mtbg')
class TestLighterCopies(TransactionCase):
    """0.4.0: the screen copies made again at WebP q70, from their original, once each, only when lighter."""

    def test_lighten(self):
        Attachment = self.env['ir.attachment'].sudo()
        self.env['ir.config_parameter'].sudo().set_param(lighten.LAST, '0')
        original = Attachment.create({'name': 'big.webp', 'raw': _webp(1600, 1000), 'mimetype': 'image/webp',
                                      'public': True})
        copy = Attachment.create({'name': 'big.webp', 'raw': _webp(800, 500), 'mimetype': 'image/webp', 'public': True,
                                  'description': 'resize: 800', 'res_model': 'ir.attachment', 'res_id': original.id,
                                  **({'original_id': original.id} if 'original_id' in Attachment._fields else {})})
        before = copy.file_size
        with patch.object(lighten, 'MIN_SIZE', 0):
            looked, lighter, _kb = Attachment._mtbg_lighten_copies(limit=1000)
        self.assertGreaterEqual(looked, 1)
        self.assertLess(copy.file_size, before * lighten.GAIN + 1)
        self.assertEqual(Image.open(io.BytesIO(copy.raw)).size, (800, 500), "the same size on screen")
        self.assertEqual(copy.mimetype, 'image/webp')
        again = copy.file_size
        with patch.object(lighten, 'MIN_SIZE', 0):
            Attachment._mtbg_lighten_copies(limit=1000)
        self.assertEqual(copy.file_size, again, "once per copy")


@tagged('post_install', '-at_install', 'mtbg')
class TestBackgroundCopies(TransactionCase):
    """0.4.1: a section's background photo saved with &#39; quotes is seen; the job makes the phone and tablet copies
    of background photos that have none, then one purge."""

    def test_single_quotes_seen(self):
        from odoo.addons.mtbg_tours_page_speed.models.ir_http import BACKGROUND
        page = b'<section style="background-image: url(&#39;/web/image/2552&#39;); background-size: cover;">'
        self.assertEqual(BACKGROUND.search(page).group(1), b'/web/image/2552')
        for quote in (b'&#34;', b'&quot;', b'"', b"'", b''):
            found = BACKGROUND.search(b'background-image: url(' + quote + b'/web/image/7' + quote + b')')
            self.assertEqual(found.group(1), b'/web/image/7', quote)

    def test_copies_made_once_then_purged_once(self):
        Attachment = self.env['ir.attachment'].sudo()
        photo = Attachment.create({'name': 'cover.webp', 'raw': _webp(1920, 1300, 95), 'mimetype': 'image/webp',
                                   'public': True})
        source = Attachment.create({'name': 'source.webp', 'raw': _webp(400, 300), 'mimetype': 'image/webp',
                                    'public': True})
        edited = Attachment.create({'name': 'edited.webp', 'raw': _webp(1700, 1100, 95), 'mimetype': 'image/webp',
                                    'public': True, **({'original_id': source.id} if 'original_id' in Attachment._fields
                                                       else {})})
        small = Attachment.create({'name': 'small.webp', 'raw': _webp(600, 400), 'mimetype': 'image/webp',
                                   'public': True})
        self.env['ir.ui.view'].create({
            'name': 'Edge cover', 'type': 'qweb', 'key': 'mtbg_tours_page_speed.test_cover',
            'arch': '<t><section style="background-image: url(&#39;/web/image/%s&#39;);"/>'
                    '<section style="background-image: url(&quot;/web/image/%s&quot;);"/>'
                    '<section style="background-image: url(&quot;/web/image/%s&quot;);"/></t>' % (photo.id, small.id, edited.id)})
        self.env.flush_all()
        self.assertIn(photo.id, Attachment._mtbg_background_ids())
        purges = []
        if 'mtbg.edge.cache' in self.env:
            changed = patch.object(type(self.env['mtbg.edge.cache']), '_mtbg_changed', autospec=True,
                                   side_effect=lambda *a: purges.append(1))
            changed.start()
            self.addCleanup(changed.stop)
        Attachment._mtbg_background_copies(limit=1000)
        copies = Attachment.search([('res_model', '=', 'ir.attachment'), ('res_id', '=', photo.id),
                                    ('description', '=like', 'resize: %')])
        self.assertEqual(sorted(copies.mapped('description')), ['resize: 1280', 'resize: 1920', 'resize: 800'],
                         "phone, tablet and (0.7.1) computer copies")
        desk = copies.filtered(lambda c: c.description == 'resize: 1920')
        self.assertLessEqual(desk.file_size, photo.file_size * 0.8, "the computer copy: clearly lighter")
        self.assertTrue(all(c.public and c.mimetype == 'image/webp' and c.file_size < photo.file_size for c in copies))
        self.assertEqual(Image.open(io.BytesIO(copies.filtered(lambda c: c.description == 'resize: 800').raw)).size,
                         (800, 542))
        self.assertTrue(Attachment.search_count([('res_id', '=', edited.id), ('res_model', '=', 'ir.attachment'),
                                                 ('description', '=like', 'resize: %')]),
                        "a picture the editor made (cropped from another): its copies too (0.7.1, www's homepage photo)")
        self.assertFalse(Attachment.search_count([('res_id', '=', small.id), ('res_model', '=', 'ir.attachment'),
                                                  ('description', '=like', 'resize: %')]), "smaller than a phone")
        if 'mtbg.edge.cache' in self.env:
            self.assertEqual(len(purges), 1, "one purge")
        Attachment._mtbg_background_copies(limit=1000)
        self.assertEqual(Attachment.search_count([('res_model', '=', 'ir.attachment'), ('res_id', '=', photo.id),
                                                  ('description', '=like', 'resize: %')]), 3, "once")
        if 'mtbg.edge.cache' in self.env:
            self.assertEqual(len(purges), 1, "nothing made, no purge")


@tagged('post_install', '-at_install', 'mtbg')
class TestShownSizes(TransactionCase):
    """0.4.2: a picture whose srcset says "100vw" while it is shown 250 px wide fetched its 1920 px original."""

    def test_sizes(self):
        from odoo.addons.mtbg_tours_page_speed.models.ir_http import speed_up
        srcset = b'srcset="/web/image/20619 256w, /web/image/20622 1280w, /web/image/2667 1600w" sizes="100vw"'
        page = (b'<html><head></head><body><div id="wrap"><p>x</p>'
                b'<img ' + srcset + b' src="/web/image/2667" style="width: 250px; max-width: 100%;" loading="lazy"/>'
                b'<div class="row"><div class="col-lg-4 pt16"><img ' + srcset + b' src="/web/image/2" loading="lazy"/>'
                b'</div></div><div class="col-md-6"><img ' + srcset + b' src="/web/image/3" loading="lazy"/></div>'
                b'<img ' + srcset + b' src="/web/image/4" loading="lazy"/>'
                b'<img srcset="/web/image/5 800w" sizes="(min-width: 992px) 50vw, 100vw" src="/web/image/5"/>'
                b'</div></body></html>')
        out = speed_up(page)
        self.assertIn(b'<img sizes="(max-width: 250px) 100vw, 250px" ', out, "its styled width")
        self.assertIn(b'<img sizes="(min-width: 1200px) 380px, (min-width: 992px) 320px, 100vw" srcset=', out,
                      "its column (col-lg-4)")
        self.assertIn(b'<img sizes="(min-width: 768px) 360px, 100vw" srcset=', out, "col-md-6")
        self.assertIn(b'<img sizes="(min-width: 1200px) 1140px, 100vw" srcset=', out, "the page's container")
        self.assertIn(b'sizes="(min-width: 992px) 50vw, 100vw" src="/web/image/5"', out, "sizes of its own: kept")
        self.assertNotIn(b'sizes="100vw"', out)

    def test_private_copy_of_a_public_photo_lightened(self):
        Attachment = self.env['ir.attachment'].sudo()
        self.env['ir.config_parameter'].sudo().set_param(lighten.LAST, '0')
        photo = Attachment.create({'name': 'hero.webp', 'raw': _webp(1600, 1000), 'mimetype': 'image/webp',
                                   'public': True})
        copy = Attachment.create({'name': 'hero.webp', 'raw': _webp(1280, 800), 'mimetype': 'image/webp',
                                  'public': False, 'description': 'resize: 1280', 'res_model': 'ir.attachment',
                                  'res_id': photo.id})
        secret = Attachment.create({'name': 's.webp', 'raw': _webp(1600, 1000), 'mimetype': 'image/webp'})
        other = Attachment.create({'name': 's.webp', 'raw': _webp(1280, 800), 'mimetype': 'image/webp',
                                   'description': 'resize: 1280', 'res_model': 'ir.attachment', 'res_id': secret.id})
        before, before_other = copy.file_size, other.file_size
        with patch.object(lighten, 'MIN_SIZE', 0):
            Attachment._mtbg_lighten_copies(limit=1000)
        self.assertLess(copy.file_size, before, "the hero's sized address is answered with it")
        self.assertEqual(Image.open(io.BytesIO(copy.raw)).size, (1280, 800))
        self.assertEqual(other.file_size, before_other, "a private picture's copy: left alone")



@tagged('post_install', '-at_install', 'mtbg')
class TestDesktopAndPhoneCopies(TransactionCase):
    """0.7.1 (owner's go, 2026-11-07): computers get a lighter 1920 copy of big photos; phones the first picture's
    ~800 px copy (a 2.6x phone took the 1280 copy: ~340 KB for the tour pages' main photo)."""

    KNOWN = {11902: {'width': 1920, 'height': 1280, 'size': 352000,
                     'copies': [(800, 21, 90000), (1280, 22, 200000), (1920, 23, 210000)]},
             2668: {'width': 1920, 'height': 1280, 'size': 347000,
                    'copies': [(800, 31, 120000), (1280, 32, 290000), (1920, 33, 200000)]}}

    def test_background_desktop_copy(self):
        from odoo.addons.mtbg_tours_page_speed.models.ir_http import speed_up
        page = (b'<html><head></head><body><div id="wrap"><section style="background-image: url(&#39;'
                b'/web/image/11902-6333e116/hero.jpg&#39;)">hero</section></div></body></html>')
        out = speed_up(page, lambda ids: self.KNOWN)
        self.assertIn(b'@media (min-width: 1280px){[data-mtbg-bg="0"]{background-image:url("/web/image/23")!important}}',
                      out)
        self.assertIn(b'media="(min-width: 1280px)" href="/web/image/23"', out, "computers preload the copy")
        self.assertNotIn(b'href="/web/image/11902-6333e116/hero.jpg"', out, "never the photo itself")

    def test_cover_srcset_and_phone_cap(self):
        from odoo.addons.mtbg_tours_page_speed.models.ir_http import speed_up
        page = (b'<html><head></head><body><div id="wrap"><img class="mtbg-tour-cover img-fluid w-100" '
                b'sizes="(min-width: 1200px) 1140px, 100vw" src="/web/image/2668" srcset="/web/image/2668/800x800 800w, '
                b'/web/image/2668/1280x1280 1280w, /web/image/2668 1920w"/></div></body></html>')
        out = speed_up(page, lambda ids: self.KNOWN)
        self.assertIn(b'/web/image/2668/1280x1280 1280w, /web/image/33 1920w"', out, "computers: the lighter copy")
        self.assertIn(b'sizes="(max-width: 767.98px) 50vw, (min-width: 1200px) 1140px, 100vw"', out, "phones: 800")
        self.assertIn(b'imagesizes="(max-width: 767.98px) 50vw, (min-width: 1200px) 1140px, 100vw"', out,
                      "the preload chooses as the picture does")

    def test_desktop_copy_only_when_clearly_lighter(self):
        from odoo.addons.mtbg_tours_page_speed.models.ir_http import _desktop_copy
        self.assertIsNone(_desktop_copy({'width': 1920, 'size': 100000, 'copies': [(1920, 5, 90000)]}))
        self.assertEqual(_desktop_copy({'width': 1920, 'size': 100000, 'copies': [(1920, 5, 70000)]}),
                         (b'/web/image/5', 1920))
        self.assertIsNone(_desktop_copy({'width': 1920, 'size': 100000, 'copies': [(1280, 5, 30000)]}),
                          "a tablet copy is too small for a computer")
