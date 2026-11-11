"""Settings › Meta: the connection, then an Instagram, a Facebook and a WhatsApp block, each with its status and its
uses switched on or off (the Feed block here; Communication Flows' chat and contact photos when its channel is
installed, and its WhatsApp Cloud numbers sending with the Meta login)."""
from odoo import _, api, fields, models

from .connector import USES


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    meta_ig_feed = fields.Boolean(string="Instagram Feed block")
    meta_ig_chat = fields.Boolean(string="Instagram chat")
    meta_ig_photos = fields.Boolean(string="Instagram contact photos")
    meta_fb_chat = fields.Boolean(string="Facebook chat")
    meta_fb_photos = fields.Boolean(string="Facebook contact photos")
    meta_wa_login = fields.Boolean(string="WhatsApp sends with the Meta login")
    meta_posting = fields.Boolean(string="Posting",
                                  help="This site posts on the Facebook Page and the Instagram account (e.g. with Marketing). "
                                       "On: Set up Meta asks for the posting permissions (pages_manage_posts, "
                                       "instagram_content_publish) at the next Facebook login. Other people than "
                                       "the Meta app's own admins need Meta's app review first.")
    meta_ig_status = fields.Char(string="Instagram account", compute="_compute_meta_status")
    meta_fb_status = fields.Char(string="Facebook Page", compute="_compute_meta_status")
    meta_wa_status = fields.Char(string="WhatsApp", compute="_compute_meta_status")
    meta_wa_installed = fields.Boolean(compute="_compute_meta_status")

    @api.model
    def get_values(self):
        values = super().get_values()
        Connector = self.env["meta.connector"]
        values.update({"meta_%s" % use: Connector._meta_use(use) for use in USES})
        values["meta_posting"] = Connector._meta_posting_on()
        return values

    def set_values(self):
        super().set_values()
        if self.env.user.has_group("base.group_system"):
            self.env["meta.connector"]._meta_set_uses({use: self["meta_%s" % use] for use in USES})
            self.env["ir.config_parameter"].sudo().set_param("meta_connector.posting", "1" if self.meta_posting else "0")

    @api.depends_context("uid")
    def _compute_meta_status(self):
        Connector = self.env["meta.connector"]
        app = Connector._meta_app()

        def status(pages, label, none):
            if not app or app.step not in ("posting", "done"):  # (the Pages saved: connected)
                return _("Not connected yet: Set up Meta.")
            if not pages:
                return none
            names = ", ".join(label(page) for page in pages)
            broken = pages.filtered(lambda page: page.state == "disconnected")
            if broken:
                return _("%(names)s: disconnected, log in with Facebook again in Set up Meta.", names=names)
            return _("%s: connected.", names)

        ig = status(Connector._meta_pages("instagram"), lambda p: "@%s" % (p.ig_username or p.ig_id),
                    _("No Instagram account ticked: Set up Meta › Change the Pages."))
        fb = status(Connector._meta_pages("page"), lambda p: p.name or p.page_id,
                    _("No Facebook Page ticked: Set up Meta › Change the Pages."))
        wa = Connector._meta_whatsapp_status()
        for settings in self:
            settings.meta_ig_status, settings.meta_fb_status = ig, fb
            settings.meta_wa_status, settings.meta_wa_installed = wa or False, wa is not False
