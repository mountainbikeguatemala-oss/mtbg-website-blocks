from .tools.move import BACKEND_UI_MOVE, NEW, OLD, check_core_hands_over, move_into


def pre_init_hook(env):
    """On a site with Tours Core: its boards, cards, screen choices and text settings become this module's, with their
    ids, before this module's records load (Core 0.7.0's pre-migrate does the same if it runs first). A plain Odoo
    database has nothing to move."""
    check_core_hands_over(env.cr)
    move_into(env.cr, OLD, NEW, **BACKEND_UI_MOVE)
