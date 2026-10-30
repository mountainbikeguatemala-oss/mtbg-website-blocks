from unittest.mock import patch

from odoo.tests import HttpCase, tagged

SOURCES = {'thing': {'name': 'Things', 'fields': [
    {'key': 'name', 'label': 'Name', 'kind': 'title'},
    {'key': 'price', 'label': 'Price', 'kind': 'price'},
    {'key': 'badge', 'label': 'Badge', 'kind': 'badge', 'icon': 'fa-star'},
    {'key': 'rating', 'label': 'Rating', 'kind': 'rating'},
    {'key': 'deadline', 'label': 'Deadline', 'kind': 'countdown'},
], 'filters': [{'key': 'kind', 'label': 'Kind', 'options': [{'key': 'big', 'label': 'Big'}]}]}}


def values(self, source, record):
    return {'url': '/thing/%s' % record, 'image': '', 'name': 'Thing %s' % record,
            # a value with another module's classes and data (e.g. a price that follows the visitor's currency)
            'price': {'text': '$%s' % (record * 10), 'class': 'x-price', 'inner_class': 'x-price__words',
                      'attrs': {'data-alt': 'Q%s' % (record * 77), 'onclick': 'alert(1)'}},
            'badge': 'New' if record == 1 else '', 'rating': {'value': 4.6, 'count': 12},
            'deadline': {'deadline': '2030-01-01T10:00:00Z', 'label': 'Closes in'}}


def item(uid, field, **kw):
    return dict({'uid': uid, 'field': field, 'look': 'plain', 'show': '', 'text': '', 'icon': ''}, **kw)


