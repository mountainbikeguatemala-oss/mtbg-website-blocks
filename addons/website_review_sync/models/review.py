import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..services import google, tripadvisor

_logger = logging.getLogger(__name__)

PLATFORMS = [('google', 'Google'), ('tripadvisor', 'Tripadvisor'), ('manual', 'Other / Manual')]



class ReviewAccount(models.Model):
    """A sign-in on a review platform: a Google account (OAuth, the business owner's) or a Tripadvisor Content API
    key. Its locations / listings are the review sources."""
    _name = 'review.account'
    _description = 'Review Account'
    _order = 'platform, name'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    platform = fields.Selection([p for p in PLATFORMS if p[0] != 'manual'], required=True, default='google')
    google_client_id = fields.Char(string='OAuth Client ID', groups='base.group_system')
    google_client_secret = fields.Char(string='OAuth Client Secret', groups='base.group_system')
    google_refresh_token = fields.Char(groups='base.group_system', copy=False)
    connected = fields.Boolean(compute='_compute_connected')
    tripadvisor_api_key = fields.Char(string='API Key', groups='base.group_system')
    source_ids = fields.One2many('review.source', 'account_id', string='Locations')
    note = fields.Text(readonly=True, copy=False)

    def _compute_connected(self):
        for account in self:
            src = account.sudo()
            account.connected = bool(src.google_refresh_token if src.platform == 'google' else src.tripadvisor_api_key)

    # ------------------------------------------------------------------ Google sign-in
    def action_google_connect(self):
        """Sign in with Google (the business owner's account) to allow reading the reviews."""
        self.ensure_one()
        src = self.sudo()
        if not (src.google_client_id and src.google_client_secret):
            raise UserError(self.env._("Enter the Google OAuth client ID and secret first (Google Cloud console)."))
        return {'type': 'ir.actions.act_url', 'target': 'self',
                'url': google.authorize_url(src.google_client_id, self._google_redirect_uri(), state=str(self.id))}

    def _google_redirect_uri(self):
        return f"{self.get_base_url()}/review_sync/google/callback"

    def _google_access_token(self):
        src = self.sudo()
        if not src.google_refresh_token:
            raise UserError(self.env._("Connect the Google account first."))
        return google.refresh_access_token(src.google_client_id, src.google_client_secret, src.google_refresh_token)

    def _google_finish_connect(self, code):
        src = self.sudo()
        tokens = google.exchange_code(src.google_client_id, src.google_client_secret, code, self._google_redirect_uri())
        if not tokens.get('refresh_token'):
            raise UserError(self.env._("Google did not return a refresh token: remove the app's access in the Google "
                                       "account's security settings and connect again."))
        src.google_refresh_token = tokens['refresh_token']
        self.action_find_locations(access_token=tokens['access_token'])

    def action_find_locations(self, access_token=None):
        """Google: add a review source for each location the account manages (existing ones are kept)."""
        for account in self.filtered(lambda a: a.platform == 'google'):
            token = access_token or account._google_access_token()
            known = set(account.source_ids.mapped('external_ref'))
            locations = google.list_locations(token)
            for loc in locations:
                ref = f"{loc['account']}/{loc['location']}"
                if ref in known:
                    continue
                # a source imported before the sign-in (same name, not connected yet) becomes this location
                imported = self.env['review.source'].search([('platform', '=', 'google'), ('account_id', '=', False),
                                                             ('name', '=ilike', loc['title'] or '')], limit=1)
                if imported:
                    imported.write({'account_id': account.id, 'external_ref': ref})
                else:
                    self.env['review.source'].create({'name': loc['title'] or ref, 'account_id': account.id,
                                                      'external_ref': ref})
            account.note = self.env._("%s location(s) found.", len(locations))
        return True

    def action_sync(self):
        return self.source_ids.action_sync()


