import re

from markupsafe import Markup, escape

from odoo import api, fields, models

# Saved in page content: the block element with the chosen block id and a placeholder; the shared body
# is filled in at render time, so every page always shows the block's current content.
PLACEHOLDER_CLASS = 's_mtbg_content_block_placeholder'
BLOCK_RE = re.compile(
    r'<(?P<tag>section|div)\b(?P<attrs>[^>]*\bdata-mtbg-block="(?P<id>\d+)"[^>]*)>\s*'
    r'<div\b[^>]*\b' + PLACEHOLDER_CLASS + r'\b[^>]*>.*?</div>\s*</(?P=tag)>',
    re.S)
BLOCK_ID_RE = re.compile(r'data-mtbg-block="(\d+)"')
# Dynamic content inside a block's shared body: ``<div data-mtbg-slot="name">`` is filled for the page it shows on
# (e.g. the tour's group discounts table, see _mtbg_slot_html); it is stored with its placeholder text only
SLOT_RE = re.compile(
    r'<div\b(?P<attrs>[^>]*\bdata-mtbg-slot="(?P<name>[\w.-]+)"[^>]*)>(?:(?!<div\b).)*?</div>', re.S)


def placeholder_html(block_id='', css='my-4'):
    """The block as it is stored in page content (see the website builder plugin's clean-for-save)."""
    return Markup(
        '<section class="s_mtbg_content_block o_not_editable %s" data-snippet="s_mtbg_content_block" '
        'data-name="Reusable Block" data-mtbg-block="%s"><div class="%s">Reusable block</div></section>'
    ) % (css, block_id, PLACEHOLDER_CLASS)


def block_ids_in(html):
    return [int(i) for i in BLOCK_ID_RE.findall(str(html or ''))]


class MtbgContentBlock(models.Model):
    _inherit = 'mtbg.tours.content.block'

    website_view_count = fields.Integer(compute='_compute_website_usage', string='Website Pages',
                                        help="Website pages (outside tour descriptions) showing this block")
    usage_total = fields.Integer(compute='_compute_website_usage', string='Used On')

    def _compute_website_usage(self):
        View = self.env['ir.ui.view'].sudo()
        for block in self:
            count = View.search_count([('arch_db', 'ilike', f'data-mtbg-block="{block.id}"')]) if block.id else 0
            block.website_view_count = count
            block.usage_total = block.usage_count + count

    # ------------------------------------------------------------------ rendering
    def _mtbg_body_html(self, editable):
        """The shared body inside a page. In the editor it is the block's own (locked) field, so
        "Edit in place" saves straight to this block. It is an ``oe_structure`` (a drop area of blocks, like the
        native Parallax block's): the website builder only gives blocks nested in another block their background
        and other section options when their parent is one."""
        self.ensure_one()
        if not editable:
            return Markup('<div class="s_mtbg_content_block_body oe_structure">%s</div>') % (self.body or Markup())
        return Markup(
            '<div class="s_mtbg_content_block_body oe_structure" data-oe-model="mtbg.tours.content.block" data-oe-id="%s" '
            'data-oe-field="body" data-oe-type="html" data-oe-expression="block.body" data-oe-readonly="1">%s</div>'
        ) % (self.id, self.body or Markup())

    @api.model
    def _mtbg_expand(self, html, editable=False):
        """Fill every reusable block placeholder of rendered ``html`` with its block's body.

        Visitors: a missing or archived block renders nothing. Editor: the block carries its name and
        how many pages use it (the editor's label), and an unknown block keeps its placeholder.
        """
        ids = {int(m.group('id')) for m in BLOCK_RE.finditer(html)}
        blocks = {b.id: b for b in self.sudo().browse(ids).exists().filtered('active')}

        def fill(match):
            block = blocks.get(int(match.group('id')))
            tag, attrs = match.group('tag'), match.group('attrs')
            if not block:
                return match.group(0) if editable else ''
            if editable:
                # attrs is page source (already escaped): append escaped values, never str + Markup
                attrs += ' data-mtbg-label="%s" data-mtbg-usage="%s"' % (escape(block.name), block.usage_total)
            return f'<{tag}{attrs}>{block._mtbg_body_html(editable)}</{tag}>'

        return Markup(BLOCK_RE.sub(fill, str(html)))

    @api.model
    def _mtbg_fill_slots(self, html, values, editable=False):
        """Fill the dynamic slots of rendered ``html`` for the page (``values``: the page's render values).
        A slot nothing fills keeps its placeholder in the editor and renders empty for visitors."""
        def fill(match):
            content = self._mtbg_slot_html(match.group('name'), values)
            if content is None:
                return match.group(0) if editable else f'<div{match.group("attrs")}></div>'
            return f'<div{match.group("attrs")}>{content}</div>'
        return Markup(SLOT_RE.sub(fill, str(html)))

    @api.model
    def _mtbg_slot_html(self, name, values):
        """The rendered content of slot ``name`` on the page rendered with ``values``, or None. Extended by the
        addons that provide slots."""
        return None

    # ------------------------------------------------------------------ website editor
    @api.model
    def mtbg_picker_data(self):
        """Blocks offered in the editor's block picker, with a short text preview."""
        types = dict(self._fields['block_type']._description_selection(self.env))
        result = []
        for block in self.search([], order='block_type, name'):
            text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', str(block.body or ''))).strip()
            image = re.search(r'<img\b[^>]*\bsrc="([^"]+)"', str(block.body or ''))
            result.append({'id': block.id, 'name': block.name, 'type': block.block_type,
                           'type_label': types.get(block.block_type, ''), 'usage': block.usage_total,
                           'excerpt': text[:220], 'image': image.group(1) if image else ''})
        return {'blocks': result, 'types': [{'key': k, 'label': v} for k, v in types.items()]}

    @api.model
    def mtbg_editor_block(self, block_id):
        """A chosen block as the editor shows it: its locked body field, name and usage."""
        block = self.browse(int(block_id)).exists()
        if not block:
            return False
        return {'id': block.id, 'name': block.name, 'usage': block.usage_total, 'html': block._mtbg_body_html(True)}

    @api.model
    def mtbg_create_from_editor(self, name):
        block = self.create({'name': (name or '').strip() or self.env._("New block"),
                             'body': Markup('<p>%s</p>') % self.env._("Write the shared content here.")})
        return self.mtbg_editor_block(block.id)

    def action_mtbg_edit_in_builder(self):
        """Open the block alone in the full website builder (see the /mtbg/block/<id> page)."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': self.env['website'].get_client_action_url(f'/mtbg/block/{self.id}', True),
            'target': 'self',
        }
