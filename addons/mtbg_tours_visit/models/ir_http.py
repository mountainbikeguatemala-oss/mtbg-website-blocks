from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _register_website_track(cls, response):
        # an anonymous visitor's page view is recorded by the page's script (controllers/visit.py), not here
        if cls._mtbg_visit_by_script_applies():
            return False
        return super()._register_website_track(response)

    @classmethod
    def _mtbg_visit_by_script_applies(cls):
        if not request or request.httprequest.method not in ('GET', 'HEAD'):
            return False
        website = getattr(request, 'website', None)
        return bool(website) and request.env.user._is_public() and website._mtbg_visit_by_script()
