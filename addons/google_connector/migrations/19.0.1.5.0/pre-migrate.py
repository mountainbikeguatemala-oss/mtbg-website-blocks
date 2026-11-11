"""19.0.1.5.0 (owner, 2026-11-10, the Google clean-up: connector code lives only in the connector): the Tours' Google
glue (mtbg_tours_google) is merged in. Its dispatcher (mtbg.google.broadcast and the mixin mtbg.google.broadcaster)
is the connector's now, with no business model named; its events and the records that announce them are Google
Calendar's and Google Maps'. Its records (the models' xml ids) become the connector's with their ids, and it is marked
uninstallable (the Tours Core's retire_into). Nothing removed, nothing sent.

The connector depends on no product: the Tours Core's tool is used where it is on the server (only a Tours site ever
had mtbg_tours_google)."""


def migrate(cr, version):
    try:
        from odoo.addons.mtbg_tours_core.tools.retire import retire_into
    except ImportError:
        return
    retire_into(cr, 'mtbg_tours_google', 'google_connector')