class ReviewSource(models.Model):
    """A Google Business Profile location or a Tripadvisor listing whose reviews are synced."""
    _name = 'review.source'
    _description = 'Review Source'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    account_id = fields.Many2one('review.account', ondelete='cascade', index=True,
                                 help="Empty for reviews entered by hand / imported")
    platform = fields.Selection(PLATFORMS, compute='_compute_platform', store=True, readonly=False, required=True,
                                precompute=True)
    external_ref = fields.Char(string='Location', help="Google: accounts/123/locations/456 (found by the account); "
                                                       "Tripadvisor: the listing's id, the number in its URL after -d")
    website_id = fields.Many2one('website', help="Only on this website (empty: every website)")
    profile_url = fields.Char(string='Profile Page', help="The listing on Google / Tripadvisor (\"See all reviews\" links)")
    auto_publish_rating = fields.Integer(default=4, string='Publish From',
                                         help="New reviews with at least this many stars show on the website; the others "
                                              "wait (unpublished)")
    languages = fields.Char(default='en,es', help="Tripadvisor: languages to fetch, comma separated")
    author_display = fields.Selection([('full', 'Full name'), ('first_initial', 'First name and initial'),
                                       ('first', 'First name only')], string='Reviewer Names', default='first_initial',
                                      required=True, help="How reviewers' names show on the website (the full name stays here)")
    last_sync = fields.Datetime(readonly=True, copy=False)
    last_error = fields.Text(readonly=True, copy=False)
    rating_average = fields.Float(readonly=True, digits=(3, 2), copy=False, help="As reported by the platform")
    rating_count = fields.Integer(readonly=True, copy=False, help="As reported by the platform")
    review_ids = fields.One2many('review.review', 'source_id')
    review_count = fields.Integer(compute='_compute_review_count')

    @api.depends('account_id.platform')
    def _compute_platform(self):
        for source in self:
            source.platform = source.account_id.platform if source.account_id else (source.platform or 'manual')

    def _compute_review_count(self):
        counts = dict(self.env['review.review']._read_group([('source_id', 'in', self.ids)], ['source_id'], ['__count']))
        for source in self:
            source.review_count = counts.get(source, 0)

    # ------------------------------------------------------------------ sync
    def action_sync(self):
        for source in self:
            source._sync()
        return True

    def _sync(self):
        self.ensure_one()
        account = self.account_id.sudo()
        try:
            if not account:
                return 0
            if self.platform == 'google':
                ref = self.external_ref or ''
                if '/locations/' not in ref:
                    raise UserError(self.env._("Set the location (accounts/…/locations/…): use Find Locations on the account."))
                acc, loc = ref.split('/locations/', 1)
                data = google.fetch_reviews(account._google_access_token(), acc, f"locations/{loc}")
            else:
                if not (account.tripadvisor_api_key and self.external_ref):
                    raise UserError(self.env._("Enter the Tripadvisor API key and the listing id first."))
                data = tripadvisor.fetch_reviews(account.tripadvisor_api_key, self.external_ref,
                                                 [x.strip() for x in (self.languages or 'en').split(',') if x.strip()])
        except Exception as exc:  # noqa: BLE001 - kept on the source, the cron goes on with the others
            _logger.warning("Reviews: %s sync failed: %s", self.name, exc)
            self.write({'last_error': str(exc), 'last_sync': fields.Datetime.now()})
            return 0
        created = self.env['review.review']._review_upsert(self, data['reviews'])
        self.write({'last_sync': fields.Datetime.now(), 'last_error': False,
                    'rating_average': data.get('average') or self.rating_average,
                    'rating_count': data.get('total') or self.rating_count})
        return created

    @api.model
    def _cron_sync(self):
        for source in self.search([('account_id', '!=', False)]):
            source._sync()
            self.env.cr.commit()

    def action_view_reviews(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'review.review', 'name': self.name,
                'view_mode': 'list,form', 'domain': [('source_id', '=', self.id)],
                'context': {'default_source_id': self.id}}


