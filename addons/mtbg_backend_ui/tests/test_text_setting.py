from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'mtbg')
class TestTextSetting(TransactionCase):

    def setUp(self):
        super().setUp()
        self.ICP = self.env['ir.config_parameter'].sudo()
        self.main = self.ICP.mtbg_main_lang()
        self.builtin = {self.main: 'Built-in', 'xx_XX': 'Integrado'}
        self.default = lambda lang: self.builtin.get(lang)

    def test_fallbacks(self):
        key = 'mtbg_tours.test_text'
        # nothing set: the built-in text in each language
        self.assertEqual(self.ICP.mtbg_get_text(key, self.main, self.default), 'Built-in')
        self.assertEqual(self.ICP.mtbg_get_text(key, 'xx_XX', self.default), 'Integrado')
        # the main text still the built-in one: other languages keep the built-in translation
        self.ICP.set_param(key, 'Built-in')
        self.assertEqual(self.ICP.mtbg_get_text(key, 'xx_XX', self.default), 'Integrado')
        # a custom main text: languages without their own text read it
        self.ICP.mtbg_set_texts(key, {self.main: 'Custom'})
        self.assertEqual(self.ICP.mtbg_get_text(key, 'xx_XX', self.default), 'Custom')
        # their own text wins; emptying it falls back again
        self.ICP.mtbg_set_texts(key, {'xx_XX': 'Propio'})
        self.assertEqual(self.ICP.get_param(f'{key}@xx_XX'), 'Propio')
        self.assertEqual(self.ICP.mtbg_get_text(key, 'xx_XX', self.default), 'Propio')
        self.ICP.mtbg_set_texts(key, {'xx_XX': ' '})
        self.assertFalse(self.ICP.get_param(f'{key}@xx_XX'))
        # a main text saved empty stays empty (no built-in text comes back), in every language without its own
        self.ICP.mtbg_set_texts(key, {self.main: ''})
        self.assertEqual(self.ICP.mtbg_get_text(key, self.main, self.default), '')
        self.assertEqual(self.ICP.mtbg_get_text(key, 'xx_XX', self.default), '')
        self.ICP.mtbg_seed_texts({key: self.default})
        self.assertEqual(self.ICP.mtbg_get_text(key, self.main, self.default), '', "seeding keeps it empty")

    def test_seed_keeps_custom_texts(self):
        self.ICP.mtbg_seed_texts({'mtbg_tours.test_a': self.default})
        self.assertEqual(self.ICP.get_param('mtbg_tours.test_a'), 'Built-in')
        self.ICP.set_param('mtbg_tours.test_b', 'Mine')
        self.ICP.mtbg_seed_texts({'mtbg_tours.test_b': self.default})
        self.assertEqual(self.ICP.get_param('mtbg_tours.test_b'), 'Mine')

    def test_page_reads_only_registered_keys(self):
        from odoo.exceptions import AccessError
        with self.assertRaises(AccessError):
            self.env['mtbg.text.setting'].mtbg_read('web.base.url')

    def test_languages_follow_the_website(self):
        """The languages are kept between pages: a language added to the website shows at once."""
        website = self.env['website'].sudo().search([], limit=1) if 'website' in self.env else None
        if not website:  # a database without a website: the active languages (test_fallbacks)
            return
        lang = self.env['res.lang'].with_context(active_test=False).search(
            [('id', 'not in', website.language_ids.ids)], limit=1)
        if not lang:
            return
        lang.active = True
        self.assertNotIn(lang, self.ICP.mtbg_text_langs())
        website.language_ids = [(4, lang.id)]
        self.assertIn(lang, self.ICP.mtbg_text_langs())
        self.assertEqual(self.ICP.mtbg_text_langs()[:1], website.default_lang_id, "the main language first")
