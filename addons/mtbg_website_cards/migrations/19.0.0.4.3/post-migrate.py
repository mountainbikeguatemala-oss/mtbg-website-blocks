"""Card Settings' Book button colours: the site's one Book Buttons colour (owner, 2026-11-03: #0074d4 was set in two
places). The settings still on the design's accent, or on "My colours" with that same #0074d4, take "The Book Buttons
colour"; other choices stay."""


def migrate(cr, version):
    cr.execute("""
        UPDATE mtbg_website_card_settings SET book_style = 'site'
         WHERE book_style = 'design'
            OR (book_style = 'custom' AND lower(coalesce(book_bg, '')) = '#0074d4'
                AND lower(coalesce(book_color, '#ffffff')) IN ('#ffffff', '#fff'))
    """)
