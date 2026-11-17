"""0.7.1 drops website_crm and the lead's Form Answers field (Odoo's CRM retired, release B). With Tours,
Communications 19.0.0.8.0 moved every lead (its answers among them) onto its contact and 19.0.0.8.1 refuses to install
before that (and so does this update, as Forms may be updated before it). Without Communications nothing moves
the leads: logged here, so the site knows before uninstalling the CRM (the leads and their answers stay until
then)."""
import logging

_logger = logging.getLogger(__name__)


def _crm_leads_not_moved(cr):
    """How many Odoo CRM leads wait for Communications 19.0.0.8.0 (release A) to move them onto their contacts: the
    CRM has leads, Communications is installed and its mark (crm_leads_moved) is missing. 0: safe."""
    cr.execute("SELECT to_regclass('crm_lead')")
    if not cr.fetchone()[0]:
        return 0
    cr.execute("SELECT state FROM ir_module_module WHERE name = 'mtbg_tours_communications'")
    row = cr.fetchone()
    if not row or row[0] not in ('installed', 'to upgrade'):
        return 0
    cr.execute("SELECT value FROM ir_config_parameter WHERE key = 'mtbg_tours_communications.crm_leads_moved'")
    row = cr.fetchone()
    if row and row[0]:
        return 0
    cr.execute("SELECT count(*) FROM crm_lead")
    return cr.fetchone()[0]


def migrate(cr, version):
    leads = _crm_leads_not_moved(cr)
    if leads:  # (with Tours: refused, the form answers would go before Communications 19.0.0.8.0 kept them)
        raise RuntimeError(
            "Forms 19.0.0.7.1 refused: %s Odoo CRM leads were never moved onto their contacts. Install "
            "Communications 19.0.0.8.0 (release A) first, then this update again. Nothing was changed." % leads)
    cr.execute("SELECT to_regclass('crm_lead')")
    if not cr.fetchone()[0]:
        return
    cr.execute("SELECT 1 FROM information_schema.columns WHERE table_name = 'crm_lead' AND column_name = "
               "'mtbg_form_answers'")
    if not cr.fetchone():
        return
    cr.execute("SELECT count(*) FROM crm_lead WHERE mtbg_form_answers IS NOT NULL")
    answered = cr.fetchone()[0]
    cr.execute("SELECT state FROM ir_module_module WHERE name = 'mtbg_tours_communications'")
    row = cr.fetchone()
    if answered and (not row or row[0] != 'installed'):
        _logger.warning("Forms 0.7.1: %s CRM leads have website form answers and Communications is not installed: "
                        "they are not moved onto their contacts; they stay in the CRM until it is uninstalled",
                        answered)
