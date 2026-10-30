"""The website's card settings, for every card at once (owner, 2026-10-30: "need book botton global settings"): the
Book button's words, icon, colours, size and shape. A design's own words for its Book button (e.g. "Book (from
{price})") and its own icon still win; the rest is the same on every card of the website.

One record (``mtbg_website_cards.card_settings``), edited in Website Blocks › Card Settings."""
import re

from odoo import api, fields, models, tools
from odoo.exceptions import ValidationError

COLOR = re.compile(r'^#[0-9a-fA-F]{6}$')
ICON = re.compile(r'^fa-[a-z0-9-]+$')


class MtbgWebsiteCardSettings(models.Model):
    _name = 'mtbg.website.card.settings'
    _description = 'Website card settings'

    name = fields.Char(default='Card settings', required=True)
    book_text = fields.Char(string='Book button words', translate=True, default='Book',
                            help="The words of every card's Book button (a design may give its own, e.g. "
                                 "\"Book (from {price})\")")
    book_icon = fields.Char(string='Book button icon', help="A Font Awesome name, e.g. fa-calendar-check-o (empty: "
                                                            "none; a design's own icon wins)")
    book_style = fields.Selection([
        ('design', "The design's accent colour"),
        ('primary', "The theme's Primary button"),
        ('secondary', "The theme's Secondary button"),
        ('custom', 'My colours'),
    ], string='Book button colours', required=True, default='design')
    book_bg = fields.Char(string='Background', help="My colours: e.g. #9b59b6")
    book_color = fields.Char(string='Text colour', help="My colours: e.g. #ffffff")
    book_size = fields.Selection([('sm', 'Small'), ('md', 'Medium'), ('lg', 'Large')], string='Size',
                                 required=True, default='md')
    book_shape = fields.Selection([('square', 'Square'), ('rounded', 'Rounded'), ('pill', 'Pill')], string='Shape',
                                  required=True, default='rounded')
    book_full = fields.Boolean(string='Full width', help="The button as wide as its line")
    book_caps = fields.Boolean(string='Capitals')

    @api.constrains('book_bg', 'book_color', 'book_icon')
    def _check_values(self):
        for record in self:
            for value in (record.book_bg, record.book_color):
                if value and not COLOR.match(value):
                    raise ValidationError(self.env._("A colour is a hex code, e.g. #9b59b6."))
            if record.book_icon and not ICON.match(record.book_icon):
                raise ValidationError(self.env._("An icon is a Font Awesome name, e.g. fa-calendar-check-o."))

    @api.model
    def _mtbg_get(self):
        """The settings (sudo), made if missing."""
        return self.sudo().browse(self._mtbg_get_id())

    @api.model
    @tools.ormcache()
    def _mtbg_get_id(self):
        """The settings' id, kept until settings are made or deleted: every card of a page asks."""
        record = self.env.ref('mtbg_website_cards.card_settings', raise_if_not_found=False)
        return (record or self.sudo().search([], limit=1) or self.sudo().create({})).id

    @api.model_create_multi
    def create(self, vals_list):
        self.env.registry.clear_cache()
        return super().create(vals_list)

    def unlink(self):
        self.env.registry.clear_cache()
        return super().unlink()

    def _mtbg_book(self):
        """What the cards need of the Book button: its words, icon, classes and colour variables."""
        self.ensure_one()
        classes = [f'mtbg-book--{self.book_style}', f'mtbg-book--{self.book_size}', f'mtbg-book--{self.book_shape}']
        if self.book_full:
            classes.append('mtbg-book--full')
        if self.book_caps:
            classes.append('mtbg-book--caps')
        style = ''
        if self.book_style == 'custom':
            style = '; '.join(f'{var}: {value}' for var, value in (('--mtbg-book-bg', self.book_bg),
                                                                 ('--mtbg-book-text', self.book_color)) if value)
        return {'text': self.book_text or '', 'icon': self.book_icon or '', 'class': ' '.join(classes),
                'style': style}

    @api.model
    def action_open(self):
        """Website Blocks › Card Settings: the one record."""
        return {'type': 'ir.actions.act_window', 'name': self.env._("Card Settings"), 'res_model': self._name,
                'res_id': self._mtbg_get().id, 'view_mode': 'form', 'target': 'current'}

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('mtbg_skip_menu_refresh') and 'website.menu' in self.env \
                and hasattr(self.env['website.menu'], 'mtbg_refresh_all'):
            self.env['website.menu'].mtbg_refresh_all()  # (the mega menus keep their cards as drawn)
        return res
