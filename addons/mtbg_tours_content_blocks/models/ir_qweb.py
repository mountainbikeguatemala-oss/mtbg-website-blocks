from odoo import models
from odoo.exceptions import AccessError
from odoo.http import request

from .content_block import PLACEHOLDER_CLASS


class IrQweb(models.AbstractModel):
    _inherit = 'ir.qweb'

    def _render(self, template, values=None, **options):
        """Reusable blocks are stored as placeholders (in tour descriptions, other HTML fields and website
        pages alike) and filled with their shared content once the whole page is rendered."""
        values = values if values is not None else {}
        result = super()._render(template, values, **options)
        if PLACEHOLDER_CLASS not in result:
            return result
        Block = self.env['mtbg.tours.content.block']
        editable = self._mtbg_cb_editable(values)
        result = Block._mtbg_expand(result, editable=editable)
        if 'data-mtbg-slot=' in result:
            result = Block._mtbg_fill_slots(result, values, editable=editable)
        return result

    def _mtbg_cb_editable(self, values):
        """Whether the page is rendered for the website editor, decided like website's
        ``_prepare_frontend_environment`` (which sets ``editable`` on its own copy of the values, so the
        caller's values usually don't carry it): designers, or restricted editors allowed to modify the
        page's main object, outside translation mode. Then the shared content is the block's own field, so
        "Edit in place" saves to the block."""
        if 'editable' in values:
            return bool(values['editable'])
        if not request or not getattr(request, 'is_frontend', False) or not getattr(request, 'website', False):
            return False
        user = self.env.user
        if not user.has_group('website.group_website_restricted_editor'):
            return False
        if self.env.context.get('lang') != self.env['ir.http']._get_default_lang().code:
            return False  # translation mode
        if user.has_group('website.group_website_designer'):
            return True
        main_object = values.get('main_object')
        if not main_object:
            return False
        try:
            request.website._check_user_can_modify(main_object.with_user(user.id))
        except AccessError:
            return False
        return True
