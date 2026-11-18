"""Page Speed's own settings page (owner 2026-11-07: "the setup link should be in a central page-speed review settings
area"): Website › Configuration › Page Speed, and the Speed log's cog. What the extension does and its state in one
place: the nightly speed log (its state, last night, the Set up wizard), the "Visitor pages without Odoo's extras"
switch (moved here from the General Settings page), the photo copies job (its state, Run now) and what is always on.

Its Save writes only Page Speed's own parameter: on www a General Settings save rewrites every parameter (it once
wiped the Zoho ones), so nothing of Page Speed's is set there any more."""
from odoo import api, fields, models
from odoo.exceptions import AccessError

from .lean import FIRST_SCREEN_PARAM, PARAM as LEAN_PARAM
from .lighten import CHECKED


class MtbgPageSpeedSettings(models.TransientModel):
    _name = 'mtbg.page.speed.settings'
    _description = 'Page speed: settings'

    lean = fields.Boolean("Visitor pages without Odoo's extras", default=lambda self: self._mtbg_lean_on(),
                          help="Anonymous visitors on ordinary pages get Odoo's script bundle and stylesheet without "
                               "the editor's, the portal's and the back end's own pieces (media dialog, Unsplash, "
                               "onboarding tours, tax helper, payment and delivery forms, passkey login); the editor's "
                               "background shapes load after the page has shown. Logged-in users and the portal, "
                               "checkout, payment and invoice pages keep Odoo's own.")
    first_screen = fields.Boolean(
        "First screen first", default=lambda self: self.env['mtbg.page.speed.lean']._mtbg_first_screen_on(),
        help="With the pages without Odoo's extras: each page carries the rules of the site stylesheet it uses "
             "(about 25 KB as sent) and the whole stylesheet (160 KB) comes after it without holding the page, so a "
             "phone shows the page sooner. Logged-in users and the portal, checkout and payment pages are not "
             "concerned.")
    log_on = fields.Boolean('Measuring every night', compute='_compute_state')
    google_ok = fields.Boolean('Google connection', compute='_compute_state')
    google_note = fields.Char(compute='_compute_state')
    last_night = fields.Date('Last night measured', compute='_compute_state')
    next_night = fields.Datetime('Next night', compute='_compute_state')
    last_night_note = fields.Char(compute='_compute_state')
    copies_last_run = fields.Datetime('Photo copies: last run', compute='_compute_state')
    copies_checked = fields.Integer('Big photos looked at', compute='_compute_state')
    copies_made = fields.Integer('Screen copies', compute='_compute_state')

    @api.model
    def _mtbg_lean_on(self):
        return self.env['mtbg.page.speed.lean']._mtbg_on()

    def _compute_state(self):
        Log = self.env['mtbg.page.speed.log'].sudo()
        on = Log._mtbg_on()
        ready, google_note = Log._mtbg_google()
        last = Log.search([('state', '=', 'done')], order='run_date desc', limit=1).run_date
        note = ''
        if last:
            night = Log.search([('run_date', '=', last)])
            note = self.env._("%(done)s measured, %(flagged)s over the limit, %(failed)s not measured",
                              done=len(night.filtered(lambda r: r.state == 'done')),
                              flagged=len(night.filtered('flagged')),
                              failed=len(night.filtered(lambda r: r.state == 'error')))
        cron = self.env.ref('mtbg_tours_page_speed.cron_lighten_copies', raise_if_not_found=False)
        night_cron = self.env.ref('mtbg_tours_page_speed.cron_speed_log', raise_if_not_found=False)
        checked = (self.env['ir.config_parameter'].sudo().get_param(CHECKED) or '').split(',')
        made = self.env['ir.attachment'].sudo().search_count([('res_model', '=', 'ir.attachment'),
                                                              ('description', '=like', 'resize: %')])
        for page in self:
            page.log_on, page.last_night, page.last_night_note = on, last, note
            page.google_ok, page.google_note = ready, google_note
            page.next_night = night_cron.sudo().nextcall if night_cron else False
            page.copies_last_run = cron.sudo().lastcall if cron else False
            page.copies_checked = len([i for i in checked if i.strip()])
            page.copies_made = made

    def _mtbg_check_admin(self):
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(self.env._("Only an administrator can change Page Speed's settings."))

    def action_save(self):
        """Only Page Speed's own switch: never the rest of the site's parameters."""
        self.ensure_one()
        self._mtbg_check_admin()
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param(LEAN_PARAM, 'True' if self.lean else 'False')
        ICP.set_param(FIRST_SCREEN_PARAM, 'True' if self.first_screen else 'False')
        self.env['mtbg.page.speed.lean']._mtbg_sync()
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'success', 'message': self.env._("Page Speed's settings saved."),
            'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}}}

    def action_setup(self):
        self._mtbg_check_admin()
        return self.env['mtbg.page.speed.log'].action_mtbg_setup()

    def action_open_google(self):
        """Set up Google (the connector's own page), when the connector is installed."""
        self._mtbg_check_admin()
        return self.env['mtbg.page.speed.log.setup'].create({}).action_open_google()

    def action_open_log(self):
        return self.env['ir.actions.act_window']._for_xml_id('mtbg_tours_page_speed.action_speed_log')

    def action_measure_now(self):
        """Measure now: tonight's list is made (if not yet today) and measured in the background, a few pages a
        minute, as at night."""
        self._mtbg_check_admin()
        Log = self.env['mtbg.page.speed.log']
        ready, note = Log._mtbg_google()
        if not Log._mtbg_on() or not ready:
            message = note if not ready else self.env._("Turn the speed log on first (Set up).")
            return {'type': 'ir.actions.client', 'tag': 'display_notification',
                    'params': {'type': 'warning', 'message': message}}
        today = fields.Date.context_today(Log)
        if Log.sudo().search_count([('run_date', '=', today)]) and \
                not Log.sudo().search_count([('run_date', '=', today), ('state', '=', 'pending')]):
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
                'type': 'info', 'message': self.env._("Today's pages are measured already: the next night is at "
                                                      "02:30.")}}
        cron = self.env.ref('mtbg_tours_page_speed.cron_speed_log', raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger()
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'info', 'message': self.env._("Measuring starts in a moment, a few pages a minute (about 40 minutes "
                                                  "for every page): Website › Reporting › Speed log.")}}

    def action_run_copies(self):
        """Run now: the photo copies job starts in the background (a few photos a minute)."""
        self._mtbg_check_admin()
        cron = self.env.ref('mtbg_tours_page_speed.cron_lighten_copies', raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger()
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'info', 'message': self.env._("The photo copies job starts in a moment, in the background.")}}
