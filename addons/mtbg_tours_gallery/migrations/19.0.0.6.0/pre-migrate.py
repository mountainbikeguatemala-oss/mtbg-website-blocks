"""0.6.0 (owner, 2026-11-11, the split): the Tiled Gallery is universal (the website blocks repository); the tours'
gallery (the tour page element, the Media Library focus point, the journal posts' Gallery photos) is Tours Website's
from 0.10.49, whose pre-migrate takes those records over with their ids. Never beside an older Tours Website (it would
have no tour gallery and the posts' photos no model): the update stops before anything changes."""
from odoo.addons.mtbg_tours_content_blocks.tools.retire import module_version_on_disk

WEBSITE_WITH_GALLERY = (0, 10, 49)


def migrate(cr, version):
    cr.execute("SELECT state FROM ir_module_module WHERE name = 'mtbg_tours_website'")
    row = cr.fetchone()
    if not row or row[0] not in ('installed', 'to upgrade', 'to install'):
        return
    disk = module_version_on_disk('mtbg_tours_website')
    if disk is not None and disk < WEBSITE_WITH_GALLERY:
        raise RuntimeError(
            "Tiled Gallery 0.6.0 hands the tours' gallery to Tours Website, whose version here (%s) does not have it "
            "yet: update Tours Website (0.10.49 or later) in the same update." % '.'.join(map(str, disk)))
