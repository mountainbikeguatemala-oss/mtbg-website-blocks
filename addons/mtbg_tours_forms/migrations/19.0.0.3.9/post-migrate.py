"""19.0.0.3.9: the Menu Contact Form (data/menu_form.xml, made by the update) in Spanish too: its texts only."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    form = env.ref('mtbg_tours_forms.form_menu_contact', raise_if_not_found=False)
    if form:
        env['mtbg.form']._mtbg_seed_translations(form)
