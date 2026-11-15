from odoo.tests import HttpCase, tagged

# a cached page's session (window.mtbgSession, mtbg_tours_edge_cache) answering France; the visitor touches the form
CHECK = """
Object.defineProperty(window, 'mtbgSession', {configurable: true, get: () => Promise.resolve({country: 'FR'})});
const select = document.querySelector('.mtbg-phone__select');
const kept = document.querySelectorAll('.mtbg-phone__select')[1];
kept.dataset.mtbgPicked = '1';
const before = kept.value;
const firstAlt = document.querySelector('.mtbg-phone__flag').alt;  // the flag named after its country
select.dispatchEvent(new FocusEvent('focusin', {bubbles: true}));
// (the picker's countries come from a file, 0.6.1: up to 5 s)
let tries = 0;
const check = () => {
    const flag = document.querySelector('.mtbg-phone__flag').getAttribute('src');
    const alt = document.querySelector('.mtbg-phone__flag').alt;
    if (select.value === 'FR' && flag.endsWith('/fr.png') && alt === 'France' && firstAlt && kept.value === before) {
        console.log('test successful');
    } else if (++tries < 50) {
        setTimeout(check, 100);
    } else {
        console.error('test failed: ' + select.value + ' ' + flag + ' ' + alt + ' ' + firstAlt + ' ' + kept.value);
    }
};
setTimeout(check, 300);
"""


@tagged('post_install', '-at_install', 'mtbg')
class TestPhoneVisitorCountry(HttpCase):
    """On a cached page, a phone field still on the default opens on the visitor's own country."""

    def test_visitor_country(self):
        view = self.env['ir.ui.view'].create({
            'name': 'Phone test', 'type': 'qweb', 'key': 'mtbg_tours_forms.test_phone_page',
            'arch': '<t t-name="mtbg_tours_forms.test_phone_page"><t t-call="website.layout"><div id="wrap">'
                    '<form><t t-call="mtbg_tours_forms.phone_field"/></form>'
                    '<form><t t-call="mtbg_tours_forms.phone_field"><t t-set="input_id" t-value="\'second\'"/></t></form>'
                    '</div></t></t>'})
        self.env['website.page'].create({'view_id': view.id, 'url': '/mtbg-phone-test', 'is_published': True,
                                         'website_id': self.env['website'].search([], limit=1).id})
        self.browser_js('/mtbg-phone-test', CHECK, ready="document.documentElement.dataset.mtbgPhoneVisitor === '1'", login=None)

    def test_countries_file(self):
        """0.6.1: the picker's countries are a file in the page's language the browser keeps, linked from every page,
        no longer in it; its address changes with the list."""
        url = self.env['res.country'].with_context(lang='en_US').mtbg_phone_countries_url()
        page = self.url_open('/contactus')
        if page.status_code == 200:
            self.assertNotIn('id="mtbg-phone-countries"', page.text, "the list is no longer in the page")
            self.assertIn('data-mtbg-phone-countries="/mtbg_forms/phone_countries/', page.text)
        response = self.url_open(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('immutable', response.headers.get('Cache-Control', ''))
        rows = response.json()
        self.assertIn('GT', [r[0] for r in rows])
        self.assertEqual(len(rows[0]), 5, "code, name, dial code, lengths, flag")
        old = self.url_open(url.rsplit('/', 1)[0] + '/older')
        self.assertEqual(old.json(), rows, "an older address: today's list")
        self.assertNotIn('immutable', old.headers.get('Cache-Control', ''))
        self.assertEqual(self.url_open('/mtbg_forms/phone_countries/xx_XX/1').status_code, 404)
