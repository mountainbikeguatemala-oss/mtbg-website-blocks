"""Settings › Zoho: the one login (its Set up Zoho wizard), what the token may do per app, and per app its organization
and two switches (On, Writes allowed), all off by default. Extensions add their own blocks to the section."""
import json

from odoo import api, fields, models

from ..services.client import APPS, Zoho


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    mtbg_zoho_books_enabled = fields.Boolean(string='Zoho Books: On', config_parameter='mtbg_tours.zoho_books_enabled',
                                             groups='base.group_system')
    mtbg_zoho_books_writes = fields.Boolean(string='Zoho Books: Writes allowed', config_parameter='mtbg_tours.zoho_books_writes',
                                            groups='base.group_system')
    mtbg_zoho_expense_enabled = fields.Boolean(string='Zoho Expense: On', config_parameter='mtbg_tours.zoho_expense_enabled',
                                               groups='base.group_system')
    mtbg_zoho_expense_writes = fields.Boolean(string='Zoho Expense: Writes allowed',
                                              config_parameter='mtbg_tours.zoho_expense_writes', groups='base.group_system')
    mtbg_zoho_expense_org_id = fields.Char(string='Zoho Expense Organization ID',
                                           config_parameter='mtbg_tours.zoho_expense_org_id', groups='base.group_system')
    mtbg_zoho_shifts_enabled = fields.Boolean(string='Zoho Shifts: On', config_parameter='mtbg_tours.zoho_shifts_enabled',
                                              groups='base.group_system')
    mtbg_zoho_shifts_writes = fields.Boolean(string='Zoho Shifts: Writes allowed',
                                             config_parameter='mtbg_tours.zoho_shifts_writes', groups='base.group_system')
    mtbg_zoho_shifts_org_id = fields.Char(string='Zoho Shifts Organization ID',
                                          config_parameter='mtbg_tours.zoho_shifts_org_id', groups='base.group_system')
    mtbg_zoho_rate_limit = fields.Integer(string='Calls per Minute (per app)', config_parameter='mtbg_tours.zoho_rate_limit',
                                          default=90, groups='base.group_system',
                                          help="Zoho Books allows 100 calls a minute per organization")
    mtbg_zoho_connection_info = fields.Text(string='Connection', compute='_compute_mtbg_zoho_info')
    mtbg_zoho_access_info = fields.Text(string='Access per App', compute='_compute_mtbg_zoho_info')
    mtbg_zoho_scopes_needed = fields.Char(string='Scopes for a New Grant Code', compute='_compute_mtbg_zoho_info')

    @api.model
    def _mtbg_zoho_scopes(self):
        """Every app's scopes, for the self client's Generate Code."""
        return ','.join(APPS[app]['scopes'] for app in APPS)

    def _compute_mtbg_zoho_info(self):
        _ = self.env._
        icp = self.env['ir.config_parameter'].sudo()
        books = Zoho(self.env, 'books')
        if books.connected:
            info = _("Connected: %(server)s, Zoho Books organization %(org)s (every Zoho link uses this login).",
                     server=icp.get_param('mtbg_tours.zoho_accounts_url') or 'https://accounts.zoho.com',
                     org=books.org_id or '-')
            granted = icp.get_param('mtbg_tours.zoho_granted_scopes')
            if granted:
                info += "\n" + _("Scopes Zoho reported for the token: %s", granted)
        else:
            info = _("Not connected: Set up Zoho, below.")
        try:
            checks = json.loads(icp.get_param('mtbg_tours.zoho_access_check') or '{}')
        except ValueError:
            checks = {}
        lines = []
        for app, spec in APPS.items():
            check = checks.get(app)
            state = (_("ok") if check['ok'] else check['message']) if check else _("not checked")
            switches = _("on") if Zoho(self.env, app).enabled else _("off")
            lines.append(f"{spec['label']}: {state} ({switches})" + (f" · {check['at']}" if check else ''))
        for record in self:
            record.mtbg_zoho_connection_info = info
            record.mtbg_zoho_access_info = "\n".join(lines)
            record.mtbg_zoho_scopes_needed = self._mtbg_zoho_scopes()

    def action_mtbg_zoho_check_access(self):
        """Save, then read once from each app: what the token may do (a missing scope shows here)."""
        self.execute()
        checks = {app: dict(Zoho(self.env, app).probe(), at=fields.Datetime.to_string(fields.Datetime.now()))
                  for app in APPS}
        self.env['ir.config_parameter'].sudo().set_param('mtbg_tours.zoho_access_check', json.dumps(checks))
        return {'type': 'ir.actions.client', 'tag': 'reload'}


class ResConfigSettingsBooksExpenses(models.TransientModel):
    """Settings › Zoho, Zoho Books: expenses (Import & Sync, here since 0.2.0): the first sync's status, the last sync,
    the categories; Run first sync and Sync now (buttons: no Settings Save needed)."""
    _inherit = 'res.config.settings'

    mtbg_zoho_expenses_sync_info = fields.Text(string='Expenses Sync', compute='_compute_mtbg_zoho_expenses_sync_info')

    def _compute_mtbg_zoho_expenses_sync_info(self):
        from .books_expenses import FIRST_SYNC, LAST_SYNC
        icp = self.env['ir.config_parameter'].sudo()
        first, last = icp.get_param(FIRST_SYNC), icp.get_param(LAST_SYNC)
        Account = self.env['mtbg.zoho.books.account'].sudo()
        labels = dict(Account._mtbg_destination_selection())
        synced = Account.search([('sync', '=', True)])
        _ = self.env._
        lines = [_("First sync: done %s (UTC)", first) if first else _("First sync: not run yet"),
                 _("Last sync: %s (UTC)", last) if last else _("Last sync: never")]
        lines += [f"· {a.name} → {labels.get(a.destination, a.destination)}"
                  f"{' (' + a.target.display_name + ')' if a.target else ''}" for a in synced]
        for record in self:
            record.mtbg_zoho_expenses_sync_info = "\n".join(lines)

    def action_mtbg_zoho_expenses_first_sync(self):
        run = self.env['mtbg.zoho.books.import'].create({})
        return {'type': 'ir.actions.act_window', 'res_model': run._name, 'res_id': run.id, 'view_mode': 'form',
                'views': [(False, 'form')], 'target': 'current'}

    def action_mtbg_zoho_expenses_sync_now(self):
        counts = self.env['mtbg.zoho.books.import']._mtbg_sync_changes()
        _ = self.env._
        message = _("Run the first sync first (Zoho Books on).") if counts is False else _(
            "%(created)s new, %(updated)s updated, %(skipped)s skipped.", **counts)
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': _("Zoho Books expenses"), 'message': message,
                           'type': 'warning' if counts is False else 'success',
                           'next': {'type': 'ir.actions.client', 'tag': 'reload'}}}

    def action_mtbg_zoho_expense_categories(self):
        return self.env['ir.actions.actions']._for_xml_id('zoho_connector.action_books_accounts')