@tagged('post_install', '-at_install', 'mtbg')
class TestCardDesigns(HttpCase):
    """Card designs with a source of its own (the pack needs no module's records)."""

    def setUp(self):
        super().setUp()
        cls = type(self.env['mtbg.website.card.design'])
        for p in (patch.object(cls, '_mtbg_card_sources', lambda self: SOURCES),
                  patch.object(cls, '_mtbg_card_values', values),
                  patch.object(cls, '_mtbg_card_records', lambda self, source, filters, limit: [1, 2, 3][:limit])):
            p.start()
            self.addCleanup(p.stop)
        self.Design = self.env['mtbg.website.card.design']

    def test_ribbons(self):
        """Ribbons: their own section; one with a ribbon look placed elsewhere moves into it, a field without one there
        takes the corner ribbon; a folded one is drawn past the card's edges."""
        data = self.Design.mtbg_designer_create('Ribbons', 'thing')
        design = self.Design.browse(data['design']['id'])
        look = {'regions': {
            'top': {'show': 'always', 'items': [dict(item('a', 'badge'), look='badge', bstyle='pill', bbg='#9b59b6')]},
            'banners': {'items': [item('b', 'name'), dict(item('c', 'price'), look='corner', bstyle='fold3d', bside='left')]},
            'below': {'items': [item('d', 'name', look='pill')]},
        }}
        design.mtbg_designer_save(dict(data['design'], look=look))
        regions = design.look['regions']
        self.assertEqual([(i['field'], i['look']) for i in regions['banners']['items']],
                         [('name', 'corner'), ('price', 'corner'), ('badge', 'badge')])
        self.assertEqual(regions['top']['items'], [])
        self.assertEqual([i['look'] for i in regions['below']['items']], ['pill'], "the other sections keep theirs")
        html = str(design.mtbg_render([1]))
        self.assertIn('mtbg-card__banners', html)
        self.assertIn('mtbg-card__banners mtbg-card__banners--out', html, "a folded ribbon reaches past the card")
        self.assertIn('mtbg-card__banner--fold3d is-left', html)
        self.assertIn('--b-bg: #9b59b6', html)

    def test_regions_and_render(self):
        data = self.Design.mtbg_designer_create('Plain', 'thing')
        design = self.Design.browse(data['design']['id'])
        self.assertTrue(design.is_default, "the first design of a source is its Default")
        self.assertEqual([r['key'] for r in data['regions']],
                         ['header', 'banners', 'top', 'center', 'bottom', 'below', 'footer'])
        self.assertIn('book', [f['key'] for f in data['fields']], "every source has the Book button")
        look = {'regions': {
            'top': {'show': 'always', 'items': [item('a', 'badge', icon='fa-star')]},
            # the price twice: a pill on the photo (on hover) and by the button
            'center': {'show': 'hover', 'items': [item('b', 'price', look='pill')]},
            'bottom': {'show': 'hover', 'shade': True, 'items': [item('c', 'deadline', look='bar', show='always')]},
            'below': {'items': [item('d', 'name'), item('e', 'nonsense')]},
            'footer': {'items': [item('f', 'price'), item('g', 'book', look='button', text='Book (from {price})')]},
        }, 'dark': {'card_bg': '#111111', 'text': 'nope'}}
        settings = dict(data['design'], look=look, hover_darken=True)
        design.mtbg_designer_draft(settings)
        self.assertIn('Book (from', str(design.mtbg_render([1], draft=True)))
        self.assertNotIn('Book (from', str(design.mtbg_render([1])), "the site keeps the saved design")
        design.mtbg_designer_save(settings)
        regions = design.look['regions']
        self.assertEqual([i['field'] for i in regions['below']['items']], ['name'], "unknown fields are dropped")
        html = str(design.mtbg_render([1, 2]))
        self.assertEqual(html.count('mtbg-card mtbg-card--'), 2)
        self.assertIn('mtbg-card__on--center', html)
        self.assertIn('data-show="hover"', html)
        self.assertIn('has-shade', html)
        self.assertIn('mtbg-card__item--bar', html)
        self.assertIn('data-deadline="2030-01-01T10:00:00Z"', html)
        self.assertEqual(html.count('class="x-price"'), 2 * 3, "each card: the pill, the footer, the button's words")
        self.assertIn('data-alt="Q77"', html)
        self.assertNotIn('onclick', html, "only data-* attributes")
        self.assertIn('href="/thing/1"', html)
        self.assertIn('hover-darken', html)
        self.assertIn('--mtbg-card-dark-card-bg: #111111', html)
        self.assertNotIn('nope', html)
        self.assertEqual(html.count('fa-star"'), 1, "the badge only on the card that has one (and no rating placed)")
        block = self.Design.mtbg_block_data()['sources'][0]
        self.assertEqual((block['key'], block['designs'][0]['id']), ('thing', design.id))
        res = self.make_jsonrpc_request('/mtbg/cards/render', {'source': 'thing', 'limit': 2})
        self.assertEqual(res['html'].count('mtbg-card mtbg-card--'), 2)
        self.assertEqual(self.make_jsonrpc_request('/mtbg/cards/render', {'source': 'unknown'})['html'], '')

    def test_old_designs_become_regions(self):
        """A 19.0.0.1.x design (parts with places) reads as regions."""
        design = self.Design.create({'name': 'Old', 'source': 'thing', 'look': {'parts': [
            {'key': 'badge', 'place': 'top_left'}, {'key': 'name', 'place': 'body'},
            {'key': 'price', 'place': 'image_bottom'}, {'key': 'rating', 'place': 'off'}]}})
        regions = design._mtbg_settings()['look']['regions']
        self.assertEqual([i['field'] for i in regions['top']['items']], ['badge'])
        self.assertEqual([i['field'] for i in regions['below']['items']], ['name'])
        self.assertEqual([i['field'] for i in regions['bottom']['items']], ['price'])
        self.assertEqual(regions['top']['show'], 'always')
        self.assertEqual(regions['center']['show'], 'hover')
        self.assertIn('Thing 1', str(design.mtbg_render([1])))

    def test_preview_page(self):
        design = self.Design.browse(self.Design.mtbg_designer_create('Plain', 'thing')['design']['id'])
        self.authenticate('admin', 'admin')
        page = self.url_open(f'/mtbg/cards/preview/{design.id}?hover=1').text
        self.assertIn('is-hovered', page)

    def test_slider_layout(self):
        """Grid or slider (owner, 2026-10-29): the same cards in one row with arrows; the block asks for it."""
        design = self.Design.browse(self.Design.mtbg_designer_create('Plain', 'thing')['design']['id'])
        grid = str(design.mtbg_render([1, 2, 3], columns=4))
        self.assertNotIn('mtbg-cards-slider', grid)
        self.assertIn('mtbg-cards mtbg-cards--grid mtbg-cards--cols-4', grid)
        self.assertIn('--mtbg-cards-lg: 4', grid)
        slider = str(design.mtbg_render([1, 2, 3], columns=4, layout='slider'))
        # the one slider (slider_templates.xml), as many at once as the columns
        self.assertIn('mtbg-slider mtbg-cards-slider', slider)
        self.assertIn('--mtbg-slider-per-lg: 4', slider)
        self.assertIn('mtbg-slider__prev', slider)
        self.assertIn('mtbg-slider__next', slider)
        self.assertEqual(slider.count('class="mtbg-slider__slide"'), 3)
        self.assertEqual(slider.count('mtbg-card mtbg-card--'), 3, "the same cards")
        self.assertNotIn('mtbg-slider', str(design.mtbg_render([1], layout='nonsense')))
        res = self.make_jsonrpc_request('/mtbg/cards/render', {'source': 'thing', 'limit': 3, 'layout': 'slider'})
        self.assertIn('mtbg-slider__track', res['html'])
        self.assertNotIn('mtbg-slider', self.make_jsonrpc_request(
            '/mtbg/cards/render', {'source': 'thing', 'limit': 3})['html'])

    def test_book_button_settings(self):
        """The website's card settings: every card's Book button (owner, 2026-10-30: "need book botton global
        settings"); a design's own words still win."""
        design = self.Design.browse(self.Design.mtbg_designer_create('Plain', 'thing')['design']['id'])
        look = {'regions': {'footer': {'items': [item('b1', 'book', look='button')]}}}
        design.mtbg_designer_save(dict(design._mtbg_settings(), look=look))
        settings = self.env['mtbg.website.card.settings']._mtbg_get().with_context(mtbg_skip_menu_refresh=True)
        settings.write({'book_text': 'Reserve', 'book_icon': 'fa-calendar-check-o', 'book_style': 'custom',
                        'book_bg': '#123456', 'book_color': '#ffffff', 'book_size': 'lg', 'book_shape': 'pill',
                        'book_full': True})
        html = str(design.mtbg_render([1]))
        self.assertIn('Reserve', html)
        self.assertIn('fa-calendar-check-o', html)
        for cls in ('mtbg-book--custom', 'mtbg-book--lg', 'mtbg-book--pill', 'mtbg-book--full'):
            self.assertIn(cls, html)
        self.assertIn('--mtbg-book-bg: #123456', html)
        look['regions']['footer']['items'][0]['text'] = 'Go ({price})'
        design.mtbg_designer_save(dict(design._mtbg_settings(), look=look))
        html = str(design.mtbg_render([1]))
        self.assertIn('Go (', html)
        self.assertNotIn('Reserve', html)
