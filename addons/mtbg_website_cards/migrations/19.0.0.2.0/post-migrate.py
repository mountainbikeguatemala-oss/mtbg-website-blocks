def migrate(cr, version):
    """The regions (19.0.0.2.0): the designer's unsaved drafts of the old look are dropped (the saved designs are
    read as regions)."""
    cr.execute("UPDATE mtbg_website_card_design SET draft = NULL WHERE draft IS NOT NULL")
