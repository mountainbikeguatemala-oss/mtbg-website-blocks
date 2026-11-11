from odoo import api, models
from odoo.http import request


class Website(models.Model):
    _inherit = 'website'

    @api.model
    def _mtbg_visit_by_script(self):
        """Anonymous visits are recorded by the page's script (Settings › Website), not while the page is built."""
        value = self.env['ir.config_parameter'].sudo().get_param('mtbg_tours.visit_by_script')
        return value not in (False, '', '0', 'False', 'false')

    def _mtbg_visit_tag(self, main_object=None, response_template=None):
        """``{'page': id or 0}`` when the page being built is one Odoo tracks (the view's Track option, as
        ir.http._register_website_track decides), for an anonymous visitor while the script records visits; else
        None. The same for every visitor of the page (it may be cached)."""
        if not request or not self._mtbg_visit_by_script() or not request.env.user._is_public():
            return None
        if getattr(main_object, '_name', False) == 'website.page':
            return {'page': main_object.id} if main_object.sudo().view_id.track else None
        template = response_template
        if isinstance(template, str) and '.' not in template:
            template = 'website.%s' % template
        if template and self.env['ir.ui.view']._get_cached_template_info(template)['track']:
            return {'page': 0}
        return None
