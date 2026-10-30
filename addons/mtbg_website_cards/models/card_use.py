"""Where cards show, and how (owner, 2026-10-29: "put everything in one module with the same settings and template
system ... all code should be shared"; "Sliding is sliding and cards are cards. Then we interperate them with
different designs on top for the different modules").

A card use is one place of the website that shows cards: the tour catalog, a mega menu's Image Cards column, a mega
menu's row or slider, the group departures block, the reviews slider and wall, the Cards block... Each says which
design draws its cards (a caller may choose another one of the same source, e.g. a mega menu column's own "Card
design"), and how they are laid out: a grid (columns by screen width), a slider (the one slider: how many at once by
width, arrows, autoplay, stacked on narrow screens) or a masonry wall. Modules bring their uses as data (a record
with an XML id, its design their shipped design: nothing changes look on install) and render through it::

    env.ref('my_module.use_x').mtbg_render(records)                       # the use's design and layout
    env.ref('my_module.use_x').mtbg_render(records, design=other, layout='slider')

The settings are changed in Website › Configuration › Card Uses (one place for all of them).
"""
from odoo import api, fields, models

LAYOUTS = [('grid', 'Grid'), ('slider', 'Slider'), ('masonry', 'Masonry wall'), ('stack', 'One under another')]


class MtbgWebsiteCardUse(models.Model):
    _name = 'mtbg.website.card.use'
    _description = 'Website card use'
    _order = 'sequence, name, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    source = fields.Selection(selection=lambda self: self.env['mtbg.website.card.design']._selection_source(),
                              required=True, help="What its cards show")
    design_id = fields.Many2one('mtbg.website.card.design', string='Card design', ondelete='set null',
                                domain="[('source', '=', source)]",
                                help="Empty: the source's Default design")
    layout = fields.Selection(LAYOUTS, required=True, default='grid')
    # how many at once: in a grid its columns, in a slider the cards in view (a fraction: the next one peeks)
    per_lg = fields.Float(string='Desktop', default=3, help="How many side by side on wide screens (992px and up)")
    per_md = fields.Float(string='Tablet', default=2, help="576 to 991px")
    per_sm = fields.Float(string='Phone', default=1, help="Under 576px; in a slider 1.2 lets the next card peek")
    gap = fields.Char(default='1.5rem', help="Space between cards (a CSS length)")
    arrows = fields.Boolean(default=True, help="Slider: arrows on the row's edges (desktop)")
    arrow_class = fields.Char(default='btn btn-light rounded-circle shadow', help="Slider: the arrows' classes")
    autoplay = fields.Integer(help="Slider: milliseconds between pages (0: no autoplay)")
    loop = fields.Boolean(help="Slider: the last page goes back to the first")
    stack_md = fields.Boolean(string='Stack on tablets and phones', help="Slider: one under another under 992px")
    css_class = fields.Char(string='Extra classes', help="Classes on the cards' container")

    @api.model
    def _mtbg_fmt(self, value):
        return ('%g' % value) if value else '1'

    def _mtbg_design(self, design=None):
        self.ensure_one()
        Design = self.env['mtbg.website.card.design'].sudo()
        if design and design.source == self.source:
            return design
        return self.design_id.sudo() or Design._mtbg_design_for(self.source)

    def mtbg_render(self, records=None, values_list=None, design=None, layout=None, **extra):
        """The cards of ``records`` (or ready ``values_list``) as this use shows them (``design`` / ``layout``: a
        caller's own choice)."""
        self.ensure_one()
        design = self._mtbg_design(design)
        if not design:
            return ''
        return design.mtbg_render(records, values_list=values_list, layout=layout or self.layout, use=self, **extra)

    def _mtbg_layout_values(self, layout):
        """The template's layout values (cards.xml): the grid's columns or the slider's options."""
        self.ensure_one()
        per = {'lg': self._mtbg_fmt(self.per_lg), 'md': self._mtbg_fmt(self.per_md), 'sm': self._mtbg_fmt(self.per_sm)}
        return {
            'per': per, 'gap': self.gap or '1.5rem', 'use_class': self.css_class or '',
            'slider_per': per, 'slider_gap': self.gap or '1.5rem', 'slider_arrows': bool(self.arrows),
            'slider_arrow_class': self.arrow_class or 'btn btn-light rounded-circle shadow',
            'slider_autoplay': self.autoplay or 0, 'slider_loop': self.loop,
            'slider_class': ' '.join(c for c in ('mtbg-slider--stack' if self.stack_md else '', self.css_class or '') if c),
        }
