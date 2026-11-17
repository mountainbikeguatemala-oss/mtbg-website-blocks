"""A first install on a database that has the page cache's former extension (mtbg_tours_edge_cache) installed: its
records become this module's before this module's data loads (no copies), and the upgrade steps it had not had run
after (the same as the 19.0.2.0.0 migration)."""
from .tools.page_cache_upgrades import run_missing
from .tools.retire import NEW, OLD, old_version, retire_into


def pre_init_hook(env):
    retire_into(env.cr, OLD, NEW)


def post_init_hook(env):
    run_missing(env, old_version(env.cr))
