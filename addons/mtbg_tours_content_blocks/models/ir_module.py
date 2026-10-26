"""The Website Blocks menu's Extensions page: every module whose manifest says it is a website block
(``'mtbg_tours_section': 'blocks'``, or ``'mtbg_website_blocks': True``), with its switch and its own page."""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

BASE = 'mtbg_tours_content_blocks'


def is_website_block(terp):
    return bool(terp) and (terp.get('mtbg_tours_section') == 'blocks' or bool(terp.get('mtbg_website_blocks')))


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    mtbg_website_block = fields.Boolean(
        string='Website Block', index=True,
        help="Listed on Website Blocks › Extensions (its manifest: 'mtbg_tours_section': 'blocks')")
    mtbg_wb_has_page = fields.Boolean(string='Has a Page', compute='_compute_mtbg_wb_has_page')

    def _update_from_terp(self, terp):
        super()._update_from_terp(terp)
        flag = is_website_block(terp)
        if self.mtbg_website_block != flag:
            self.mtbg_website_block = flag

    @api.model
    def _mtbg_wb_fill(self):
        """Read every module's manifest once (on install / update; later the module list keeps it right)."""
        for module in self.sudo().search([]):
            flag = is_website_block(self.get_module_info(module.name))
            if module.mtbg_website_block != flag:
                module.mtbg_website_block = flag

    def _mtbg_wb_page_xmlid(self):
        """The module's own page (``<module>.action_mtbg_extension_page``), else its settings form
        (``<module>.action_mtbg_extension_settings``)."""
        self.ensure_one()
        if self.state != 'installed':
            return False
        for name in ('action_mtbg_extension_page', 'action_mtbg_extension_settings'):
            xmlid = '%s.%s' % (self.name, name)
            if self.env.ref(xmlid, raise_if_not_found=False):
                return xmlid
        return False

    def _compute_mtbg_wb_has_page(self):
        for module in self:
            module.mtbg_wb_has_page = bool(module._mtbg_wb_page_xmlid())

    def action_mtbg_wb_open(self):
        self.ensure_one()
        xmlid = self._mtbg_wb_page_xmlid()
        if xmlid:
            return self.env['ir.actions.actions']._for_xml_id(xmlid)
        return {'type': 'ir.actions.act_window', 'res_model': 'ir.module.module', 'res_id': self.id,
                'views': [(False, 'form')], 'target': 'new', 'name': self.shortdesc}

    def action_mtbg_wb_switch_on(self):
        return self.button_immediate_install()

    def action_mtbg_wb_switch_off(self):
        """Switching a block off uninstalls it (its data is deleted): Odoo's uninstall dialog lists what goes."""
        if self.filtered(lambda m: m.name == BASE):
            raise UserError(_("Reusable Blocks is the base of the website blocks: it cannot be switched off here."))
        return self.button_uninstall_wizard()
