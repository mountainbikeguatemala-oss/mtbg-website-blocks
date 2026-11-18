"""Single sign-on, both ends.

* ``/site_link/sso/<token>`` (the site that gives the ticket): the one-time sign-in link a linked site asked for
  (site.link.api.sso_ticket). A good link signs its user in and opens ``redirect`` (a path of this site) or /odoo; any
  other (used, expired, unknown, user no longer allowed) opens the login page. Every sign-in, done or refused, is in
  the site link's log.
* ``/site_link/sso/start?return=<url>`` (the site with the staff accounts): the employee, signed in here (the login
  page first when not), is sent to ``return`` signed in there. ``return`` must be on the address of a linked site;
  that site gives the ticket for this user's login.
* ``/web/login`` (the site that gives the ticket): a "Log in with your staff account" button when a linked site has
  the role Staff accounts."""
from urllib.parse import quote, urlencode, urlparse

from odoo import http
from odoo.http import request

from odoo.addons.web.controllers.home import Home

from ..models.site_link import SiteLinkError


def local_path(path):
    """``path`` when it is a path of this site (not //host, not a full address), else None."""
    if not isinstance(path, str) or not path.startswith('/') or path.startswith(('//', '/\\')):
        return None
    parsed = urlparse(path)
    if parsed.scheme or parsed.netloc or any(c in path for c in '\r\n\t'):
        return None
    return path


def same_site(url, base_url):
    """True when ``url`` is an http(s) address on the host (and port) of ``base_url``, without user info."""
    try:
        target, base = urlparse(url), urlparse((base_url or '').strip())
    except ValueError:
        return False
    return (target.scheme in ('http', 'https') and target.scheme == base.scheme and not target.username
            and not target.password and bool(target.hostname) and target.hostname == base.hostname
            and target.port == base.port and '\\' not in url)


class SiteLinkSso(http.Controller):

    @http.route('/site_link/sso/<string:token>', type='http', auth='public', methods=['GET'], readonly=False,
                sitemap=False)
    def site_link_sso(self, token, redirect=None, **kwargs):
        env = request.env
        user, status, refusal = env['site.link.sso.ticket'].sudo()._site_link_redeem(token)
        Log = env['site.link.log'].sudo()
        if refusal:
            Log._site_link_event('sso', 'sso_login', env._("Sign-in refused: %s", refusal), status=status,
                                 user=user or None, model='/site_link/sso')
            return request.redirect('/web/login', local=True)
        user = user.sudo()
        if request.session.uid:
            request.session.logout(keep_db=True)
        request.session['pre_login'] = user.login
        request.session['pre_uid'] = user.id
        request.session.finalize(env)
        request.env = env(user=user.id, su=False)
        env['res.users'].with_user(user)._update_last_login()
        Log._site_link_event('sso', 'sso_login', env._("Signed in %s by single sign-on.", user.login),
                             user=user, model='/site_link/sso')
        return request.redirect(local_path(redirect) or '/odoo', local=True)

    @http.route('/site_link/sso/start', type='http', auth='public', methods=['GET'], readonly=False, sitemap=False)
    def site_link_sso_start(self, **kwargs):
        env = request.env
        target = kwargs.get('return') or ''
        Site = env['site.link'].sudo()
        site = Site.search([]).filtered(lambda s: s.api_key and same_site(target, s.base_url))[:1]
        if not site:
            env['site.link.log'].sudo()._site_link_event(
                'sso', 'sso_start', env._("Refused: %s is not the address of a linked site.", target[:300]),
                status=403, model='/site_link/sso/start')
            return request.make_response(env._("This sign-in link does not lead to a linked site."),
                                         [('Content-Type', 'text/plain; charset=utf-8')], status=403)
        user = env.user
        if not request.session.uid or user._is_public():
            back = '/site_link/sso/start?' + urlencode({'return': target})
            return request.redirect('/web/login?' + urlencode({'redirect': back}), local=True)
        if user.share:
            return request.make_response(env._("Only staff accounts sign in on the linked site."),
                                         [('Content-Type', 'text/plain; charset=utf-8')], status=403)
        try:
            ticket_url = Site._site_link_sso_url(user.login, site=site)
        except SiteLinkError as exc:
            return request.make_response(env._("The linked site could not sign you in: %s", exc.args[0]),
                                         [('Content-Type', 'text/plain; charset=utf-8')], status=502)
        parsed = urlparse(target)
        path = parsed.path or '/odoo'
        if parsed.query:
            path += '?' + parsed.query
        if local_path(path) and path not in ('/', '/web/login') and not path.startswith('/web/login?'):
            ticket_url += '?' + urlencode({'redirect': path})
        return request.redirect(ticket_url, local=False)


class SiteLinkLogin(Home):

    @http.route()
    def web_login(self, redirect=None, **kw):
        response = super().web_login(redirect=redirect, **kw)
        if getattr(response, 'is_qweb', False) and request.db:
            site = request.env['site.link'].sudo().search([('role', '=', 'staff_source')], limit=1)
            if site and (site.base_url or '').strip().startswith(('http://', 'https://')):
                back = request.httprequest.url_root.rstrip('/') + (local_path(redirect) or '/odoo')
                response.qcontext['site_link_staff_login_url'] = (
                    site.base_url.strip().rstrip('/') + '/site_link/sso/start?return=' + quote(back, safe=''))
        return response
