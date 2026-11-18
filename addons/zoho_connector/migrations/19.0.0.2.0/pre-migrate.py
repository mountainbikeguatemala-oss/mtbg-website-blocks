"""0.2.0 (2026-11-18, "zoho connector should be global"): the Zoho Books expenses' Import & Sync and the vendors'
Zoho Books link come here from the Tours' Zoho extension, under the same names. Their xml ids, table constraints and
many2many table are handed over before this version loads: every table, row, setting and job stays as it is (nothing
deleted, nothing sent). A site without the Tours' extension: nothing to move, the tables are made."""
import logging

from odoo.addons.zoho_connector.hooks import take_over

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    moved = take_over(cr)
    if moved:
        _logger.info("Zoho Connector 0.2.0: %s records taken over from the Tours' Zoho extension", moved)
