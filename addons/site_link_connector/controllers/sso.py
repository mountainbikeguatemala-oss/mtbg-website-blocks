"""Single sign-on, both ends.

* ``/site_link/sso/<token>`` (the site that gives the ticket): the one-time sign-in link a linked site asked for
  (site.link.api.sso_ticket). A good link signs its user in and opens ``return`` (``redirect``, its older name): a
  path of this site, or a full address on this site's own host, else /odoo; any other link (used, expired, unknown,
  user no longer allowed) opens the login page. Every sign-in, done or refused, is in the site link's log, and so is
  a return address refused.
* ``/site_link/sso/start?return=<url>`` (the site with the staff accounts, or either site of a switch between their
  apps): the employee, signed in here (the login page first when not), is sent to ``return`` signed in there.
  ``return`` must be on the address of a linked site with an API key; that site gives the ticket for this user's
  login. ``fallback=1``: when it gives none (no such user there, an administrator, not allowed), ``return`` opens as
  it is instead of an error page (logged).
* ``/web/login`` (the site that gives the ticket): a "Log in with your staff account" button when a linked site has
  the role Staff accounts."""
from urllib.parse import quote, urlencode, urlparse

from odoo import http
from odoo.http import request

from odoo.addons.web.controllers.home import Home

from ..models.site_link import SiteLinkError, is_local_path


def local_path(path):
    """``path`` when it is a path of this site (not //host, not a full address), else None."""
    return path if is_local_path(path) else None


def same_site(url, base_url):
    """True when ``url`` is an http(s) address on the host (and port) of ``base_url``, without user info."""
    try:
        target, base = urlparse(url), urlparse((base_url or '').strip())
        return (target.scheme in ('http', 'https') and target.scheme == base.scheme and not target.username
                and not target.password and bool(target.hostname) and target.hostname == base.hostname
                and target.port == base.port and '\\' not in url)
    except ValueError:  # (a port that is not a number: "host:8069.evil.example.com")
        return False


def own_path(target, host_url):
    """The path (and query) to open after a sign-in: ``target`` when it is a path of this site, or the path of a full
    address on this site's own host (``host_url``: scheme, host and port of the request); None for anything else."""
    if not isinstance(target, str) or not target:
        return None
    if target.startswith('/'):
        return local_path(target)
    if not same_site(target, host_url):
        return None
    parsed = urlparse(target)
    path = (parsed.path or '/') + ('?' + parsed.query if parsed.query else '')
    return local_path(path)


class SiteLinkSso(http.Controller):

    @http.route('/site_link/sso/<string:token>', type='http', auth='public', methods=['GET'], readonly=False,
                sitemap=False)
    def site_link_sso(self, token, redirect=None, **kwargs):
        env = request.env
        target = kwargs.get('return') or redirect
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
        path = own_path(target, request.httprequest.host_url)
        if target and not path:
            Log._site_link_event('sso', 'sso_login',
                                 env._("Return address refused (not this site's): %s; opened /odoo.", target[:300]),
                                 status=400, user=user, model='/site_link/sso')
        return request.redirect(path or '/odoo', local=True)

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
            back = '/site_link/sso/start?' + urlencode({'return': target, **({'fallback': '1'} if
                                                                                kwargs.get('fallback') == '1' else {})})
            return request.redirect('/web/login?' + urlencode({'redirect': back}), local=True)
        if user.share:
            return request.make_response(env._("Only staff accounts sign in on the linked site."),
                                         [('Content-Type', 'text/plain; charset=utf-8')], status=403)
        parsed = urlparse(target)
        path = parsed.path or '/odoo'
        if parsed.query:
            path += '?' + parsed.query
        if not local_path(path) or path in ('/', '/web/login') or path.startswith('/web/login?'):
            path = None
        try:
            ticket_url = Site._site_link_sso_url(user.login, site=site, return_path=path)
        except SiteLinkError as exc:
            if kwargs.get('fallback') == '1':
                # (a switch between the two sites' apps: the page itself, signed in there when the browser is)
                env['site.link.log'].sudo()._site_link_event(
                    'sso', 'sso_start', env._("No sign-in for %(login)s (%(why)s): opened %(to)s as it is.",
                                              login=user.login, why=exc.args[0][:500], to=target[:300]),
                    status=exc.status or 502, user=user, model='/site_link/sso/start')
                return request.redirect(target, local=False)
            return request.make_response(env._("The linked site could not sign you in: %s", exc.args[0]),
                                         [('Content-Type', 'text/plain; charset=utf-8')], status=502)
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
