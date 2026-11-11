"""Zoho Books vendors by name (owner, 2026-11-08: "expenses created in odoo and sent to zoho books have no vendor").

An expense names where it was bought (a vendor record, or the vendor's name on a unit expense). Its Zoho Books vendor is
found by that name, spelling-insensitive (accents, case and spaces aside); when Zoho Books has none, it is created
there (only while Books writes are on: the request refuses otherwise). One lookup per name per run."""
import re
import unicodedata


def vendor_key(name):
    """A name to compare: no accents, lower case, letters and digits with single spaces."""
    text = unicodedata.normalize('NFKD', name or '')
    text = ''.join(c for c in text if not unicodedata.combining(c)).lower()
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', text).split())


def find_or_create_vendor(books, name, cache=None, create=True):
    """The Zoho Books vendor contact id for ``name`` (made when missing and ``create``), or False for no name."""
    name = ' '.join((name or '').split())
    key = vendor_key(name)
    if not key:
        return False
    if cache is not None and key in cache:
        return cache[key]
    hits = books.request('GET', 'contacts', params={'contact_type': 'vendor', 'contact_name_contains': name,
                                                    'filter_by': 'Status.All'}).get('contacts') or []
    found = next((c for c in hits if c.get('contact_type', 'vendor') == 'vendor'
                  and vendor_key(c.get('contact_name') or c.get('vendor_name') or '') == key), None)
    contact_id = str(found['contact_id']) if found else False
    if not contact_id and create:
        made = books.request('POST', 'contacts', json={'contact_name': name, 'contact_type': 'vendor'})
        contact_id = str(made['contact']['contact_id'])
    if cache is not None:
        cache[key] = contact_id
    return contact_id
