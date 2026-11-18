"""Import & Sync from Zoho Books: one wizard for every expense (owner, 2026-11-06: "a general wizard and rule for ALL
EXPENSES ... anywhere we bring in expenses into the system"; Zoho 0.4.0). Zoho Connector's since 0.2.0 (2026-11-18,
"zoho connector should be global"): any site can read its categories and run it; the destinations come from the
extensions installed (without any: Skip and Internal only).

* **Expense Categories** (``mtbg.zoho.books.account``): Zoho Books' expense accounts (read from it), each with where
  its expenses go here (its destination: a vehicle unit, staff expenses and tour costs, internal, skip) and, for some,
  which record (a unit). Extensions bring their destinations (``_mtbg_destinations``) and suggest them
  (``_mtbg_suggest``): Zoho Unit Expenses the vehicles, Zoho Staff Books staff expenses and tour costs.
* **A run** (``mtbg.zoho.books.import``): the categories picked and a first day, then Import, in the background a
  few expenses a step (the client keeps Zoho's pace): each account's expenses listed, each expense read
  (GET expenses/{id}) for its lines; each line on a picked account goes to its destination's ``_mtbg_import_line``,
  found again by its Zoho ids (``expense_id:line_item_id``, the references), so a run again updates and never adds
  twice. A line its destination is not sure of waits in the run's review list (pick its record, or Skip).
* Read only: every call is a GET, no receipt is downloaded (each line's View in Zoho Books shows them). An expense Odoo
  sent itself (a Staff App expense, a unit expense, a payroll payment) is never brought back in.
"""
import json
import logging
from datetime import datetime, timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..services.client import Zoho, ZohoError

_logger = logging.getLogger(__name__)

PER_PAGE = 200
MAX_PAGES = 100
STEP = 10  # expenses read per background step
# what Odoo sends to Zoho Books itself: an expense with one of these references is never brought in
FIRST_SYNC = 'mtbg_tours.zoho_books_expenses_first_sync'  # when the first sync was done (UTC)
LAST_SYNC = 'mtbg_tours.zoho_books_expenses_last_sync'  # the last pull's time (UTC): the next reads changes since
SENT_KINDS = ('staff_expense', 'wage_expense', 'wage_payment', 'reimbursement_payment', 'vehicle_expense_out',
              'reimbursement', 'payment_fee')
# kinds made per record they are for, "<prefix><id>" (a pay stub's wages of one vehicle: vehicle_wage_payment:<unit id>)
SENT_PREFIXES = ('vehicle_wage_payment:',)


