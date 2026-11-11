"""The Meta connector's API for the apps using Facebook Pages and Instagram accounts (frozen: docs/ARCHITECTURE.md,
"Meta connector"). Apps read the connection and its Pages here, and extend the hooks (with super())."""
from odoo import api, models

from . import graph

# what Settings › Meta switches on and off (on unless switched off): the connector's Instagram Feed block, and the
# apps' uses (Communication Flows' chat and contact photos; its WhatsApp Cloud numbers sending with this login)
USES = ("ig_feed", "ig_chat", "ig_photos", "fb_chat", "fb_photos", "wa_login")


class MetaConnector(models.AbstractModel):
    _name = "meta.connector"
    _description = "Meta Connector"

    @api.model
    def _meta_app(self):
        """The connection (sudo), or an empty recordset."""
        return self.env["meta.connector.app"].sudo().search([], limit=1)

    @api.model
    def _meta_pages(self, kind=None):
        """The Pages this site uses: ``kind`` "page" (its Facebook Page), "instagram" (its Instagram account), or
        either."""
        domain = [("app_id.active", "=", True)]
        if kind == "page":
            domain.append(("use_page", "=", True))
        elif kind == "instagram":
            domain += [("use_instagram", "=", True), ("ig_id", "!=", False)]
        else:
            domain += ["|", ("use_page", "=", True), ("use_instagram", "=", True)]
        return self.env["meta.connector.page"].sudo().search(domain)

    @api.model
    def _meta_use(self, use):
        """Is ``use`` (one of USES) switched on in Settings › Meta? On unless switched off."""
        return not self.env["ir.config_parameter"].sudo().get_param("meta_connector.%s_off" % use)

    @api.model
    def _meta_set_uses(self, values):
        """Switch uses on or off ({use: bool}); the apps hear which ones changed."""
        changed = [use for use, on in values.items() if use in USES and bool(on) != self._meta_use(use)]
        Param = self.env["ir.config_parameter"].sudo()
        for use in changed:
            Param.set_param("meta_connector.%s_off" % use, False if values[use] else "1")
        if changed:
            self._meta_uses_changed(changed)
        return changed

    @api.model
    def _meta_login(self, scopes=(), permanent=False):
        """The login's user token, for apps that call Meta with the login itself (e.g. WhatsApp business accounts):
        only when it has every one of ``scopes`` and, with ``permanent``, never expires (a system user's token, from
        Facebook Login for Business); else False."""
        app = self._meta_app()
        if not app or not app.active or not app.user_token:
            return False
        if permanent and app.user_token_expires:
            return False
        granted = set((app.granted_scopes or "").split(","))
        return app.user_token if set(scopes) <= granted else False

    @api.model
    def _meta_targets(self, scope):
        """The IDs of the assets ``scope`` is limited to for the login (e.g. its WhatsApp business accounts)."""
        app = self._meta_app()
        return list((app.granted_targets or {}).get(scope) or []) if app else []

    # ------------------------------------------------------------------ hooks (apps extend them)
    @api.model
    def _meta_uses_changed(self, uses):
        """After Settings › Meta switched ``uses`` on or off: the apps follow."""
        if "ig_feed" in uses and self._meta_use("ig_feed"):
            cron = self.env.ref("meta_connector.ir_cron_meta_instagram_feed", raise_if_not_found=False)
            if cron:
                cron.sudo()._trigger()

    @api.model
    def _meta_scopes(self):
        """The permissions the Facebook login asks for: the connector's, and every app's (the posting ones when an
        app posts: Marketing installed; they need Meta's app review)."""
        scopes = list(graph.SCOPES)
        if self._meta_posting_wanted():
            scopes += [scope for scope in graph.POSTING_SCOPES if scope not in scopes]
        return scopes

    @api.model
    def _meta_posting_wanted(self):
        """An app posts on the Page and Instagram (owner, 2026-11-10: "if marketing is installed"): the setup has a
        Posting step and the login asks for the posting permissions. A soft check: no dependency. Posting switched
        on in Settings counts too (owner, 2026-11-11: a site without Marketing, e.g. a shop, still wants the Page's
        and Instagram's posting permissions granted)."""
        return "mtbg.marketing.item" in self.env or self._meta_posting_on()

    # ------------------------------------------------------------------ posting (apps call it, e.g. Marketing)
    @api.model
    def _meta_posting_on(self):
        """Settings › Meta › Posting: off unless switched on (its permissions need Meta's app review)."""
        return self.env["ir.config_parameter"].sudo().get_param("meta_connector.posting") == "1"

    @api.model
    def _meta_post(self, kind, caption, image_url):
        """Post ``caption`` with the picture at ``image_url`` (a public address) on the site's Facebook Page
        (``kind`` "facebook") or Instagram account ("instagram"): {"id", "url"}. Raises UserError with the reason:
        Posting off, not connected, no Page / account ticked, a permission Meta has not granted, or Meta's answer."""
        from odoo.exceptions import UserError
        _ = self.env._
        if kind not in graph.POST_SCOPES:
            raise UserError(_("Meta posts go to \"facebook\" or \"instagram\"."))
        if not self._meta_posting_on():
            raise UserError(_("Posting is off in Settings › Meta."))
        app = self._meta_app()
        if not app or not app.active:
            raise UserError(_("Meta is not connected (Settings › Meta › Set up Meta)."))
        granted = set((app.granted_scopes or "").split(","))
        missing = [scope for scope in graph.POST_SCOPES[kind] if scope not in granted]
        if missing:
            raise UserError(_("Meta has not granted %(scopes)s to this login yet (app review, then log in with "
                              "Facebook again in Set up Meta).", scopes=", ".join(missing)))
        page = self._meta_pages("instagram" if kind == "instagram" else "page")[:1]
        if not page:
            raise UserError(_("No %(what)s ticked in Set up Meta › Change the Pages.",
                              what=_("Instagram account") if kind == "instagram" else _("Facebook Page")))
        token = page.sudo().page_token
        try:
            if kind == "instagram":
                result = graph.ig_publish(page.ig_id, token, image_url, caption)
            else:
                result = graph.page_photo_post(page.page_id, token, image_url, caption)
        except graph.GraphError as error:
            raise UserError(str(error)) from error
        post_id = result.get("post_id") or result.get("id") or ""
        return {"id": post_id, "url": graph.permalink(post_id, token) if post_id else ""}

    @api.model
    def _meta_webhook_fields(self):
        """The app's webhooks this site needs: {"page": [fields], "instagram": [fields]} (none: no webhook)."""
        return {}

    @api.model
    def _meta_webhook(self, payload):
        """A webhook call, signed by the app: the apps act on it."""

    @api.model
    def _meta_whatsapp_status(self):
        """Settings › Meta's WhatsApp block: its status line (False: no WhatsApp app here, no block)."""
        return False

    @api.model
    def _meta_pages_changed(self, pages):
        """After the Pages step, a new login or a token check: ``pages`` (all the Pages found, used or not, with
        their ``state``). Context ``meta_connector_setup``: from the setup (subscribe them, etc.)."""
