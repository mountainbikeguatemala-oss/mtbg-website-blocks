"""0.6.11 (2026-11-26): the editor's hint of an empty Tiled Gallery block ("Tiled Gallery — choose ... in the block
options.") is written while editing only (gallery.js), never saved. The blocks already saved in pages and HTML fields
held it in English, in every language (Spanish pages showed it in their HTML): it is taken out of them here, in every
language; the empty placeholder stays (the editor fills it in again)."""
from odoo.tools import SQL

MARK = 's_mtbg_gallery_placeholder'
# the placeholder's opening tag (not a self-closed one), its text and icon, its closing tag
PATTERN = r'(<div[^>]*class="[^"]*%s[^"]*"[^>/]*>)[^<]*(?:<i[^>]*>(?:</i>)?)?[^<]*(</div>)' % MARK


def strip_saved_hint(cr, mark, pattern):
    """Empty every saved ``mark`` placeholder: the views' archs (the website's edited areas) and every stored HTML
    field, in all their languages."""
    cr.execute("SELECT model, name FROM ir_model_fields WHERE ttype = 'html' AND store")
    targets = [('ir.ui.view', 'arch_db')] + cr.fetchall()
    for model, column in targets:
        table = model.replace('.', '_')
        cr.execute("SELECT data_type FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
                   (table, column))
        row = cr.fetchone()
        if not row:
            continue
        like = '%%%s%%' % mark
        if row[0] == 'jsonb':
            cr.execute(SQL(
                "UPDATE %(t)s SET %(c)s = (SELECT jsonb_object_agg(e.key, regexp_replace(e.value, %(p)s, %(r)s, 'g'))"
                " FROM jsonb_each_text(%(t)s.%(c)s) e) WHERE %(c)s::text LIKE %(l)s",
                t=SQL.identifier(table), c=SQL.identifier(column), p=pattern, r=r'\1\2', l=like))
        elif row[0] in ('text', 'character varying'):
            cr.execute(SQL("UPDATE %(t)s SET %(c)s = regexp_replace(%(c)s, %(p)s, %(r)s, 'g') WHERE %(c)s LIKE %(l)s",
                           t=SQL.identifier(table), c=SQL.identifier(column), p=pattern, r=r'\1\2', l=like))


def migrate(cr, version):
    strip_saved_hint(cr, MARK, PATTERN)
