"""Reply status on the pipeline (0.6.0): the filters, the order (waiting on us first, the oldest wait first), the
label, the Alert Feed rules and the contact page's badge. The status is stored by the Communication Flow Designer
(its own tests); here it is set on the columns directly, so these run without it. Nothing is ever sent."""
from datetime import timedelta
from types import SimpleNamespace

from lxml import etree

from odoo import fields
from odoo.tests import HttpCase, TransactionCase, tagged



def set_status(partner, status, since, preview=None):
    rank = {'waiting_us': 1, 'follow_up': 2, 'waiting_them': 3}.get(status)
    partner.env.flush_all()
    partner.env.cr.execute(
        "UPDATE res_partner SET cfd_reply_status = %s, cfd_reply_since = %s, cfd_reply_rank = %s, "
        "cfd_reply_preview = %s WHERE id = %s", [status, since, rank, preview, partner.id])
    partner.invalidate_recordset()


@tagged('post_install', '-at_install')
class TestReplyStatusPipeline(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Partner = cls.env['res.partner']
        now = fields.Datetime.now()
        cls.now = now
        cls.waiting_old = Partner.create({'name': 'Reply Waiting Old', 'mtbg_contact_type': 'lead'})
        cls.waiting_new = Partner.create({'name': 'Reply Waiting New', 'mtbg_contact_type': 'lead'})
        cls.follow = Partner.create({'name': 'Reply Follow Up', 'mtbg_contact_type': 'lead'})
        cls.them = Partner.create({'name': 'Reply Waiting Them', 'mtbg_contact_type': 'lead'})
        cls.quiet = Partner.create({'name': 'Reply None', 'mtbg_contact_type': 'lead'})
        cls.client = Partner.create({'name': 'Reply Client Waiting', 'mtbg_contact_type': 'client'})
        set_status(cls.waiting_old, 'waiting_us', now - timedelta(days=8), "We would like an e bike coffee tour")
        set_status(cls.waiting_new, 'waiting_us', now - timedelta(minutes=30), "Is there space tomorrow?")
        set_status(cls.follow, 'follow_up', now - timedelta(days=9))
        set_status(cls.them, 'waiting_them', now - timedelta(days=2))
        set_status(cls.client, 'waiting_us', now - timedelta(days=1))
        cls.ours = cls.waiting_old | cls.waiting_new | cls.follow | cls.them | cls.quiet | cls.client

    def filter_domain(self, name):
        arch = self.env['res.partner'].get_view(view_type='search')['arch']
        node = etree.fromstring(arch).xpath("//filter[@name='%s']" % name)
        self.assertTrue(node, name)
        return eval(node[0].get('domain'))  # noqa: S307 - the view's own literal domain

    def test_filters(self):
        Partner = self.env['res.partner']
        mine = [('id', 'in', self.ours.ids)]
        self.assertEqual(Partner.search(mine + self.filter_domain('mtbg_reply_waiting_us')),
                         self.waiting_old | self.waiting_new | self.client)
        self.assertEqual(Partner.search(mine + self.filter_domain('mtbg_reply_follow_up')), self.follow)
        self.assertEqual(Partner.search(mine + self.filter_domain('mtbg_reply_waiting_them')), self.them)

    def test_order_waiting_on_us_first_oldest_first(self):
        list_view = self.env.ref('mtbg_tours_crm_rules.view_partner_pipeline_list')
        order = etree.fromstring(list_view.arch).get('default_order')
        self.assertTrue(order.startswith('cfd_reply_rank, cfd_reply_since'))
        leads = self.env['res.partner'].search([('id', 'in', self.ours.ids), ('mtbg_contact_type', '=', 'lead')],
                                               order=order)
        self.assertEqual(leads.mapped('name'), ['Reply Waiting Old', 'Reply Waiting New', 'Reply Follow Up',
                                                'Reply Waiting Them', 'Reply None'])
        kanban = etree.fromstring(self.env.ref('mtbg_tours_crm_rules.view_partner_pipeline_kanban').arch)
        self.assertEqual(kanban.get('default_order'), order)

    def test_label(self):
        self.assertEqual(self.waiting_old.mtbg_reply_label, "Waiting on us · 8 d")
        self.assertEqual(self.waiting_new.mtbg_reply_label, "Waiting on us · 30 min")
        self.assertEqual(self.follow.mtbg_reply_label, "Follow up · 9 d")
        self.assertEqual(self.them.mtbg_reply_label, "Waiting on them · 2 d")
        self.assertFalse(self.quiet.mtbg_reply_label)

    def test_alert_sources(self):
        Partner = self.env['res.partner']
        if 'mtbg.alert.rule' in self.env:  # the Alert Feed (Tours) asks for the sources
            codes = {spec['code'] for spec in Partner._mtbg_alert_sources()}
            self.assertTrue({'crm_leads_waiting_us', 'crm_leads_follow_up'} <= codes)
        rule = SimpleNamespace(days=1)
        alerts = Partner._mtbg_alerts_leads_waiting_us(rule, self.now.date())
        self.assertEqual(len(alerts), 1)
        ids = set(alerts[0]['action']['domain'][0][2])
        self.assertIn(self.waiting_old.id, ids)
        self.assertNotIn(self.waiting_new.id, ids, "waiting less than the rule's hours")
        self.assertNotIn(self.client.id, ids, "leads only")
        self.assertIn("Reply Waiting Old (8 d): We would like an e bike coffee tour", alerts[0]['detail'])
        follow = Partner._mtbg_alerts_leads_follow_up(rule, self.now.date())
        self.assertIn(self.follow.id, follow[0]['action']['domain'][0][2])
        self.assertNotIn(self.them.id, follow[0]['action']['domain'][0][2])


@tagged('post_install', '-at_install')
class TestReplyStatusBadge(HttpCase):
    """The contact page's badge renders, red with the wait and what they asked."""

    def test_badge_renders(self):
        partner = self.env['res.partner'].create({'name': 'Brandon Badge', 'mtbg_contact_type': 'lead'})
        set_status(partner, 'waiting_us', fields.Datetime.now() - timedelta(days=8),
                   "We would like an e bike coffee tour in Antigua")
        check = """
let n = 0;
const timer = setInterval(() => {
    const box = document.querySelector('.o_mtbg_reply_status:not(.d-none) .o_mtbg_reply_badge .text-bg-danger');
    const text = box ? box.closest('.o_mtbg_reply_status').textContent : '';
    if (text.includes('Waiting on us · 8 d') && text.includes('e bike coffee tour')) {
        clearInterval(timer); console.log('test successful');
    } else if (++n > 150) {
        clearInterval(timer); console.error('badge not shown: ' + text);
    }
}, 100);
"""
        self.browser_js('/odoo/res.partner/%s' % partner.id, check, "odoo.isReady", login='admin')
