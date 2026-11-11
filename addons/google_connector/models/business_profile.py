"""Google Business Profile reviews: the connector's "reviews" app reads them for the Tours' Reviews (owner,
2026-11-07: a connector's API code lives in the connector, never in a main extension). Reviews asks these methods
only when the connector is installed; nothing here needs Reviews.

Google Business Profile: the accounts (Account Management API), their locations (Business Information API) and the
reviews (v4: 50 per page, with the average and total). The Google Cloud project needs these APIs, which Google
grants on request."""
import datetime
import logging
import re

import requests

from odoo import api, models
from odoo.exceptions import UserError

from .client import GoogleError

APP = 'reviews'
ACCOUNTS_URL = 'https://mybusinessaccountmanagement.googleapis.com/v1/accounts'
LOCATIONS_URL = 'https://mybusinessbusinessinformation.googleapis.com/v1/{account}/locations'
REVIEWS_URL = 'https://mybusiness.googleapis.com/v4/{account}/{location}/reviews'
SCOPES = ['https://www.googleapis.com/auth/business.manage']
_logger = logging.getLogger(__name__)
PHOTO_SIZE = 's1600'          # a FIFE photo asked at most 1600px on its long side
PHOTO_MAX_BYTES = 15 * 1024 * 1024
PHOTO_TIMEOUT = 20
FIFE_SIZE_RE = re.compile(r'=[^/=]*$')
STARS = {'ONE': 1, 'TWO': 2, 'THREE': 3, 'FOUR': 4, 'FIVE': 5}


def parse_review(item):
    """A Google review as review.review._review_upsert takes it."""
    reviewer = item.get('reviewer') or {}
    when = (item.get('createTime') or '')[:10]
    comment = item.get('comment') or ''
    # Google appends its machine translation: keep the reviewer's own words
    if '(Translated by Google)' in comment and '(Original)' in comment:
        comment = comment.split('(Original)', 1)[1].strip()
    elif '(Translated by Google)' in comment:
        comment = comment.split('(Translated by Google)', 1)[0].strip()
    return {
        'external_id': item.get('reviewId') or item['name'].rsplit('/', 1)[-1],
        'author_name': reviewer.get('displayName') or 'Google user',
        'author_photo_url': reviewer.get('profilePhotoUrl') or False,
        'rating': STARS.get(item.get('starRating'), 5),
        'text': comment,
        'review_date': datetime.date.fromisoformat(when) if when else False,
        'reply_text': (item.get('reviewReply') or {}).get('comment') or False,
        # the reviewer's photos and videos (v4.9, 2026-04-20: reviewMediaItems); a FIFE photo URL changes over time,
        # so whoever keeps them stores a copy (_google_review_photo)
        'media': [{'photo_url': m.get('thumbnailUrl') or False, 'label': m.get('thumbnailLabel') or False,
                   'video_url': m.get('videoUrl') or False}
                  for m in item.get('reviewMediaItems') or [] if m.get('thumbnailUrl') or m.get('videoUrl')],
    }


def photo_url(url):
    """A FIFE photo URL asked at PHOTO_SIZE (its own size option replaced)."""
    if 'googleusercontent.com' not in (url or ''):
        return url
    return (FIFE_SIZE_RE.sub('', url) if FIFE_SIZE_RE.search(url.rsplit('/', 1)[-1]) else url) + '=' + PHOTO_SIZE


def plain_error(env, error):
    """A Google error in words the person at the screen can act on (UserError, shown and kept on the account or
    source)."""
    message = str(error)
    short = message if len(message) <= 300 else message[:300] + '…'
    status = getattr(error, 'status', None)
    if status == 429 and 'quota' in message.lower():
        # a new project's Business Profile APIs have a quota of 0 until Google approves the access
        return UserError(env._("Google hasn't approved Business Profile API access for this project yet (quota 0). "
                               "Request access in Google, then try again."))
    if status == 429:
        return UserError(env._("Google is busy (too many requests): try again in a few minutes."))
    if status == 403:
        return UserError(env._("Google refused: the Business Profile APIs are not enabled in the Google Cloud "
                               "project, or the Google account has not granted access. Check Set up Google (APIs, "
                               "then Reconnect). Google said: %s", short))
    return UserError(env._("Google: %s", short))


