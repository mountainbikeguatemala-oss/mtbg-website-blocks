"""Meta: the webhook (the "Callback URL" of the Meta app's Page and Instagram webhooks), the end of the Facebook
login, and the Instagram feed of the website block.

Webhook GET: Meta checks the address with the connection's verify token. POST: the call must be signed with the
app secret (X-Hub-Signature-256), else it is refused; the apps act on it (meta.connector._meta_webhook). The
addresses of a connection moved from Communication Flows (/cfd/meta/...) answer too."""
import json
import logging

from odoo import SUPERUSER_ID, http
from odoo.http import request

from ..models import graph
from ..models.app import LEGACY_OAUTH_PATH, LEGACY_WEBHOOK_PATH, OAUTH_PATH, WEBHOOK_PATH

_logger = logging.getLogger(__name__)


class MetaConnectorController(http.Controller):

    def _apps(self):
        return request.env(user=SUPERUSER_ID)["meta.connector.app"].search([("app_secret", "!=", False)])

    @http.route([WEBHOOK_PATH, LEGACY_WEBHOOK_PATH], type="http", auth="none", methods=["GET"], csrf=False,
                save_session=False)
    def verify(self, **params):
        token = params.get("hub.verify_token") or ""
        if params.get("hub.mode") == "subscribe" and token and token in self._apps().mapped("verify_token"):
            return request.make_response(params.get("hub.challenge") or "", headers=[("Content-Type", "text/plain")])
        return request.make_response("Forbidden", status=403)

    @http.route([WEBHOOK_PATH, LEGACY_WEBHOOK_PATH], type="http", auth="none", methods=["POST"], csrf=False,
                save_session=False, readonly=False)
    def receive(self, **_kwargs):
        body = request.httprequest.get_data()
        signature = request.httprequest.headers.get("X-Hub-Signature-256", "")
        apps = self._apps()
        if not any(graph.signature_ok(app.app_secret, body, signature) for app in apps):
            _logger.warning("Meta: webhook call refused (bad signature)")
            return request.make_response("Forbidden", status=403)
        try:
            payload = json.loads(body or b"{}")
        except ValueError:
            return request.make_response("Bad Request", status=400)
        apps.env["meta.connector"]._meta_webhook(payload)
        return request.make_response("EVENT_RECEIVED", headers=[("Content-Type", "text/plain")])

    @http.route([OAUTH_PATH, LEGACY_OAUTH_PATH], type="http", auth="user", methods=["GET"])
    def oauth(self, state=None, code=None, error=None, error_description=None, **_kwargs):
        if not request.env.user.has_group("base.group_system"):
            return request.make_response("Forbidden", status=403)
        app = request.env["meta.connector.app"]._oauth_done(state, code=code, error=error_description or error)
        if not app:
            return request.redirect("/odoo")
        return request.redirect("/odoo/action-meta_connector.action_meta_connector_app/%s" % app.id)

    @http.route("/meta_connector/instagram/feed", type="jsonrpc", auth="public", website=True, readonly=True)
    def instagram_feed(self, count=6, username=None):
        """The website block's posts (kept here by the cron: never a call to Instagram)."""
        try:
            count = int(count)
        except (TypeError, ValueError):
            count = 6
        return request.env["meta.connector.media"].sudo()._meta_feed(count=count, username=username or None)


class MetaConnectorMarketingPreview(http.Controller):
    """A record drawn with a marketing template (the marketing engine), 360 px wide: a queue's card of a story or
    post not drawn yet shows the real picture. Internal users only, the record read with their rights."""

    @http.route("/meta_connector/overlay/<int:overlay_id>/preview/<string:model>/<int:res_id>", type="http",
                auth="user", methods=["GET"], readonly=True)
    def marketing_preview(self, overlay_id, model, res_id, lang=None, width=360, **options):
        env = request.env
        if not env.user._is_internal() or model not in env:
            return request.not_found()
        overlay = env["mtbg.marketing.overlay"].browse(overlay_id).exists()
        record = env[model].browse(res_id).exists()
        if not overlay or not record:
            return request.not_found()
        overlay.check_access("read")
        record.check_access("read")
        options.pop("unique", None)
        website = env["website"].browse(int(options.pop("website_id"))).exists() \
            if str(options.get("website_id") or "").isdigit() else None
        try:
            width = max(60, min(1080, int(width)))
        except (TypeError, ValueError):
            width = 360
        image = overlay.sudo()._mtbg_render_record(record.sudo(), lang or "en", website=website, fmt="JPEG",
                                                   preview_width=width, **options)
        return request.make_response(image, headers=[("Content-Type", "image/jpeg"),
                                                     ("Cache-Control", "private, max-age=600")])
