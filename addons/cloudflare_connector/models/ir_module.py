from odoo import api, models

from ..tools.retire import keep_retired


class IrModuleModule(models.Model):
    """The page cache's former extension stays uninstallable while its folder may still be on a server (Update Apps
    List would list it again; installed beside this module, its models and jobs would be there twice)."""
    _inherit = 'ir.module.module'

    def _register_hook(self):
        super()._register_hook()
        keep_retired(self.env)

    @api.model
    def update_list(self):
        result = super().update_list()
        keep_retired(self.env)
        return result
