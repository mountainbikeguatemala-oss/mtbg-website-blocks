"""The Reusable Blocks page (client action ``mtbg_content_block_library``, the extension's tile): every reusable block
with where it is used, organised by type and tags, with a live preview (``/mtbg/block/<id>?preview=1``). The content
itself is edited in the full website builder (``/mtbg/block/<id>``); this page edits the rest (name, type, tags,
internal note) and acts on several blocks at once.
"""
import hashlib
import re
from collections import defaultdict

from odoo import _, api, models
from odoo.exceptions import AccessError, UserError

from .content_block import BLOCK_ID_RE

TAG_COLORS = 12


def _text(html):
    """The words of a block's body (its CSS and scripts left out)."""
    html = re.sub(r'<(style|script)\b.*?</\1>', ' ', str(html or ''), flags=re.S | re.I)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html)).strip()


class MtbgContentBlockLibrary(models.AbstractModel):
    _name = 'mtbg.content.block.library'
    _description = 'Reusable Blocks page'

    def _check(self):
        if not self.env['mtbg.tours.content.block'].has_access('write'):
            raise AccessError(_("You cannot change reusable blocks."))

    @api.model
    def _blocks(self):
        return self.env['mtbg.tours.content.block'].with_context(active_test=False)

    # ------------------------------------------------------------------
    # Where blocks are used
    # ------------------------------------------------------------------
    @api.model
    def _mtbg_usage_index(self):
        """{block id: {'views': views, 'blocks': blocks, 'records': [{kind, name, url}]}}: the website views (pages,
        header, footer...) and the other blocks that contain it, and the records of other modules whose content
        places it (``records``: Tours adds its tours, _mtbg_usage_records)."""
        index = defaultdict(lambda: {'views': self.env['ir.ui.view'], 'blocks': self.env['mtbg.tours.content.block'],
                                     'records': []})
        self._mtbg_usage_records(index)
        for view in self.env['ir.ui.view'].sudo().search([('arch_db', 'ilike', 'data-mtbg-block=')]):
            for block_id in {int(i) for i in BLOCK_ID_RE.findall(view.arch_db or '')}:
                index[block_id]['views'] |= view
        for block in self._blocks().sudo().search([('body', 'ilike', 'data-mtbg-block=')]):
            for block_id in {int(i) for i in BLOCK_ID_RE.findall(str(block.body or ''))} - {block.id}:
                index[block_id]['blocks'] |= block
        return index

    @api.model
    def _mtbg_usage_records(self, index):
        """Add the records of other modules whose content places a block: index[block id]['records'] += [{kind,
        name, url}]. None here."""
        return index

    @api.model
    def _mtbg_builtin(self):
        """{block id: extension name} of the blocks an extension creates and uses by itself (its data: banners,
        group discounts, reviews...). They count as used and are never deleted."""
        data = self.env['ir.model.data'].sudo().search([('model', '=', 'mtbg.tours.content.block')])
        modules = {m.name: m.shortdesc for m in self.env['ir.module.module'].sudo().search(
            [('name', 'in', list(set(data.mapped('module'))))])}
        return {d.res_id: modules.get(d.module) or d.module for d in data}

    @api.model
    def _mtbg_usage_rows(self, usage):
        """Where one block is used, as the page lists it: [{kind, name, url}]."""
        rows = list(usage['records'])
        pages = self.env['website.page'].sudo().search([('view_id', 'in', usage['views'].ids)])
        page_views = pages.view_id
        rows += [{'kind': 'page', 'name': page.name, 'url': page.url} for page in pages]
        rows += [{'kind': 'template', 'name': view.name, 'url': False} for view in usage['views'] - page_views]
        rows += [{'kind': 'block', 'name': block.name, 'id': block.id, 'url': False} for block in usage['blocks']]
        return rows

    # ------------------------------------------------------------------
    # The page
    # ------------------------------------------------------------------
    @api.model
    def mtbg_get_library(self):
        Block = self._blocks()
        types = dict(Block._fields['block_type']._description_selection(self.env))
        usage = self._mtbg_usage_index()
        builtin = self._mtbg_builtin()
        blocks = Block.search([], order='name, id')
        # possible duplicates: the same name or the same (non-empty) content
        by_name, by_body = defaultdict(list), defaultdict(list)
        for block in blocks:
            by_name[(block.name or '').strip().lower()].append(block.id)
            text = _text(block.body)
            if text:
                by_body[hashlib.md5(str(block.body).encode()).hexdigest()].append(block.id)
        duplicates = {i for group in list(by_name.values()) + list(by_body.values()) if len(group) > 1 for i in group}
        rows = []
        for block in blocks:
            text = _text(block.body)
            image = re.search(r'<img\b[^>]*\bsrc="([^"]+)"', str(block.body or ''))
            used = usage.get(block.id)
            count = (len(used['records']) + len(used['views']) + len(used['blocks'])) if used else 0
            count += 1 if block.id in builtin else 0
            rows.append({
                'id': block.id, 'name': block.name, 'type': block.block_type, 'tag_ids': block.tag_ids.ids,
                'active': block.active, 'usage': count, 'excerpt': text[:200], 'image': image.group(1) if image else '',
                'empty': not text and not image, 'duplicate': block.id in duplicates, 'builtin': block.id in builtin,
                'write_date': block.write_date and block.write_date.isoformat(), 'note': bool(block.note),
            })
        Tag = self.env['mtbg.tours.content.block.tag']
        return {
            'blocks': rows,
            'types': [{'key': key, 'label': label} for key, label in types.items()],
            'tags': [{'id': t.id, 'name': t.name, 'color': t.color} for t in Tag.search([])],
            'can_edit': Block.has_access('write'),
            'can_delete': Block.has_access('unlink'),
            'list_action': self.env.ref('mtbg_tours_content_blocks.action_content_block').id,
        }

    @api.model
    def mtbg_get_block(self, block_id):
        """One block for the page's details panel: its fields and where it is used."""
        block = self._blocks().browse(int(block_id)).exists()
        if not block:
            return False
        usage = self._mtbg_usage_index().get(block.id)
        extension = self._mtbg_builtin().get(block.id)
        used_on = [{'kind': 'extension', 'name': _("The %s extension", extension), 'url': False}] if extension else []
        return {
            'id': block.id, 'name': block.name, 'type': block.block_type, 'tag_ids': block.tag_ids.ids,
            'note': block.note or '', 'active': block.active, 'builtin': bool(extension),
            'used_on': used_on + (self._mtbg_usage_rows(usage) if usage else []),
            'write_date': block.write_date and block.write_date.isoformat(),
            'write_uid': block.write_uid.name,
        }

    @api.model
    def mtbg_save_block(self, block_id, vals):
        """The details panel's fields (saved as they change)."""
        self._check()
        block = self._blocks().browse(int(block_id)).exists()
        if not block:
            raise UserError(_("This block no longer exists."))
        allowed = {k: v for k, v in vals.items() if k in ('name', 'block_type', 'note', 'tag_ids')}
        if 'name' in allowed and not (allowed['name'] or '').strip():
            raise UserError(_("A block needs a name."))
        if 'tag_ids' in allowed:
            allowed['tag_ids'] = [(6, 0, [int(t) for t in allowed['tag_ids']])]
        block.write(allowed)
        return self.mtbg_get_block(block.id)

    @api.model
    def mtbg_create_block(self, name, tag_ids=None, block_type=None):
        self._check()
        block = self._blocks().create({
            'name': (name or '').strip() or _("New block"),
            'body': '<p>%s</p>' % _("Write the shared content here."),
            'block_type': block_type or 'generic',
            'tag_ids': [(6, 0, [int(t) for t in tag_ids or []])],
        })
        return block.id

    @api.model
    def mtbg_used_inside(self, block_ids):
        """The other reusable blocks that contain these blocks ({block name: [names of the blocks containing it]}):
        archiving one empties it there, so the page asks first."""
        usage = self._mtbg_usage_index()
        result = {}
        for block in self._blocks().browse([int(i) for i in block_ids]).exists():
            inside = usage[block.id]['blocks'] if block.id in usage else self._blocks()
            if inside:
                result[block.name] = inside.mapped('name')
        return result

    @api.model
    def mtbg_bulk(self, block_ids, operation, value=None):
        """An action on the blocks ticked in the list: add_tag / remove_tag (``value``: tag id), set_type, archive,
        restore, duplicate, delete (unused blocks only)."""
        self._check()
        blocks = self._blocks().browse([int(i) for i in block_ids]).exists()
        if operation == 'add_tag':
            blocks.write({'tag_ids': [(4, int(value))]})
        elif operation == 'remove_tag':
            blocks.write({'tag_ids': [(3, int(value))]})
        elif operation == 'set_type':
            blocks.write({'block_type': value})
        elif operation == 'archive':
            blocks.write({'active': False})
        elif operation == 'restore':
            blocks.write({'active': True})
        elif operation == 'duplicate':
            return [block.copy({'name': _("%s (copy)", block.name)}).id for block in blocks]
        elif operation == 'delete':
            usage, builtin = self._mtbg_usage_index(), self._mtbg_builtin()
            used = blocks.filtered(lambda b: b.id in usage or b.id in builtin)
            if used:
                raise UserError(_("Still used (or built into an extension), so not deleted: %s. Take it off its pages "
                                  "first, or archive it.",
                                  ", ".join(used.mapped('name'))))
            blocks.unlink()
        else:
            raise UserError(_("Unknown action: %s", operation))
        return True

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------
    @api.model
    def mtbg_save_tag(self, tag_id, name, color=None):
        """Create (``tag_id`` False) or rename / recolour a tag."""
        self._check()
        Tag = self.env['mtbg.tours.content.block.tag']
        name = (name or '').strip()
        if not name:
            raise UserError(_("A tag needs a name."))
        if Tag.search([('name', '=ilike', name), ('id', '!=', tag_id or 0)], limit=1):
            raise UserError(_("A tag named %s already exists.", name))
        vals = {'name': name}
        if color is not None:
            vals['color'] = int(color) % TAG_COLORS
        if tag_id:
            Tag.browse(int(tag_id)).write(vals)
            return int(tag_id)
        vals.setdefault('color', Tag.search_count([]) % TAG_COLORS + 1)
        return Tag.create(vals).id

    @api.model
    def mtbg_delete_tag(self, tag_id):
        """Remove a tag (from every block; the blocks stay)."""
        self._check()
        self.env['mtbg.tours.content.block.tag'].browse(int(tag_id)).unlink()
        return True
