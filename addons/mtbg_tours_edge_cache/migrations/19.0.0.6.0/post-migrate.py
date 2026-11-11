"""Every public page (owner's plan, 2026-11-03): the blog and the tour policies join the pages Cloudflare may keep (each
entry now stands for every language: /blog is /es/blog too); the website's own pages are kept without being listed."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    ICP = api.Environment(cr, SUPERUSER_ID, {})['ir.config_parameter']
    paths = (ICP.get_param('mtbg_tours.edge_cache_paths') or '').split()
    added = [path for path in ('/blog', '/tour-policies') if path not in paths]
    if added:
        ICP.set_param('mtbg_tours.edge_cache_paths', ' '.join(paths + added))
