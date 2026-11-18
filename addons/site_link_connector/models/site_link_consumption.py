"""One row per part_consume reference: what makes the consumption idempotent (a reference consumes once), and what a
repeated call answers. No dependency on Inventory: the stock move is kept by its id."""
from odoo import fields, models


class SiteLinkConsumption(models.Model):
    _name = 'site.link.consumption'
    _description = 'Linked site: part consumption'
    _order = 'id desc'
    _rec_name = 'reference'

    reference = fields.Char(required=True, readonly=True, index=True)
    move_id = fields.Integer(string='Stock Move ID', readonly=True)
    product_id = fields.Integer(string='Product ID', readonly=True)
    product_name = fields.Char(readonly=True)
    qty = fields.Float(string='Quantity', readonly=True)
    uom = fields.Char(string='Unit', readonly=True)
    unit_cost = fields.Float(readonly=True)
    total_cost = fields.Float(readonly=True)
    currency = fields.Char(readonly=True)
    note = fields.Text(readonly=True)

    _reference_uniq = models.Constraint('UNIQUE(reference)', "A part consumption reference is used once.")

    def _site_link_answer(self, already_done):
        self.ensure_one()
        return {
            'reference': self.reference,
            'move_id': self.move_id,
            'product_id': self.product_id,
            'product_name': self.product_name,
            'qty': self.qty,
            'uom': self.uom,
            'unit_cost': self.unit_cost,
            'total_cost': self.total_cost,
            'currency': self.currency,
            'already_done': already_done,
        }
