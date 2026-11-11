"""What the Google apps did: one row per sync or batch (google.connector.sync_log), kept 90 days."""
from datetime import timedelta

from odoo import api, fields, models

KEEP_DAYS = 90


class GoogleConnectorLog(models.Model):
    _name = "google.connector.log"
    _description = "Google sync log"
    _order = "id desc"

    app_code = fields.Char(string="App", required=True, index=True)
    account_id = fields.Many2one("google.connector.account", string="Google Account", ondelete="set null")
    operation = fields.Char(required=True)
    state = fields.Selection([("running", "Running"), ("done", "Done"), ("failed", "Failed")], default="running",
                             required=True)
    created = fields.Integer()
    updated = fields.Integer()
    skipped = fields.Integer()
    failed = fields.Integer()
    note = fields.Text()
    started_at = fields.Datetime(default=fields.Datetime.now)
    finished_at = fields.Datetime()

    def add(self, created=0, updated=0, skipped=0, failed=0, note=""):
        """Count what a sync did (google.connector.sync_log)."""
        for log in self:
            log.write({"created": log.created + created, "updated": log.updated + updated,
                       "skipped": log.skipped + skipped, "failed": log.failed + failed,
                       "note": "\n".join(filter(None, [log.note, note])) or False})

    @api.model
    def _cron_clean(self):
        self.search([("create_date", "<", fields.Datetime.now() - timedelta(days=KEEP_DAYS))]).unlink()
