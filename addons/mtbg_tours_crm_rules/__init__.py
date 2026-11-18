from . import models


def post_init_hook(env):  # the sources of modules installed together with it
    """A rule for each source installed (Contact Rules' own and the extensions'), off until switched on."""
    env['mtbg.crm.rule']._mtbg_sync_sources()
