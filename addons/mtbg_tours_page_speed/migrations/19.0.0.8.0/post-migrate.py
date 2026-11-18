"""0.8.0: "Over the limit" now means slow two nights in a row. The nights logged before keep their own values: each
row's old flag becomes its "Slow tonight", and it is "Over the limit" only when the page on the same screen was slow
on its measured night before too."""


def migrate(cr, version):
    cr.execute("UPDATE mtbg_page_speed_log SET slow = COALESCE(flagged, FALSE)")
    cr.execute("""
        WITH nights AS (
            SELECT id, slow, LAG(slow) OVER (PARTITION BY url, strategy ORDER BY run_date) AS before
              FROM mtbg_page_speed_log
             WHERE state = 'done'
        )
        UPDATE mtbg_page_speed_log log
           SET flagged = nights.slow AND COALESCE(nights.before, FALSE)
          FROM nights
         WHERE nights.id = log.id
    """)
