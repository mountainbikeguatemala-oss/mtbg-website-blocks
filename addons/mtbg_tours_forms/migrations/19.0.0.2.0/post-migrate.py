"""19.0.0.2.0: the contact form is the Form Designer's "contact" form (data/forms.xml); its Spanish, as the site had
it (the data file's hook only runs on a new install); the WhatsApp opt-ins on the contact's own opt-in."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    # the WhatsApp opt-ins the old connector kept (wa_is_opted_in): on the contact's own opt-in, which the forms use
    cr.execute("""SELECT 1 FROM information_schema.columns WHERE table_name = 'res_partner'
                  AND column_name = 'wa_is_opted_in'""")
    if cr.fetchone():
        cr.execute("UPDATE res_partner SET mtbg_whatsapp_opt_in = TRUE WHERE wa_is_opted_in AND NOT COALESCE(mtbg_whatsapp_opt_in, FALSE)")
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['mtbg.form']._mtbg_seed_translations()
