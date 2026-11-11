"""Import / Export on a settings page (the lists' cog opens the page): a model's records out as a spreadsheet (its list
view's columns, every record the user may read) and in through Odoo's import."""
import base64
import csv
import io

from lxml import etree

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

SKIPPED = ('binary', 'image', 'html', 'properties', 'properties_definition', 'json')


class MtbgDataTransfer(models.AbstractModel):
    _name = 'mtbg.data.transfer'
    _description = 'Import / Export'

    @api.model
    def _mtbg_export_fields(self, model):
        """The list view's visible columns (stored or not, but exportable), else the name."""
        Model = self.env[model]
        arch = etree.fromstring(Model.get_view(view_type='list')['arch'])
        names = []
        for node in arch.iter('field'):
            name = node.get('name')
            field = Model._fields.get(name)
            if not field or name in names or field.type in SKIPPED or node.getparent().tag != 'list':
                continue
            if node.get('column_invisible') in ('1', 'True') or node.get('invisible') in ('1', 'True'):
                continue
            names.append(name)
        return names or [Model._rec_name or 'id']

    @api.model
    def mtbg_export(self, model):
        """Every record of ``model`` the user may read, as a CSV download: its url."""
        if model not in self.env:
            raise AccessError(_("Nothing to export."))
        Model = self.env[model]
        Model.check_access('read')
        names = self._mtbg_export_fields(model)
        records = Model.search([])
        rows = records.export_data(names).get('datas', [])
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow([Model._fields[n]._description_string(self.env) for n in names])
        writer.writerows(rows)
        stamp = fields.Datetime.context_timestamp(self, fields.Datetime.now()).strftime('%Y-%m-%d')
        attachment = self.env['ir.attachment'].create({
            'name': f"{Model._description} {stamp}.csv", 'type': 'binary', 'mimetype': 'text/csv',
            'datas': base64.b64encode(out.getvalue().encode('utf-8-sig')),
        })
        return {'url': f"/web/content/{attachment.id}?download=true", 'count': len(records)}
