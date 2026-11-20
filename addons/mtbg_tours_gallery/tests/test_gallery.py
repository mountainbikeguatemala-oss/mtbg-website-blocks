import base64
import io

from PIL import Image
import PIL.WebPImagePlugin  # noqa: F401

from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

from ..services.layout import justified, layout, patterns


def _picture(width, height, fmt='PNG'):
    buf = io.BytesIO()
    Image.new('RGB', (width, height), 'green').save(buf, fmt)
    return base64.b64encode(buf.getvalue())


def _photos(*ratios):
    return [{'ratio': r} for r in ratios]


@tagged('post_install', '-at_install', 'mtbg')
class TestLayout(TransactionCase):
    """Rows like the old site's Jetpack Tiled Gallery, with the shares and heights kept within limits."""

    def test_rhythm_of_the_example_page(self):
        # Top of the World: 15 photos -> big + stack, stack + big, three pairs, big + stack
        self.assertEqual(patterns(15, ('big_left', 'big_right', 'pair', 'pair', 'pair')),
                         ['big_left', 'big_right', 'pair', 'pair', 'pair', 'big_left'])

    def test_shares_match_jetpack(self):
        # 4:3 beside a 3:2 over a 4:3: Jetpack measured 65.5 % / 34.5 %
        row = layout(_photos(4 / 3, 1.5, 4 / 3))[0]
        self.assertAlmostEqual(row['columns'][0]['share'], 0.654, places=2)
        self.assertEqual([len(c['cells']) for c in row['columns']], [1, 2])
        # the second row has the big photo on the right
        row = layout(_photos(1, 1, 1, 1.5, 1.5, 1.5))[1]
        self.assertEqual([len(c['cells']) for c in row['columns']], [2, 1])

    def test_limits(self):
        # a panorama beside two portraits would take 87 %: kept at 70 %
        row = layout(_photos(4, 0.66, 0.66))[0]
        self.assertAlmostEqual(row['columns'][0]['share'], 0.70)
        self.assertAlmostEqual(row['columns'][1]['share'], 0.30)
        # two panoramas: a row no flatter than 4:1
        row = layout(_photos(1, 1, 1, 1, 1, 1, 5, 5))[2]
        self.assertAlmostEqual(row['ratio'], 4.0)
        # pairs share 40-60 %
        self.assertAlmostEqual(row['columns'][0]['share'], 0.5)
        row = layout(_photos(1, 1, 1, 1, 1, 1, 3, 0.5))[2]
        self.assertAlmostEqual(row['columns'][0]['share'], 0.6)

    def test_last_row_fits_the_photos_left(self):
        self.assertEqual([r['pattern'] for r in layout(_photos(1.5, 1.5, 1.5, 1.5))], ['big_left', 'one'])
        self.assertEqual([r['pattern'] for r in layout(_photos(1.5, 1.5, 1.5, 1.5, 1.5))], ['big_left', 'pair'])
        self.assertEqual(layout([]), [])

    def test_phone_rows(self):
        self.assertEqual([r['pattern'] for r in layout(_photos(*[1.5] * 7), 'phone')], ['one', 'pair', 'big_left', 'one'])
        # a single landscape photo: no flatter than the phone's limit
        self.assertAlmostEqual(layout(_photos(3), 'phone')[0]['ratio'], 1 / 0.45)

    def test_stacked_photos_share_by_shape(self):
        row = layout(_photos(1.5, 2, 1))[0]
        cells = row['columns'][1]['cells']
        self.assertAlmostEqual(cells[0]['grow'], 100 / 3)
        self.assertAlmostEqual(cells[1]['grow'], 200 / 3)
        self.assertAlmostEqual(row['columns'][0]['cells'][0]['grow'], 100, msg="a single photo fills its column")


