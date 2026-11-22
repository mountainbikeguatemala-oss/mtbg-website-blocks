"""Reply status on the pipeline (0.6.0, owner 2026-11-21: "our leads are getting lost we need some way to distinguish
if we have gotten back to them, if they are waiting a response from us, or a week has passed since they got back to
us").

The status lives where the conversations live: the Communication Flow Designer (3.47.0) computes and stores it on
each contact from their messages on every channel (its ``reply_status.py``: what counts as their message and as our
reply; only messages a person of ours writes are a reply, never automated ones). This extension does not depend on
it: it declares the same stored fields (same names, same definitions) so its lists, board, filters, contact page
badge and Alert Feed rules work on any site; without the Designer the fields stay empty (no status, no alert).

* **Waiting on us** (red): their last message is newer than our last reply, with how long ("Waiting on us · 8 d").
* **Waiting on them** (blue): we answered last, less than the days ago (Settings › Communication Flows).
* **Follow up** (amber): we answered last and the days went by without a word from them.

Leads waiting on us sort first, the oldest wait first (``cfd_reply_rank, cfd_reply_since``). Nothing is ever sent.
"""
from datetime import timedelta

from odoo import api, fields, models

# the same definitions as the Communication Flow Designer's (communication_flow_designer/models/reply_status.py)
REPLY_STATUSES = [("waiting_us", "Waiting on us"), ("follow_up", "Follow up"), ("waiting_them", "Waiting on them")]


def id_list(records):
    return ",".join(map(str, sorted(records.ids)))


def wait_text(env, since, now):
    if not since:
        return ''
    seconds = max(0, int((now - since).total_seconds()))
    if seconds < 3600:
        return env._("%s min", max(1, seconds // 60))
    if seconds < 86400:
        return env._("%s h", seconds // 3600)
    return env._("%s d", seconds // 86400)


class ResPartnerReplyStatus(models.Model):
    _inherit = 'res.partner'

    # stored by the Communication Flow Designer (SQL, from the message archive); declared here too so the pipeline's
    # screens work without it
    cfd_reply_status = fields.Selection(
        REPLY_STATUSES, string="Reply Status", readonly=True, copy=False, index=True,
        help="Waiting on us: their last message is newer than our last reply. Waiting on them: we answered last. "
             "Follow up: we answered last and they have not written back for days. Empty: no conversation yet.")
    cfd_reply_since = fields.Datetime(string="Reply Status Since", readonly=True, copy=False,
                                      help="Waiting on us: when they wrote. Otherwise: when we last answered.")
    cfd_reply_rank = fields.Integer(string="Reply Order", readonly=True, copy=False, index=True,
                                    help="1 waiting on us, 2 follow up, 3 waiting on them, empty: none.")
    cfd_reply_preview = fields.Char(string="Their Last Message", readonly=True, copy=False)
    mtbg_reply_label = fields.Char(string="Reply", compute='_compute_mtbg_reply_label',
                                   help="Who has to write next, and since when.")

    @api.depends('cfd_reply_status', 'cfd_reply_since')
    def _compute_mtbg_reply_label(self):
        now = fields.Datetime.now()
        labels = dict(self._fields['cfd_reply_status']._description_selection(self.env))
        for partner in self:
            status = partner.cfd_reply_status
            partner.mtbg_reply_label = "%s · %s" % (labels[status], wait_text(self.env, partner.cfd_reply_since, now)) \
                if status and partner.cfd_reply_since else (labels.get(status) or False)

    # ------------------------------------------------------------------ Alert Feed (soft: mtbg_tours_alerts)
    def _mtbg_alert_sources(self):
        return super()._mtbg_alert_sources() + [{
            'code': 'crm_leads_waiting_us', 'name': self.env._("Leads waiting on us"), 'section': 'communications',
            'level': 'danger', 'sequence': 18, 'days': 1, 'days_label': self.env._("hours waiting at least"),
            'icon': 'fa-exclamation-circle', 'alerts': '_mtbg_alerts_leads_waiting_us',
            'description': self.env._("Leads whose last message (any channel, a website form too) is newer than our "
                                      "last reply."),
        }, {
            'code': 'crm_leads_follow_up', 'name': self.env._("Follow-ups due"), 'section': 'communications',
            'level': 'warning', 'sequence': 19, 'icon': 'fa-clock-o', 'alerts': '_mtbg_alerts_leads_follow_up',
            'description': self.env._("Leads we answered last who have not written back for the days set in "
                                      "Settings › Communication Flows (Reply status)."),
        }]

    @api.model
    def _mtbg_reply_leads(self, status, before=None):
        domain = [('cfd_reply_status', '=', status), ('mtbg_contact_type', '=', 'lead'), ('mtbg_lost', '=', False)]
        if before:
            domain.append(('cfd_reply_since', '<=', before))
        return self.sudo().search(domain, order='cfd_reply_since, id')

    def _mtbg_reply_alert(self, title, name, today):
        now = fields.Datetime.now()
        return [{
            'key': id_list(self), 'title': title,
            'detail': " · ".join("%s (%s)%s" % (p.display_name, wait_text(self.env, p.cfd_reply_since, now),
                                                 ": " + p.cfd_reply_preview[:60] if p.cfd_reply_preview else "")
                                 for p in self[:5]),
            'date': self[:1].cfd_reply_since.date() if self[:1].cfd_reply_since else today,
            'action': {'res_model': 'res.partner', 'domain': [('id', 'in', self.ids)], 'name': name},
        }]

    @api.model
    def _mtbg_alerts_leads_waiting_us(self, rule, today):
        """Leads waiting on us for at least the rule's hours, the oldest first: one alert listing them."""
        leads = self._mtbg_reply_leads('waiting_us', fields.Datetime.now() - timedelta(hours=rule.days or 0))
        if not leads:
            return []
        return leads._mtbg_reply_alert(self.env._("%s lead(s) waiting on us", len(leads)),
                                       self.env._("Leads waiting on us"), today)

    @api.model
    def _mtbg_alerts_leads_follow_up(self, rule, today):
        """Leads due a follow-up (we answered last, the days went by), the oldest first."""
        leads = self._mtbg_reply_leads('follow_up')
        if not leads:
            return []
        return leads._mtbg_reply_alert(self.env._("%s follow-up(s) due", len(leads)),
                                       self.env._("Follow-ups due"), today)


def sync_alert_sources(env):
    """The Alert Feed, when installed, gives these sources their rules (install and update)."""
    if 'mtbg.alert.rule' in env and hasattr(env['mtbg.alert.rule'], '_mtbg_sync_sources'):
        env['mtbg.alert.rule']._mtbg_sync_sources()
