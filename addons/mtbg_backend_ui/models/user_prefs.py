"""Each user's screen choices, kept on the server (owner, 2026-11-09: "the filter for column selection should be
permanent across sessions"): which optional columns a list shows, a fold left open or closed. Browser storage is lost
on another browser or device, a cleared cache or a private window; these follow the user everywhere.

One row per user and key; the value is any JSON. The admin loads them all with the session (``session_info``:
``mtbg_user_prefs``); static/src/user_prefs saves a change as it is made. A user reads and writes only their own."""
from odoo import api, fields, models

MAX_KEY = 512
MAX_PREFS = 2000  # per user: a runaway caller can't grow the session without end


class MtbgUserPref(models.Model):
    _name = 'mtbg.user.pref'
    _description = "A user's screen choice"
    _rec_name = 'key'

    user_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True,
                              default=lambda self: self.env.user)
    key = fields.Char(required=True)
    value = fields.Json()

    _user_key = models.Constraint('UNIQUE(user_id, key)', "One value per user and key.")

    @api.model
    def _mtbg_prefs(self):
        """{key: value} of the current user's choices."""
        rows = self.sudo().search_read([('user_id', '=', self.env.uid)], ['key', 'value'], limit=MAX_PREFS)
        return {row['key']: row['value'] for row in rows}

    @api.model
    def mtbg_set_pref(self, key, value):
        """The current user's choice ``key`` set to ``value`` (None: forgotten)."""
        key = (key or '')[:MAX_KEY]
        if not key or self.env.user._is_public():
            return False
        Pref = self.sudo()
        row = Pref.search([('user_id', '=', self.env.uid), ('key', '=', key)], limit=1)
        if value is None:
            row.unlink()
        elif row:
            row.value = value
        elif Pref.search_count([('user_id', '=', self.env.uid)]) < MAX_PREFS:
            Pref.create({'user_id': self.env.uid, 'key': key, 'value': value})
        return True
