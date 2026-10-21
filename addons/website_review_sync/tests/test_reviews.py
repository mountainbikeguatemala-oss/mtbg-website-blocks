from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from ..services import google, tripadvisor

GOOGLE_PAGE = {
    'reviews': [
        {'name': 'accounts/1/locations/2/reviews/r1', 'reviewId': 'r1', 'starRating': 'FIVE',
         'reviewer': {'displayName': 'Ana', 'profilePhotoUrl': 'https://img/ana'},
         'comment': 'Amazing trails!\n\n(Translated by Google)\n¡Senderos increíbles!', 'createTime': '2026-09-01T10:00:00Z',
         'reviewReply': {'comment': 'Thanks Ana!'}},
        {'name': 'accounts/1/locations/2/reviews/r2', 'reviewId': 'r2', 'starRating': 'TWO',
         'reviewer': {'displayName': 'Bob'}, 'comment': 'Too hard', 'createTime': '2026-08-01T10:00:00Z'},
    ],
    'averageRating': 4.9, 'totalReviewCount': 312,
}
TRIP_REVIEWS = {'data': [{'id': 9001, 'lang': 'en', 'rating': 5, 'title': 'Best day', 'text': 'Great guides',
                          'published_date': '2026-07-04T00:00:00Z', 'url': 'https://ta/9001',
                          'user': {'username': 'Carla', 'user_location': {'name': 'Denver, CO'},
                                   'avatar': {'small': 'https://img/carla'}}}]}
TRIP_DETAILS = {'rating': '5.0', 'num_reviews': '220'}


