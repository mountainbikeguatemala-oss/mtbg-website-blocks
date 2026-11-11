"""The Form Designer (client action ``mtbg_form_designer``, the Forms extension's tile, in its Forms page): a form's blocks in
order (drag and drop, steps added inline), each block's texts in every language of the site, its width, its show /
required rules, and the form's look per variant (page, popup, sidebar), with a live preview
(``/mtbg_forms/designer/preview``) of the unsaved form (``mtbg_preview``)."""
from odoo import _, api, models
from odoo.exceptions import AccessError, ValidationError

from .form import (COLOR, FIELDS, KEY_RE, LAYOUT_KINDS, MODES_REQUIRE, MODES_SHOW, POPUP_PAGE_KINDS, STYLE_TOKENS,
                   _number, _rule, clean_popup, clean_title_look)

BLOCK_TEXTS = ('label', 'placeholder', 'help', 'content', 'choices')
FORM_TEXTS = ('name', 'thanks_title', 'thanks_text', 'header_title', 'header_subtitle', 'popup_bar_text')
LAYOUTS = {key for key, _label in LAYOUT_KINDS}
# blocks a form always shows (the eye cannot hide them)
ALWAYS_ON = {'submit', 'pt_waivers'}


class MtbgFormDesigner(models.AbstractModel):
    _name = 'mtbg.form.designer'
    _description = 'Form Designer'

    def _check(self):
        if not self.env['mtbg.form'].has_access('write'):  # who may change the forms (website designers; Tours managers too)
            raise AccessError(_("You are not allowed to change the website forms."))

    @api.model
    def _mtbg_langs(self):
        return self.env['ir.config_parameter'].mtbg_text_langs()  # the site's languages, the main one first

    @api.model
    def _mtbg_texts(self, record, names, langs):
        """{name: {lang: text as saved ('' when not translated)}}."""
        raw = record.with_context(check_translations=True)
        return {name: {lang.code: raw.with_context(lang=lang.code)[name] or '' for lang in langs} for name in names}

    @api.model
    def _mtbg_kinds(self):
        """Every kind of block ({key: label}): the designer's own and the form types' (selection_add)."""
        return dict(self.env['mtbg.form.block']._fields['kind']._description_selection(self.env))

    @api.model
    def _mtbg_currencies(self):
        """The preview's currencies: the company's, and the second one prices show in when set."""
        ICP = self.env['ir.config_parameter'].sudo()
        currencies = [{'key': 'base', 'code': self.env.company.currency_id.name}]
        code = ICP.get_param('mtbg_tours.alt_currency_code')
        if code and float(ICP.get_param('mtbg_tours.alt_currency_rate') or 0):
            currencies.append({'key': 'alt', 'code': code})
        return currencies

    @api.model
    def mtbg_get_page(self, form_id=None, handler=None):
        """The designer's data for a form: every form of the site in its list (the website's first, then each
        extension's own, e.g. the pre-tour forms), grouped by type. ``handler``: the form type the page was opened
        for (its first form when no ``form_id``)."""
        self._check()
        langs = self._mtbg_langs()
        Form = self.env['mtbg.form'].sudo()
        own_pages = self._mtbg_own_page_handlers()
        handlers = dict(Form._fields['handler']._description_selection(self.env))
        groups = self._mtbg_form_groups()
        forms = Form.search([]).sorted(lambda f: (f.handler in own_pages, f.handler, f.id))
        form = (Form.browse(form_id).exists() if form_id else Form) or (
            forms.filtered(lambda f: f.handler == handler)[:1] if handler else forms[:1])
        blocks = form.with_context(active_test=False).block_ids.sorted(lambda b: (b.sequence, b.id))
        kind_labels = self._mtbg_kinds()
        looks = Form._mtbg_look_schemas()
        return {
            'handler': handler or False,
            'forms': [{'id': f.id, 'name': f.name, 'key': f.key,
                       'type': 'website' if f.handler not in own_pages else f.handler} for f in forms],
            # the form types of the list, in order, each with its "+ New ..." entry
            'form_types': [{'key': 'website', 'group': _("Website forms"), 'new_label': _("+ New website form")}]
            + [dict(t, group=groups.get(t['key']) or handlers.get(t['key'], t['key'])) for t in self._mtbg_form_types()],
            'form': {
                'id': form.id, 'key': form.key, 'handler': form.handler, 'style': form.style or {},
                'variants': [v.strip() for v in (form.variants or 'page').split(',') if v.strip()],
                'texts': self._mtbg_texts(form, FORM_TEXTS + form._mtbg_extra_text_names(), langs),
                'extra_texts': form._mtbg_extra_texts(),
                'has_style': form._mtbg_has_style(),
                'has_header': form._mtbg_has_header(),
                'step_by_step': form.step_by_step,
                'header_look': clean_title_look(form.header_look),
                # a website form can be a popup (its look, its pages) and sign people up for the newsletter
                'is_website': form.handler not in own_pages,
                'popup': form.popup, 'newsletter': form.newsletter, 'popup_settings': form.mtbg_popup(),
                'logo': form.mtbg_logo_url(),
                'visit_subjects': form._mtbg_visit_subjects(),
                'known_answers': form._mtbg_known_answers(),
            } if form else None,
            'blocks': [{
                'id': b.id, 'kind': b.kind, 'key': b.key or '', 'width': b.width, 'system': b.system,
                'active': b.active, 'show_mode': b.show_mode, 'show_rule': _rule(b.show_rule), 'look': b.look or {},
                'text_size': b.text_size or 0, 'text_color': b.text_color or '', 'text_color_dark': b.text_color_dark or '',
                'heading_level': b.heading_level or 'h3',
                'text_bold': b.text_bold, 'text_upper': b.text_upper, 'text_align': b.text_align or '',
                'line_height': b.line_height or 0,
                'require_mode': b.require_mode, 'require_rule': _rule(b.require_rule),
                'texts': self._mtbg_texts(b, BLOCK_TEXTS, langs),
            } for b in blocks],
            'popups': self._mtbg_popups(),
            'popup_page_kinds': [{'key': k, 'label': label} for k, label in zip(POPUP_PAGE_KINDS, (
                _("Homepage"), _("Tour pages"), _("Rental pages"), _("Blog"), _("Contact page")))],
            'langs': [{'code': lang.code, 'url_code': lang.url_code, 'name': lang.name} for lang in langs],
            'currencies': self._mtbg_currencies(),
            'kinds': [{'key': key, 'label': label, 'field': key in FIELDS,
                       'system': key not in FIELDS and key not in LAYOUTS, 'always_on': key in ALWAYS_ON,
                       'look': looks.get(key)}
                      for key, label in kind_labels.items()],
            'show_modes': [{'key': k, 'label': v} for k, v in MODES_SHOW],
            'require_modes': [{'key': k, 'label': v} for k, v in MODES_REQUIRE],
            'style_tokens': list(STYLE_TOKENS),
            'tours': self._mtbg_preview_subjects(),
        }

    @api.model
    def _mtbg_preview_subjects(self):
        """[{id, name}]: the records the preview can show a form about (the "Preview on" picker; Booking Form: the
        published tours). Forms has none."""
        return []

    @api.model
    def _mtbg_popups(self):
        """The website forms that are popups, in their order (on a page, only the first matching one opens)."""
        forms = self.env['mtbg.form'].sudo().search([('popup', '=', True)], order='popup_sequence, id')
        return [{'id': f.id, 'name': f.name, 'pages': f.mtbg_popup()['pages']} for f in forms]

    @api.model
    def mtbg_popups_order(self, form_ids):
        """The popups' order (the Popup tab's list): the first one a page takes is the one it opens."""
        self._check()
        forms = self.env['mtbg.form'].sudo().browse([int(i) for i in form_ids or []]).exists()
        for sequence, form in enumerate(forms, start=1):
            form.popup_sequence = sequence * 10
        return self._mtbg_popups()

    @api.model
    def mtbg_popup_upload(self, name, data):
        """A picture (or logo) for a popup: a public image, its URL."""
        self._check()
        attachment = self.env['ir.attachment'].sudo().create({
            'name': (name or 'popup')[:120], 'datas': data, 'res_model': 'mtbg.form', 'public': True})
        if not (attachment.mimetype or '').startswith('image/'):
            attachment.unlink()
            raise ValidationError(_("Please choose a picture (JPEG, PNG, WebP or SVG)."))
        return f"/web/image/{attachment.id}/{attachment.name}"

    @api.model
    def _mtbg_form_types(self):
        """The form types extensions add to the form list after the website's: [{key (the handler), new_label}];
        each implements ``_mtbg_new_form(key, source)`` for its "+ New ..." entry."""
        return []

    @api.model
    def _mtbg_new_form(self, kind, source):
        """A new form of an extension's type (``source``: the form open in the designer); returns it."""
        raise ValidationError(_("No new form of this kind can be made here."))

    @api.model
    def mtbg_new_form(self, kind='website', source_id=None):
        """The form list's "+ New ..." entries: a new form of that type, open in the designer. A website form: a copy
        of the website form open (else of the contact form), shown on the pages its Form block is dropped on (website
        editor > Contact & Forms > Form)."""
        self._check()
        Form = self.env['mtbg.form'].sudo()
        own_pages = self._mtbg_own_page_handlers()
        source = Form.browse(int(source_id or 0)).exists()
        if kind != 'website':
            if kind not in [t['key'] for t in self._mtbg_form_types()]:
                raise ValidationError(_("No new form of this kind can be made here."))
            return self.mtbg_get_page(self._mtbg_new_form(kind, source).id)
        if not source or source.handler in own_pages:
            source = Form.mtbg_get('contact') or Form.search([('handler', 'not in', own_pages)], limit=1)
        if not source:
            raise ValidationError(_("There is no website form to start from."))
        n = 2
        while Form.with_context(active_test=False).search_count([('key', '=', f'form_{n}')]):
            n += 1
        form = source.copy({'key': f'form_{n}', 'variants': 'page'})
        for lang in self._mtbg_langs():
            form.with_context(lang=lang.code).name = self.with_context(lang=lang.code).env._("New form %s", n)
        return self.mtbg_get_page(form.id)

    @api.model
    def _mtbg_form_groups(self):
        """The name of each extension's group of forms in the designer's list ({handler: label})."""
        return {}

    @api.model
    def _mtbg_own_page_handlers(self):
        """Form types an extension adds (e.g. the pre-tour forms: its tabs in the designer): listed after the
        website's forms, not shown by a Form block."""
        return []

    # ------------------------------------------------------------------ save
    @api.model
    def _mtbg_block_vals(self, item, sequence):
        kind = item.get('kind')
        if kind not in self._mtbg_kinds():
            raise ValidationError(_("Unknown block: %s", kind))
        key = (item.get('key') or '').strip()
        if kind in FIELDS and not KEY_RE.match(key):
            raise ValidationError(_("Every field needs a name of lower-case letters, digits and _ (%s).", key or kind))
        vals = {
            'sequence': sequence * 10, 'kind': kind, 'key': key or False, 'active': bool(item.get('active', True)),
            'width': 'half' if item.get('width') == 'half' else 'full',
            'show_mode': item.get('show_mode') if item.get('show_mode') in dict(MODES_SHOW) else 'always',
            'show_rule': self._mtbg_clean_rule(item.get('show_rule')),
            'require_mode': item.get('require_mode') if item.get('require_mode') in dict(MODES_REQUIRE) else 'never',
            'require_rule': self._mtbg_clean_rule(item.get('require_rule')),
            'text_size': int(min(max(_number(item.get('text_size')) or 0, 0), 200)),
            'text_color': item.get('text_color') if COLOR.match(str(item.get('text_color') or '')) else False,
            'text_color_dark': item.get('text_color_dark') if COLOR.match(str(item.get('text_color_dark') or '')) else False,
            'heading_level': item.get('heading_level') if item.get('heading_level') in ('h3', 'h4', 'h5') else 'h3',
            'line_height': int(min(max(_number(item.get('line_height')) or 0, 0), 250)),
            'text_bold': bool(item.get('text_bold')), 'text_upper': bool(item.get('text_upper')),
            'text_align': item.get('text_align') if item.get('text_align') in ('left', 'center', 'right') else False,
        }
        if 'look' in item:
            vals['look'] = self.env['mtbg.form']._mtbg_clean_look(kind, item['look'])
        if kind in ALWAYS_ON:
            vals['active'] = True  # a form always has its button (a pre-tour form its waivers)
        return vals

    @api.model
    def _mtbg_clean_rule(self, rule):
        rule = rule if isinstance(rule, dict) else {}
        conditions = [{'subject': str(c.get('subject') or ''), 'op': str(c.get('op') or ''),
                       'value': '' if c.get('value') is None else str(c.get('value'))}
                      for c in rule.get('conditions') or [] if isinstance(c, dict) and c.get('subject')]
        return {'match': 'any' if rule.get('match') == 'any' else 'all', 'conditions': conditions}

    @api.model
    def _mtbg_clean_style(self, style):
        out = {}
        for variant, tokens in (style or {}).items():
            if isinstance(tokens, dict):
                kept = {k: v for k, v in tokens.items() if k in STYLE_TOKENS and v not in (None, '', False)}
                if kept:
                    out[str(variant)] = kept
        return out

    @api.model
    def _mtbg_write_texts(self, record, names, texts, langs):
        main = langs[:1].code or 'en_US'
        for name in names:
            if name not in (texts or {}):
                continue  # not edited here
            values = texts[name] or {}
            main_value = (values.get(main) or '').strip()
            if not main_value and record._fields[name].required:
                continue  # (the form's name) never emptied
            record.with_context(lang=main).write({name: main_value or False})
            if main_value:
                translations = {lang.code: (values.get(lang.code) or '').strip() or False for lang in langs[1:]}
                if translations:
                    record.update_field_translations(name, translations)

    @api.model
    def mtbg_save(self, form_id, data):
        """Save the form: its texts and look, the blocks in order (new ones created, removed ones deleted; the
        form's own blocks stay)."""
        self._check()
        form = self.env['mtbg.form'].sudo().browse(form_id).exists()
        if not form:
            raise ValidationError(_("This form no longer exists."))
        langs = self._mtbg_langs()
        Block = self.env['mtbg.form.block'].sudo().with_context(active_test=False)
        items = data.get('blocks') or []
        keys = [i.get('key') for i in items if i.get('kind') in FIELDS]
        if len(keys) != len(set(keys)):
            raise ValidationError(_("Two fields of the form share a name: each field needs its own."))
        for kind, message in form._mtbg_required_blocks().items():
            if not any(i.get('kind') == kind for i in items):
                raise ValidationError(message)
        form.write({'style': self._mtbg_clean_style(data.get('style'))})
        if 'step_by_step' in data:
            form.step_by_step = bool(data['step_by_step'])
        if 'header_look' in data:
            form.header_look = clean_title_look(data['header_look'])
        if form.handler not in self._mtbg_own_page_handlers():
            for name in ('popup', 'newsletter'):
                if name in data:
                    form[name] = bool(data[name])
            if 'popup_settings' in data:
                form.popup_settings = clean_popup(data['popup_settings'])
            # a popup draws the form's popup variant (its look on the Style tab)
            variants = [v.strip() for v in (form.variants or 'page').split(',') if v.strip()]
            if form.popup and 'popup' not in variants:
                form.variants = ','.join(variants + ['popup'])
        if data.get('logo') is False:
            form.header_logo = False
        elif isinstance(data.get('logo'), str) and not data['logo'].startswith('data:'):
            form.header_logo = data['logo']  # a new upload (base64)
        self._mtbg_write_texts(form, FORM_TEXTS + form._mtbg_extra_text_names(), data.get('texts'), langs)
        kept = []
        for sequence, item in enumerate(items, start=1):
            vals = self._mtbg_block_vals(item, sequence)
            block = Block.browse(item['id']).exists() if isinstance(item.get('id'), int) else Block
            if block and block.form_id == form:
                if block.system:
                    vals.pop('kind'), vals.pop('key')  # the form's own blocks keep what they are
                block.write(vals)
            else:
                block = Block.create(dict(vals, form_id=form.id))
            self._mtbg_write_texts(block, BLOCK_TEXTS, item.get('texts'), langs)
            kept.append(block.id)
        (form.with_context(active_test=False).block_ids.filtered(lambda b: b.id not in kept and not b.system)).unlink()
        return self.mtbg_get_page(form.id, form.handler if form.handler in self._mtbg_own_page_handlers() else None)

    # ------------------------------------------------------------------ preview
    @api.model
    def _mtbg_draft_view(self, form, data, variant, lang, known=False, tour_id=0, facts=None, show_all=False,
                         sample=False, walk=False):
        """mtbg_view of the unsaved form (new records, nothing written), in ``lang``."""
        main = self._mtbg_langs()[:1].code or 'en_US'
        env = self.with_context(lang=lang).env

        def text(texts, name):
            values = (texts or {}).get(name) or {}
            return (values.get(lang) or '').strip() or (values.get(main) or '').strip() or False
        Form, Block = env['mtbg.form'].sudo(), env['mtbg.form.block'].sudo()
        logo = data.get('logo')
        logo = form.header_logo if logo is None or (isinstance(logo, str) and logo.startswith('data:')) else logo
        draft_form = Form.new({'key': form.key, 'handler': form.handler, 'name': form.name, 'header_logo': logo or False,
                               'step_by_step': bool(data.get('step_by_step', form.step_by_step)),
                               'header_look': clean_title_look(data['header_look']) if 'header_look' in data
                               else form.header_look,
                               **{name: text(data.get('texts'), name)
                                  for name in FORM_TEXTS + form._mtbg_extra_text_names()}})
        blocks = Block
        for sequence, item in enumerate(data.get('blocks') or [], start=1):
            vals = self._mtbg_block_vals(item, sequence)
            if not vals['active']:
                continue
            blocks |= Block.new(dict(vals, **{name: text(item.get('texts'), name) for name in BLOCK_TEXTS}))
        tour = env['mtbg.form']._mtbg_subject(tour_id)
        return draft_form.mtbg_view(variant, tour, blocks=blocks, style=self._mtbg_clean_style(data.get('style')),
                                    known=known, preview=True, ctx=self._mtbg_preview_facts(form, facts),
                                    show_all=show_all, sample=sample, walk=walk)

    @api.model
    def _mtbg_preview_facts(self, form, facts):
        """The yes / no facts of the preview (the designer's "Preview as" switches; else each fact's default)."""
        facts = facts or {}
        return {s['key']: bool(facts.get(s['key'], s.get('preview', False))) for s in form._mtbg_visit_subjects()
                if s.get('ops') == 'bool' and s['key'] not in ('known', 'known_phone')}

    @api.model
    def mtbg_preview(self, form_id, data, variant='page', lang=None, known=False, tour_id=0, facts=None,
                     show_all=False, sample=False, walk=False):
        """The form rendered with the designer's unsaved changes (form.js MtbgFormPreview puts it in place):
        ``facts`` the preview's switches, ``show_all`` the blocks their rules hide shown too, ``sample`` a made-up
        answer in every field and ``walk`` one step at a time (the full preview)."""
        self._check()
        form = self.env['mtbg.form'].sudo().browse(form_id).exists()
        lang = lang or self.env.lang
        view = self._mtbg_draft_view(form, data, variant, lang, known, tour_id, facts, show_all, sample, walk)
        return form.with_context(lang=lang)._mtbg_designer_render(view, variant, lang)
