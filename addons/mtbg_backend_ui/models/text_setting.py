"""Text settings in every language of the site.

A customer-facing text setting (a tooltip, terms) is a system parameter per language: ``<key>`` holds the main
language (the website's default) and ``<key>@<lang>`` each translation, e.g. ``mtbg_tours.book_now_tooltip`` and
``mtbg_tours.book_now_tooltip@es_ES``. A language without its own text reads the main one, or the built-in
translation while the main text is still the built-in one. A main text saved empty stays empty (nothing is
shown, in any language without its own text): it is stored as ``EMPTY`` so it is not mistaken for "never set".
"""
from odoo import _, api, models, tools
from odoo.exceptions import AccessError

EMPTY = "[empty]"   # a main text deliberately left empty


class IrConfigParameter(models.Model):
    _inherit = 'ir.config_parameter'

    @api.model
    def mtbg_text_langs(self):
        """The languages text settings are written in, the main language first."""
        return self.env['res.lang'].sudo().browse(self._mtbg_text_lang_ids())

    @api.model
    @tools.ormcache()
    def _mtbg_text_lang_ids(self):
        """Kept until the website or a language changes (both empty Odoo's caches): every text setting a page shows
        asks for them."""
        Lang = self.env['res.lang'].sudo()
        website = self.env['website'].sudo().search([], limit=1) if 'website' in self.env else None
        if website:
            main, langs = website.default_lang_id, website.language_ids
        else:
            langs = Lang.search([('active', '=', True)])
            main = langs.filtered(lambda lang: lang.code == 'en_US')[:1] or langs[:1]
        return tuple((main | langs.sorted('name')).ids)

    @api.model
    def mtbg_main_lang(self):
        return self.mtbg_text_langs()[:1].code or 'en_US'

    @api.model
    def mtbg_text_key(self, key, lang):
        return key if lang == self.mtbg_main_lang() else f"{key}@{lang}"

    @api.model
    def mtbg_get_text(self, key, lang=None, default=None):
        """The text in ``lang`` (default: the reader's language).

        ``default(lang)`` gives the built-in text: used when nothing is set, and for a language without its own text
        while the main text is still the built-in one."""
        ICP = self.sudo()
        main = ICP.mtbg_main_lang()
        lang = lang or self.env.lang or main
        if lang != main:
            own = ICP.get_param(f"{key}@{lang}")
            if own:
                return '' if own == EMPTY else own
        base = ICP.get_param(key)
        if base == EMPTY:
            return ''
        if default and (not base or (lang != main and base == default(main))):
            return default(lang) or base or ''
        return base or ''

    @api.model
    def mtbg_get_texts(self, key, default=None):
        """{lang: text} as saved, for every language of the site (what a settings page shows and edits).

        The main text: saved, empty when saved empty, else the built-in one. A translation: its own text, else
        empty (the page shows that it falls back to the main text)."""
        ICP = self.sudo()
        langs = ICP.mtbg_text_langs()
        base = ICP.get_param(key)
        main = '' if base == EMPTY else base if base else (default(langs[:1].code) if default and langs else '')
        values = {lang.code: ICP.get_param(f"{key}@{lang.code}") or '' for lang in langs[1:]}
        return {langs[:1].code: main or ''} | {code: '' if text == EMPTY else text for code, text in values.items()}

    @api.model
    def mtbg_set_texts(self, key, values):
        """Write ``{lang: text}``. An empty main text stays empty; an empty translation falls back to it."""
        ICP = self.sudo()
        main = ICP.mtbg_main_lang()
        for lang, text in values.items():
            text = (text or '').strip()
            ICP.set_param(ICP.mtbg_text_key(key, lang), text or (EMPTY if lang == main else False))

    @api.model
    def mtbg_seed_texts(self, defaults):
        """Copy built-in texts into the settings that are still empty: ``defaults`` is {key: default(lang)}.

        Translations are copied only while the main text is the built-in one (a custom main text is not
        silently paired with translations of a different text)."""
        ICP = self.sudo()
        main = ICP.mtbg_main_lang()
        for key, default in defaults.items():
            base = ICP.get_param(key)
            if not base:
                base = default(main)
                ICP.set_param(key, base or False)
            if base != default(main):
                continue
            for lang in ICP.mtbg_text_langs()[1:]:
                text = default(lang.code)
                if text and text != base and not ICP.get_param(f"{key}@{lang.code}"):
                    ICP.set_param(f"{key}@{lang.code}", text)


class MtbgTextSetting(models.AbstractModel):
    """What the settings pages' language button reads and writes."""
    _name = 'mtbg.text.setting'
    _description = 'Translated text setting'

    @api.model
    def _mtbg_texts(self):
        """{system parameter: default(lang) or None} of the text settings that can be translated.

        Extensions add theirs (tooltips, terms)."""
        return {}

    @api.model
    def mtbg_text(self, key, lang=None):
        """The setting in the reader's language (or ``lang``), falling back as described above."""
        return self.env['ir.config_parameter'].mtbg_get_text(key, lang, self._mtbg_texts().get(key))

    def _check(self, key):
        if not self.env.user._mtbg_ui_manager():
            raise AccessError(_("Only managers can change these texts."))
        if key not in self._mtbg_texts():
            raise AccessError(_("%s is not a translated text setting.", key))

    @api.model
    def mtbg_read(self, key):
        self._check(key)
        ICP = self.env['ir.config_parameter']
        return {
            'langs': [{'code': lang.code, 'name': lang.name} for lang in ICP.mtbg_text_langs()],
            'values': ICP.mtbg_get_texts(key, self._mtbg_texts()[key]),
        }

    @api.model
    def mtbg_write(self, key, values):
        self._check(key)
        self.env['ir.config_parameter'].mtbg_set_texts(key, values)
        return True

    @api.model
    def mtbg_seed(self):
        """Fill the empty text settings with their built-in texts (install and update hooks)."""
        self.env['ir.config_parameter'].mtbg_seed_texts({k: d for k, d in self._mtbg_texts().items() if d})
