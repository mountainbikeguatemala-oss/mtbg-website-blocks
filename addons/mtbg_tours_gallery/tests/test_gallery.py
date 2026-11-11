import base64
import io

from PIL import Image
import PIL.WebPImagePlugin  # noqa: F401

from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

from ..services.layout import layout, patterns


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
