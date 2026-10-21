"""Import a reviews export (``reviews.json`` with ``listing`` + ``reviews``, and its ``photos/`` folder) into a
review source: Google (username, reviewer_profile, avatar, rating, text, date_approx, owner_response, photo_files)
or Tripadvisor (username, profile, reviewer_meta, rating, title, review_url, trip_date, date, text,
owner_response, photo_files). Photos become public attachments.

Idempotent: the key is the reviewer's Google contributor id, or the Tripadvisor review id (the API's id too, so
later Content API syncs update these reviews rather than adding them again).

    >>> from odoo.addons.website_review_sync.services.export_import import import_google_export, import_tripadvisor_export
    >>> import_google_export(env, '/path/listing_folder', source)
"""
import base64
import datetime
import json
import mimetypes
import os
import re

CONTRIB_RE = re.compile(r'/contrib/(\d+)')
# a few very common Spanish words: enough to tell a Spanish review from an English one
SPANISH_RE = re.compile(r'\b(que|muy|una|para|con|los|las|del|excelente|gracias|recomiendo|experiencia)\b', re.I)
ENGLISH_RE = re.compile(r'\b(the|and|was|very|great|with|we|our|for)\b', re.I)


def _language(text):
    if not text:
        return False
    return 'es' if len(SPANISH_RE.findall(text)) > len(ENGLISH_RE.findall(text)) else 'en'


def _avatar(url):
    """Google sends a 36px avatar: ask for an 88px one (sharp on the card)."""
    return re.sub(r'=w\d+-h\d+', '=w88-h88', url) if url else False


TA_REVIEW_RE = re.compile(r'-r(\d+)-')
CONTRIBUTIONS_RE = re.compile(r'\s*\d[\d,.]*\s+contributions?\s*$', re.I)


def _load(folder):
    with open(os.path.join(folder, 'reviews.json'), encoding='utf-8') as fh:
        return json.load(fh)


def _google_vals(row):
    m = CONTRIB_RE.search(row.get('reviewer_profile') or '')
    text = (row.get('text') or '').strip()
    return {
        'external_id': m.group(1) if m else f"{row.get('username')}:{row.get('date_approx')}",
        'platform': 'google', 'author_name': row.get('username') or 'Google user',
        'author_photo_url': _avatar(row.get('avatar')), 'author_url': row.get('reviewer_profile') or False,
        'rating': int(row.get('rating') or 5), 'text': text, 'language': _language(text),
        'reply_text': (row.get('owner_response') or {}).get('text') or False,
        'review_date': datetime.date.fromisoformat(row['date_approx']) if row.get('date_approx') else False,
        'date_approx': bool(row.get('date_approx')),
    }


def _tripadvisor_vals(row):
    m = TA_REVIEW_RE.search(row.get('review_url') or '')
    text = (row.get('text') or '').strip()
    # "San Francisco, California650 contributions" -> "San Francisco, California"
    place = CONTRIBUTIONS_RE.sub('', row.get('reviewer_meta') or '').strip() or False
    if place and re.fullmatch(r'[\d,.]+\s*contributions?', place, re.I):
        place = False
    return {
        'external_id': m.group(1) if m else f"{row.get('username')}:{row.get('date')}",
        'platform': 'tripadvisor', 'author_name': row.get('username') or 'Tripadvisor traveller',
        'author_url': row.get('profile') or False, 'author_location': place, 'rating': int(row.get('rating') or 5),
        'title': row.get('title') or False, 'text': text, 'language': _language(text),
        'url': row.get('review_url') or False, 'trip_date': (row.get('trip_date') or '').strip() or False,
        'reply_text': (row.get('owner_response') or {}).get('text') or False,
        'review_date': datetime.date.fromisoformat(row['date']) if row.get('date') else False,
    }


def import_google_export(env, folder, source):
    return _import(env, folder, source, _google_vals)


def import_tripadvisor_export(env, folder, source):
    return _import(env, folder, source, _tripadvisor_vals)


def _import(env, folder, source, to_vals):
    data = _load(folder)
    listing = data.get('listing', {})
    Review, Att = env['review.review'].sudo(), env['ir.attachment'].sudo()
    existing = {r.external_id: r for r in Review.search([('source_id', '=', source.id)])}
    created = updated = photos = 0
    for row in data['reviews']:
        vals = dict(to_vals(row), source_id=source.id)
        key = vals['external_id']
        rec = existing.get(key)
        if rec:
            rec.write(vals)
            updated += 1
        else:
            # the business reviewing itself, or a low rating: kept, but not on the website until checked
            own = (row.get('username') or '').strip().lower() == (listing.get('name') or '').strip().lower()
            vals['is_published'] = not own and vals['rating'] >= (source.auto_publish_rating or 0)
            rec = Review.create(vals)
            existing[key] = rec
            created += 1
        if not rec.image_ids:
            atts = Att.browse()
            for rel in row.get('photo_files') or []:
                path = os.path.join(folder, rel)
                if not os.path.isfile(path):
                    continue
                with open(path, 'rb') as fh:
                    atts |= Att.create({'name': os.path.basename(path), 'datas': base64.b64encode(fh.read()),
                                        'mimetype': mimetypes.guess_type(path)[0] or 'image/jpeg', 'public': True,
                                        'res_model': 'review.review', 'res_id': rec.id})
            if atts:
                rec.image_ids = [(6, 0, atts.ids)]
                photos += len(atts)
    source.sudo().write({'rating_average': listing.get('average_rating') or source.rating_average,
                         'rating_count': listing.get('review_count') or len(data['reviews'])})
    return {'created': created, 'updated': updated, 'photos': photos}
