"""External references: which Zoho record an Odoo record is, per app and kind. The business records carry no Zoho id;
the Zoho links keep theirs here.

    ref = env['mtbg.zoho.ref']._mtbg_find(departure, 'books', 'project')
    ref.zoho_id          # the project's id
    ref.zoho_parent_id   # its customer's (contact) id
    env['mtbg.zoho.ref']._mtbg_set(departure, 'books', 'project', zoho_id='…', zoho_parent_id='…')

Each extension using the connector keeps its own kinds here (e.g. books/project for a departure, books/vendor for a
vendor contact, shifts/time_entry for a time entry); the connector knows none of them.
"""
import logging
from datetime import timedelta

import psycopg2

from odoo import _, api, fields, models
from odoo.exceptions import UserError

REF_STATES = [('waiting', 'Waiting'), ('done', 'Synced'), ('error', 'Error'), ('skipped', 'Skipped')]
SYSTEMS = [('books', 'Zoho Books'), ('expense', 'Zoho Expense'), ('shifts', 'Zoho Shifts'), ('crm', 'Zoho CRM (history)')]
RETRY_MAX_HOURS = 24  # an error is retried after 1, 2, 4… hours, at most a day apart (owner: no one has to press Retry)


_logger = logging.getLogger(__name__)


class MtbgZohoRef(models.Model):
    _name = 'mtbg.zoho.ref'
    _description = 'Zoho reference'
    _order = 'write_date desc, id desc'
    _rec_name = 'name'

    system = fields.Selection(SYSTEMS, string='Zoho App', required=True, index=True)
    kind = fields.Char(required=True, index=True, help="What the Zoho record is (project, vendor, wage_expense...)")
    res_model = fields.Char(string='Odoo Model', required=True, index=True)
    res_id = fields.Many2oneReference(string='Odoo Record ID', model_field='res_model', required=True, index=True)
    name = fields.Char(help="The Odoo record's name when the reference was written")
    zoho_id = fields.Char(string='Zoho ID', index=True, copy=False)
    zoho_parent_id = fields.Char(string='Zoho Parent ID', copy=False,
                                 help="A second Zoho id the reference needs (a project's customer)")
    zoho_scope_id = fields.Char(string='Zoho Scope ID', copy=False, index='btree_not_null',
                                help="A third Zoho id the reference needs (an expense line's account)")
    state = fields.Selection(REF_STATES, default='waiting', required=True, index=True)
    error = fields.Char(copy=False)
    last_sync = fields.Datetime(string='Last Sync', copy=False)
    fingerprint = fields.Char(copy=False, help="A hash of what was sent last (sent again only when it changes)")
    retry_count = fields.Integer(string='Errors in a row', copy=False, readonly=True)
    retry_after = fields.Datetime(string='Next retry', copy=False, readonly=True,
                                  help="An error is tried again by itself from then (empty: on the next run)")
    zoho_url = fields.Char(string='Open in Zoho', compute='_compute_zoho_url')

    _ref_uniq = models.Constraint('UNIQUE(system, kind, res_model, res_id)',
                                  'An Odoo record has one Zoho reference of each kind.')

    def _compute_zoho_url(self):
        icp = self.env['ir.config_parameter'].sudo()
        accounts = icp.get_param('mtbg_tours.zoho_accounts_url') or 'https://accounts.zoho.com'
        domain = accounts.split('//')[-1].strip('/').removeprefix('accounts.') or 'zoho.com'
        books_org = icp.get_param('mtbg_tours.zoho_org_id') or ''
        paths = {('books', 'project'): 'projects', ('books', 'vendor'): 'contacts', ('books', 'wage_expense'): 'expenses',
                 ('books', 'vehicle_expense'): 'expenses'}
        for ref in self:
            path = paths.get((ref.system, ref.kind))
            # a vehicle expense's reference is one line of the Zoho expense: the page is the expense's
            zoho_id = ref.zoho_parent_id if ref.kind == 'vehicle_expense' else ref.zoho_id
            ref.zoho_url = f"https://books.{domain}/app/{books_org}#/{path}/{zoho_id}" if path and zoho_id else False

    # ------------------------------------------------------------------ API for the Zoho links
    @api.model
    def _mtbg_find(self, record, system, kind):
        """The reference of ``record`` (one record) for that app and kind, or an empty recordset."""
        if not record:
            return self.browse()
        return self.sudo().search([('system', '=', system), ('kind', '=', kind), ('res_model', '=', record._name),
                                   ('res_id', '=', record.id)], limit=1)

    @api.model
    def _mtbg_set(self, record, system, kind, **vals):
        """Create or update the reference; a ``done`` one gets its sync time."""
        ref = self._mtbg_find(record, system, kind)
        if vals.get('state') == 'error':  # tried again by itself, later each time
            count = (ref.retry_count or 0) + 1
            vals.update(retry_count=count, retry_after=fields.Datetime.now()
                        + timedelta(hours=min(2 ** (count - 1), RETRY_MAX_HOURS)))
        elif 'state' in vals:
            vals.update(retry_count=0, retry_after=False)
        if vals.get('state') == 'done':
            vals.setdefault('last_sync', fields.Datetime.now())
            vals.setdefault('error', False)
        vals.setdefault('name', (record.display_name or '')[:250])
        if ref:
            ref.write(vals)
            return ref
        return self.sudo().create(dict(vals, system=system, kind=kind, res_model=record._name, res_id=record.id))

    @api.model
    def _mtbg_records(self, system, kind, model, zoho_id):
        """The Odoo records that are this Zoho record."""
        refs = self.sudo().search([('system', '=', system), ('kind', '=', kind), ('res_model', '=', model),
                                   ('zoho_id', '=', zoho_id)])
        return self.env[model].browse(refs.mapped('res_id')).exists()

    def _mtbg_lock(self):
        """This reference locked for this transaction (one send at a time: a run, the save's run and a button may
        meet), re-read after; False when another transaction holds it (it is sending: skip, never twice)."""
        self.ensure_one()
        try:
            with self.env.cr.savepoint():
                self.env.cr.execute(f'SELECT id FROM "{self._table}" WHERE id = %s FOR UPDATE NOWAIT', [self.id])
        except psycopg2.errors.LockNotAvailable:
            _logger.info("Zoho reference %s is being sent by another run: skipped", self.id)
            return False
        self.invalidate_recordset()
        return True

    def _mtbg_retry_due(self):
        """The errors whose next retry has come (an error from before 0.3.7 has none: retried on the next run)."""
        now = fields.Datetime.now()
        return self.filtered(lambda r: r.state == 'error' and (not r.retry_after or r.retry_after <= now))

    def _mtbg_retry(self):
        """Try these references again now. Each extension retries its own kinds (it overrides this, handles its
        references and passes the others to super()); returns the references nobody knew how to retry."""
        return self

    def action_mtbg_retry_errors(self):
        """The References list's "Retry errors": the selected errors tried again now."""
        if not self._mtbg_zoho_manager():
            raise UserError(_("Only Zoho managers can retry Zoho errors."))
        errors = self.filtered(lambda r: r.state == 'error')
        errors.sudo().write({'retry_after': False})
        errors.sudo()._mtbg_retry()
        return True

    @api.model
    def _mtbg_zoho_manager(self):
        """Whether the user may retry and open the sync's records: administrators; extensions add their managers."""
        return self.env.user.has_group('base.group_system')

    def action_mtbg_open_record(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': self.res_model, 'res_id': self.res_id, 'view_mode': 'form'}
