import json

from odoo import http
from odoo.http import request



def _request_country_code():
    """The visitor's country: Cloudflare's header on the live site, else Odoo's geo IP (as Forms reads it)."""
    if not request:
        return ''
    code = (request.httprequest.headers.get('CF-IPCountry') or '').upper()
    if len(code) == 2 and code not in ('XX', 'T1'):
        return code
    geo = getattr(request, 'geoip', None) or {}
    code = (geo.get('country_code') if hasattr(geo, 'get') else getattr(geo, 'country_code', None)) or ''
    return code.upper()


class MtbgEdgeSession(http.Controller):

    @http.route('/mtbg/session', type='http', auth='public', methods=['GET'], website=True, sitemap=False)
    def session(self, **kw):
        """A cached page's session: its form token, and the visitor's country for the phone field. Never cached."""
        request.session['mtbg_session'] = True  # (kept: the token belongs to it, and the visit beacon uses it)
        body = json.dumps({'csrf_token': request.csrf_token(), 'country': _request_country_code() or None})
        return request.make_response(body, headers=[('Content-Type', 'application/json'),
                                                    ('Cache-Control', 'no-store')])
