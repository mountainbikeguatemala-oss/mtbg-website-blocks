from odoo.tests import BaseCase, tagged

from ..models.measure import parse_age, parse_height, parse_weight, weight_unit_for_phone


@tagged('post_install', '-at_install', 'mtbg')
class TestMeasure(BaseCase):
    """The user's real examples (PRE_TOUR_FORM_SPEC "Height and weight")."""

    def test_height(self):
        for text in ('5ft 2in', '5ft2', '5\'2"', "5'2in", '5’2”', '5 ′ 2 ″', '5 ft. 2 in.', '5 feet 2 inches',
                     '5 pies 2 pulgadas'):
            self.assertEqual(parse_height(text)['value'], 157, text)
        for text in ('170', '170cm', '1.7m', '1.7', '1,70 m'):
            self.assertEqual(parse_height(text)['value'], 170, text)
        self.assertEqual(parse_height("5'10")['value'], 178)
        self.assertEqual(parse_height('70 in')['value'], 178)
        self.assertEqual(parse_height('6 ft')['value'], 183)
        five_ten = parse_height('5.10')
        self.assertEqual((five_ten['value'], five_ten['flag']), (178, True), "5.10 means 5'10\", asked back")
        self.assertTrue(parse_height('70')['flag'])
        self.assertEqual(parse_height('70')['value'], 178)
        self.assertEqual(parse_height('178 cm')['shown'], '178 cm · 5′10″')
        for text in ('tall', '', '300', '5 meters 80'):
            self.assertIsNone(parse_height(text)['value'], text)

    def test_weight(self):
        for text in ('165', '165lbs', '165 lb', '165 pounds', '165#', '165 libras'):
            self.assertEqual(parse_weight(text)['value'], 165, text)
        for text in ('75kg', '75 kg', '75 kilos', '75 kilogramos'):
            self.assertEqual(parse_weight(text)['value'], 165, text)
        self.assertEqual(parse_weight('11st 10')['value'], 164)
        self.assertEqual(parse_weight('11st')['value'], 154)
        self.assertEqual(parse_weight('160-170')['value'], 165)
        self.assertEqual(parse_weight('~170')['value'], 170)
        us = parse_weight('75', weight_unit_for_phone('+1 541 555 0123'))
        self.assertEqual((us['value'], us['flag']), (75, True))
        gt = parse_weight('75', weight_unit_for_phone('+502 5555 1234'))
        self.assertEqual((gt['value'], gt['flag']), (165, True))
        self.assertEqual(parse_weight('165')['shown'], '165 lb · 75 kg')
        self.assertIsNone(parse_weight('heavy')['value'])

    def test_age(self):
        self.assertEqual(parse_age('34 years')['value'], 34)
        self.assertEqual(parse_age('34 años')['value'], 34)
        self.assertIsNone(parse_age('120')['value'])
