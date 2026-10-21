"""Google Business Profile: OAuth sign-in of the business owner and the location's reviews.

Reviews are read with the Business Profile API (v4 reviews: 50 per page, with the average and total). The Google
Cloud project needs the Business Profile APIs enabled (access is granted by Google on request).
"""
import datetime
from urllib.parse import urlencode

import requests

AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
SCOPE = 'https://www.googleapis.com/auth/business.manage'
ACCOUNTS_URL = 'https://mybusinessaccountmanagement.googleapis.com/v1/accounts'
LOCATIONS_URL = 'https://mybusinessbusinessinformation.googleapis.com/v1/{account}/locations'
REVIEWS_URL = 'https://mybusiness.googleapis.com/v4/{account}/{location}/reviews'
STARS = {'ONE': 1, 'TWO': 2, 'THREE': 3, 'FOUR': 4, 'FIVE': 5}
TIMEOUT = 30


def authorize_url(client_id, redirect_uri, state):
    return AUTH_URL + '?' + urlencode({
        'client_id': client_id, 'redirect_uri': redirect_uri, 'response_type': 'code', 'scope': SCOPE,
        'access_type': 'offline', 'prompt': 'consent', 'include_granted_scopes': 'true', 'state': state})


def _post_token(data):
    resp = requests.post(TOKEN_URL, data=data, timeout=TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(f"Google sign-in failed: {resp.status_code} {resp.text[:300]}")
    return resp.json()


def exchange_code(client_id, client_secret, code, redirect_uri):
    return _post_token({'code': code, 'client_id': client_id, 'client_secret': client_secret,
                        'redirect_uri': redirect_uri, 'grant_type': 'authorization_code'})


def refresh_access_token(client_id, client_secret, refresh_token):
    return _post_token({'refresh_token': refresh_token, 'client_id': client_id, 'client_secret': client_secret,
                        'grant_type': 'refresh_token'})['access_token']


def _get(url, token, params=None):
    resp = requests.get(url, headers={'Authorization': f'Bearer {token}'}, params=params or {}, timeout=TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(f"Google API {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def list_locations(token):
    """[{account, location, title}] the signed-in user manages."""
    result = []
    for account in _get(ACCOUNTS_URL, token).get('accounts', []):
        page = None
        while True:
            data = _get(LOCATIONS_URL.format(account=account['name']), token,
                        {'readMask': 'name,title', 'pageSize': 100, **({'pageToken': page} if page else {})})
            result += [{'account': account['name'], 'location': loc['name'], 'title': loc.get('title', '')}
                       for loc in data.get('locations', [])]
            page = data.get('nextPageToken')
            if not page:
                break
    return result


def parse_review(item):
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
    }


def fetch_reviews(token, account, location):
    """Every review of the location: {'reviews': [...], 'average', 'total'}."""
    reviews, average, total, page = [], 0.0, 0, None
    while True:
        data = _get(REVIEWS_URL.format(account=account, location=location), token,
                    {'pageSize': 50, **({'pageToken': page} if page else {})})
        reviews += [parse_review(r) for r in data.get('reviews', [])]
        average = data.get('averageRating', average)
        total = data.get('totalReviewCount', total)
        page = data.get('nextPageToken')
        if not page:
            break
    return {'reviews': reviews, 'average': average, 'total': total}
