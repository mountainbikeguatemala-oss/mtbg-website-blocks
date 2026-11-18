"""The site link's log, kept 90 days, admins only:

* failed calls this site made to a linked site (calls that worked are not logged);
* calls this site answered for a linked site (the customer and repair methods);
* single sign-on: every ticket asked for (given or refused) and every sign-in (done or refused)."""
from datetime import timedelta

from odoo import api, fields, models
from odoo.modules import module as odoo_module

KEEP_DAYS = 90
KINDS = [
    ('failed', 'Failed call'),
    ('served', 'Call answered'),
    ('sso', 'Single sign-on'),
]


class SiteLinkLog(models.Model):
    _name = 'site.link.log'
    _description = 'Linked site: log'
    _order = 'id desc'

    kind = fields.Selection(KINDS, required=True, default='failed', index=True, readonly=True)
    site_id = fields.Many2one('site.link', string='Site', index=True, ondelete='cascade', readonly=True)
    model = fields.Char(readonly=True)
    method = fields.Char(readonly=True)
    status = fields.Integer(string='HTTP Status', readonly=True,
                            help="Failed calls: the other site's answer (0: no answer: unreachable, time limit, setup). "
                                 "Calls answered and sign-ins: 200 done, 403 refused, 410 link used or expired.")
    user_id = fields.Many2one('res.users', string='User', ondelete='set null', readonly=True,
                              help="Single sign-on: the user the ticket or sign-in was for.")
    message = fields.Text(readonly=True)
    duration_ms = fields.Integer(string='Duration (ms)', readonly=True)

    @api.model
    def _site_link_event(self, kind, method, message, status=200, user=None, own_cursor=False, model='site.link.api'):
        """One log row for something this site answered or did. ``own_cursor``: written through a cursor of its own,
        so it stays when the caller's transaction rolls back (a refusal raises); in tests it goes with the test's
        transaction instead."""
        vals = {'kind': kind, 'model': model, 'method': method, 'status': status,
                'message': (message or '')[:2000], 'user_id': user.id if user else False}
        if own_cursor and not odoo_module.current_test:
            try:
                with self.env.registry.cursor() as cr:
                    env = api.Environment(cr, self.env.uid, self.env.context)
                    if vals['user_id'] and not env['res.users'].sudo().browse(vals['user_id']).exists():
                        vals['user_id'] = False
                    env['site.link.log'].sudo().create(vals)
                return
            except Exception:  # noqa: BLE001 - the log must never hide the answer itself
                pass
        with self.env.cr.savepoint():
            self.sudo().create(vals)

    @api.model
    def _site_link_cleanup(self):
        """Cron: the log keeps its last KEEP_DAYS days; single sign-on tickets go after a day."""
        self.sudo().search([('create_date', '<', fields.Datetime.now() - timedelta(days=KEEP_DAYS))]).unlink()
        self.env['site.link.sso.ticket'].sudo().search(
            [('create_date', '<', fields.Datetime.now() - timedelta(days=1))]).unlink()
