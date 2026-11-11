from odoo.exceptions import AccessError
from odoo.tests import HttpCase, TransactionCase, tagged

from ..models.topbar import DEFAULT_ORDER


@tagged('post_install', '-at_install', 'mtbg')
class TestTopbar(TransactionCase):
    """The top bar icons kept for everyone (owner, 2026-10-29)."""

    def setUp(self):
        super().setUp()
        self.Topbar = self.env['mtbg.topbar']
        self.Topbar.mtbg_topbar_reset()

    def test_default(self):
        """Messaging, emails, notifications, visits, the clock, the company; the company name off."""
        settings = self.Topbar.mtbg_topbar_settings()
        self.assertEqual([i['key'] for i in settings['items']], DEFAULT_ORDER)
        self.assertEqual(DEFAULT_ORDER[:5], ['cfd_inbox', 'cfd_mailbox', 'mtbg_tours_alerts.alert_menu',
                                             'cfd_visitors_online', 'mail.activity_menu'])
        self.assertFalse(any(i['hidden'] for i in settings['items']))
        self.assertFalse(settings['company_name'])

    def test_save(self):
        """The order and the hidden ones kept; the user menu never (always last), a key once; the switch alone."""
        settings = self.Topbar.mtbg_topbar_save([
            {'key': 'mail.activity_menu'}, {'key': 'cfd_inbox', 'hidden': True}, {'key': 'web.user_menu'},
            {'key': 'mail.activity_menu'}, {'key': 'some_module.icon'}, 'junk'])
        self.assertEqual(settings['items'], [{'key': 'mail.activity_menu', 'hidden': False},
                                             {'key': 'cfd_inbox', 'hidden': True},
                                             {'key': 'some_module.icon', 'hidden': False}])
        settings = self.Topbar.mtbg_topbar_save(company_name=True)
        self.assertTrue(settings['company_name'])
        self.assertEqual(len(settings['items']), 3, "the switch alone leaves the order")
        settings = self.Topbar.mtbg_topbar_reset()
        self.assertEqual([i['key'] for i in settings['items']], DEFAULT_ORDER)
        self.assertFalse(settings['company_name'])

    def test_only_admins(self):
        user = self.env['res.users'].create({'name': 'Top Bar Staff', 'login': 'zz_topbar_staff',
                                             'group_ids': [(6, 0, [self.env.ref('base.group_user').id])]})
        Topbar = self.Topbar.with_user(user)
        self.assertTrue(Topbar.mtbg_topbar_settings()['items'], "everyone reads it")
        with self.assertRaises(AccessError):
            Topbar.mtbg_topbar_save([{'key': 'cfd_inbox'}])
        with self.assertRaises(AccessError):
            Topbar.mtbg_topbar_reset()


@tagged('post_install', '-at_install', 'mtbg')
class TestTopbarPage(HttpCase):
    """The web client applies it: the order kept, a hidden icon gone, the company name off, the user menu last."""

    def test_order_applied(self):
        self.env['mtbg.topbar'].mtbg_topbar_save(
            [{'key': 'SwitchCompanyMenu'}, {'key': 'mail.activity_menu', 'hidden': True}], company_name=False)
        code = """
            const deadline = Date.now() + 20000;
            (function check() {
                const tray = document.querySelector('.o_menu_systray');
                const kids = tray ? [...tray.children].filter((el) => el.getBoundingClientRect().width > 0) : [];
                const clock = tray && tray.querySelector('.fa-clock-o');
                const company = tray && tray.querySelector('.o_switch_company_menu');
                const user = tray && tray.querySelector('.o_user_menu');
                const iconOnly = document.body.classList.contains('o_mtbg_topbar_company_icon');
                if (kids.length && !clock && iconOnly && user && kids[kids.length - 1] === user
                        && (!company || kids.indexOf(company) === kids.length - 2)) {
                    console.log('test successful');
                    return;
                }
                if (Date.now() > deadline) {
                    console.error('kids: ' + kids.map((el) => el.className).join(' | ') + ' clock: ' + !!clock + ' iconOnly: ' + iconOnly);
                } else {
                    setTimeout(check, 300);
                }
            })();
        """
        self.browser_js('/odoo', code, ready="document.readyState === 'complete'", login='admin', timeout=90)


@tagged('post_install', '-at_install', 'mtbg')
class TestTopbarPhone(HttpCase):
    """On a phone the top bar still fits: the icons in the kept order, the phone's menu button last, nothing past the
    screen's edge."""
    browser_size = '390x844'
    touch_enabled = True

    def test_phone(self):
        self.env['mtbg.topbar'].mtbg_topbar_reset()
        code = """
            const deadline = Date.now() + 20000;
            (function check() {
                const tray = document.querySelector('.o_menu_systray');
                const kids = tray ? [...tray.children].filter((el) => el.getBoundingClientRect().width > 0) : [];
                const last = kids[kids.length - 1];
                const right = Math.max(0, ...kids.map((el) => el.getBoundingClientRect().right));
                const burger = last && last.querySelector('.o_mobile_menu_toggle');
                if (kids.length > 1 && right <= window.innerWidth + 1 && burger) {
                    console.log('test successful');
                    return;
                }
                if (Date.now() > deadline) {
                    console.error('kids: ' + kids.map((el) => el.className).join(' | ') + ' right: ' + right + ' width: ' + window.innerWidth);
                } else {
                    setTimeout(check, 300);
                }
            })();
        """
        self.browser_js('/odoo', code, ready="document.readyState === 'complete'", login='admin', timeout=90)


@tagged('post_install', '-at_install', 'mtbg')
class TestTopbarBubbles(HttpCase):
    """A bubble with "125" stays readable: in its button's room, never under the next icon (www 2026-10-29)."""

    def test_bubble_room(self):
        self.env['mtbg.topbar'].mtbg_topbar_reset()
        code = """
            const deadline = Date.now() + 20000;
            (function check() {
                const tray = document.querySelector('.o_menu_systray');
                const kids = tray ? [...tray.children].filter((el) => el.getBoundingClientRect().width > 0) : [];
                const clock = tray && tray.querySelector('.fa-clock-o');
                if (clock && kids.length > 2) {
                    const button = clock.parentElement;
                    let badge = button.querySelector(':scope > .badge');
                    if (!badge) {
                        badge = document.createElement('span');
                        badge.className = 'badge rounded-pill';
                        button.appendChild(badge);
                    }
                    badge.textContent = '125';
                    const item = kids.find((el) => el.contains(button));
                    const next = kids[kids.indexOf(item) + 1];
                    const b = badge.getBoundingClientRect();
                    const nextIcon = next && next.querySelector('i.fa, img');
                    const clear = !nextIcon || nextIcon.getBoundingClientRect().left >= b.right;
                    const size = parseFloat(getComputedStyle(badge).fontSize);
                    if (clear && size >= 11.5 && b.right <= item.getBoundingClientRect().right + 1) {
                        console.log('test successful');
                        return;
                    }
                    if (Date.now() > deadline) {
                        console.error('badge ' + JSON.stringify(b) + ' size ' + size + ' clear ' + clear);
                        return;
                    }
                }
                if (Date.now() > deadline) {
                    console.error('no clock in the top bar: ' + kids.map((el) => el.className).join(' | '));
                } else {
                    setTimeout(check, 300);
                }
            })();
        """
        self.browser_js('/odoo', code, ready="document.readyState === 'complete'", login='admin', timeout=90)
