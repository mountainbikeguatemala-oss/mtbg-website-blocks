from odoo.exceptions import ValidationError
from odoo.tests import HttpCase, TransactionCase, tagged


def _preset_data(env, key):
    page = env['review.settings.page']
    return next(p for p in page.get_page()['presets'] if p['key'] == key)


@tagged('post_install', '-at_install')
class TestReviewPresets(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.page = cls.env['review.settings.page']
        cls.src_a = cls.env['review.source'].create({'name': 'Preset A', 'platform': 'manual'})
        cls.src_b = cls.env['review.source'].create({'name': 'Preset B', 'platform': 'manual'})

    def test_builtin_presets_render(self):
        """The five blocks of before are built-in presets; a block names its preset and is drawn from it."""
        keys = self.env['review.preset'].search([]).mapped('key')
        self.assertTrue({'bubbles', 'cards', 'dark', 'site', 'wall'} <= set(keys))
        html = self.env['review.preset'].render_block('site')
        for part in ('s_review_slider', 's_review_bubbles', 's_review_site', 'o_cc5', 's_review_boxed',
                     's_review_total_inline', 'Check out some of our recent reviews', 'data-source-id="all"'):
            self.assertIn(part, html)
        wall = self.env['review.preset'].render_block('wall')
        self.assertIn('s_review_wall_filters', wall)
        self.assertIn('s_review_wall_grid', wall)
        self.assertNotIn('s_review_slider_track', wall)
        self.assertEqual(self.env['review.preset'].render_block('gone'), '')

    def test_layout_colours_and_sources(self):
        """Drag-and-drop order, hidden parts, own colours and several sources reach the block."""
        data = _preset_data(self.env, 'bubbles')
        data['card_parts'] = [{'key': 'reviewer', 'show': True}, {'key': 'text', 'show': True},
                              {'key': 'rating', 'show': True}, {'key': 'photos', 'show': False}]
        data['layout'] = [{'key': 'button', 'show': True}, {'key': 'reviews', 'show': False}, {'key': 'total', 'show': False}]
        data['colors']['bubble'] = '#112233'
        data['source_ids'] = [self.src_a.id, self.src_b.id]
        html = self.page.preview(data)
        self.assertIn('s_review_reviewer_top', html, "reviewer dragged first: above the bubble")
        self.assertIn('--rv-o-reviewer: 0', html)
        self.assertIn('--rv-o-text: 1', html)
        self.assertIn('s_review_hide_photos', html)
        self.assertIn('rv-bubble', html)
        self.assertIn('--rv-bubble: #112233', html)
        self.assertIn(f'data-source-id="{self.src_a.id},{self.src_b.id}"', html)
        # the reviews always show; the button comes before them, the total is hidden
        self.assertIn('s_review_slider_track', html)
        self.assertLess(html.index('See all reviews'), html.index('s_review_slider_track'))
        self.assertNotIn('s_review_total_number', html)
        data['colors']['star'] = 'red; background: url(x)'
        with self.assertRaises(ValidationError):
            self.page.preview(data)
        data['colors']['star'] = ''
        data['button_url'] = 'javascript:alert(1)'
        with self.assertRaises(ValidationError):
            self.page.preview(data)

    def test_stars_count_up_and_button(self):
        """The stars are a part of their own (one banner when next to the total), the count-up's time and curve
        reach the block, the button has its own colours."""
        data = _preset_data(self.env, 'site')
        keys = [p['key'] for p in data['layout']]
        self.assertEqual(keys.index('stars') + 1, keys.index('total'), "saved before: the stars stay above the total")
        html = self.page.preview(data)
        self.assertEqual(html.count('s_review_total '), 1, "stars next to the total: one banner")
        self.assertIn('s_review_total_inline', html)
        # the stars moved above the heading: a banner of their own
        data['layout'] = [{'key': 'stars', 'show': True}, {'key': 'heading', 'show': True},
                          {'key': 'total', 'show': True}, {'key': 'reviews', 'show': True}]
        data.update(count_ms=1500, count_ease='log')
        data['colors'].update(button='#ff6600', button_text='#000000')
        html = self.page.preview(data)
        self.assertLess(html.index('s_review_total_stars'), html.index('s_review_heading'))
        self.assertGreater(html.index('s_review_total_number'), html.index('s_review_heading'))
        self.assertIn('data-count-ms="1500"', html)
        self.assertIn('data-count-ease="log"', html)
        self.assertIn('rv-button rv-button-text', html.replace('rv-button ', 'rv-button ', 1))
        self.assertIn('--rv-button: #ff6600', html)
        self.assertIn('rv-arrows', html, "arrows on: beside the reviews")
        data.update(button_size='lg', button_style='primary', logo='bubble', arrows=False)
        html = self.page.preview(data)
        self.assertIn('btn btn-primary btn-lg', html)
        self.assertIn('rv-logo-bubble', html)
        self.assertNotIn('rv-arrows', html)
        data['count_ease'] = 'bounce'
        with self.assertRaises(ValidationError):
            self.page.preview(data)

    def test_several_sources_domain(self):
        Review = self.env['review.review']
        for source in (self.src_a, self.src_b):
            Review.create({'source_id': source.id, 'author_name': source.name.split()[-1] + 'nna', 'rating': 5,
                           'text': 'Great'})
        found = Review.slider_reviews(source_id=f'{self.src_a.id},{self.src_b.id}', min_rating=5)
        self.assertEqual({r['author'] for r in found['reviews']}, {'Anna', 'Bnna'})
        only_a = Review.slider_reviews(source_id=str(self.src_a.id), min_rating=5)
        self.assertEqual([r['author'] for r in only_a['reviews']], ['Anna'])

    def test_save_new_delete(self):
        """A new preset gets its own key; built-in presets cannot be deleted, others can."""
        data = dict(_preset_data(self.env, 'cards'), id=None, key='', name='Tour Pages Dark')
        data['texts']['heading'] = {lang: 'Our riders say' for lang in data['texts']['heading']}
        page = self.page.save_presets([data])
        new = self.env['review.preset'].browse(page['saved'][0])
        self.assertEqual((new.key, new.heading, new.style), ('tour-pages-dark', 'Our riders say', 'cards'))
        again = self.page.save_presets([dict(data, id=None)])
        self.assertEqual(self.env['review.preset'].browse(again['saved'][0]).key, 'tour-pages-dark-2')
        builtin = self.env.ref('website_review_sync.preset_bubbles')
        self.page.save_presets([], deleted=[builtin.id, new.id])
        self.assertTrue(builtin.exists())
        self.assertFalse(new.exists())

    def test_menus_centralized(self):
        """No menus left: the extension tiles open the Reviews page."""
        for xmlid in ('website_review_sync.menu_reviews', 'website_review_sync.menu_review_review',
                      'website_review_sync.menu_review_source', 'website_review_sync.menu_review_account',
                      'mtbg_tours_reviews.menu_tours_reviews'):
            self.assertFalse(self.env.ref(xmlid, raise_if_not_found=False), xmlid)
        action = self.env.ref('website_review_sync.action_mtbg_extension_page')
        self.assertEqual(action.tag, 'review_settings_page')
        page = self.page.get_page()
        self.assertTrue({'presets', 'sources', 'accounts', 'langs', 'block_parts', 'card_parts'} <= set(page))
        rows = self.page.reviews({'status': 'published'})
        self.assertIn('rows', rows)


@tagged('post_install', '-at_install')
class TestReviewSettingsPage(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        source = cls.env['review.source'].create({'name': 'Page Test', 'platform': 'manual'})
        for n in range(3):
            cls.env['review.review'].create({'source_id': source.id, 'author_name': f'Rider {n}', 'rating': 5,
                                             'text': f'Great ride number {n}', 'title': f'Title {n}'})

    def test_routes(self):
        result = self.make_jsonrpc_request('/review_sync/preset', {'key': 'cards'})
        self.assertIn('s_review_cards', result['html'])
        self.authenticate('admin', 'admin')
        preset = self.env.ref('website_review_sync.preset_dark')
        html = self.url_open(f'/review_sync/preset/preview?preset={preset.id}').text
        self.assertIn('data-review-preset-preview', html)
        self.assertIn('s_review_dark', html)

    def test_page_live_preview(self):
        """The page: an unsaved heading, the card style and a dragged part reach the preview; the tabs load."""
        code = """
        (async () => {
            const wait = async (fn, what) => {
                for (let i = 0; i < 200; i++) {
                    const found = fn();
                    if (found) { return found; }
                    await new Promise((r) => setTimeout(r, 100));
                }
                throw new Error('timeout: ' + what);
            };
            const frameDoc = () => document.querySelector('.rv_frame')?.contentDocument;
            const block = () => frameDoc()?.querySelector('[data-review-preset-preview] .s_review_ordered');
            const picker = await wait(() => document.querySelector('#rv_preset'), 'presets');
            picker.value = [...picker.options].find((o) => o.textContent.includes('Website colours')).value;
            picker.dispatchEvent(new Event('change', { bubbles: true }));
            await wait(() => block()?.classList.contains('s_review_site'), 'saved preset in the preview');
            await wait(() => frameDoc().querySelector('.s_review_slider_card'), 'reviews in the preview');
            const heading = document.querySelector('input[aria-label="Heading text"]');
            heading.value = 'Zebra heading';
            heading.dispatchEvent(new Event('input', { bubbles: true }));
            await wait(() => frameDoc().querySelector('.s_review_heading')?.textContent.includes('Zebra heading'), 'heading');
            [...document.querySelectorAll('.rv_style_btn')].find((b) => b.textContent.includes('Cards')).click();
            await wait(() => block()?.classList.contains('s_review_cards'), 'cards');
            // the three steps, in order
            const steps = [...document.querySelectorAll('.rv_step')].map((h) => h.textContent.replace(/^\d/, '').trim());
            if (steps.join('|') !== 'Sources|Design|Content and layout') { throw new Error('steps: ' + steps.join('|')); }
            // the first part of a review (stars) moves down one with the keyboard
            const grips = [...document.querySelectorAll('.rv_parts')][1].querySelectorAll('.rv_grip');
            grips[0].dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
            await wait(() => block()?.getAttribute('style').includes('--rv-o-rating: 1'), 'dragged part');
            if (!document.querySelector('.badge.text-bg-warning')) { throw new Error('no unsaved badge'); }
            [...document.querySelectorAll('.rv_tabs .nav-link')].find((a) => a.textContent.includes('Reviews')).click();
            await wait(() => [...document.querySelectorAll('.rv_table tbody tr')].some((tr) => tr.textContent.includes('Rider 1')), 'reviews table');
            [...document.querySelectorAll('.rv_tabs .nav-link')].find((a) => a.textContent.includes('Sources')).click();
            await wait(() => document.body.textContent.includes('Page Test'), 'sources');
            console.log('test successful');
        })().catch((e) => console.error(e.message));
        """
        self.browser_js('/odoo/action-website_review_sync.action_mtbg_extension_page', code, login='admin', timeout=120)