class ReviewReview(models.Model):
    _name = 'review.review'
    _description = 'Review'
    _order = 'featured desc, review_date desc, id desc'
    _rec_name = 'author_name'

    source_id = fields.Many2one('review.source', ondelete='cascade', index=True)
    platform = fields.Selection(PLATFORMS, required=True, default='manual', index=True)
    external_id = fields.Char(index=True, copy=False, help="The review's id on its platform (sync key)")
    author_name = fields.Char(required=True, string='Reviewer')
    author_photo_url = fields.Char(string='Reviewer Photo')
    author_location = fields.Char(string='From')
    author_url = fields.Char(string='Reviewer Profile')
    rating = fields.Integer(required=True, default=5)
    title = fields.Char(translate=False)
    text = fields.Text()
    language = fields.Char()
    review_date = fields.Date(index=True)
    date_approx = fields.Boolean(string='Approximate Date', help="Worked out from the platform's \"3 months ago\"")
    trip_date = fields.Char(string='Travelled', help="e.g. October 2025 (Tripadvisor)")
    url = fields.Char(string='Review Link')
    reply_text = fields.Text(string='Our Reply')
    is_published = fields.Boolean(string='On Website', default=True, index=True)
    featured = fields.Boolean(help="Shown first in the sliders")
    image_ids = fields.Many2many('ir.attachment', 'review_review_image_rel', 'review_id', 'attachment_id',
                                 string='Photos', help="The reviewer's photos (shown on the review's card)")
    has_photos = fields.Boolean(compute='_compute_has_photos', store=True, index=True)
    translation_ids = fields.One2many('review.review.translation', 'review_id', string='Translations',
                                      help="The review in other languages: visitors see the one of the page's "
                                           "language (with the original a click away)")

    @api.depends('image_ids')
    def _compute_has_photos(self):
        for review in self:
            review.has_photos = bool(review.image_ids)

    _source_external_uniq = models.Constraint('unique(source_id, external_id)', 'This review is already imported.')
    _rating_range = models.Constraint('CHECK(rating BETWEEN 1 AND 5)', 'A rating goes from 1 to 5 stars.')

    @api.model
    def _review_upsert(self, source, rows):
        """Create / update a source's reviews from normalized rows (services.*.fetch_reviews); returns the number
        of new reviews. Website flags (published, featured...) are never overwritten."""
        existing = {r.external_id: r for r in self.search([('source_id', '=', source.id), ('external_id', 'in', [x['external_id'] for x in rows])])}
        created = 0
        for row in rows:
            vals = dict(row, platform=source.platform, source_id=source.id)
            rec = existing.get(row['external_id'])
            if rec:
                rec.write({k: v for k, v in vals.items() if k not in ('is_published',)})
            else:
                vals['is_published'] = (row.get('rating') or 0) >= (source.auto_publish_rating or 0)
                self.create(vals)
                created += 1
        return created

    # ------------------------------------------------------------------ website
    @api.model
    def _slider_domain(self, platform=None, source_id=None, min_rating=4, website=None, **options):
        """Published reviews of a Reviews block. Extension point: ``options['scope'] == 'page'`` asks for the
        reviews of ``options['page_record']`` (the page's record, e.g. a product): modules linking reviews to
        records add that condition (none known: no reviews)."""
        domain = [('is_published', '=', True), ('rating', '>=', int(min_rating or 1)),
                  # rating-only reviews (no words) are not shown unless asked for
                  *([] if options.get('with_empty') else [('text', '!=', False), ('text', '!=', '')]),
                  '|', ('source_id', '=', False), ('source_id.website_id', 'in', [False] + ([website.id] if website else []))]
        if platform in dict(PLATFORMS):
            domain.append(('platform', '=', platform))
        source_ids = self._source_ids(source_id)
        if source_ids:
            domain.append(('source_id', 'in', source_ids))
        if options.get('with_photos'):
            domain.append(('has_photos', '=', True))
        if options.get('language'):
            domain.append(('language', '=', options['language']))
        if options.get('scope') == 'page' and not self._slider_page_domain(options.get('page_record')):
            domain.append(('id', '=', 0))
        elif options.get('scope') == 'page':
            domain += self._slider_page_domain(options.get('page_record'))
        return domain

    @api.model
    def _source_ids(self, source_id):
        """A block's sources: one id, or several ("3,5", a preset's sources); [] for every source."""
        if not source_id or source_id == 'all':
            return []
        return [int(part) for part in str(source_id).split(',') if part.strip().isdigit()]

    def _slider_page_domain(self, record):
        """Condition for the reviews of the page's record (override); [] when not known."""
        return []

    @api.model
    def slider_reviews(self, platform=None, source_id=None, min_rating=4, limit=12, lang=None, website=None, **options):
        """Published reviews for a Reviews block, as plain values (public JSON)."""
        domain = self._slider_domain(platform=platform, source_id=source_id, min_rating=min_rating, website=website, **options)
        reviews = self.sudo().search(domain, limit=max(1, min(int(limit or 12), 50)),
                                     order=self.WALL_ORDERS.get(options.get('sort') or 'featured', self.WALL_ORDERS['featured']))
        if lang and reviews and (options.get('sort') or 'featured') == 'featured':
            # the visitor's language first (by review), others after
            short = lang.split('_')[0]
            reviews = reviews.sorted(lambda r: (not r.featured, (r.language or '')[:2] != short))
        source_ids = self._source_ids(source_id)
        sources = self.env['review.source'].sudo().search([('active', '=', True)] + (
            [('id', 'in', source_ids)] if source_ids else []))
        return {
            'reviews': self._card_values(reviews),
            'summary': self._summary_values(sources, platform),
            'five_star': self._five_star_count(platform=platform, source_id=source_id, website=website, **options),
        }

    WALL_ORDERS = {'featured': 'featured desc, review_date desc, id desc', 'newest': 'review_date desc, id desc',
                   'recent': 'review_date desc, id desc', 'best': 'rating desc, review_date desc, id desc',
                   'photos': 'has_photos desc, review_date desc, id desc'}

    def _five_star_count(self, **filters):
        """Published five-star reviews (rating-only ones included) the block's filters cover: its "400+"."""
        filters = {k: v for k, v in filters.items() if k not in ('min_rating', 'with_photos', 'language', 'sort')}
        domain = self._slider_domain(min_rating=5, with_empty=True, **filters)
        return self.sudo().search_count(domain)

    @api.model
    def wall_reviews(self, offset=0, limit=12, sort='newest', website=None, **filters):
        """A page of the Reviews wall (filters as the slider's, plus with_photos / language), with the total; with
        ``limit=0``, what the filters offer (platforms, sources, languages) and the rating badges."""
        filters.setdefault('min_rating', 1)  # the full list: every rating unless filtered
        domain = self._slider_domain(website=website, **filters)
        Review = self.sudo()
        if not limit:
            all_reviews = Review.search(self._slider_domain(website=website, min_rating=1))
            sources = all_reviews.source_id.filtered('active').sorted('sequence')
            names = dict(self._fields['platform']._description_selection(self.env))
            languages = {'en': 'English', 'es': 'Español'}
            return {
                'summary': self._summary_values(sources, None),
                'five_star': self._five_star_count(website=website, platform=filters.get('platform'),
                                                   source_id=filters.get('source_id')),
                'platforms': [{'key': p, 'name': names.get(p, p)} for p in dict.fromkeys(all_reviews.mapped('platform'))
                              if p != 'manual'],
                # (two listings can share a name: the platform tells them apart)
                'sources': [{'id': s.id, 'name': f"{s.name} · {names.get(s.platform, s.platform)}"} for s in sources],
                'languages': [{'code': code, 'name': languages.get(code, code)}
                              for code in sorted(set(all_reviews.mapped('language')) - {False})],
            }
        reviews = Review.search(domain, offset=max(0, int(offset or 0)), limit=max(1, min(int(limit), 48)),
                                order=self.WALL_ORDERS.get(sort, self.WALL_ORDERS['newest']))
        return {'reviews': self._card_values(reviews), 'total': Review.search_count(domain)}

    def _display_author(self):
        """The reviewer's name as the source shows it: "Graham Prior" / "Graham P." / "Graham"."""
        self.ensure_one()
        parts = (self.author_name or '').split()
        mode = self.source_id.author_display or 'first_initial'
        if len(parts) < 2 or mode == 'full':
            return self.author_name or ''
        if mode == 'first':
            return parts[0]
        return f"{parts[0]} {parts[-1][0].upper()}."

    def _summary_values(self, sources, platform):
        return [{'platform': s.platform, 'name': s.name, 'average': round(s.rating_average, 1), 'count': s.rating_count,
                 'url': s.profile_url or ''} for s in sources if s.rating_count and (not platform or s.platform == platform)]

    def _card_values(self, reviews):
        """Plain values of the review cards, in the visitor's language: a review written in another language shows
        its translation when there is one, the original in ``original``."""
        short = (self.env.lang or 'en_US').split('_')[0]
        cards = []
        for r in reviews:
            card = {
                'id': r.id, 'platform': r.platform, 'author': r._display_author(), 'photo': r.author_photo_url or '',
                'from': r.author_location or '', 'rating': r.rating, 'title': r.title or '', 'text': r.text or '',
                'date': r.review_date.isoformat() if r.review_date else '', 'url': r.url or r.author_url or '',
                'photos': [f'/web/image/{a.id}/600x600' for a in r.image_ids[:3]],
            }
            translation = (r.language or short)[:2] != short and r.translation_ids.filtered(lambda t: t.lang == short)[:1]
            if translation and translation.text:
                card['original'] = {'title': card['title'], 'text': card['text']}
                card.update(title=translation.title or '', text=translation.text)
            cards.append(card)
        return cards

    @api.model
    def import_translations(self, rows):
        """Add / update review translations from rows {id, lang, title, text, reply_text} (``lang``: "es",
        "en"...); returns the number written."""
        reviews = self.browse([int(r['id']) for r in rows]).exists()
        existing = {(t.review_id.id, t.lang): t for t in reviews.translation_ids}
        known = set(reviews.ids)
        count = 0
        for row in rows:
            rid, lang = int(row['id']), (row.get('lang') or '')[:2].lower()
            if rid not in known or not lang or not (row.get('text') or row.get('title')):
                continue
            vals = {'title': row.get('title') or False, 'text': row.get('text') or False,
                    'reply_text': row.get('reply_text') or False}
            if (rid, lang) in existing:
                existing[rid, lang].write(vals)
            else:
                self.env['review.review.translation'].create(dict(vals, review_id=rid, lang=lang))
            count += 1
        return count


class ReviewTranslation(models.Model):
    _name = 'review.review.translation'
    _description = 'Review Translation'
    _order = 'lang'

    review_id = fields.Many2one('review.review', required=True, ondelete='cascade', index=True)
    lang = fields.Char(string='Language', required=True, help="Language code: es, en, fr...")
    title = fields.Char()
    text = fields.Text()
    reply_text = fields.Text(string='Our Reply')

    _review_lang_uniq = models.Constraint('unique(review_id, lang)', 'The review has a translation in this language already.')
