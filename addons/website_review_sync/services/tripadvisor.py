"""Tripadvisor Content API: the listing's latest reviews (the API returns the 5 most recent per language), and
its rating and review count. Synced regularly, the local table keeps every review seen."""
import datetime

import requests

BASE = 'https://api.content.tripadvisor.com/api/v1/location/{location}'
TIMEOUT = 30


def _get(url, params):
    # the key is bound to the site's domain in Tripadvisor's console: send it as the referer
    resp = requests.get(url, params=params, headers={'accept': 'application/json'}, timeout=TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(f"Tripadvisor API {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def parse_review(item, lang):
    user = item.get('user') or {}
    avatar = (user.get('avatar') or {})
    when = (item.get('published_date') or '')[:10]
    location = (user.get('user_location') or {}).get('name')
    return {
        'external_id': str(item['id']),
        'author_name': user.get('username') or 'Tripadvisor traveller',
        'author_photo_url': avatar.get('small') or avatar.get('thumbnail') or False,
        'author_location': location or False,
        'rating': int(item.get('rating') or 5),
        'title': item.get('title') or False,
        'text': item.get('text') or '',
        'language': item.get('lang') or lang,
        'review_date': datetime.date.fromisoformat(when) if when else False,
        'trip_date': item.get('travel_date') or False,
        'url': item.get('url') or False,
        'reply_text': ((item.get('owner_response') or {}).get('text')) or False,
    }


def fetch_reviews(key, location, languages=('en',)):
    reviews = {}
    for lang in languages:
        data = _get(BASE.format(location=location) + '/reviews', {'key': key, 'language': lang})
        for item in data.get('data', []):
            reviews.setdefault(str(item['id']), parse_review(item, lang))
    details = _get(BASE.format(location=location) + '/details', {'key': key, 'language': languages[0]})
    return {'reviews': list(reviews.values()),
            'average': float(details.get('rating') or 0), 'total': int(details.get('num_reviews') or 0)}
