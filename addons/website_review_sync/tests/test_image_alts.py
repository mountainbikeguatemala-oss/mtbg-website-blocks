import base64
import io

from PIL import Image

from odoo.tests import HttpCase, tagged

# every picture the Reviews block draws: no alt missing or empty, the lightbox's too
CHECK = """
const wait = (test, then, tries = 100) => test() ? then() : (tries ? setTimeout(() => wait(test, then, tries - 1), 100)
    : console.error('test failed: the review cards never came'));
wait(() => document.querySelector('.s_review_slider_card .s_review_slider_photos img'), () => {
    const imgs = [...document.querySelectorAll('.s_review_preset img')];
    const bad = imgs.filter((img) => !(img.getAttribute('alt') || '').trim()).map((img) => img.outerHTML);
    const avatar = document.querySelector('.s_review_slider_photo');
    const photo = document.querySelector('.s_review_slider_photos img');
    const shown = document.querySelector('.s_review_slider_who b').textContent;  // the name as the source shows it
    if (!bad.length && shown.startsWith('Ana') && avatar.alt === shown && photo.alt.includes(shown)) {
        console.log('test successful');
    } else {
        console.error('test failed: ' + JSON.stringify(bad) + ' ' + avatar.alt + ' ' + photo.alt);
    }
});
"""


@tagged('post_install', '-at_install')
class TestReviewImageAlts(HttpCase):
    """Alt text for every picture on the page (owner, 2026-11-03): a reviewer's photo is named after them, a review's
    photos after its review."""

    def test_review_pictures_have_alt(self):
        out = io.BytesIO()
        Image.new('RGB', (8, 8), (200, 80, 20)).save(out, 'PNG')
        photo = self.env['ir.attachment'].create({'name': 'IMG_0042.png', 'datas': base64.b64encode(out.getvalue()),
                                                  'public': True})
        avatar = self.env['ir.attachment'].create({'name': 'a.png', 'datas': base64.b64encode(out.getvalue()),
                                                   'public': True})
        source = self.env['review.source'].create({'name': 'Alt test', 'platform': 'manual'})
        self.env['review.review'].create({
            'source_id': source.id, 'author_name': 'Ana Torres', 'rating': 5, 'text': 'Great guides and trails',
            'review_date': '2026-10-01', 'featured': True, 'author_photo_url': '/web/image/%s' % avatar.id,
            'image_ids': [(6, 0, photo.ids)]})
        view = self.env['ir.ui.view'].create({
            'name': 'Review alt test', 'type': 'qweb', 'key': 'website_review_sync.test_alt_page',
            'arch': '<t t-name="website_review_sync.test_alt_page"><t t-call="website.layout"><div id="wrap">'
                    '<t t-call="website_review_sync.s_review_slider"/></div></t></t>'})
        self.env['website.page'].create({'url': '/review-alt-test', 'view_id': view.id, 'is_published': True})
        self.browser_js('/review-alt-test', CHECK, login=None)
