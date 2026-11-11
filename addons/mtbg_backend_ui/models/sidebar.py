"""The list's side bar (as the Resources & Equipment page has): a model's records as a tree with their counts, beside
its list (``js_class="mtbg_sidebar_list"``, the model inheriting ``mtbg.sidebar.mixin``). A click on a branch shows its
records only; again, all. The counts follow the search.

    _mtbg_sidebar_sections(domain)  [{key, label, icon, sequence?, nodes: [node]}]   (super() + yours: an extension adds
                                    a section; ``sequence`` places it, 100 by default)
    node                            {key, label, count, domain, color?, hint?, children?: [node]}
    _mtbg_settings_xmlid()          the model's settings page (the list's cog opens it; Import / Export there)

Helpers build the usual nodes: a field's values (``_mtbg_sidebar_field``), a many2one's records with their own
records under each (``_mtbg_sidebar_parents``).
"""
from lxml import etree

from odoo import api, models

CHILDREN_LIMIT = 60
# fields never offered as a list column (the chatter's, the activities', technical ones)
HIDDEN_PREFIXES = ('message_', 'activity_', 'website_message', '__')
HIDDEN_TYPES = ('binary', 'html', 'one2many', 'json', 'properties', 'properties_definition', 'reference',
                'many2one_reference')


class MtbgSidebarMixin(models.AbstractModel):
    _name = 'mtbg.sidebar.mixin'
    _description = 'List side bar'

    @api.model
    def _mtbg_sidebar_sections(self, domain):
        """The side bar's sections for the records of ``domain`` (the search)."""
        return []

    @api.model
    def _mtbg_settings_xmlid(self):
        return False

    @api.model
    def _mtbg_list_extra_field(self, name, field):
        """Whether the list's column picker offers ``field`` (any field of the record a person can read)."""
        return not (name in ('id', 'display_name') or name.startswith(HIDDEN_PREFIXES) or field.type in HIDDEN_TYPES
                    or field.groups or not field.string)

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        """A side bar list offers every field of its records in its column picker (hidden until picked)."""
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type == 'list' and arch is not None and arch.get('js_class', '') == 'mtbg_sidebar_list':
            present = {node.get('name') for node in arch.iter('field')}
            extra = [(field._description_string(self.env), name) for name, field in self._fields.items()
                     if name not in present and self._mtbg_list_extra_field(name, field)]
            for _label, name in sorted(extra, key=lambda ln: ln[0].lower()):
                node = etree.Element('field', name=name, optional='hide')
                if self._fields[name].type == 'many2many':
                    node.set('widget', 'many2many_tags')
                arch.append(node)
        return arch, view

    @api.model
    def _mtbg_settings_action_id(self):
        """The settings page's action (the cog's), if the model has one."""
        xmlid = self._mtbg_settings_xmlid()
        action = xmlid and self.env.ref(xmlid, raise_if_not_found=False)
        return action.id if action else False

    @api.model
    def mtbg_sidebar(self, domain):
        """The side bar: its sections (empty ones left out), the total, the settings page (the list's cog). Filters
        and groups are the search's (its Filters and Group By)."""
        domain = list(domain or [])
        sections = [s for s in self._mtbg_sidebar_sections(domain) if s.get('nodes')]
        sections.sort(key=lambda sec: sec.get('sequence', 100))  # each extension places its folders
        return {'sections': sections, 'total': self.search_count(domain),
                'settings_action': self._mtbg_settings_action_id()}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @api.model
    def _mtbg_sidebar_nodes(self, domain, specs):
        """Nodes from (key, label, node domain[, colour]) specs, each counted in ``domain`` (the empty ones left
        out)."""
        nodes = []
        for spec in specs:
            key, label, node_domain = spec[:3]
            count = self.search_count(list(domain) + list(node_domain))
            if count:
                nodes.append({'key': key, 'label': label, 'count': count, 'domain': list(node_domain),
                              'color': spec[3] if len(spec) > 3 else False})
        return nodes

    @api.model
    def _mtbg_sidebar_field(self, domain, field_name, colors=None, keep_empty=False):
        """A node per value of a selection / many2one field, with its count (in the field's order)."""
        field = self._fields[field_name]
        counts = dict(self._read_group(domain, [field_name], ['__count']))
        colors = colors or {}
        if field.type == 'selection':
            values = [(key, label) for key, label in field._description_selection(self.env)]
        else:
            values = [(rec, rec.display_name) for rec in counts if rec]
        nodes = []
        for value, label in values:
            count = counts.get(value, 0)
            if not count and not keep_empty:
                continue
            raw = value.id if field.type == 'many2one' else value
            nodes.append({'key': f"{field_name}:{raw}", 'label': label, 'count': count,
                          'domain': [(field_name, '=', raw)], 'color': colors.get(raw) or False})
        return nodes

    @api.model
    def _mtbg_sidebar_parents(self, domain, field_name, child_label=None, child_domain=None, child_order=None):
        """A node per record of many2one ``field_name`` (its count), the records of ``domain`` under it, or what
        ``child_domain(record)`` says (e.g. a tour, its departures)."""
        nodes = []
        counts = self._read_group(domain, [field_name], ['__count'])
        for parent, count in sorted(counts, key=lambda pc: (pc[0].display_name or '').lower()):
            if not parent:
                continue
            records = self.search(domain + [(field_name, '=', parent.id)], order=child_order, limit=CHILDREN_LIMIT)
            children = []
            for rec in records:
                children.append({'key': f"id:{rec.id}", 'label': child_label(rec) if child_label else rec.display_name,
                                 'count': False, 'domain': [('id', '=', rec.id)]})
            nodes.append({'key': f"{field_name}:{parent.id}", 'label': parent.display_name, 'count': count,
                          'domain': [(field_name, '=', parent.id)], 'children': children})
        return nodes
