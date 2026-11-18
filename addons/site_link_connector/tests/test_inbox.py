"""inbox_unread: soft (offered only with Communication Flows' side panel), the waiting count for a login."""
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestSiteLinkInbox(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.link_user = new_test_user(cls.env, 'slc_inbox_link', groups='base.group_user,'
                                      'site_link_connector.group_site_link_remote')
        cls.plain_user = new_test_user(cls.env, 'slc_inbox_plain', groups='base.group_user')
        cls.seller = new_test_user(cls.env, 'slc_inbox_seller@example.com', groups='base.group_user')
        cls.Api = cls.env['site.link.api'].with_user(cls.link_user)

    def test_soft(self):
        has_inbox = self.Api._site_link_has_inbox()
        self.assertEqual('inbox_unread' in self.Api.health()['methods'], has_inbox)
        if not has_inbox:
            with self.assertRaises(UserError):
                self.Api.inbox_unread('slc_inbox_seller@example.com')

    def test_count(self):
        if not self.Api._site_link_has_inbox():
            self.skipTest("no shared inbox (Communication Flows' side panel) on this database")
        Conversation = type(self.env['omni.conversation'])
        asked = []

        def count(self_, user):
            asked.append(user)
            return 3
        with patch.object(Conversation, '_cfd_popup_waiting_count', count):
            self.assertEqual(self.Api.inbox_unread(' SLC_INBOX_SELLER@example.com '), {'count': 3, 'enabled': True})
            self.assertEqual(asked[-1], self.seller, "the login, case does not matter")
            self.Api.inbox_unread('nobody@example.com')
            self.assertFalse(asked[-1], "an unknown login: nobody's count")
        with patch.object(Conversation, '_cfd_popup_waiting_count', lambda self_, user: None):
            self.assertEqual(self.Api.inbox_unread('slc_inbox_seller@example.com'), {'count': 0, 'enabled': False})
        with self.assertRaises(UserError):
            self.Api.inbox_unread('')
        with self.assertRaises(AccessError):
            self.env['site.link.api'].with_user(self.plain_user).inbox_unread('slc_inbox_seller@example.com')
