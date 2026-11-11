"""The newsletter popup as a Form Designer form (the owner, 2026-10-26): made once (on install, and by the update to
19.0.0.4.0 from the hand-made popup of 2025), with its fields, wording, pictures, logo, overlay and offer bar, on
every page but the tour and rental pages, as before."""
from odoo import api, models

KEY = 'newsletter_popup'
ES = {
    'Newsletter popup': 'Ventana del boletín',
    'Sign Up For Our Newsletter': 'Suscríbete a nuestro boletín',
    'We always have tours departing! Sign up and get the latest to your inbox.':
        '¡Siempre tenemos tours saliendo! Suscríbete y recibe las novedades en tu correo.',
    'Name': 'Nombre', 'Email': 'Correo electrónico',
    'Mobile (optional, for WhatsApp / SMS updates)': 'Celular (opcional, para avisos por WhatsApp / SMS)',
    'Subscribe': 'Suscribirme', "You're in!": '¡Listo!',
    'Watch your inbox for our next departures.': 'Pronto recibirás nuestras próximas salidas en tu correo.',
}
UNLESS_KNOWN = {'match': 'all', 'conditions': [{'subject': 'known', 'op': 'yes'}]}
TEXTING = {'match': 'any', 'conditions': [{'subject': 'field:phone', 'op': 'min_digits', 'value': '3'},
                                          {'subject': 'known_phone', 'op': 'yes'}]}


class MtbgForm(models.Model):
    _inherit = 'mtbg.form'

    @api.model
    def _mtbg_make_newsletter_popup(self):
        """The newsletter popup's form, once (nothing when a form with its key exists)."""
        Form = self.sudo().with_context(active_test=False)
        if Form.search_count([('key', '=', KEY)]):
            return False
        params = self.env['ir.config_parameter'].sudo()
        images = [u.strip() for u in (params.get_param('mtbg_tours.contact_popup_images') or '').split(',') if u.strip()]
        form = Form.create({
            'name': 'Newsletter popup', 'key': KEY, 'handler': 'contact', 'variants': 'popup', 'sequence': 20,
            'newsletter': True, 'popup': True, 'popup_sequence': 10,
            'popup_settings': {'look': 'full', 'images': images, 'rotate': True, 'overlay': 45,
                               'logo': params.get_param('mtbg_tours.newsletter_logo') or '', 'bar': True,
                               'bar_color': '#111111', 'bar_text_color': '#ffffff', 'pages': 'all',
                               'include': {'kinds': [], 'words': []},
                               'exclude': {'kinds': ['tours', 'rentals'], 'words': []}},
            'popup_bar_text': params.get_param('mtbg_tours.newsletter_offer') or '',
            'thanks_title': "You're in!", 'thanks_text': 'Watch your inbox for our next departures.',
            # the yellow Subscribe button of the original
            'style': {'popup': {'accent': '#ffcc00', 'accent_text': '#ffffff'}},
        })
        Block = self.env['mtbg.form.block'].sudo()
        blocks = [
            {'kind': 'heading', 'label': 'Sign Up For Our Newsletter',
             'help': 'We always have tours departing! Sign up and get the latest to your inbox.'},
            {'kind': 'known', 'system': True},
            {'kind': 'text', 'key': 'name', 'label': 'Name', 'width': 'half', 'show_mode': 'unless',
             'show_rule': UNLESS_KNOWN, 'require_mode': 'always'},
            {'kind': 'email', 'key': 'email', 'label': 'Email', 'width': 'half', 'show_mode': 'unless',
             'show_rule': UNLESS_KNOWN, 'require_mode': 'always'},
            {'kind': 'phone', 'key': 'phone', 'label': 'Mobile (optional, for WhatsApp / SMS updates)',
             'show_mode': 'unless', 'show_rule': UNLESS_KNOWN},
            {'kind': 'texting', 'system': True, 'show_mode': 'when', 'show_rule': TEXTING},
            {'kind': 'submit', 'label': 'Subscribe', 'system': True},
        ]
        records = Block
        for sequence, vals in enumerate(blocks, start=1):
            records |= Block.create(dict(vals, form_id=form.id, sequence=sequence * 10))
        # its Spanish (the hand-made popup's), and the offer bar's own Spanish setting
        if self.env['res.lang']._lang_get('es_ES'):
            es = self.env['ir.config_parameter'].sudo().get_param('mtbg_tours.newsletter_offer_es_ES')
            vals = {'name': ES['Newsletter popup'], 'thanks_title': ES["You're in!"],
                    'thanks_text': ES['Watch your inbox for our next departures.']}
            if es:
                vals['popup_bar_text'] = es
            form.with_context(lang='es_ES').write(vals)
            for block in records:
                vals = {name: ES[block[name]] for name in ('label', 'help') if block[name] and block[name] in ES}
                if vals:
                    block.with_context(lang='es_ES').write(vals)
        return form
