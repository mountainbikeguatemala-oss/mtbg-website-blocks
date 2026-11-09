"""0.10.3, end of the run: the Bullets extension, upgraded in this run while its old folder is still on the server, is
uninstallable again; its copy of the snippets entry (the same xml id as this module's) goes."""
from odoo import SUPERUSER_ID, api

from odoo.addons.mtbg_tours_content_blocks.tools.retire import retire_finish


def migrate(cr, version):
    retire_finish(api.Environment(cr, SUPERUSER_ID, {}), 'mtbg_tours_bullets', 'mtbg_tours_content_blocks')
