from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'mtbg')
class TestIconList(TransactionCase):
    """The Bullets block (views/snippets.xml) and the old site's list classes (icon_list.scss)."""

    def test_block_renders_a_preset_list(self):
        html = str(self.env['ir.qweb']._render('mtbg_tours_bullets.s_mtbg_icon_list', {}))
        self.assertIn('s_mtbg_icon_list', html)
        self.assertIn('mtbg-icons--check', html, "a new block starts with the Check box preset")
        self.assertIn('<ul class="mtbg-icon-list">', html)

    def test_old_list_classes_are_styled(self):
        bundle = self.env['ir.qweb']._get_asset_bundle('web.assets_frontend', css=True, js=False)
        css = ''.join(asset.content for asset in bundle.stylesheets if 'icon_list' in (asset.url or ''))
        for cls in ('ul.highlights', 'ul.checkbullet', 'ul.xbullet'):
            self.assertIn(cls, css, cls)
