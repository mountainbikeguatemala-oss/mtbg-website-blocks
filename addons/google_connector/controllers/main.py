"""Google's sign-in comes back here (the Authorized redirect URI added in Google Cloud) with a code for the account
named in the signed ``state``; the administrator lands on step 3 of Set up Google."""
import logging

from werkzeug.utils import redirect

from odoo import http
from odoo.http import request

from ..models.client import GoogleError
from ..models.connector import OAUTH_PATH

_logger = logging.getLogger(__name__)


class GoogleConnectorOAuth(http.Controller):

    @http.route(OAUTH_PATH, type="http", auth="user", methods=["GET"], readonly=False)
    def oauth(self, state=None, code=None, error=None, **_kwargs):
        if not request.env.user.has_group("base.group_system"):
            return request.not_found()
        Connector = request.env["google.connector"]
        account = Connector._account_from_state(state)
        if not account:
            return request.not_found()
        if error or not code:
            account.write({"state": "error", "state_reason": "Google sign-in: %s" % (error or "no code")})
        else:
            try:
                Connector._oauth_done(account, code)
            except GoogleError as failure:
                _logger.warning("Google sign-in failed: %s", failure)
                account.write({"state": "error", "state_reason": str(failure)[:250]})
        return redirect("/odoo/action-google_connector.action_google_setup_accounts")
