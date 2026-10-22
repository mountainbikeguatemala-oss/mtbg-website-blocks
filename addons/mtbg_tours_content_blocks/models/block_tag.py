from odoo import fields, models


class MtbgContentBlockTag(models.Model):
    """A tag to organise reusable blocks (Reusable Blocks page): any number per block, filtered by in the library
    and the website editor's block picker."""
    _name = 'mtbg.tours.content.block.tag'
    _description = 'Reusable block tag'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    color = fields.Integer(default=0, help="Odoo colour index (0-11)")
    sequence = fields.Integer(default=10)
    block_ids = fields.Many2many('mtbg.tours.content.block', 'mtbg_content_block_tag_rel', 'tag_id', 'block_id',
                                 string='Blocks')

    _name_unique = models.Constraint('UNIQUE(name)', "A tag with this name already exists.")