@tagged('post_install', '-at_install')
class TestReviewSync(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.g_account = cls.env['review.account'].create({
            'name': 'Business Google', 'platform': 'google', 'google_client_id': 'cid', 'google_client_secret': 'sec',
            'google_refresh_token': 'refresh'})
        cls.g_source = cls.env['review.source'].create({'name': 'Tecpán', 'account_id': cls.g_account.id,
                                                        'external_ref': 'accounts/1/locations/2'})
        cls.t_account = cls.env['review.account'].create({'name': 'Business TA', 'platform': 'tripadvisor',
                                                          'tripadvisor_api_key': 'key'})
        cls.t_source = cls.env['review.source'].create({'name': 'Antigua', 'account_id': cls.t_account.id,
                                                        'external_ref': '16787311', 'languages': 'en'})

    def test_google_sync_keeps_the_original_words_and_is_idempotent(self):
        with patch.object(google, 'refresh_access_token', return_value='tok'), \
                patch.object(google, '_get', return_value=GOOGLE_PAGE):
            self.assertEqual(self.g_source._sync(), 2)
            self.assertEqual(self.g_source._sync(), 0, "a second sync updates, never duplicates")
        self.assertEqual(self.g_source.platform, 'google')
        reviews = self.g_source.review_ids.sorted('rating')
        self.assertEqual(reviews.mapped('rating'), [2, 5])
        ana = reviews[-1]
        self.assertEqual(ana.text, 'Amazing trails!', "Google's machine translation is dropped")
        self.assertEqual((ana.reply_text, str(ana.review_date)), ('Thanks Ana!', '2026-09-01'))
        self.assertTrue(ana.is_published)
        self.assertFalse(reviews[0].is_published, "under the source's 'publish from' rating: waits for review")
        self.assertEqual((self.g_source.rating_average, self.g_source.rating_count), (4.9, 312))

    def test_hidden_review_stays_hidden_after_sync(self):
        with patch.object(google, 'refresh_access_token', return_value='tok'), \
                patch.object(google, '_get', return_value=GOOGLE_PAGE):
            self.g_source._sync()
            ana = self.g_source.review_ids.filtered(lambda r: r.external_id == 'r1')
            ana.is_published = False
            self.g_source._sync()
        self.assertFalse(ana.is_published)

    def test_tripadvisor_sync(self):
        def fake(url, params):
            return TRIP_DETAILS if url.endswith('/details') else TRIP_REVIEWS
        with patch.object(tripadvisor, '_get', side_effect=fake):
            self.assertEqual(self.t_source._sync(), 1)
        review = self.t_source.review_ids
        self.assertEqual((review.author_name, review.author_location, review.title, review.url),
                         ('Carla', 'Denver, CO', 'Best day', 'https://ta/9001'))
        self.assertEqual(self.t_source.rating_count, 220)

    def test_failed_sync_is_reported_on_the_source(self):
        with patch.object(tripadvisor, '_get', side_effect=RuntimeError('Tripadvisor API 401: bad key')):
            self.assertEqual(self.t_source._sync(), 0)
        self.assertIn('401', self.t_source.last_error)

    def test_slider_values(self):
        with patch.object(google, 'refresh_access_token', return_value='tok'), \
                patch.object(google, '_get', return_value=GOOGLE_PAGE):
            self.g_source._sync()
        Review = self.env['review.review']
        data = Review.slider_reviews(min_rating=4)
        self.assertEqual([r['author'] for r in data['reviews']], ['Ana'], "published, 4 stars and up")
        self.assertEqual(data['summary'][0]['count'], 312)
        self.assertFalse(Review.slider_reviews(platform='tripadvisor')['reviews'])
        self.assertEqual(len(Review.slider_reviews(source_id=self.g_source.id, min_rating=1)['reviews']), 1,
                         "hidden reviews never show")
        self.assertFalse(Review.slider_reviews(scope='page', page_record=self.env.user)['reviews'],
                         "the page's reviews: none known for a record nothing links reviews to")

    def test_locations_found_become_sources(self):
        with patch.object(google, 'list_locations', return_value=[
                {'account': 'accounts/1', 'location': 'locations/2', 'title': 'Tecpán'},
                {'account': 'accounts/1', 'location': 'locations/3', 'title': 'Antigua'}]):
            self.g_account.action_find_locations(access_token='tok')
        self.assertEqual(sorted(self.g_account.source_ids.mapped('external_ref')),
                         ['accounts/1/locations/2', 'accounts/1/locations/3'], "existing one kept, new one added")


@tagged('post_install', '-at_install')
class TestGoogleExportImport(TransactionCase):

    def test_import_is_idempotent_with_photos_and_replies(self):
        import json, os, tempfile
        from ..services.export_import import import_google_export
        folder = tempfile.mkdtemp()
        os.makedirs(os.path.join(folder, 'photos'))
        with open(os.path.join(folder, 'photos', '001_Ana_1.jpg'), 'wb') as fh:
            fh.write(b'\xff\xd8\xff\xe0' + b'0' * 64)
        with open(os.path.join(folder, 'reviews.json'), 'w') as fh:
            json.dump({'listing': {'name': 'Bike Shop', 'review_count': 3, 'average_rating': 4.67}, 'reviews': [
                {'username': 'Ana', 'reviewer_profile': 'https://www.google.com/maps/contrib/111/reviews', 'rating': 5,
                 'avatar': 'https://lh3/a=w36-h36-p', 'text': 'Great guides and the best trails',
                 'date_approx': '2025-07-20', 'owner_response': {'text': 'Thanks!'}, 'photo_files': ['photos/001_Ana_1.jpg']},
                {'username': 'Bike Shop', 'reviewer_profile': 'https://www.google.com/maps/contrib/222/reviews',
                 'rating': 5, 'text': '', 'date_approx': '2020-10-20', 'photo_files': []},
                {'username': 'Luis', 'reviewer_profile': 'https://www.google.com/maps/contrib/333/reviews', 'rating': 5,
                 'text': 'Excelente experiencia, muy recomendado para los que buscan aventura', 'photo_files': []},
            ]}, fh)
        source = self.env['review.source'].create({'name': 'Bike Shop', 'platform': 'google'})
        self.assertEqual(import_google_export(self.env, folder, source), {'created': 3, 'updated': 0, 'photos': 1})
        self.assertEqual(import_google_export(self.env, folder, source)['created'], 0, "a re-import updates")
        ana = source.review_ids.filtered(lambda r: r.author_name == 'Ana')
        self.assertEqual((ana.reply_text, ana.language, len(ana.image_ids), ana.author_photo_url),
                         ('Thanks!', 'en', 1, 'https://lh3/a=w88-h88-p'))
        self.assertEqual(source.review_ids.filtered(lambda r: r.author_name == 'Luis').language, 'es')
        self.assertFalse(source.review_ids.filtered(lambda r: r.author_name == 'Bike Shop').is_published,
                         "the business reviewing itself is not shown")
        self.assertEqual((source.rating_count, source.rating_average), (3, 4.67))
        data = self.env['review.review'].slider_reviews(source_id=source.id)
        self.assertEqual(sorted(r['author'] for r in data['reviews']), ['Ana', 'Luis'], "rating-only reviews left out")
        self.assertEqual(len(next(r for r in data['reviews'] if r['author'] == 'Ana')['photos']), 1)

    def test_tripadvisor_export(self):
        import json, os, tempfile
        from ..services.export_import import import_tripadvisor_export
        folder = tempfile.mkdtemp()
        with open(os.path.join(folder, 'reviews.json'), 'w') as fh:
            json.dump({'listing': {'name': 'Bike Shop', 'review_count': 1, 'average_rating': 5}, 'reviews': [{
                'username': 'bouchee', 'profile': 'https://www.tripadvisor.com/Profile/bouchee1947',
                'reviewer_meta': 'San Francisco, California650 contributions', 'rating': 5, 'title': 'Epic day',
                'review_url': 'https://www.tripadvisor.com/ShowUserReviews-g1-d2-r1077148510-Bike.html',
                'trip_date': 'Sep 2026 • Solo', 'date': '2026-09-10', 'text': 'Awesome views and the best guide',
                'owner_response': None, 'photo_files': []}]}, fh)
        source = self.env['review.source'].create({'name': 'Bike Shop TA', 'platform': 'tripadvisor'})
        self.assertEqual(import_tripadvisor_export(self.env, folder, source)['created'], 1)
        r = source.review_ids
        self.assertEqual((r.external_id, r.author_location, r.title, r.trip_date, str(r.review_date), r.date_approx),
                         ('1077148510', 'San Francisco, California', 'Epic day', 'Sep 2026 • Solo', '2026-09-10', False),
                         "the Tripadvisor review id: the Content API's id too")


@tagged('post_install', '-at_install')
class TestReviewWall(TransactionCase):

    def test_wall_pages_filters_and_choices(self):
        Review = self.env['review.review']
        g = self.env['review.source'].create({'name': 'G place', 'platform': 'google', 'rating_count': 12, 'rating_average': 4.9})
        t = self.env['review.source'].create({'name': 'T place', 'platform': 'tripadvisor'})
        photo = self.env['ir.attachment'].create({'name': 'p.jpg', 'raw': b'x', 'public': True})
        for i in range(7):
            Review.create({'source_id': g.id, 'platform': 'google', 'author_name': f'G{i}', 'rating': 5 if i else 3,
                           'text': f'google review {i}', 'language': 'en', 'review_date': f'2026-0{i + 1}-01'})
        Review.create({'source_id': t.id, 'platform': 'tripadvisor', 'author_name': 'T', 'rating': 4, 'text': 'muy bien',
                       'language': 'es', 'review_date': '2025-01-01', 'image_ids': [(6, 0, photo.ids)]})
        page = Review.wall_reviews(offset=0, limit=5)
        self.assertEqual((len(page['reviews']), page['total']), (5, 8))
        self.assertEqual(page['reviews'][0]['author'], 'G6', "newest first")
        self.assertEqual(len(Review.wall_reviews(offset=5, limit=5)['reviews']), 3, "the next page")
        self.assertEqual(Review.wall_reviews(platform='tripadvisor', limit=12)['total'], 1)
        self.assertEqual(Review.wall_reviews(min_rating=5, limit=12)['total'], 6)
        self.assertEqual([r['author'] for r in Review.wall_reviews(with_photos=True, limit=12)['reviews']], ['T'])
        self.assertEqual(Review.wall_reviews(language='es', limit=12)['total'], 1)
        self.assertEqual(Review.wall_reviews(sort='photos', limit=1)['reviews'][0]['author'], 'T')
        self.assertEqual(Review.wall_reviews(sort='best', limit=12)['reviews'][-1]['author'], 'G0')
        meta = Review.wall_reviews(limit=0)
        self.assertEqual(sorted(p['key'] for p in meta['platforms']), ['google', 'tripadvisor'])
        self.assertEqual([l['code'] for l in meta['languages']], ['en', 'es'])
        self.assertEqual(meta['summary'][0]['count'], 12)


@tagged('post_install', '-at_install')
class TestReviewerNames(TransactionCase):

    def test_names_as_the_source_shows_them(self):
        source = self.env['review.source'].create({'name': 'S', 'platform': 'google', 'author_display': 'first'})
        review = self.env['review.review'].create({'source_id': source.id, 'author_name': 'Graham Prior', 'rating': 5,
                                                   'text': 'Great ride'})
        self.assertEqual(review._display_author(), 'Graham')
        source.author_display = 'first_initial'
        self.assertEqual(review._display_author(), 'Graham P.')
        source.author_display = 'full'
        self.assertEqual(review._display_author(), 'Graham Prior')
        source.author_display = 'first'
        self.assertEqual(self.env['review.review'].slider_reviews(source_id=source.id)['reviews'][0]['author'], 'Graham',
                         "the website never gets the last name")


@tagged('post_install', '-at_install')
class TestReviewTranslations(TransactionCase):

    def test_cards_in_the_visitor_language_with_the_original(self):
        self.env['res.lang']._activate_lang('es_ES')
        source = self.env['review.source'].create({'name': 'S', 'platform': 'google'})
        review = self.env['review.review'].create({'source_id': source.id, 'author_name': 'Ana', 'rating': 5,
                                                   'title': 'Great', 'text': 'Great ride', 'language': 'en'})
        Review = self.env['review.review']
        self.assertEqual(Review.import_translations([{'id': review.id, 'lang': 'es', 'title': 'Genial',
                                                      'text': 'Gran paseo'}]), 1)
        self.assertEqual(Review.import_translations([{'id': review.id, 'lang': 'es', 'text': 'Gran ride'}]), 1,
                         "a re-import updates")
        self.assertEqual(len(review.translation_ids), 1)
        es = Review.with_context(lang='es_ES').slider_reviews(source_id=source.id)['reviews'][0]
        self.assertEqual((es['text'], es['original']['text']), ('Gran ride', 'Great ride'))
        en = Review.with_context(lang='en_US').slider_reviews(source_id=source.id)['reviews'][0]
        self.assertEqual(en['text'], 'Great ride')
        self.assertNotIn('original', en, "written in the visitor's language: no translation shown")