class GoogleConnector(models.AbstractModel):
    _inherit = 'google.connector'

    @api.model
    def _google_app_specs(self):
        """The reviews app, once Reviews is installed (it holds the reviews; this connector reads them)."""
        specs = super()._google_app_specs()
        if self.env.get('review.review') is None:
            return specs
        return dict(specs, **{APP: {
            'label': 'Google Business Profile', 'module': 'mtbg_tours_reviews', 'sequence': 50,
            # Google has no read-only access for reviews: business.manage is the one the reviews API takes
            'read_scopes': SCOPES, 'needs_account': True,
            'settings_action': 'mtbg_tours_reviews.action_review_account',
            'description': "Your Google Business Profile reviews, synced every day into Reviews (read only).",
        }})

    @api.model
    def _google_reviews_ready(self):
        """The Google Business Profile app is on, with an account that granted its access."""
        app = self._google_app(APP)
        return bool(app) and app.status == 'ready'

    @api.model
    def _google_reviews_locations(self):
        """[{account, location, title}] the app's Google account manages (a UserError in plain words on failure)."""
        try:
            return self._google_reviews_read_locations()
        except GoogleError as error:
            raise plain_error(self.env, error) from error

    @api.model
    def _google_reviews_fetch(self, account_ref, location_ref):
        """{'reviews': [values], 'average', 'total'} of a location (a UserError in plain words on failure)."""
        try:
            return self._google_reviews_read(account_ref, location_ref)
        except GoogleError as error:
            raise plain_error(self.env, error) from error

    @api.model
    def _google_review_photo(self, url):
        """A review photo's bytes: {'data': bytes, 'mimetype'}, or None (not an image, too big, or Google did not
        answer). The photos are public: no Google sign-in is sent. Never raises."""
        if not url or not url.startswith('https://'):
            return None
        try:
            response = requests.get(photo_url(url), timeout=PHOTO_TIMEOUT, stream=True)
            mimetype = (response.headers.get('Content-Type') or '').split(';')[0].strip()
            if response.status_code != 200 or not mimetype.startswith('image/'):
                return None
            data = b''
            for chunk in response.iter_content(65536):
                data += chunk
                if len(data) > PHOTO_MAX_BYTES:
                    return None
            return {'data': data, 'mimetype': mimetype} if data else None
        except requests.RequestException as error:
            _logger.warning("Google review photo %s: %s", url, error)
            return None

    @api.model
    def _google_reviews_read_locations(self):
        client = self.client(APP)
        result = []
        for account in client.get(ACCOUNTS_URL).get('accounts', []):
            page = None
            while True:
                data = client.get(LOCATIONS_URL.format(account=account['name']),
                                  params={'readMask': 'name,title', 'pageSize': 100, **({'pageToken': page} if page else {})})
                result += [{'account': account['name'], 'location': loc['name'], 'title': loc.get('title', '')}
                           for loc in data.get('locations', [])]
                page = data.get('nextPageToken')
                if not page:
                    break
        return result

    @api.model
    def _google_reviews_read(self, account_ref, location_ref):
        client = self.client(APP)
        reviews, average, total, page = [], 0.0, 0, None
        while True:
            data = client.get(REVIEWS_URL.format(account=account_ref, location=location_ref),
                              params={'pageSize': 50, **({'pageToken': page} if page else {})})
            reviews += [parse_review(r) for r in data.get('reviews', [])]
            average = data.get('averageRating', average)
            total = data.get('totalReviewCount', total)
            page = data.get('nextPageToken')
            if not page:
                break
        return {'reviews': reviews, 'average': average, 'total': total}
