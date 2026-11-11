"""Height, weight and age as people type them: any unit in, one unit stored (height in cm, weight in lb).

One parser for the web forms, the website chat and the WhatsApp flows (the browser has the same rules in
``@mtbg_tours_forms/measure``), and for cleaning the heights and weights imported from Zoho.

Each returns a dict: ``value`` (cm / lb / years, or None), ``flag`` (True when we guessed and should ask "did you
mean ...?"), ``error`` (a message key when unreadable) and ``shown`` (the reading in both units, "178 cm · 5′10″").
"""
import re

CM_PER_INCH = 2.54
LB_PER_KG = 2.20462

_QUOTES = str.maketrans({'’': "'", '‘': "'", '′': "'", '´': "'", '`': "'", '”': '"', '“': '"', '″': '"'})
_NUM = r'(\d+(?:[.,]\d+)?)'


def _number(text):
    return float(text.replace(',', '.'))


def feet_inches(cm):
    inches = round(cm / CM_PER_INCH)
    return '%d′%d″' % divmod(inches, 12)


def _height(cm, flag=False):
    cm = round(cm)
    if not 120 <= cm <= 220:
        return {'value': None, 'flag': False, 'error': 'height', 'shown': ''}
    return {'value': cm, 'flag': flag, 'error': None, 'shown': '%d cm · %s' % (cm, feet_inches(cm))}


def parse_height(text):
    """'5ft 2in', "5'2", '170', '1.7m', '1,70 m', '70 in', '5 pies 2 pulgadas' -> cm."""
    t = (text or '').strip().lower().translate(_QUOTES)
    t = re.sub(r'\s+', ' ', t)
    if not t:
        return {'value': None, 'flag': False, 'error': 'height', 'shown': ''}
    t = (t.replace('feet', 'ft').replace('foot', 'ft').replace('pies', 'ft').replace('pie', 'ft')
          .replace('inches', 'in').replace('inch', 'in').replace('pulgadas', 'in').replace('pulgada', 'in')
          .replace('ft.', 'ft').replace('in.', 'in'))
    # feet and inches: 5'10, 5' 10", 5ft10, 5 ft 10 in, 5-10, 5 10
    m = re.fullmatch(r"(\d)\s*(?:'|ft|-| )\s*(\d{1,2}(?:[.,]\d+)?)\s*(?:\"|in|'')?", t)
    if m and _number(m.group(2)) < 12:
        return _height((int(m.group(1)) * 12 + _number(m.group(2))) * CM_PER_INCH)
    # feet only: 5', 6 ft
    m = re.fullmatch(r"(\d(?:[.,]\d+)?)\s*(?:'|ft)", t)
    if m:
        return _height(_number(m.group(1)) * 12 * CM_PER_INCH)
    # inches: 70 in, 70"
    m = re.fullmatch(_NUM + r'\s*(?:in|")', t)
    if m:
        return _height(_number(m.group(1)) * CM_PER_INCH)
    # centimetres / metres with their unit
    m = re.fullmatch(_NUM + r'\s*cm', t)
    if m:
        return _height(_number(m.group(1)))
    m = re.fullmatch(_NUM + r'\s*(?:m|mts?|metros?|meters?|metres?)', t)
    if m:
        return _height(_number(m.group(1)) * 100)
    # a bare number: which unit it is from its size
    m = re.fullmatch(_NUM, t)
    if m:
        n = _number(m.group(1))
        if 100 <= n <= 230:
            return _height(n)
        if 1.2 <= n <= 2.3:
            return _height(n * 100)
        if 4 <= n < 8 and re.search(r'[.,]', t):
            # "5.10" / "5.9": people mean feet.inches (5 ft 10 in), not 5.1 ft
            feet, _sep, inches = m.group(1).replace(',', '.').partition('.')
            if int(inches) < 12:
                return _height((int(feet) * 12 + int(inches)) * CM_PER_INCH, flag=True)
        if 48 <= n <= 90:
            return _height(n * CM_PER_INCH, flag=True)  # inches, probably
    return {'value': None, 'flag': False, 'error': 'height', 'shown': ''}


def _weight(lb, flag=False):
    lb = round(lb)
    if not 30 <= lb <= 400:
        return {'value': None, 'flag': False, 'error': 'weight', 'shown': ''}
    return {'value': lb, 'flag': flag, 'error': None, 'shown': '%d lb · %d kg' % (lb, round(lb / LB_PER_KG))}


def parse_weight(text, default_unit='lb'):
    """'165', '165 lbs', '75 kg', '11st 10', '160-170', '~170' -> lb. A bare number from 40 to 140 is read in
    ``default_unit`` (lb for +1 phone numbers, kg otherwise) and flagged for confirmation."""
    t = (text or '').strip().lower().replace('~', '').replace('about', '').replace('aprox', '').strip()
    t = re.sub(r'\s+', ' ', t)
    if not t:
        return {'value': None, 'flag': False, 'error': 'weight', 'shown': ''}
    # stone (and pounds)
    m = re.fullmatch(r'(\d+)\s*(?:st|stone)s?\s*(?:(\d+)\s*(?:lbs?|pounds?)?)?', t)
    if m:
        return _weight(int(m.group(1)) * 14 + int(m.group(2) or 0))
    # a range: the middle
    m = re.fullmatch(_NUM + r'\s*(?:-|–|to|a)\s*' + _NUM + r'\s*(lbs?|pounds?|kgs?|kilos?|kilogramos?|libras?)?', t)
    if m:
        middle = (_number(m.group(1)) + _number(m.group(2))) / 2
        unit = m.group(3) or ''
        return parse_weight('%s %s' % (middle, unit), default_unit) if unit else parse_weight(str(middle), default_unit)
    m = re.fullmatch(_NUM + r'\s*(?:lbs?|pounds?|libras?|#)', t)
    if m:
        return _weight(_number(m.group(1)))
    m = re.fullmatch(_NUM + r'\s*(?:kgs?|kilos?|kilogramos?|kilograms?)', t)
    if m:
        return _weight(_number(m.group(1)) * LB_PER_KG)
    m = re.fullmatch(_NUM, t)
    if m:
        n = _number(m.group(1))
        if 40 <= n <= 140:
            # kg or lb? the rider's likely unit, and ask
            return _weight(n * LB_PER_KG if default_unit == 'kg' else n, flag=True)
        if 140 < n <= 400:
            return _weight(n)
    return {'value': None, 'flag': False, 'error': 'weight', 'shown': ''}


def weight_unit_for_phone(phone):
    """The likely unit for a bare weight: lb for +1 (US / Canada) numbers, kg otherwise."""
    digits = re.sub(r'[^\d+]', '', phone or '')
    return 'lb' if digits.startswith('+1') else 'kg'


def parse_age(text):
    """'34', '34 years', '34 años' -> 34 (5 to 90)."""
    m = re.search(r'\d+', text or '')
    age = int(m.group(0)) if m else 0
    if not 5 <= age <= 90:
        return {'value': None, 'flag': False, 'error': 'age', 'shown': ''}
    return {'value': age, 'flag': False, 'error': None, 'shown': str(age)}
