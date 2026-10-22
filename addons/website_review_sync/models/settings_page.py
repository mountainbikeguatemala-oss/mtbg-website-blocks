"""The Reviews page (client action ``review_settings_page``): the presets of the Reviews blocks with a live preview,
the reviews themselves, their sources and accounts, in one place."""
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

from .preset import BLOCK_PARTS, CARD_PARTS, COLORS, TEXTS

PAGE_SIZE = 50


class ReviewSettingsPage(models.AbstractModel):
    _name = 'review.settings.page'
    _description = 'Reviews page'

    def _check(self):
        if not self.env.user.has_group('website.group_website_designer'):
            raise AccessError(_("Only website designers can change the reviews."))

    @api.model
    def _langs(self):
        """The website's languages, its main one first."""
        website = self.env['website'].sudo().search([], limit=1)
        if not website:
            return self.env['res.lang'].sudo().search([('active', '=', True)])
        return website.default_lang_id | website.language_ids.sorted('name')

    @api.model
    def _currencies(self):
        """The preview's currencies: the website's, and the second one the site shows prices in when set
        (MTBG Tours: mtbg_tours.alt_currency_code / _rate)."""
        website = self.env['website'].sudo().search([], limit=1)
        currencies = [{'key': 'base', 'code': (website.company_id or self.env.company).currency_id.name}]
        ICP = self.env['ir.config_parameter'].sudo()
        code = ICP.get_param('mtbg_tours.alt_currency_code')
        if code and float(ICP.get_param('mtbg_tours.alt_currency_rate') or 0):
            currencies.append({'key': 'alt', 'code': code})
        return currencies

    @api.model
    def _preset_data(self, preset, langs):
        raw = preset.with_context(check_translations=True)
        texts = {name: {lang.code: raw.with_context(lang=lang.code)[name] or '' for lang in langs} for name in TEXTS}
        builtin = bool(preset.get_external_id().get(preset.id))
        return dict(preset._values(), texts=texts, builtin=builtin, usage=preset._usage())

    @api.model
    def _source_data(self, source):
        return {
            'id': source.id, 'name': source.name, 'platform': source.platform, 'active': source.active,
            'account': source.account_id.name or '', 'synced': bool(source.account_id),
            'average': round(source.rating_average, 1), 'count': source.rating_count,
            'reviews': source.review_count, 'url': source.profile_url or '',
            'last_sync': fields.Datetime.to_string(source.last_sync) if source.last_sync else False,
            'last_error': source.last_error or '',
        }

    @api.model
    def get_page(self):
        self._check()
        langs = self._langs()
        is_admin = self.env.user.has_group('base.group_system')
        Source = self.env['review.source'].with_context(active_test=False)
        accounts = self.env['review.account'].sudo().with_context(active_test=False).search([]) if is_admin else []
        platforms = dict(self.env['review.source']._fields['platform']._description_selection(self.env))
        return {
            'presets': [self._preset_data(p, langs) for p in self.env['review.preset'].search([])],
            'sources': [self._source_data(s) for s in Source.search([])],
            'accounts': [{'id': a.id, 'name': a.name, 'platform': a.platform, 'connected': a.connected,
                          'active': a.active, 'locations': len(a.source_ids), 'note': a.note or ''} for a in accounts],
            'platforms': [{'key': k, 'label': v} for k, v in platforms.items()],
            'langs': [{'code': lang.code, 'url_code': lang.url_code, 'name': lang.name} for lang in langs],
            'block_parts': BLOCK_PARTS, 'card_parts': CARD_PARTS, 'colors': COLORS,
            'is_admin': is_admin, 'total_reviews': self.env['review.review'].search_count([]),
            'currencies': self._currencies(),
        }

    # ------------------------------------------------------------------ presets
    @api.model
    def _write_texts(self, preset, texts, langs):
        main = langs[:1].code or 'en_US'
        for name in TEXTS:
            values = (texts or {}).get(name) or {}
            main_value = (values.get(main) or '').strip()
            preset.with_context(lang=main).write({name: main_value or False})
            translations = {lang.code: (values.get(lang.code) or '').strip() or False for lang in langs[1:]}
            if main_value and translations:
                preset.update_field_translations(name, translations)

    @api.model
    def save_presets(self, presets, deleted=None):
        """Save the edited presets (new ones without an id) and delete the removed ones (not the built-in ones)."""
        self._check()
        Preset = self.env['review.preset']
        langs = self._langs()
        main = langs[:1].code or 'en_US'
        for preset_id in deleted or []:
            preset = Preset.browse(int(preset_id)).exists()
            if preset and not preset.get_external_id().get(preset.id):
                preset.unlink()
        saved = []
        for data in presets or []:
            vals = Preset._clean(data)
            preset = Preset.browse(data['id']).exists() if isinstance(data.get('id'), int) else Preset
            if preset:
                preset.with_context(lang=main).write(vals)
            else:
                key = (data.get('key') or '').strip().lower() or Preset._new_key(vals['name'])
                if Preset.with_context(active_test=False).search_count([('key', '=', key)]):
                    key = Preset._new_key(key)
                preset = Preset.with_context(lang=main).create(dict(vals, key=key))
            self._write_texts(preset, data.get('texts'), langs)
            saved.append(preset.id)
        return dict(self.get_page(), saved=saved)

    @api.model
    def preview(self, data, lang=None):
        """A preset's block with the page's unsaved values, in ``lang`` (the preview puts it in place)."""
        self._check()
        langs = self._langs()
        main = langs[:1].code or 'en_US'
        lang = lang or main
        texts = {name: ((data.get('texts') or {}).get(name) or {}).get(lang)
                 or ((data.get('texts') or {}).get(name) or {}).get(main) or '' for name in TEXTS}
        return self.env['review.preset'].with_context(lang=lang)._render(self.env['review.preset']._clean(data), texts)

    # ------------------------------------------------------------------ reviews
    @api.model
    def _review_domain(self, filters):
        filters = filters or {}
        domain = []
        if filters.get('search'):
            term = filters['search']
            domain += ['|', '|', ('author_name', 'ilike', term), ('text', 'ilike', term), ('title', 'ilike', term)]
        if filters.get('source_id'):
            domain.append(('source_id', '=', int(filters['source_id'])))
        if filters.get('rating'):
            domain.append(('rating', '=', int(filters['rating'])))
        status = filters.get('status')
        if status == 'published':
            domain.append(('is_published', '=', True))
        elif status == 'hidden':
            domain.append(('is_published', '=', False))
        elif status == 'featured':
            domain.append(('featured', '=', True))
        elif status == 'photos':
            domain.append(('has_photos', '=', True))
        return domain

    @api.model
    def reviews(self, filters=None, offset=0):
        """A page of the reviews table."""
        self._check()
        Review = self.env['review.review']
        domain = self._review_domain(filters)
        rows = Review.search(domain, offset=max(0, int(offset or 0)), limit=PAGE_SIZE,
                             order='review_date desc, id desc')
        return {
            'total': Review.search_count(domain), 'offset': int(offset or 0), 'page_size': PAGE_SIZE,
            'rows': [{'id': r.id, 'date': fields.Date.to_string(r.review_date) if r.review_date else '',
                      'platform': r.platform, 'source': r.source_id.name or '', 'author': r.author_name,
                      'rating': r.rating, 'title': r.title or '', 'text': (r.text or '')[:280],
                      'language': r.language or '', 'photos': len(r.image_ids), 'published': r.is_published,
                      'featured': r.featured, 'url': r.url or ''} for r in rows],
        }

    @api.model
    def set_review(self, review_id, values):
        """On website / featured, from the table."""
        self._check()
        allowed = {k: bool(v) for k, v in (values or {}).items() if k in ('is_published', 'featured')}
        if not allowed:
            raise ValidationError(_("Nothing to change."))
        self.env['review.review'].browse(int(review_id)).exists().write(allowed)
        return True

    # ------------------------------------------------------------------ sources
    @api.model
    def sync_sources(self, source_ids=None):
        """Sync now: the given sources, or every synced one."""
        self._check()
        Source = self.env['review.source']
        sources = Source.browse(source_ids).exists() if source_ids else Source.search([('account_id', '!=', False)])
        sources.filtered('account_id').action_sync()
        return [self._source_data(s) for s in Source.with_context(active_test=False).search([])]