@tagged('post_install', '-at_install', 'mtbg')
class TestPictures(TransactionCase):

    def test_size_measured_and_kept(self):
        att = self.env['ir.attachment'].create({'name': 'a.png', 'datas': _picture(64, 48), 'public': True})
        att._mtbg_measure()
        self.assertEqual((att.mtbg_width, att.mtbg_height), (64, 48))
        att.datas = _picture(30, 60)
        self.assertEqual(att.mtbg_width, 0, "a new file is measured again")
        att._mtbg_measure()
        self.assertEqual((att.mtbg_width, att.mtbg_height), (30, 60))

    def test_webp_copies_and_srcset(self):
        att = self.env['ir.attachment'].create({'name': 'big.webp', 'datas': _picture(1920, 1280, 'WEBP'),
                                                'mimetype': 'image/webp', 'public': True})
        att._mtbg_measure()
        made = att._mtbg_make_copies()
        self.assertEqual(sorted(made.mapped('mtbg_width')), [480, 800, 1280])
        self.assertEqual(set(made.mapped('description')), {'resize: 480', 'resize: 800', 'resize: 1280'})
        self.assertTrue(all(made.mapped('public')))
        self.assertEqual(made.original_id, att, "an optimized copy: the media library hides it")
        self.assertFalse(att._mtbg_make_copies(), "copies are made once")
        sources = att._mtbg_sources()
        copy_800 = made.filtered(lambda c: c.mtbg_width == 800)
        self.assertEqual(sources['src'], '/web/image/%s' % copy_800.id)
        self.assertEqual(sources['full'], '/web/image/%s' % att.id)
        self.assertIn('/web/image/%s 800w' % copy_800.id, sources['srcset'])
        self.assertIn('/web/image/%s 1920w' % att.id, sources['srcset'])
        self.assertNotIn('x0', sources['srcset'], "never Odoo's on-the-fly sizes for WebP (it returns the full file)")

    def test_small_webp_needs_no_copies(self):
        att = self.env['ir.attachment'].create({'name': 's.webp', 'datas': _picture(400, 300, 'WEBP'),
                                                'mimetype': 'image/webp', 'public': True})
        self.assertFalse(att._mtbg_make_copies())
        att._mtbg_measure()
        self.assertEqual(att._mtbg_sources(), {'src': '/web/image/%s' % att.id, 'full': '/web/image/%s' % att.id,
                                               'srcset': ''})

    def test_jpeg_uses_odoo_sizes(self):
        att = self.env['ir.attachment'].create({'name': 'p.jpg', 'datas': _picture(1000, 500, 'JPEG'), 'public': True})
        att._mtbg_measure()
        sources = att._mtbg_sources()
        self.assertEqual(sources['srcset'], '/web/image/{0}/480x0 480w, /web/image/{0}/800x0 800w, '
                                            '/web/image/{0} 1000w'.format(att.id))