class MtbgZohoBooksAccount(models.Model):
    _name = 'mtbg.zoho.books.account'
    _description = 'Zoho Books expense category and where its expenses go'
    _order = 'name, id'
    _rec_name = 'name'

    zoho_account_id = fields.Char(string='Zoho Account ID', required=True, index=True)
    name = fields.Char(string='Zoho Books Category', required=True)
    destination = fields.Selection(selection='_mtbg_destination_selection', string='Goes To', default='skip',
                                   required=True)
    target = fields.Reference(selection='_mtbg_target_selection', string='Record',
                              help="Where its expenses go when that is one record (a vehicle)")
    active = fields.Boolean(default=True)
    note = fields.Char(readonly=True, help="Why it was suggested")
    sync = fields.Boolean(string='Kept in Sync', readonly=True,
                          help="Brought in by a first sync: its new and changed expenses come in by themselves")

    _account_uniq = models.Constraint('UNIQUE(zoho_account_id)', 'Each Zoho Books account once.')

    # ------------------------------------------------------------------ the hooks (extensions)
    @api.model
    def _mtbg_destinations(self):
        """[{key, label, target (model or False)}]: where expenses can go. Extensions add theirs."""
        return [{'key': 'skip', 'label': self.env._("Skip (not brought in)"), 'target': False},
                {'key': 'internal', 'label': self.env._("Internal (not brought in, counted)"), 'target': False}]

    @api.model
    def _mtbg_destination_selection(self):
        return [(d['key'], d['label']) for d in self._mtbg_destinations() if not d.get('hidden')]

    @api.model
    def _mtbg_target_selection(self):
        models_ = {}
        for d in self._mtbg_destinations():
            if d.get('target') and d['target'] in self.env:
                models_[d['target']] = self.env[d['target']]._description
        return sorted(models_.items())

    def _mtbg_suggest(self):
        """{destination, target, note} for a new category (or {}): extensions suggest theirs."""
        self.ensure_one()
        return {}

    def _mtbg_import_line(self, run, expense, line):
        """One Zoho Books expense line of this category: ('created' | 'updated' | 'review' | 'skipped', note).
        ``line``: the GET expenses/{id} line item ({line_item_id, account_id, amount, description...}).
        Extensions take their destinations; the base ones bring nothing in."""
        self.ensure_one()
        return 'skipped', ''

    def _mtbg_apply_review(self, review):
        """A reviewed line, its record picked (``review.target``): as ``_mtbg_import_line``."""
        self.ensure_one()
        return 'skipped', ''

    # ------------------------------------------------------------------ reading the categories
    @api.model
    def mtbg_read_accounts(self):
        """Zoho Books' expense accounts into the list (new ones with their suggested destination). Read only."""
        books = Zoho(self.env, 'books')
        if not books.enabled:
            raise UserError(self.env._("Switch Zoho Books on first (Settings › Zoho)."))
        accounts = []
        try:
            for page in range(1, 20):
                body = books.request('GET', 'chartofaccounts', params={
                    'filter_by': 'AccountType.Expense', 'page': page, 'per_page': PER_PAGE})
                accounts += body.get('chartofaccounts') or []
                if not (body.get('page_context') or {}).get('has_more_page'):
                    break
        except ZohoError as error:
            raise UserError(self.env._("Zoho Books: %s", error)) from error
        Account = self.sudo().with_context(active_test=False)
        known = {a.zoho_account_id: a for a in Account.search([])}
        for row in accounts:
            account_id, name = str(row.get('account_id') or ''), row.get('account_name') or ''
            if not account_id:
                continue
            if account_id in known:
                known[account_id].name = name or known[account_id].name
                continue
            account = Account.create({'zoho_account_id': account_id, 'name': name or account_id})
            suggestion = account._mtbg_suggest()
            if suggestion:
                account.write(suggestion)
        return len(accounts)

    def action_mtbg_read_accounts(self):
        count = self.mtbg_read_accounts()
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': self.env._("Zoho Books"), 'message': self.env._("%s expense categories read.", count),
                           'type': 'success', 'next': {'type': 'ir.actions.client', 'tag': 'reload'}}}


