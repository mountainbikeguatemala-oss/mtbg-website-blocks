from unittest.mock import patch

from odoo.tests import HttpCase, tagged

SOURCES = {'thing': {'name': 'Things', 'fields': [
    {'key': 'name', 'label': 'Name', 'kind': 'title', 'place': 'body'},
    {'key': 'price', 'label': 'Price', 'kind': 'price', 'place': 'body'},
    {'key': 'badge', 'label': 'Badge', 'kind': 'badge', 'place': 'top_left'},
    {'key': 'rating', 'label': 'Rating', 'kind': 'rating', 'place': 'off'},
], 'filters': [{'key': 'kind', 'label': 'Kind', 'options': [{'key': 'big', 'label': 'Big'}]}]}}


def values(self, source, record):
    return {'url': '/thing/%s' % record, 'image': '', 'name': 'Thing %s' % record, 'price': '$%s' % (record * 10),
            'badge': 'New' if record == 1 else '', 'rating': {'value': 4.6, 'count': 12}}


@tagged('post_install', '-at_install', 'mtbg')
class TestCardDesigns(HttpCase):
    """Card designs with a source of its own (the pack needs no module's records)."""

    def _patch(self):
        cls = type(self.env['mtbg.website.card.design'])
        return [patch.object(cls, '_mtbg_card_sources', lambda self: SOURCES),
                patch.object(cls, '_mtbg_card_values', values),
                patch.object(cls, '_mtbg_card_records', lambda self, source, filters, limit: [1, 2, 3][:limit])]

    def test_design_and_render(self):
        patches = self._patch()
        for p in patches:
            p.start()
        try:
            Design = self.env['mtbg.website.card.design']
            data = Design.mtbg_designer_create('Plain', 'thing')
            design = Design.browse(data['design']['id'])
            self.assertTrue(design.is_default, "the first design of a source is its Default")
            parts = data['design']['look']['parts']
            self.assertEqual([p['key'] for p in parts], ['name', 'price', 'badge', 'rating'])
            html = str(design.mtbg_render([1, 2]))
            self.assertIn('Thing 1', html)
            self.assertIn('mtbg-card--below', html)
            self.assertIn('mtbg-card__badge', html)
            self.assertNotIn('fa-star', html, "the rating is hidden")
            # move the rating onto the photo, text over the photo, dark colours; draft first, then saved
            settings = dict(data['design'], style='overlay', hover_darken=True)
            settings['look'] = {'parts': [{'key': 'rating', 'place': 'top_right'}] + parts[:3],
                                'dark': {'card_bg': '#111111', 'text': 'nope'}}
            design.mtbg_designer_draft(settings)
            self.assertIn('fa-star', str(design.mtbg_render([1], draft=True)))
            self.assertNotIn('fa-star', str(design.mtbg_render([1])), "the site keeps the saved design")
            design.mtbg_designer_save(settings)
            self.assertEqual(design.style, 'overlay')
            html = str(design.mtbg_render([1]))
            self.assertIn('mtbg-card--overlay', html)
            self.assertIn('hover-darken', html)
            self.assertIn('--mtbg-card-dark-card-bg: #111111', html)
            self.assertNotIn('nope', html)
            block = Design.mtbg_block_data()['sources'][0]
            self.assertEqual((block['key'], block['designs'][0]['id']), ('thing', design.id))
            res = self.make_jsonrpc_request('/mtbg/cards/render', {'source': 'thing', 'limit': 2})
            self.assertEqual(res['html'].count('mtbg-card mtbg-card--'), 2)
            self.assertEqual(self.make_jsonrpc_request('/mtbg/cards/render', {'source': 'unknown'})['html'], '')
        finally:
            for p in patches:
                p.stop()
