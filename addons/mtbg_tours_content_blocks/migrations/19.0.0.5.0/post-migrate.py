"""19.0.0.5.0: page templates. Each kind of page (tour, rental) gets its Default template, laid out as the page has
always been (docs/architecture/page-templates.md); made once every module is loaded (models/page_template.py)."""


def migrate(cr, version):
    cr.execute("""
        INSERT INTO ir_config_parameter (key, value, create_date, write_date)
        VALUES ('mtbg_tours_content_blocks.page_templates_sync', '1', now(), now())
        ON CONFLICT (key) DO UPDATE SET value = '1'
    """)
