"""The hotel pages (/hotels/<slug>, Accommodations) join the pages Cloudflare may keep (their prices are live)."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    ICP = api.Environment(cr, SUPERUSER_ID, {})['ir.config_parameter']
    paths = (ICP.get_param('mtbg_tours.edge_cache_paths') or '').split()
    added = [path for path in ('/hotels', '/es/hotels') if path not in paths]
    if added:
        ICP.set_param('mtbg_tours.edge_cache_paths', ' '.join(paths + added))
