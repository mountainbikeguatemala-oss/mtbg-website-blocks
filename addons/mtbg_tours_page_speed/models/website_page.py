from odoo import http, models


class WebsitePage(models.Model):
    _inherit = 'website.page'

    def _get_response(self, request):
        """Odoo refreshes a page it cached more than an hour ago and hands back the very response it keeps in its
        cache: the visitor gets a copy of it (as Odoo does for a page served from its cache), so what this request
        does to its page (the pictures and fonts here, ir.http._post_dispatch) never changes the cached one."""
        response = super()._get_response(request)
        if (isinstance(response, http.Response) and getattr(response, 'time', None) is not None
                and not response.template and self._allow_to_use_cache(request)):
            # (a page made for this request, its body ready: the refresh path, or a page Odoo would not cache)
            response = http.Response(headers=response.headers.copy(), mimetype=response.mimetype,
                                     content_type=response.content_type, status=response.status,
                                     response=list(response.response))
        return response
