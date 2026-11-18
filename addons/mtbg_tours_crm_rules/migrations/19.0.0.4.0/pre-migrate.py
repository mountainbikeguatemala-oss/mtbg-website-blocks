"""0.4.0 (owner, 2026-11-18: the same contact pipeline on every site): the contact type, its stage, lost, the lead
flag and the source channel come here from Tours (Communications and Core), under the same names. Their xml ids are
handed over before this version loads: every column, value, source channel and the daily job stay as they are
(nothing deleted, nothing sent). A site without Tours: nothing to move, the columns are made (and typed after)."""
import logging

from odoo.addons.mtbg_tours_crm_rules.hooks import take_over

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    moved = take_over(cr)
    if moved:
        _logger.info("Contact Rules 0.4.0: %s records taken over from Tours (the contact pipeline)", moved)
