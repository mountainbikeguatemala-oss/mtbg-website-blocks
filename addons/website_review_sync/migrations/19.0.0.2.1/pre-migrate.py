"""The scheduled job became noupdate: mark it so before the data loads, or this upgrade would still reset it (a job
the site paused would run again)."""


def migrate(cr, version):
    cr.execute("""
        UPDATE ir_model_data SET noupdate = TRUE
         WHERE module = 'website_review_sync' AND name = 'cron_review_sync' AND model = 'ir.cron'
    """)
