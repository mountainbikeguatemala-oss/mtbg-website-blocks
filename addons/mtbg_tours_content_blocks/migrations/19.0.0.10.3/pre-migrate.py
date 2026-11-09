"""0.10.3 (owner, 2026-11-08, the module clean-up): the Bullets block (mtbg_tours_bullets) is merged into the website
blocks: its block template, its snippet entry, options, styles (the old site's .highlights / .checkbullet / .xbullet
lists) and translations are here now. Where it was installed, its records become this module's with their ids
(retire_into: xml ids, view keys, static paths in the pages); it is marked uninstallable. Nothing removed."""
from odoo.addons.mtbg_tours_content_blocks.tools.retire import retire_into


def migrate(cr, version):
    retire_into(cr, 'mtbg_tours_bullets', 'mtbg_tours_content_blocks')
