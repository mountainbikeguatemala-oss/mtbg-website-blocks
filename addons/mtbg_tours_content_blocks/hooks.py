import logging

from markupsafe import Markup
from psycopg2.extras import Json

from .models.content_block import placeholder_html

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Turn each tour's block placements (shown after the description) into reusable block elements at
    the end of its description, in every language, the placement title above as a heading. Pages look
    the same; from now on blocks are placed, moved and chosen in the website editor."""
    cr = env.cr
    cr.execute("""
        SELECT l.tour_id, l.block_id, l.title, l.hidden, l.override_body
          FROM mtbg_tour_block_line l
         ORDER BY l.tour_id, l.sequence, l.id""")
    placements = {}
    for tour_id, block_id, title, hidden, override in cr.fetchall():
        if not hidden:
            placements.setdefault(tour_id, []).append((block_id, title or {}, override or {}))
    if not placements:
        return
    cr.execute("SELECT id, description FROM mtbg_tour WHERE id = ANY(%s)", [list(placements)])
    moved = 0
    for tour_id, description in cr.fetchall():
        description = dict(description or {})
        langs = set(description) or {'en_US'}
        for lang in langs:
            parts = [description.get(lang) or '']
            for block_id, title, override in placements[tour_id]:
                heading = title.get(lang) or title.get('en_US')
                if heading:
                    parts.append(Markup('<h2 class="mt-4">%s</h2>') % heading)
                local = override.get(lang) or override.get('en_US')
                # a tour-only override was never shared: it becomes ordinary content of this page
                parts.append(Markup('<div class="my-4">%s</div>') % Markup(local) if local
                             else placeholder_html(block_id, 'my-4' if not heading else 'mb-4'))
            description[lang] = ''.join(str(p) for p in parts)
        cr.execute("UPDATE mtbg_tour SET description = %s WHERE id = %s", [Json(description), tour_id])
        moved += len(placements[tour_id])
    env['mtbg.tour'].invalidate_model(['description'])
    tours = env['mtbg.tour'].browse(list(placements))
    tours._mtbg_sync_block_lines()
    _logger.info("MTBG Tours content blocks: %s placement(s) moved into %s tour description(s)", moved, len(tours))
