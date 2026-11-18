"""One row per customer repair reference (repair_quote): what makes the quote and its invoice happen once per
reference, and how a later call finds them. No dependency on Sales or Repair: the records are kept by their ids."""
from odoo import fields, models


class SiteLinkRepair(models.Model):
    _name = 'site.link.repair'
    _description = 'Linked site: customer repair'
    _order = 'id desc'
    _rec_name = 'reference'

    reference = fields.Char(required=True, readonly=True, index=True)
    partner_id = fields.Integer(string='Contact ID', readonly=True)
    order_id = fields.Integer(string='Quotation ID', readonly=True)
    repair_id = fields.Integer(string='Repair Order ID', readonly=True)
    invoice_id = fields.Integer(string='Invoice ID', readonly=True)
    lines_hash = fields.Char(string='Lines Fingerprint', readonly=True,
                             help="The last lines sent: the same lines again change nothing.")

    _reference_uniq = models.Constraint('UNIQUE(reference)', "A customer repair reference is used once.")
