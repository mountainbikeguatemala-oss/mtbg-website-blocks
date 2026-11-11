"""0.6.1 (2026-11-11): a site going from before 0.6.0 straight to this one with a full update ("-u all") reloads the
Blog and the Catalog before Tours Website, whose 0.10.49 pre-migrate takes over the tours' and posts' gallery. Until
then the post form's Gallery photos tab and the Catalog media form's focus point were still this module's views, so
Odoo checked them against fields that only Tours Website has now, and the update stopped. These two views pass to
Tours Website here, as soon as this module loads, so Odoo leaves them out until Tours Website itself loads. Tours
Website's pre-migrate still moves everything else, and finds these two already moved. Nothing else changes."""
from odoo.addons.mtbg_tours_content_blocks.tools.retire import move_into

# this module's former views that inherit other modules' forms, with fields that are Tours Website's now
FORM_VIEWS = ('view_blog_post_form_gallery', 'view_media_form_focus')


def migrate(cr, version):
    cr.execute("SELECT state FROM ir_module_module WHERE name = 'mtbg_tours_website'")
    row = cr.fetchone()
    if row and row[0] in ('installed', 'to upgrade', 'to install'):
        move_into(cr, 'mtbg_tours_gallery', 'mtbg_tours_website', names=FORM_VIEWS)