@tagged('post_install', '-at_install', 'mtbg')
class TestTiledGalleryBlock(HttpCase):
    """The block on any website page, with pictures chosen in the editor ("ids:"): no other module needed."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pictures = cls.env['ir.attachment']
        for i, (w, h) in enumerate(((1600, 1200), (1500, 1000), (1600, 1200), (1500, 1000), (1920, 1080))):
            cls.pictures |= cls.env['ir.attachment'].create({'name': f'photo-{i}.webp', 'datas': _picture(w, h, 'WEBP'),
                                                             'mimetype': 'image/webp', 'public': True})
        cls.pictures[1].write({'mtbg_focus_x': 20, 'mtbg_focus_y': 70})
        cls.source = 'ids:' + ','.join(str(i) for i in cls.pictures.ids)
        new_test_user(cls.env, login='gallery_designer', groups='base.group_user,website.group_website_designer')

    def _page(self, url, arch):
        self.env['website.page'].create({
            'name': url, 'url': url, 'is_published': True, 'type': 'qweb',
            'key': 'mtbg_tours_gallery.test_page_' + url.strip('/').replace('-', '_'),
            'arch': '<t t-call="website.layout"><div id="wrap">%s</div></t>' % arch,
        })

    def _render(self, gallery, **kw):
        return self.make_jsonrpc_request('/mtbg_tours_gallery/render', {'gallery': gallery, **kw})

    def test_tiles(self):
        items = self.env['mtbg.gallery']._mtbg_source_items(self.source)
        html = str(self.env['mtbg.gallery']._mtbg_render(items))
        self.assertIn('class="mtbg-tg"', html)
        # 5 photos: big + stack, then a pair; desktop and phone rows
        self.assertEqual(html.count('class="mtbg-tg-cell"'), 10)
        self.assertEqual(html.count('class="mtbg-tg-row"'), 2 + 3)
        self.assertIn('object-position: 20% 70%', html)
        self.assertIn('alt="photo 0"', html, "a chosen picture's alt text from its file name")
        self.assertIn('data-index="0"', html)
        self.assertIn('aspect-ratio:', html)

    def test_block_render_route(self):
        result = self._render(self.source)
        self.assertEqual(result['count'], 5)
        self.assertIn('mtbg-tg-cell', result['html'])
        private = self.env['ir.attachment'].create({'name': 'private.png', 'datas': _picture(40, 30)})
        result = self._render('ids:%s,%s' % (private.id, self.pictures[2].id))
        self.assertEqual(result['count'], 1, "only public pictures for visitors")
        self.assertEqual(self._render('nonsense')['count'], 0)
        self.assertEqual(self._render('nokind:%s' % self.pictures[0].id)['count'], 0, "a kind no module offers")
        self.assertEqual(self._render('nokind:page', page_model='res.partner', page_id=1)['count'], 0)

    def test_sources_for_the_editor(self):
        self.authenticate('gallery_designer', 'gallery_designer')
        sources = self.make_jsonrpc_request('/mtbg_tours_gallery/sources', {})
        self.assertIsInstance(sources, list)
        for source in sources:
            self.assertTrue({'kind', 'model', 'label', 'record_label', 'search_label'} <= set(source))
        self.assertEqual(self.make_jsonrpc_request('/mtbg_tours_gallery/record_add', {
            'kind': 'nokind', 'res_id': 1, 'attachment_ids': self.pictures[:1].ids})['added'], 0)

    def test_block_on_a_page_has_no_heading(self):
        """The Tiled Gallery block on any page (one or more per page) brings no heading of its own."""
        block = '<section class="s_mtbg_gallery o_not_editable my-3" data-snippet="s_mtbg_gallery" data-gallery="%s"/>'
        self._page('/photo-page', '<div class="oe_structure">%s%s</div>' % (block % self.source, block % self.source))
        page = self.url_open('/photo-page').text
        self.assertEqual(page.count('data-snippet="s_mtbg_gallery"'), 2)
        self.assertNotIn('<h2', self._render(self.source)['html'], "the block's tiles carry no heading")

    def test_visitors_get_the_copies(self):
        att = self.pictures[0]
        att._mtbg_make_copies()
        copy = next(iter(att._mtbg_copies()[att.id].values()))
        res = self.url_open('/web/image/%s' % copy.id)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers['Content-Type'], 'image/webp')

    LIGHTBOX = """
        const deadline = Date.now() + 20000;
        let clicked = false;
        (function attempt() {
            const cell = document.querySelector('.mtbg-tg-desktop .mtbg-tg-cell[data-index="1"]');
            if (cell && !clicked) { clicked = true; cell.querySelector('img').click(); }
            const counter = document.querySelector('.pswp--open .pswp__counter');
            const img = document.querySelector('.pswp--open .pswp__item:not([aria-hidden="true"]) img.pswp__img:not(.pswp__img--placeholder)');
            if (counter && img) {
                const expected = (__TOTAL__);
                if (document.querySelector('.modal .carousel')) { console.error('another lightbox opened too'); }
                else if (counter.textContent.replace(/\\s/g, '') !== (__INDEX__) + '/' + expected) { console.error('counter: ' + counter.textContent + ', expected ' + (__INDEX__) + ' / ' + expected); }
                else if (new URL(img.src).pathname !== cell.getAttribute('href')) { console.error('not the full picture: ' + img.src); }
                else if (document.querySelector('.mtbg-pswp-caption').textContent !== __CAPTION__) { console.error('caption: ' + document.querySelector('.mtbg-pswp-caption').textContent); }
                else { console.log('test successful'); }
            } else if (Date.now() > deadline) {
                console.error('lightbox did not open');
            } else {
                setTimeout(attempt, 300);
            }
        })();
    """
    READY = "document.documentElement.dataset.mtbgLightbox && !!document.querySelector('.mtbg-tg-desktop .mtbg-tg-cell img')"

    def _gallery_page(self, url='/gallery-page', before=''):
        self._page(url, '%s<section class="s_mtbg_gallery" data-gallery="%s"/>' % (before, self.source))

    def test_lightbox_elsewhere(self):
        """A page with a Tiled Gallery block: the lightbox for its photos, full size."""
        self._gallery_page()
        code = self.LIGHTBOX.replace('__TOTAL__', '5').replace('__INDEX__', '2').replace('__CAPTION__', "''")
        self.browser_js('/gallery-page', code, ready=self.READY, timeout=60)

    def test_lightbox_on_older_browsers(self):
        """Without Element.checkVisibility (iOS before 17.4, Chrome before 105) the lightbox still opens."""
        self._gallery_page()
        code = "delete Element.prototype.checkVisibility;\n" + self.LIGHTBOX.replace(
            '__TOTAL__', '5').replace('__INDEX__', '2').replace('__CAPTION__', "''")
        self.browser_js('/gallery-page', code, ready=self.READY, timeout=60)

    def test_page_photos(self):
        """A page naming its own photos (data-mtbg-lightbox-photos, e.g. a tour page's cover and description) opens
        them with the gallery's, in page order; one marked data-mtbg-lightbox-always whatever its size."""
        cover = self.pictures[4]
        self._gallery_page(before='<div data-mtbg-lightbox-photos=".test-cover, .test-text img">'
                                  '<img class="test-cover" data-mtbg-lightbox-always="1" src="/web/image/%s" '
                                  'style="width:200px"/><p class="test-text">no photo</p></div>' % cover.id)
        code = self.LIGHTBOX.replace('__TOTAL__', '1 + 5').replace('__INDEX__', '1 + 2').replace('__CAPTION__', "''")
        self.browser_js('/gallery-page', code, ready=self.READY, timeout=60)

    def test_marked_photo_set(self):
        """Photos inside a ``data-mtbg-photo-set`` element (an extension's markup, e.g. a hotel card) open as a set of
        their own, each at its ``data-mtbg-full`` picture (owner, 2026-11-03: hotel upgrade photos in the lightbox)."""
        self._gallery_page()
        small = self.pictures[:3].ids
        code = """
            const set = document.createElement('div');
            set.dataset.mtbgPhotoSet = 'test';
            set.innerHTML = __IDS__.map((id) => `<img src="/web/image/${id}/120x80" data-mtbg-full="/web/image/${id}" style="width:120px;height:80px">`).join('');
            document.querySelector('#wrap').prepend(set);
            const deadline = Date.now() + 20000;
            let clicked = false;
            (function attempt() {
                if (!clicked) { clicked = true; set.querySelectorAll('img')[1].click(); }
                const counter = document.querySelector('.pswp--open .pswp__counter');
                const img = document.querySelector('.pswp--open .pswp__item:not([aria-hidden="true"]) img.pswp__img:not(.pswp__img--placeholder)');
                if (counter && img) {
                    if (counter.textContent.replace(/\\s/g, '') !== '2/3') { console.error('counter: ' + counter.textContent); }
                    else if (new URL(img.src).pathname !== '/web/image/' + __IDS__[1]) { console.error('not the full picture: ' + img.src); }
                    else if (document.querySelector('.modal .carousel')) { console.error('another lightbox opened too'); }
                    else { console.log('test successful'); }
                } else if (Date.now() > deadline) {
                    console.error('lightbox did not open');
                } else {
                    setTimeout(attempt, 300);
                }
            })();
        """.replace('__IDS__', repr(small))
        self.browser_js('/gallery-page', code, ready=self.READY, timeout=60)

    def test_lightbox_on_a_phone(self):
        """On a phone the photo shows (Odoo's mobile rule "section { height: auto !important }" used to collapse
        PhotoSwipe's scroll layer, a <section>: a black screen)."""
        self.browser_size = '390x844'
        self._gallery_page()
        code = """
            const deadline = Date.now() + 20000;
            let clicked = false;
            (function attempt() {
                const img = document.querySelector('.mtbg-tg-phone .mtbg-tg-cell img');
                if (img && !clicked) { clicked = true; img.click(); }
                const wrap = document.querySelector('.pswp--open .pswp__scroll-wrap');
                const shown = document.querySelector('.pswp--open .pswp__item:not([aria-hidden="true"]) img.pswp__img:not(.pswp__img--placeholder)');
                if (wrap && shown && shown.complete) {
                    const r = shown.getBoundingClientRect();
                    const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
                    if (wrap.getBoundingClientRect().height < 400) { console.error('scroll layer collapsed: ' + wrap.getBoundingClientRect().height); }
                    else if (!hit || hit.classList.contains('pswp__bg')) { console.error('the photo is hidden behind the background'); }
                    else { console.log('test successful'); }
                } else if (Date.now() > deadline) {
                    console.error('lightbox did not open');
                } else {
                    setTimeout(attempt, 300);
                }
            })();
        """
        self.browser_js('/gallery-page', code, ready=self.READY.replace('mtbg-tg-desktop', 'mtbg-tg-phone'), timeout=60)

    def test_site_lightbox_has_no_download(self):
        """A site gallery's viewer stays as it was (content blocks 0.11.4's Download and video slides are opt-in, for
        the client photo album only)."""
        self._gallery_page()
        code = """
            const deadline = Date.now() + 20000;
            let clicked = false;
            (function attempt() {
                const img = document.querySelector('.mtbg-tg-desktop .mtbg-tg-cell img');
                if (img && !clicked) { clicked = true; img.click(); }
                if (document.querySelector('.pswp--open .pswp__counter')) {
                    if (document.querySelector('.pswp .mtbg-pswp-download, .pswp video')) { console.error('a site gallery got the album extras'); }
                    else { console.log('test successful'); }
                } else if (Date.now() > deadline) { console.error('lightbox did not open'); }
                else { setTimeout(attempt, 300); }
            })();
        """
        self.browser_js('/gallery-page', code, ready=self.READY, timeout=60)

    def test_gallery_loads_when_scrolled_near(self):
        """0.5.9 (owner, 2026-11-10: "there is no reason to load the gallery until the page scrolls that far down"):
        a gallery far below the first screen fetches nothing until the page scrolls near it; then its tiles come."""
        self.env['website.page'].create({
            'name': 'Far gallery page', 'url': '/far-gallery-page', 'is_published': True, 'type': 'qweb',
            'key': 'mtbg_tours_gallery.test_far_gallery_page',
            'arch': '<t t-call="website.layout"><div id="wrap"><div style="height: 5000px">Intro</div>'
                    '<section class="s_mtbg_gallery" data-gallery="%s"/></div></t>' % self.source,
        })
        # (the page's scripts start on the visitor's first scroll: a small one first, the gallery still far below)
        code = """
            const fetched = () => performance.getEntriesByType('resource').some(r => r.name.includes('/mtbg_tours_gallery/render'));
            window.scrollTo(0, 50);
            const deadline = Date.now() + 20000;
            (function started() {
                if (!document.documentElement.dataset.mtbgLightbox) {
                    return Date.now() > deadline ? console.error('the page scripts did not start') : setTimeout(started, 200);
                }
                setTimeout(() => {
                    if (fetched() || document.querySelector('.mtbg-tg-cell')) { return console.error('the gallery loaded before the page scrolled to it'); }
                    document.querySelector('.s_mtbg_gallery').scrollIntoView();
                    (function wait() {
                        if (document.querySelector('.mtbg-tg-cell img') && fetched()) { console.log('test successful'); }
                        else if (Date.now() > deadline + 15000) { console.error('the gallery did not load once scrolled to'); }
                        else { setTimeout(wait, 200); }
                    })();
                }, 2500);
            })();
        """
        self.browser_js('/far-gallery-page', code, ready="document.readyState === 'complete'", timeout=60)


@tagged('post_install', '-at_install', 'mtbg')
class TestJustified(TransactionCase):
    """Justified rows for other pages (19.0.0.6.3, owner 2026-11-15: "tiles are too small and the gifs are still
    cropped heavily"), with real shapes: portraits 3:4, landscapes 4:3, a 9:16 and a 16:9 video."""

    P, L, V916, V169 = 0.75, 4 / 3, 9 / 16, 16 / 9

    def shapes(self, rows):
        return [[round(c['share'] * r['ratio'], 4) for c in r['columns']] for r in rows]

    def test_every_shape_kept(self):
        mix = _photos(self.P, self.L, self.V916, self.P, self.V169, self.L, self.P, self.P, self.V916)
        for screen in ('phone', 'tablet', 'desktop'):
            rows = justified(mix, screen)
            got = [x for row in self.shapes(rows) for x in row]
            self.assertEqual(got, [round(p['ratio'], 4) for p in mix], "%s: no crop, in order" % screen)

    def test_phone_big_tiles(self):
        mix = _photos(self.P, self.L, self.V916, self.P, self.V169, self.P, self.V916, self.L, self.P)
        rows = justified(mix, 'phone')
        self.assertTrue(all(len(r['columns']) <= 2 for r in rows), "at most 2 a row")
        for row in rows:
            ratios = [c['share'] * row['ratio'] for c in row['columns']]
            if any(r > 1.05 for r in ratios):
                self.assertEqual((len(ratios), row['width']), (1, 1.0), "a landscape alone, full width")
            height = row['width'] / row['ratio']  # in screen widths
            self.assertGreaterEqual(height, 0.55, "big tiles")
            self.assertLessEqual(height, 0.91)
        lone = justified(_photos(self.V916), 'phone')[0]
        self.assertAlmostEqual(lone['width'], self.V916 * 0.9, msg="a tall video alone: centred, 0.9 widths tall")
        pair = justified(_photos(self.V916, self.P), 'phone')
        self.assertEqual(len(pair), 1, "a tall video paired with a portrait")

    def test_desktop_and_tablet(self):
        mix = _photos(*([self.P, self.L] * 8))
        for screen, most in (('desktop', 4), ('tablet', 3)):
            rows = justified(mix, screen)
            self.assertTrue(all(len(r['columns']) <= most for r in rows), screen)
        desktop = justified(mix, 'desktop')
        self.assertTrue(all(r['ratio'] <= 3.5 + 4 / 3 for r in desktop))
        # ~320 px rows on a ~1110 px page
        self.assertTrue(all(1110 / r['ratio'] >= 250 for r in desktop[:-1]))

    def test_short_last_row_keeps_its_height(self):
        rows = justified(_photos(self.L, self.L, self.L, self.P), 'desktop')
        self.assertEqual(rows[0]['width'], 1.0)
        self.assertLess(rows[-1]['width'], 1.0)

    def test_block_layout_unchanged(self):
        """The gallery block keeps its own rows (Jetpack's rectangular style)."""
        self.assertEqual([r['pattern'] for r in layout(_photos(1.5, 1, 1, 1.5, 0.75, 1, 1, 1), 'desktop')],
                         ['big_left', 'big_right', 'pair'])


@tagged('post_install', '-at_install', 'mtbg')
class TestPhotoGallery(HttpCase):
    """The photo gallery (19.0.0.6.5, owner 2026-11-20: content blocks use the hotel section's gallery): a main photo,
    5 thumbnails, "+N" on the fifth when more, the rest in the lightbox only; every photo opens the page's lightbox
    as one set. From the template (other modules) or written by hand in a content block."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pictures = cls.env['ir.attachment']
        for i in range(8):
            cls.pictures |= cls.env['ir.attachment'].create({
                'name': f'shared-{i}.png', 'datas': _picture(300 + i, 200), 'mimetype': 'image/png', 'public': True})

    def _photos(self):
        return [{'src': '/web/image/%s/512x341' % p.id, 'full': '/web/image/%s' % p.id, 'alt': p.name}
                for p in self.pictures]

    def test_template(self):
        html = str(self.env['ir.qweb']._render('mtbg_tours_gallery.photo_gallery', {
            'gallery_photos': self._photos(), 'gallery_set': 'test-set'}))
        self.assertIn('data-mtbg-photo-set="test-set"', html)
        self.assertEqual(html.count('class="mtbg-gallery__main"'), 1)
        self.assertEqual(html.count('class="mtbg-gallery__thumb '), 5, "5 thumbnails")
        self.assertIn('data-more="+3"', html, "7 more photos: the fifth says +3")
        self.assertEqual(html.count('class="mtbg-gallery__hidden"'), 2, "the rest: in the lightbox only")
        self.assertEqual(html.count('data-mtbg-full='), 8, "every photo at full size")
        few = str(self.env['ir.qweb']._render('mtbg_tours_gallery.photo_gallery', {
            'gallery_photos': self._photos()[:4], 'gallery_set': 'few'}))
        self.assertNotIn('data-more', few)
        self.assertNotIn('mtbg-gallery__hidden', few)
        self.assertFalse(str(self.env['ir.qweb']._render('mtbg_tours_gallery.photo_gallery', {
            'gallery_photos': [], 'gallery_set': 'none'})).strip(), "no photos: nothing")

    def test_written_in_a_content_block(self):
        """A content block's own markup (a main photo, every thumbnail listed): "+N" on the fifth, the rest not seen,
        each photo opens the lightbox with all of them (the fifth thumbnail: 6 / 8, its full picture)."""
        ids = self.pictures.ids
        thumbs = ''.join('<span class="mtbg-gallery__thumb"><img src="/web/image/%s/96x64" data-mtbg-full="/web/image/%s" alt="t"/></span>'
                         % (i, i) for i in ids[1:])
        block = ('<div class="mtbg-gallery" data-mtbg-photo-set="ruins"><img class="mtbg-gallery__main" '
                 'src="/web/image/%s/512x341" data-mtbg-full="/web/image/%s" alt="main"/>'
                 '<div class="mtbg-gallery__thumbs">%s</div></div>' % (ids[0], ids[0], thumbs))
        self.env['website.page'].create({
            'name': 'block', 'url': '/photo-gallery-page', 'is_published': True, 'type': 'qweb',
            'key': 'mtbg_tours_gallery.test_page_photo_gallery',
            'arch': '<t t-call="website.layout"><div id="wrap"><section><div class="container" style="max-width:600px">%s</div></section></div></t>' % block,
        })
        code = """
            const fifth = () => document.querySelectorAll('.mtbg-gallery__thumb')[4];
            const deadline = Date.now() + 20000;
            let clicked = false;
            (function attempt() {
                const grid = document.querySelector('.mtbg-gallery__thumbs').getBoundingClientRect();
                const sixth = document.querySelectorAll('.mtbg-gallery__thumb')[5].getBoundingClientRect();
                if (!clicked) {
                    if (fifth().dataset.more !== '+3') { console.error('fifth: ' + fifth().dataset.more); return; }
                    if (sixth.width > 2) { console.error('the sixth thumbnail shows'); return; }
                    if (document.documentElement.scrollWidth > window.innerWidth) { console.error('sideways scroll'); return; }
                    clicked = true;
                    fifth().querySelector('img').click();
                }
                const counter = document.querySelector('.pswp--open .pswp__counter');
                const img = document.querySelector('.pswp--open .pswp__item:not([aria-hidden="true"]) img.pswp__img:not(.pswp__img--placeholder)');
                if (counter && img) {
                    if (counter.textContent.replace(/\\s/g, '') !== '6/8') { console.error('counter: ' + counter.textContent); }
                    else if (new URL(img.src).pathname !== '/web/image/__ID__') { console.error('not the full picture: ' + img.src); }
                    else { console.log('test successful'); }
                } else if (Date.now() > deadline) {
                    console.error('lightbox did not open');
                } else {
                    setTimeout(attempt, 300);
                }
            })();
        """.replace('__ID__', str(ids[5]))
        self.browser_js('/photo-gallery-page', code, timeout=60,
                        ready="!!(document.documentElement.dataset.mtbgLightbox && document.querySelectorAll('.mtbg-gallery__thumb')[4]?.dataset.more)")

    # 19.0.0.6.7 (owner, 2026-11-20: "each small thumb should change the main photo above. and then clicking on the
    # main photo launches the lightbox")

    JS_HELPERS = """
        const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
        const check = (ok, what) => { if (!ok) { throw new Error(what); } };
        async function until(fn, what, timeout = 15000) {
            const end = Date.now() + timeout;
            while (!fn()) {
                if (Date.now() > end) { throw new Error('timed out: ' + what); }
                await sleep(100);
            }
        }
        const path = (url) => new URL(url, location.href).pathname;
        const main = () => document.querySelector('.mtbg-gallery__main');
        const thumbs = () => [...document.querySelectorAll('.mtbg-gallery__thumbs > .mtbg-gallery__thumb')];
        const counter = () => document.querySelector('.pswp--open .pswp__counter')?.textContent.replace(/\\s/g, '');
        const shown = () => document.querySelector('.pswp--open .pswp__item:not([aria-hidden="true"]) img.pswp__img:not(.pswp__img--placeholder)');
        async function closeLightbox() {
            await sleep(600); // (its opening animation done)
            odoo.loader.modules.get('@mtbg_tours_content_blocks/shared/lightbox').openViewer().close();
            await until(() => !document.querySelector('.pswp'), 'the lightbox closed');
            await sleep(300);
        }
    """

    def _browser(self, url, code, ready):
        self.browser_js(url, """
            (async () => {
                %s
                try {
                    %s
                    console.log('test successful');
                } catch (e) {
                    console.error(e.message);
                }
            })();
        """ % (self.JS_HELPERS, code), ready=ready, timeout=90)

    def _page(self, url, body):
        self.env['website.page'].create({
            'name': url, 'url': url, 'is_published': True, 'type': 'qweb',
            'key': 'mtbg_tours_gallery.test_page%s' % url.replace('/', '_').replace('-', '_'),
            'arch': '<t t-call="website.layout"><div id="wrap"><section><div class="container" style="max-width:600px">'
                    '%s</div></section></div></t>' % body,
        })

    def test_thumbnail_shows_its_photo_main_opens_lightbox(self):
        """A content block's gallery (the template's div thumbnails): a thumbnail shows its photo in the main photo's
        box (the main photo's size, nothing moves, it ringed), the lightbox stays closed; the main photo opens it at
        the photo shown (3 / 8, its full picture); Enter and Space on a thumbnail do the same as a tap, the active one
        brings back the first photo; "+N" opens the lightbox at its photo."""
        ids = self.pictures.ids
        thumbs = ''.join('<div class="mtbg-gallery__thumb"><img src="/web/image/%s/192x128" data-mtbg-full="/web/image/%s" '
                         'alt="t%s" width="96" height="64"/></div>' % (i, i, n) for n, i in enumerate(ids[1:], 1))
        self._page('/photo-gallery-swap', '<div class="mtbg-gallery" data-mtbg-photo-set="swap"><img class="mtbg-gallery__main" '
                   'src="/web/image/%s/512x341" data-mtbg-full="/web/image/%s" alt="main" width="512" height="341"/>'
                   '<div class="mtbg-gallery__thumbs">%s</div></div>' % (ids[0], ids[0], thumbs))
        self._browser('/photo-gallery-swap', """
            const box = main().getBoundingClientRect();
            const below = document.querySelector('.mtbg-gallery__thumbs').getBoundingClientRect().top;
            check(thumbs().every((t) => t.getAttribute('role') === 'button' && t.tabIndex === 0), 'thumbnails are buttons');
            check(main().getAttribute('role') === 'button' && main().tabIndex === 0, 'the main photo is a button');
            // a tap on the second thumbnail: its photo in the main photo's box, at the main photo's size
            thumbs()[1].querySelector('img').click();
            await until(() => path(main().src) === '/web/image/__2__/512x341', 'the main photo is the second thumbnail\\'s');
            await sleep(400);
            check(!document.querySelector('.pswp--open'), 'a thumbnail does not open the lightbox');
            const after = main().getBoundingClientRect();
            check(Math.abs(after.width - box.width) < 1 && Math.abs(after.height - box.height) < 1, 'the box keeps its size');
            check(Math.abs(document.querySelector('.mtbg-gallery__thumbs').getBoundingClientRect().top - below) < 1, 'nothing moves');
            check(thumbs()[1].classList.contains('mtbg-gallery__thumb--active') && thumbs()[1].getAttribute('aria-pressed') === 'true', 'marked');
            check(thumbs().filter((t) => t.classList.contains('mtbg-gallery__thumb--active')).length === 1, 'only it');
            check(main().alt === 't2' && path(main().dataset.mtbgFull) === '/web/image/__2__', 'its alt and full picture');
            // the main photo: the lightbox at the photo shown, every photo of the gallery in it
            main().click();
            await until(() => counter() && shown(), 'the lightbox opened');
            check(counter() === '3/8', 'at the photo shown: ' + counter());
            check(path(shown().src) === '/web/image/__2__', 'its full picture: ' + shown().src);
            await closeLightbox();
            // the keyboard: Enter on the first thumbnail, Space on it again (the active one): the first photo back
            thumbs()[0].focus();
            thumbs()[0].dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
            await until(() => path(main().src) === '/web/image/__1__/512x341', 'Enter shows the first thumbnail\\'s photo');
            const space = new KeyboardEvent('keydown', { key: ' ', bubbles: true, cancelable: true });
            thumbs()[0].dispatchEvent(space);
            check(space.defaultPrevented, 'Space does not scroll the page');
            await until(() => path(main().src) === '/web/image/__0__/512x341', 'the active one again: the first photo');
            check(!document.querySelector('.mtbg-gallery__thumb--active'), 'no thumbnail marked');
            main().dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
            await until(() => counter(), 'Enter on the main photo opens the lightbox');
            check(counter() === '1/8', 'at the first photo: ' + counter());
            await closeLightbox();
            // "+3" (the fifth): the lightbox at its photo, the main photo unchanged
            check(thumbs()[4].dataset.more === '+3', '+3 on the fifth');
            thumbs()[4].querySelector('img').click();
            await until(() => counter(), '+N opens the lightbox');
            check(counter() === '6/8', '+N at its photo: ' + counter());
            check(path(main().src) === '/web/image/__0__/512x341', 'the main photo unchanged');
        """.replace('__0__', str(ids[0])).replace('__1__', str(ids[1])).replace('__2__', str(ids[2])),
            ready="!!(document.documentElement.dataset.mtbgLightbox && document.querySelector('.mtbg-gallery__thumb[role]'))")

    def test_older_blocks_spans_merged_and_repeated_main(self):
        """A block written before 19.0.0.6.7 (www's block 941): span thumbnails with data-mtbg-thumb, a span the website
        editor merged holding 3 photos, the first thumbnail repeating the main photo. Each photo its own thumbnail,
        the repeated one the first photo's button, the lightbox with each photo once (8, not 9); "+N" counted."""
        ids = self.pictures.ids
        span = lambda n, *pics: '<span class="mtbg-gallery__thumb" data-mtbg-thumb="%s">%s</span>' % (n, ''.join(
            '<img src="/web/image/%s/192x128" data-mtbg-full="/web/image/%s" alt="t" width="96" height="64"/>' % (i, i) for i in pics))
        grid = span(1, ids[0]) + span(2, ids[1]) + span(3, ids[2], ids[3], ids[4]) + span(6, ids[5]) + span(7, ids[6]) + span(8, ids[7])
        self._page('/photo-gallery-older', '<div class="mtbg-gallery" data-mtbg-photo-set="older"><img class="mtbg-gallery__main" '
                   'src="/web/image/%s/512x341" data-mtbg-full="/web/image/%s" alt="main" width="512" height="341"/>'
                   '<div class="mtbg-gallery__thumbs">%s</div></div>' % (ids[0], ids[0], grid))
        self._browser('/photo-gallery-older', """
            check(thumbs().length === 8, 'one thumbnail a photo: ' + thumbs().length);
            check(thumbs().every((t) => t.querySelectorAll('img').length === 1), 'the merged span split');
            check(thumbs()[4].dataset.more === '+4', '+4 on the fifth: ' + thumbs()[4].dataset.more);
            check(thumbs()[5].getBoundingClientRect().width <= 2, 'the sixth not seen');
            check(thumbs()[0].classList.contains('mtbg-gallery__thumb--active'), 'the repeated main photo: the first photo, shown');
            thumbs()[2].click();
            await until(() => path(main().src) === '/web/image/__2__/512x341', 'a photo of the merged span');
            main().click();
            await until(() => counter(), 'the lightbox opened');
            check(counter() === '3/8', 'each photo once: ' + counter());
            await closeLightbox();
            thumbs()[0].click();
            await until(() => path(main().src) === '/web/image/__0__/512x341', 'the repeated one: the first photo back');
        """.replace('__0__', str(ids[0])).replace('__2__', str(ids[2])),
            ready="!!(document.documentElement.dataset.mtbgLightbox && document.querySelector('.mtbg-gallery__thumb[role]'))")

    def test_template_swaps_too(self):
        """Other modules' galleries (the template, e.g. Accommodations' hotel sections and upgrade slides): the same."""
        ids = self.pictures.ids
        self.env['ir.ui.view'].create({
            'name': 'gallery host', 'type': 'qweb', 'key': 'mtbg_tours_gallery.test_template_host',
            'arch': '<t t-name="mtbg_tours_gallery.test_template_host"><t t-call="mtbg_tours_gallery.photo_gallery">'
                    '<t t-set="gallery_photos" t-value="photos"/><t t-set="gallery_set" t-value="&quot;tpl&quot;"/></t></t>'})
        html = str(self.env['ir.qweb']._render('mtbg_tours_gallery.test_template_host', {'photos': self._photos()}))
        self.assertEqual(html.count('<div class="mtbg-gallery__thumb '), 5, "div thumbnails (never merged by the editor)")
        self.assertNotIn('<span', html)
        self._page('/photo-gallery-template', html)
        self._browser('/photo-gallery-template', """
            thumbs()[3].click();
            await until(() => path(main().src) === '/web/image/__4__/512x341', 'the fourth thumbnail\\'s photo');
            main().click();
            await until(() => counter(), 'the lightbox opened');
            check(counter() === '5/8', 'at the photo shown, the hidden ones in the set: ' + counter());
        """.replace('__4__', str(ids[4])),
            ready="!!(document.documentElement.dataset.mtbgLightbox && document.querySelector('.mtbg-gallery__thumb[role]'))")

    def test_saved_in_the_website_editor(self):
        """A reusable block with a gallery, edited and saved in the website editor: the div thumbnails stay one
        element each (the editor merged identical neighbouring spans), nothing the page's code adds is saved."""
        ids = self.pictures.ids
        thumbs = ''.join('<div class="mtbg-gallery__thumb"><img src="/web/image/%s/192x128" data-mtbg-full="/web/image/%s" '
                         'alt="t" width="96" height="64"/></div>' % (i, i) for i in ids[1:])
        block = self.env['mtbg.tours.content.block'].create({'name': 'Gallery host', 'body': (
            '<p class="mtbg-test-text">Before the gallery.</p><div class="mtbg-gallery" data-mtbg-photo-set="saved">'
            '<img class="mtbg-gallery__main" src="/web/image/%s/512x341" data-mtbg-full="/web/image/%s" alt="main" '
            'width="512" height="341"/><div class="mtbg-gallery__thumbs">%s</div></div>') % (ids[0], ids[0], thumbs)})
        self.start_tour(self.env['website'].get_client_action_url(f'/mtbg/block/{block.id}', True),
                        'mtbg_photo_gallery_save_tour', login='admin', timeout=180)
        body = str(block.body)
        self.assertIn('Edited next to the gallery', body, "saved")
        self.assertEqual(body.count('class="mtbg-gallery__thumb"'), 7, "7 thumbnails, one element each")
        for added in ('role=', 'tabindex', 'aria-pressed', 'mtbg-gallery__thumb--active', 'data-more', '--more'):
            self.assertNotIn(added, body)
