"""Single sign-on tickets: a linked site asks for one (site.link.api.sso_ticket) for one of this site's users, sends
that user to /site_link/sso/<token>, and the user is signed in here. Only the token's hash is kept; a ticket works
once, within SSO_TTL seconds, for an active internal user in the group "Site Link: single sign-on allowed", never for
user ids 1 and 2 (superuser and admin)."""
import hashlib
import secrets
from datetime import timedelta

from odoo import fields, models

SSO_TTL = 60
SSO_BLOCKED_UIDS = (1, 2)
SSO_GROUP = 'site_link_connector.group_site_link_sso'


def sso_hash(token):
    return hashlib.sha256((token or '').encode()).hexdigest()


class SiteLinkSsoTicket(models.Model):
    _name = 'site.link.sso.ticket'
    _description = 'Linked site: single sign-on ticket'
    _order = 'id desc'
    _rec_name = 'user_id'

    token_hash = fields.Char(required=True, readonly=True, index=True)
    user_id = fields.Many2one('res.users', required=True, readonly=True, ondelete='cascade')
    expires_at = fields.Datetime(required=True, readonly=True)
    used_at = fields.Datetime(readonly=True)

    _token_hash_uniq = models.Constraint('UNIQUE(token_hash)', "A single sign-on token is used once.")

    def _site_link_sso_refusal(self, user):
        """Why ``user`` may not sign in by single sign-on (None: it may)."""
        _ = self.env._
        if not user:
            return _("no such user")
        user = user.sudo()
        if user.id in SSO_BLOCKED_UIDS:
            return _("user id %s (superuser or admin) never signs in by single sign-on", user.id)
        if not user.active:
            return _("user %s is archived", user.login)
        if user.share or not user._is_internal():
            return _("user %s is not an internal user", user.login)
        if not user.has_group(SSO_GROUP):
            return _("user %s is not in the group \"Site Link: single sign-on allowed\"", user.login)
        return None

    def _site_link_issue(self, user):
        """A new ticket for ``user`` (checked by the caller): the token (shown once, never kept)."""
        token = secrets.token_urlsafe(32)
        self.sudo().create({
            'token_hash': sso_hash(token),
            'user_id': user.id,
            'expires_at': fields.Datetime.now() + timedelta(seconds=SSO_TTL),
        })
        return token

    def _site_link_redeem(self, token):
        """Use the ticket of ``token``: (user, 200, None) when it signs in, else (user or None, status, reason): 410 for a
        link used or expired, 403 for anything else.
        The ticket is spent by one UPDATE ... WHERE used_at IS NULL: two requests with one token never both pass."""
        _ = self.env._
        if not token or len(token) > 200:
            return None, 403, _("no such link")
        self.env.cr.execute("""
            UPDATE site_link_sso_ticket SET used_at = now() at time zone 'UTC', write_date = now() at time zone 'UTC'
             WHERE token_hash = %s AND used_at IS NULL
         RETURNING id
        """, (sso_hash(token),))
        row = self.env.cr.fetchone()
        Ticket = self.sudo().with_context(active_test=False)
        if not row:
            Ticket.invalidate_model()
            used = Ticket.search([('token_hash', '=', sso_hash(token))], limit=1)
            return (used.user_id, 410, _("link already used")) if used else (None, 403, _("no such link"))
        ticket = Ticket.browse(row[0])
        ticket.invalidate_recordset()
        if ticket.expires_at < fields.Datetime.now():
            return ticket.user_id, 410, _("link expired (valid %s seconds)", SSO_TTL)
        refusal = self._site_link_sso_refusal(ticket.user_id)
        return ticket.user_id, 403 if refusal else 200, refusal
