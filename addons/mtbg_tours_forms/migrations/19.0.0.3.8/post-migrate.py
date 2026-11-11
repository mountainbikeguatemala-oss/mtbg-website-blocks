"""19.0.0.3.8: the contact form shows inside the phone menu too: its 'menu' variant (a look of its own)."""


def migrate(cr, version):
    cr.execute("""
        UPDATE mtbg_form SET variants = variants || ',menu'
         WHERE key = 'contact' AND ',' || coalesce(variants, '') || ',' NOT LIKE '%,menu,%'
    """)