class MtbgZohoBooksImport(models.Model):
    _name = 'mtbg.zoho.books.import'
    _description = 'Import & Sync from Zoho Books (a run)'
    _order = 'id desc'

    name = fields.Char(compute='_compute_name')
    date_from = fields.Date(string='From', required=True, default=lambda self: fields.Date.today() - timedelta(days=60))
    date_to = fields.Date(string='To', help="Empty: today")
    account_ids = fields.Many2many('mtbg.zoho.books.account', 'mtbg_zoho_books_import_account_rel',
                                   string='Categories', help="The Zoho Books expense categories to bring in")
    state = fields.Selection([('draft', 'New'), ('reading', 'Reading…'), ('importing', 'Importing…'),
                              ('done', 'Done'), ('error', 'Error')], default='draft', required=True, readonly=True)
    message = fields.Text(readonly=True)
    queue = fields.Text(readonly=True)  # the expense ids still to read (JSON)
    expense_total = fields.Integer(string='Expenses Found', readonly=True)
    expense_done = fields.Integer(string='Expenses Read', readonly=True)
    created_count = fields.Integer(string='New Lines', readonly=True)
    updated_count = fields.Integer(string='Found Again', readonly=True)
    skipped_count = fields.Integer(string='Skipped', readonly=True)
    review_ids = fields.One2many('mtbg.zoho.books.review', 'run_id', string='To Review',
                                 domain=[('state', '=', 'review')])
    all_review_ids = fields.One2many('mtbg.zoho.books.review', 'run_id', string='Reviewed Lines')
    review_count = fields.Integer(compute='_compute_review_count', string='To Review')
    finished_on = fields.Datetime(readonly=True)

    def _compute_name(self):
        for run in self:
            run.name = self.env._("Import & Sync from %s", run.date_from) if run.date_from else self.env._("Import")

    def _compute_review_count(self):
        for run in self:
            run.review_count = len(run.review_ids)

    def _check(self):
        # who may: the Zoho managers (administrators; extensions add theirs, ``mtbg.zoho.ref._mtbg_zoho_manager``)
        if not self.env.su and not self.env['mtbg.zoho.ref']._mtbg_zoho_manager():
            raise UserError(self.env._("Only a Zoho manager imports from Zoho Books."))

    def action_import(self):
        """Read the picked categories' expenses in the background (a few minutes)."""
        self._check()
        self.ensure_one()
        if self.state in ('reading', 'importing'):
            raise UserError(self.env._("It is running: reload the page in a minute."))
        if not self.account_ids:
            raise UserError(self.env._("Pick the Zoho Books categories to bring in."))
        if not Zoho(self.env, 'books').enabled:
            raise UserError(self.env._("Switch Zoho Books on first (Settings › Zoho). Writes allowed can stay off."))
        self.write({'state': 'reading', 'queue': '[]', 'expense_total': 0, 'expense_done': 0, 'created_count': 0,
                    'updated_count': 0, 'skipped_count': 0, 'message': self.env._("Reading Zoho Books…")})
        self._mtbg_trigger()
        return True

    def action_refresh(self):
        return True

    def action_apply_reviews(self):
        """The review list's picked records: their lines brought in."""
        self._check()
        stats = {'created': 0, 'updated': 0, 'skipped': 0}
        for review in self.review_ids.filtered('target'):
            what, note = review.account_id._mtbg_apply_review(review)
            if what in stats:
                stats[what] += 1
            review.write({'state': 'done' if what in ('created', 'updated') else 'review', 'note': note or review.note})
        self.write({'created_count': self.created_count + stats['created'],
                    'updated_count': self.updated_count + stats['updated']})
        return True

    def _mtbg_trigger(self):
        cron = self.env.ref('zoho_connector.cron_zoho_books_import', raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger()

    @api.model
    def _mtbg_cron(self):
        from odoo.modules.module import current_test
        for run in self.sudo().search([('state', 'in', ('reading', 'importing'))], order='id'):
            try:
                with self.env.cr.savepoint():
                    if run._mtbg_step():
                        run._mtbg_trigger()
            except (ZohoError, UserError) as error:
                self.env.invalidate_all()
                run.write({'state': 'error', 'message': str(error)[:2000]})
            if not current_test:
                self.env.cr.commit()

    def _mtbg_run_all(self):
        """Every step now (tests)."""
        if self.state not in ('reading', 'importing'):
            self.action_import()
        for _i in range(1000):
            if self.state not in ('reading', 'importing'):
                break
            self._mtbg_cron()
        return self

    def _mtbg_step(self):
        """One background step. True: more to do."""
        self.ensure_one()
        books = Zoho(self.env, 'books')
        if self.state == 'reading':
            # Zoho Books ignores account_id on the expense list: one listing, kept to the picked categories here
            accounts = {a.zoho_account_id: a for a in self.account_ids}
            end = fields.Date.to_string(self.date_to or fields.Date.context_today(self))
            ids = self._mtbg_list_ids(books, accounts, {
                'date_start': fields.Date.to_string(self.date_from), 'date_end': end, 'sort_column': 'date'},
                date_from=fields.Date.to_string(self.date_from), date_to=end)
            ids = list(dict.fromkeys(ids))
            self.write({'state': 'importing', 'queue': json.dumps(ids), 'expense_total': len(ids),
                        'message': self.env._("%s expenses to read…", len(ids))})
            return True
        queue = json.loads(self.queue or '[]')
        todo, rest = queue[:STEP], queue[STEP:]
        accounts = {a.zoho_account_id: a for a in self.account_ids}
        counts = {'created': 0, 'updated': 0, 'skipped': 0}
        for expense_id in todo:
            self._mtbg_take(books, expense_id, accounts, counts)
        vals = {'queue': json.dumps(rest), 'expense_done': self.expense_done + len(todo),
                'created_count': self.created_count + counts['created'],
                'updated_count': self.updated_count + counts['updated'],
                'skipped_count': self.skipped_count + counts['skipped']}
        if rest:
            vals['message'] = self.env._("%(done)s of %(total)s expenses read…", done=vals['expense_done'],
                                         total=self.expense_total)
        else:
            # the first sync done: its categories are kept in sync from now on (the hourly sync)
            self.account_ids.sudo().write({'sync': True})
            icp = self.env['ir.config_parameter'].sudo()
            now = fields.Datetime.to_string(fields.Datetime.now())
            if not icp.get_param(FIRST_SYNC):
                icp.set_param(FIRST_SYNC, now)
            icp.set_param(LAST_SYNC, now)
            vals.update(state='done', finished_on=fields.Datetime.now(), message=self.env._(
                "Done: %(new)s new lines, %(again)s found again, %(skip)s skipped; %(review)s to review.",
                new=vals['created_count'], again=vals['updated_count'], skip=vals['skipped_count'],
                review=len(self.review_ids)))
        self.write(vals)
        return bool(rest)

    def _mtbg_list_ids(self, books, accounts, params, date_from=None, date_to=None, modified_since=None):
        """The expense ids on ``accounts`` from Zoho Books' expense list. The list ignores account_id (and may
        ignore the date filters), so each entry is kept here by its category: its account id or name, or
        "Itemized" (several lines: read to see them; so is an entry without either). Only those are read one by
        one afterwards."""
        names = {(a.name or '').strip().lower() for a in accounts.values()}
        ids = []
        for page in range(1, MAX_PAGES + 1):
            body = books.request('GET', 'expenses', params=dict(params, filter_by='Status.All', page=page,
                                                                 per_page=PER_PAGE))
            for entry in body.get('expenses') or []:
                if not entry.get('expense_id'):
                    continue
                name = (entry.get('account_name') or '').strip().lower()
                known = entry.get('account_id') or name
                if known and not (str(entry.get('account_id') or '') in accounts or name in names
                                  or name == 'itemized'):
                    continue
                day = entry.get('date') or ''
                if (date_from and day and day < date_from) or (date_to and day and day > date_to):
                    continue
                if modified_since and entry.get('last_modified_time'):
                    try:
                        changed = datetime.strptime(entry['last_modified_time'][:19], '%Y-%m-%dT%H:%M:%S')
                        offset = entry['last_modified_time'][19:]
                        if offset and offset[0] in '+-':
                            sign = 1 if offset[0] == '+' else -1
                            hours, minutes = int(offset[1:3]), int(offset[-2:])
                            changed -= sign * timedelta(hours=hours, minutes=minutes)
                        if changed < modified_since:
                            continue
                    except ValueError:
                        pass
                ids.append(str(entry['expense_id']))
            if not (body.get('page_context') or {}).get('has_more_page'):
                break
        return list(dict.fromkeys(ids))

    def _mtbg_take(self, books, expense_id, accounts, counts):
        """One Zoho Books expense (read again: GET expenses/{id}): each line on ``accounts`` to its destination;
        one Odoo sent itself is never brought back in (no loop)."""
        expense = books.request('GET', f'expenses/{expense_id}').get('expense') or {}
        if not expense:
            return
        Ref = self.env['mtbg.zoho.ref'].sudo()
        kinds = ['|'] * len(SENT_PREFIXES) + [('kind', 'in', SENT_KINDS)] + [('kind', '=like', f"{prefix}%")
                                                                           for prefix in SENT_PREFIXES]
        sent = Ref.search_count([('system', '=', 'books')] + kinds + [
                                 ('zoho_id', 'in', [str(expense_id)] + [f"{expense_id}:{l.get('line_item_id')}"
                                                                        for l in expense.get('line_items') or []])])
        if sent:
            counts['skipped'] += 1
            return
        for line in expense.get('line_items') or [dict(expense, line_item_id='')]:
            account = accounts.get(str(line.get('account_id') or ''))
            if not account:
                continue
            what, note = account._mtbg_import_line(self, expense, line)
            if what == 'review':
                self.env['mtbg.zoho.books.review']._mtbg_add(self, account, expense, line, note)
            elif what in counts:
                counts[what] += 1

    # ------------------------------------------------------------------ from then on: the hourly sync
    @api.model
    def _mtbg_sync_changes(self):
        """Cron (hourly) and Settings › Zoho › Sync now, once the first sync is done: the expenses created or
        changed in Zoho Books since the last pull (last_modified_time) on the categories kept in sync, each to its
        destination (by its references: updated, never twice); no receipt read. Returns the counts, or False."""
        icp = self.env['ir.config_parameter'].sudo()
        books = Zoho(self.env, 'books')
        accounts = {a.zoho_account_id: a for a in self.env['mtbg.zoho.books.account'].sudo().search([('sync', '=', True)])}
        if not icp.get_param(FIRST_SYNC) or not books.enabled or not accounts:
            return False
        since = fields.Datetime.to_datetime(icp.get_param(LAST_SYNC) or icp.get_param(FIRST_SYNC))
        started = fields.Datetime.now()
        # the run that holds what is to review (the latest one)
        run = self.sudo().search([('state', '=', 'done')], limit=1) or self.sudo().create(
            {'date_from': fields.Date.context_today(self), 'state': 'done'})
        counts = {'created': 0, 'updated': 0, 'skipped': 0}
        cut = since - timedelta(minutes=5)
        ids = self._mtbg_list_ids(books, accounts, {'last_modified_time': cut.strftime('%Y-%m-%dT%H:%M:%S+0000')},
                                  modified_since=cut)
        for expense_id in dict.fromkeys(ids):
            run._mtbg_take(books, expense_id, accounts, counts)
        icp.set_param(LAST_SYNC, fields.Datetime.to_string(started))
        return counts

    @api.model
    def _mtbg_cron_sync(self):
        try:
            self._mtbg_sync_changes()
        except (ZohoError, UserError) as error:
            _logger.warning("Zoho Books expenses sync: %s", error)


class MtbgZohoBooksReview(models.Model):
    _name = 'mtbg.zoho.books.review'
    _description = 'Import & Sync from Zoho Books: a line to review'
    _order = 'state, date, id'

    run_id = fields.Many2one('mtbg.zoho.books.import', required=True, ondelete='cascade', index=True)
    account_id = fields.Many2one('mtbg.zoho.books.account', string='Category', required=True, ondelete='cascade')
    destination = fields.Selection(related='account_id.destination')
    zoho_line_id = fields.Char(string='Zoho Books Line', readonly=True, index=True)
    expense_id = fields.Char(string='Zoho Books Expense', readonly=True)
    date = fields.Date(readonly=True)
    description = fields.Char(readonly=True)
    vendor = fields.Char(readonly=True)
    project = fields.Char(readonly=True)
    customer = fields.Char(readonly=True)
    report = fields.Char(readonly=True)
    amount = fields.Float(readonly=True)
    currency_code = fields.Char(string='Currency', readonly=True)
    target = fields.Reference(selection='_mtbg_target_selection', string='Goes To')
    note = fields.Char(string='Why', readonly=True)
    payload = fields.Text(readonly=True)  # the expense and its line (JSON), for Apply
    state = fields.Selection([('review', 'To review'), ('done', 'Brought in'), ('skip', 'Skipped')], default='review',
                             required=True, readonly=True)
    zoho_url = fields.Char(compute='_compute_zoho_url', string='Zoho Books Link')

    @api.model
    def _mtbg_target_selection(self):
        return self.env['mtbg.zoho.books.account']._mtbg_target_selection()

    def _compute_zoho_url(self):
        for review in self:
            review.zoho_url = books_url(self.env, review.expense_id)

    @api.model
    def _mtbg_add(self, run, account, expense, line, note):
        line_id = f"{expense['expense_id']}:{line.get('line_item_id')}" if line.get('line_item_id') else \
            str(expense['expense_id'])
        vals = {'run_id': run.id, 'account_id': account.id, 'zoho_line_id': line_id,
                'expense_id': str(expense['expense_id']), 'date': (expense.get('date') or '')[:10] or False,
                'description': (line.get('description') or expense.get('description') or '')[:250],
                'vendor': expense.get('vendor_name') or False, 'project': expense.get('project_name') or False,
                'customer': expense.get('customer_name') or False, 'report': expense.get('report_name') or False,
                'amount': float(line.get('item_total') or line.get('amount') or 0.0),
                'currency_code': expense.get('currency_code') or False, 'note': note or False,
                'payload': json.dumps({'expense': expense, 'line': line}, default=str)}
        same = self.search([('zoho_line_id', '=', line_id), ('state', '=', 'review')], limit=1)
        return same.write(vals) if same else self.create(vals)

    def _mtbg_payload(self):
        self.ensure_one()
        data = json.loads(self.payload or '{}')
        return data.get('expense') or {}, data.get('line') or {}

    def action_skip(self):
        self.write({'state': 'skip'})
        return True

    def action_mtbg_open_zoho(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': self.zoho_url, 'target': 'new'} if self.zoho_url else False


def books_url(env, expense_id):
    """https://books.zoho.com/app/<org>#/expenses/<id> (the data centre's domain)."""
    if not expense_id:
        return False
    icp = env['ir.config_parameter'].sudo()
    accounts = icp.get_param('mtbg_tours.zoho_accounts_url') or 'https://accounts.zoho.com'
    domain = accounts.split('//')[-1].strip('/').removeprefix('accounts.') or 'zoho.com'
    org = icp.get_param('mtbg_tours.zoho_org_id') or ''
    return f"https://books.{domain}/app/{org}#/expenses/{str(expense_id).split(':')[0]}" if org else False
