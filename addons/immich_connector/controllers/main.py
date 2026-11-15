"""The setup wizard's zip (administrators only): config.env with this site's settings and the token, the photo
server's files."""
from odoo import http
from odoo.http import request


class ImmichSetupController(http.Controller):

    @http.route("/immich_connector/setup/<int:wizard_id>/photo-server.zip", type="http", auth="user",
                methods=["GET"], readonly=True)
    def bundle(self, wizard_id, **_kw):
        if not request.env.user.has_group("base.group_system"):
            return request.make_response("Forbidden", status=403)
        wizard = request.env["immich.setup.wizard"].browse(wizard_id).exists()
        if not wizard or wizard.create_uid != request.env.user:
            return request.not_found()
        return request.make_response(wizard._bundle(), headers=[
            ("Content-Type", "application/zip"), ("Cache-Control", "no-store"),
            ("Content-Disposition", 'attachment; filename="photo-server.zip"')])
