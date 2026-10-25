from odoo import api, models

from .content_block import block_ids_in


class MtbgTour(models.Model):
    _inherit = 'mtbg.tour'

    @api.model_create_multi
    def create(self, vals_list):
        tours = super().create(vals_list)
        tours._mtbg_sync_block_lines()
        return tours

    def write(self, vals):
        res = super().write(vals)
        if 'description' in vals:
            self._mtbg_sync_block_lines()
        return res

    def _mtbg_sync_block_lines(self):
        """Reusable blocks are placed with the website block inside the description; the tour's
        block lines are the index of what it shows (the block's "Used On" list)."""
        Line = self.env['mtbg.tour.block.line'].sudo()
        known = set(self.env['mtbg.tours.content.block'].sudo().with_context(active_test=False).search([]).ids)
        for tour in self.sudo():
            wanted = [i for i in block_ids_in(tour.with_context(lang='en_US').description) if i in known]
            current = tour.block_line_ids.sorted(lambda l: (l.sequence, l.id))
            if [line.block_id.id for line in current] == wanted:
                continue
            current.unlink()
            Line.create([{'tour_id': tour.id, 'block_id': block_id, 'sequence': n}
                         for n, block_id in enumerate(wanted, start=1)])

    def get_public_blocks(self):
        # blocks now render inside the description
        return self.env['mtbg.tour.block.line']

    def _mtbg_tour_page_layout(self):
        """The page as its template lays it out (Website's registry defaults when there is none)."""
        self.ensure_one()
        template = self.env['mtbg.page.template'].sudo()._mtbg_template_for(self)
        return template._mtbg_layout() if template else super()._mtbg_tour_page_layout()
