"""The marketing engine's drawing (owner, 2026-11-22: "the marketing template preview should be GLOBAL marketing
extension I don't want to have to code everything twice for two websites"; moved here from Tours Marketing, whose
overlays it drew first: "generate live overlays on the photos with font / size settings for date"), with Pillow at
full resolution:

    vertical  1080 x 1920 (a story, 9:16)
    square    1080 x 1080 (a post, 1:1)

The photo is cropped to the shape (centred, "cover"), or shown whole in a box on a background colour ("contain": a
product's square picture on a story), then, in order: the scrim (a gradient from the top and / or the
bottom), then each layer by its sequence:

* text: its font (a font Odoo ships, or an uploaded TTF / OTF), size (px at full resolution), colour, alignment and
  anchor (x %, y %: the point the block hangs from: left / centre / right of the block on x, top / middle / bottom
  on y); wrapped at its max width (%), and shrunk (8 % at a time, down to its min size) until it fits its max lines
  and every word fits the width; an optional shadow (soft), outline, and background box (colour, opacity, padding,
  rounded corners, a border) behind the whole block; turned by a few degrees (a sticker: "NEW IN", "BARGAIN");
* logo: a picture (its shape kept), its width a share of the image's, at its anchor;
* QR code (the story's short link: Meta's API cannot put a link sticker on a story): black on white with a white
  quiet zone, its side a share of the short edge, at one of 9 anchors with offsets.

Pure functions (no Odoo records): the template's preview and the post are the same drawing."""
import io
import os
import re

from babel.dates import format_date
from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont, ImageOps

from odoo.tools.misc import file_path

SIZES = {'vertical': (1080, 1920), 'square': (1080, 1080)}
DEFAULT_FONT = 'web/static/fonts/google/Oswald/Oswald-Bold.ttf'
FONT_DIRS = ('web/static/fonts/google', 'web/static/fonts/lato')
PLACEHOLDER = re.compile(r'\{([a-z_]+)\}')


def shipped_fonts():
    """[(path, label)]: the TTF / OTF fonts Odoo's web module ships (Oswald, Montserrat, Open Sans, Raleway, Roboto,
    Lato...), "Oswald Bold" style labels, sorted."""
    fonts = []
    for folder in FONT_DIRS:
        try:
            root = file_path(folder)
        except (OSError, FileNotFoundError, ValueError):
            continue
        for dirpath, _dirs, names in os.walk(root):
            for name in names:
                if name.lower().endswith(('.ttf', '.otf')):
                    full = os.path.join(dirpath, name)
                    rel = folder + full[len(root):]
                    label = os.path.splitext(name)[0].replace('-webfont', '').replace('_', ' ').replace('-', ' ')
                    fonts.append((rel, label))
    fonts.sort(key=lambda f: f[1])
    if DEFAULT_FONT not in {path for path, _label in fonts}:
        fonts.insert(0, (DEFAULT_FONT, 'Oswald Bold'))
    return fonts


def load_font(font, size):
    """``font``: bytes (an uploaded font) or a path of Odoo's; a font that does not open: Oswald Bold, else
    Pillow's own."""
    size = max(4, int(size))
    try:
        if isinstance(font, bytes):
            return ImageFont.truetype(io.BytesIO(font), size)
        return ImageFont.truetype(file_path(font or DEFAULT_FONT), size)
    except (OSError, FileNotFoundError, ValueError):
        try:
            return ImageFont.truetype(file_path(DEFAULT_FONT), size)
        except (OSError, FileNotFoundError, ValueError):
            return ImageFont.load_default(size)


def rgba(value, default='#FFFFFF', opacity=1.0):
    try:
        color = ImageColor.getrgb(value or default)
    except ValueError:
        color = ImageColor.getrgb(default)
    return tuple(color[:3]) + (max(0, min(255, int(round(255 * opacity)))),)


# ---------------------------------------------------------------------- dates and placeholders
def ordinal(day):
    """1st, 2nd, 3rd, 4th, 11th, 12th, 13th, 21st, 22nd, 23rd, 31st."""
    if 10 <= day % 100 <= 20:
        return '%sth' % day
    return '%s%s' % (day, {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th'))


def _month(day, lang, pattern):
    """The month's name in ``lang`` (English, else Spanish), no trailing dot ("sept." -> "sept")."""
    spanish = (lang or 'en').startswith('es')
    return re.sub(r'\.$', '', format_date(day, pattern, locale='es' if spanish else 'en'))


def dates_text(start, end, lang, style='short', upper=False, day_first=False):
    """The one place marketing writes a departure's dates (owner, 2026-11-21: "two day tours should be labled Nov 25-26
    or Oct 31 - Nov 1 on all marketing"): one day as before, several days their range.

    English short: "Nov 26"; "Nov 25-26"; "Oct 31 - Nov 1"; "Dec 31 - Jan 1, 2027" (a year only across years).
    English long: "November 26th"; "November 25-26"; "October 31 - November 1" (``upper``: the months in capitals,
    "NOVEMBER 25-26", an ordinal stays small). Spanish short: "26 nov"; "25-26 nov"; "31 oct - 1 nov"; "31 dic - 1 ene
    2027"; long: "26 de noviembre"; "25-26 de noviembre"; "31 de octubre - 1 de noviembre" (``upper``: all capitals).
    ``day_first``: English short day first too ("25-26 Nov", the calendar story's table)."""
    if not start:
        return ''
    spanish = (lang or 'en').startswith('es')
    pattern = 'MMMM' if style == 'long' else 'MMM'
    month = lambda day: _month(day, lang, pattern)  # noqa: E731
    one_day = not end or end <= start
    if spanish or day_first:
        joiner = ' de ' if spanish and style == 'long' else ' '
        caps = (lambda text: text.capitalize()) if day_first and not spanish else (lambda text: text)
        if one_day:
            text = '%s%s%s' % (start.day, joiner, caps(month(start)))
        elif (start.year, start.month) == (end.year, end.month):
            text = '%s-%s%s%s' % (start.day, end.day, joiner, caps(month(end)))
        else:
            text = '%s%s%s - %s%s%s' % (start.day, joiner, caps(month(start)), end.day, joiner, caps(month(end)))
            if start.year != end.year:
                text += '%s%s' % (' de ' if spanish and style == 'long' else ' ', end.year)
        return text.upper() if upper else text
    cased = (lambda text: text.upper()) if upper else (lambda text: text)
    if one_day:
        return '%s %s' % (cased(month(start)), ordinal(start.day) if style == 'long' else start.day)
    if (start.year, start.month) == (end.year, end.month):
        return '%s %s-%s' % (cased(month(start)), start.day, end.day)
    text = '%s %s - %s %s' % (cased(month(start)), start.day, cased(month(end)), end.day)
    return text + (', %s' % end.year if start.year != end.year else '')


def date_long(day, lang, upper=False, end=None):
    """English "October 2nd" ("OCTOBER 2nd" upper: the ordinal stays small, as the owner wrote it); Spanish
    "2 de octubre" ("2 DE OCTUBRE"); several days (``end``): their range ("November 25-26", ``dates_text``)."""
    return dates_text(day, end, lang, style='long', upper=upper)


def date_short(day, lang, end=None):
    """"Oct 2" / "2 oct"; several days (``end``): "Nov 25-26" / "25-26 nov" (``dates_text``)."""
    return dates_text(day, end, lang, style='short')


def fill(text, values, upper=False):
    """``text`` with its {placeholders} filled (an unknown one stays as written); ``upper``: its words in capitals,
    the values too (except the ordinal of {date_long}: ``values['date_long_upper']``)."""
    parts, last = [], 0
    for match in PLACEHOLDER.finditer(text or ''):
        literal = text[last:match.start()]
        parts.append(literal.upper() if upper else literal)
        name = match.group(1)
        if name not in values:
            value = match.group(0)
        elif upper and name == 'date_long' and 'date_long_upper' in values:
            value = str(values['date_long_upper'])
        else:
            value = str(values[name])
            value = value.upper() if upper else value
        parts.append(value if value.strip() else EMPTY)
        last = match.end()
    tail = (text or '')[last:]
    parts.append(tail.upper() if upper else tail)
    return drop_empty(''.join(parts))


# a placeholder that came out empty, until ``drop_empty`` drops it with the separator it leaves dangling
EMPTY = '\x01'
_SEP = r'[,·;|–—\-]'


def fill_moustache(text, values):
    """A post's ``{{name}}`` placeholders filled from ``values`` (an unknown one: empty), no separator left dangling
    by an empty one (``drop_empty``)."""
    def value(match):
        found = str(values.get(match.group(1), '') or '')
        return found if found.strip() else EMPTY
    return drop_empty(MOUSTACHE.sub(value, text or ''))


MOUSTACHE = re.compile(r'\{\{\s*([a-z_0-9]+)\s*\}\}')


def drop_empty(text):
    """``text`` with its empty values (``EMPTY``) gone and no separator left dangling (owner, 2026-11-21: "{price_from},
    {spaces_left_text} left" with no price is "7 spaces left", never ", 7 spaces left"): an empty value at a line's start
    takes the separator after it, at its end the one before it, between two separators one of them; then no double
    spaces. Text without an empty value is left exactly as it is."""
    if EMPTY not in (text or ''):
        return text or ''
    lines = []
    for line in text.split('\n'):
        if EMPTY in line:
            line = re.sub(r'^([ \t]*)(?:%s[ \t]*%s?[ \t]*)+' % (re.escape(EMPTY), _SEP), r'\1', line)
            line = re.sub(r'(?:[ \t]*%s?[ \t]*%s)+[ \t]*$' % (_SEP, re.escape(EMPTY)), '', line)
            # after a sentence's end: the separator after it goes ("Nov 25-26. {price}, 7 left": "Nov 25-26. 7 left")
            line = re.sub(r'([.!?:])[ \t]*%s[ \t]*%s[ \t]*' % (re.escape(EMPTY), _SEP), r'\1 ', line)
            line = re.sub(r'(%s)[ \t]*%s[ \t]*(?=%s)' % (_SEP, re.escape(EMPTY), _SEP), '', line)
            line = re.sub(r'[ \t]*%s[ \t]*(%s)' % (re.escape(EMPTY), _SEP), r'\1', line)
            line = line.replace(EMPTY, '')
            line = re.sub(r'(?<=\S)[ \t]{2,}(?=\S)', ' ', line)
        lines.append(line)
    return '\n'.join(lines)


# any {name} written, known or not (a typo shows: "{Date_long}", "{dias}"); ``PLACEHOLDER`` fills only the known
DETECT = re.compile(r'\{([A-Za-z0-9_]+)\}')


def unknown(text, known, pattern=DETECT):
    """The {placeholders} of ``text`` not in ``known``, in order, once each."""
    seen = []
    for match in pattern.finditer(text or ''):
        if match.group(1) not in known and match.group(1) not in seen:
            seen.append(match.group(1))
    return seen


def segments(text, values, nested=None, pattern=DETECT):
    """``text`` filled as ``fill`` does, in pieces for a preview: [{text, name?, unknown?}]; ``nested``: a name whose
    value is itself pieces (a caption's {description}: its own unknown placeholders still show)."""
    out, last = [], 0
    for match in pattern.finditer(text or ''):
        if match.start() > last:
            out.append({'text': text[last:match.start()]})
        name = match.group(1)
        if nested and name in nested:
            out.extend(nested[name])
        elif name in values:
            out.append({'text': str(values[name]), 'name': name})
        else:
            out.append({'text': match.group(0), 'name': name, 'unknown': True})
        last = match.end()
    if last < len(text or ''):
        out.append({'text': text[last:]})
    return _segments_drop_empty(out)


def _segments_drop_empty(out):
    """The preview's pieces as ``drop_empty`` writes the text: an empty value takes its dangling separator with it."""
    sep = r'[ \t]*%s[ \t]*' % _SEP
    for index, piece in enumerate(out):
        if not piece.get('name') or piece.get('unknown') or piece['text'].strip():
            continue
        before = out[index - 1] if index and not out[index - 1].get('name') else None
        after = out[index + 1] if index + 1 < len(out) and not out[index + 1].get('name') else None
        starts = index == 0 or (before is not None and (not before['text'].strip(' \t')
                                                         or before['text'].rstrip(' \t').endswith('\n')))
        ends = index + 1 == len(out) or (after is not None and (not after['text'].strip(' \t')
                                                                or after['text'].lstrip(' \t').startswith('\n')))
        stop = before is not None and re.search(r'[.!?:][ \t]*$', before['text'])
        if (starts or stop) and after is not None:
            after['text'] = re.sub(r'^' + sep, '', after['text'])
        elif ends and before is not None:
            before['text'] = re.sub(sep + r'$', '', before['text'])
        elif before is not None and after is not None and re.search(sep + r'$', before['text']) \
                and re.match(sep, after['text']):
            before['text'] = re.sub(sep + r'$', '', before['text'])
        elif before is not None:
            before['text'] = before['text'].rstrip(' \t') if after is not None and re.match(sep, after['text']) \
                else before['text']
        piece['text'] = ''
    return out


def tidy(pieces):
    """A caption's pieces as a post has them: no run of blank lines (an empty {description}), no space at the ends."""
    pieces = [dict(p, text=re.sub(r'\n{3,}', '\n\n', p['text'])) for p in pieces]
    while pieces and not pieces[0]['text'].strip() and not pieces[0].get('unknown'):
        pieces.pop(0)
    while pieces and not pieces[-1]['text'].strip() and not pieces[-1].get('unknown'):
        pieces.pop()
    if pieces:
        pieces[0] = dict(pieces[0], text=pieces[0]['text'].lstrip())
        pieces[-1] = dict(pieces[-1], text=pieces[-1]['text'].rstrip())
    return pieces


def time_text(hours, lang):
    """7.5: "7:30 AM" / "7:30 a. m."; none (0): empty."""
    if not hours:
        return ''
    total = int(round(hours * 60))
    hour, minute = divmod(total, 60)
    hour = hour % 24
    spanish = (lang or 'en').startswith('es')
    suffix = ('a. m.' if hour < 12 else 'p. m.') if spanish else ('AM' if hour < 12 else 'PM')
    return '%s:%02d %s' % (hour % 12 or 12, minute, suffix)


def days_text(days, lang):
    """"1 day" / "3 days" ("1 día" / "3 días")."""
    days = int(days or 0)
    if (lang or 'en').startswith('es'):
        return '1 día' if days == 1 else '%s días' % days
    return '1 day' if days == 1 else '%s days' % days


def hashtags(text):
    """"mtb, #enduro  guatemala" -> "#mtb #enduro #guatemala" (each word a hashtag, once)."""
    tags = []
    for word in re.split(r'[\s,;]+', text or ''):
        word = word.strip()
        if not word:
            continue
        word = '#' + word.lstrip('#')
        if len(word) > 1 and word.lower() not in [t.lower() for t in tags]:
            tags.append(word)
    return ' '.join(tags)


# ---------------------------------------------------------------------- text
def wrap(draw, text, font, width):
    """``text`` in lines no wider than ``width`` (a word wider than it stays whole: shrink handles it); explicit line
    breaks kept."""
    lines = []
    for paragraph in (text or '').split('\n'):
        line = ''
        for word in paragraph.split():
            attempt = (line + ' ' + word).strip()
            if line and draw.textlength(attempt, font=font) > width:
                lines.append(line)
                line = word
            else:
                line = attempt
        lines.append(line)
    while lines and not lines[-1]:
        lines.pop()
    return lines or ['']


def fit_text(draw, text, font_ref, size, min_size, width, max_lines):
    """(font, lines): the layer's size, or smaller (8 % a step, not under ``min_size``) until the wrapped text has at
    most ``max_lines`` lines (0: any) and every line fits ``width``."""
    size = max(4, int(size))
    min_size = max(4, min(int(min_size or size), size))
    while True:
        font = load_font(font_ref, size)
        lines = wrap(draw, text, font, width)
        fits = all(draw.textlength(line, font=font) <= width + 0.5 for line in lines) and \
            (not max_lines or len(lines) <= max_lines)
        if fits or size <= min_size:
            return font, lines
        size = max(min_size, int(size * 0.92))


def _block_origin(x, y, width, height, align, valign):
    left = x if align == 'left' else x - width if align == 'right' else x - width / 2.0
    top = y if valign == 'top' else y - height if valign == 'bottom' else y - height / 2.0
    return left, top


def draw_text(canvas, layer, scale=1.0):
    """One text layer on ``canvas`` (RGBA, full size). ``layer``: {text, font, size, min_size, color, align, valign,
    x, y, max_width, max_lines, line_height, shadow, shadow_color, outline, outline_color, box, box_color,
    box_opacity, box_padding, box_radius, box_border, box_border_color, rotate}. Returns {size, lines} (what was
    drawn: the tests read it). ``rotate`` (degrees, counter-clockwise): the block drawn apart, then turned about its
    centre (a sticker); 0: drawn in place."""
    angle = float(layer.get('rotate') or 0.0)
    if angle % 360:
        piece = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        drawn = _draw_text(piece, layer, scale)
        bbox = piece.getbbox()
        if bbox:
            cut = piece.crop(bbox).rotate(angle, resample=Image.BICUBIC, expand=True)
            cx, cy = (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0
            canvas.alpha_composite(cut, (int(round(cx - cut.width / 2.0)), int(round(cy - cut.height / 2.0))))
        return drawn
    return _draw_text(canvas, layer, scale)


def _draw_text(canvas, layer, scale=1.0):
    W, H = canvas.size
    text = layer.get('text') or ''
    if not text.strip():
        return {'size': 0, 'lines': []}
    measure = ImageDraw.Draw(canvas)
    width = max(10.0, (layer.get('max_width') or 90) / 100.0 * W)
    font, lines = fit_text(measure, text, layer.get('font'), (layer.get('size') or 60) * scale,
                           (layer.get('min_size') or layer.get('size') or 60) * scale, width,
                           int(layer.get('max_lines') or 0))
    ascent, descent = font.getmetrics()
    step = int(round((ascent + descent) * (layer.get('line_height') or 1.1)))
    widths = [measure.textlength(line, font=font) for line in lines]
    block_w = max(widths) if widths else 0
    block_h = step * (len(lines) - 1) + ascent + descent
    align = layer.get('align') or 'center'
    left, top = _block_origin((layer.get('x') or 0) / 100.0 * W, (layer.get('y') or 0) / 100.0 * H,
                              block_w, block_h, align, layer.get('valign') or 'middle')
    if layer.get('box'):
        pad = (layer.get('box_padding') or 0) * scale
        box = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        border = int(round((layer.get('box_border') or 0) * scale))
        ImageDraw.Draw(box).rounded_rectangle(
            (left - pad, top - pad, left + block_w + pad, top + block_h + pad),
            radius=int((layer.get('box_radius') or 0) * scale),
            fill=rgba(layer.get('box_color'), '#000000', layer.get('box_opacity') if layer.get('box_opacity')
                      is not None else 0.6),
            outline=rgba(layer.get('box_border_color'), '#000000') if border else None, width=border or 1)
        canvas.alpha_composite(box)

    def positions():
        for index, line in enumerate(lines):
            lx = left if align == 'left' else left + block_w - widths[index] if align == 'right' \
                else left + (block_w - widths[index]) / 2.0
            yield line, lx, top + index * step

    if layer.get('shadow'):
        shadow = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        offset = max(1, int(font.size * 0.04))
        sdraw = ImageDraw.Draw(shadow)
        for line, lx, ly in positions():
            sdraw.text((lx + offset, ly + offset), line, font=font,
                       fill=rgba(layer.get('shadow_color'), '#000000', 0.75))
        shadow = shadow.filter(ImageFilter.GaussianBlur(max(1, font.size * 0.05)))
        canvas.alpha_composite(shadow)
    draw = ImageDraw.Draw(canvas)
    stroke = int(round((layer.get('outline') or 0) * scale))
    for line, lx, ly in positions():
        draw.text((lx, ly), line, font=font, fill=rgba(layer.get('color'), '#FFFFFF'),
                  stroke_width=stroke, stroke_fill=rgba(layer.get('outline_color'), '#000000') if stroke else None)
    return {'size': font.size, 'lines': lines, 'box': (left, top, block_w, block_h)}


def draw_logo(canvas, layer, scale=1.0):
    """A logo layer: {image: bytes, size: width % of the image, x, y, align, valign, opacity}."""
    data = layer.get('image')
    if not data:
        return
    try:
        mark = Image.open(io.BytesIO(data))
        mark.load()
        mark = mark.convert('RGBA')
    except Exception:  # noqa: BLE001 - a logo that does not open: the overlay without it
        return
    W, H = canvas.size
    width = max(8, int((layer.get('size') or 25) / 100.0 * W))
    height = max(1, int(mark.height * width / float(mark.width or 1)))
    mark = mark.resize((width, height), Image.LANCZOS)
    opacity = layer.get('opacity')
    if opacity is not None and opacity < 1:
        alpha = mark.getchannel('A').point(lambda a: int(a * max(0.0, opacity)))
        mark.putalpha(alpha)
    left, top = _block_origin((layer.get('x') or 50) / 100.0 * W, (layer.get('y') or 5) / 100.0 * H, width, height,
                              layer.get('align') or 'center', layer.get('valign') or 'top')
    canvas.alpha_composite(mark, (int(left), int(top)))


ANCHORS = [('top-left', 'Top left'), ('top', 'Top'), ('top-right', 'Top right'), ('left', 'Left'),
           ('center', 'Centre'), ('right', 'Right'), ('bottom-left', 'Bottom left'), ('bottom', 'Bottom'),
           ('bottom-right', 'Bottom right')]


def anchor_box(width, height, w, h, anchor='bottom-right', offset_x=4.0, offset_y=4.0):
    """(x, y) of a ``w`` x ``h`` box on a ``width`` x ``height`` image at one of the 9 anchors, ``offset_x`` /
    ``offset_y`` % of the width / height in from its edges (ignored on the centred axis)."""
    col = 'left' if anchor in ('top-left', 'left', 'bottom-left') else \
        'right' if anchor in ('top-right', 'right', 'bottom-right') else 'center'
    row = 'top' if anchor in ('top-left', 'top', 'top-right') else \
        'bottom' if anchor in ('bottom-left', 'bottom', 'bottom-right') else 'middle'
    x = {'left': offset_x / 100.0 * width, 'center': (width - w) / 2.0,
         'right': width - w - offset_x / 100.0 * width}[col]
    y = {'top': offset_y / 100.0 * height, 'middle': (height - h) / 2.0,
         'bottom': height - h - offset_y / 100.0 * height}[row]
    return int(round(x)), int(round(y))


def qr_matrix(data, border=3):
    """The QR code of ``data`` as rows of booleans (True: dark), with ``border`` light modules all round (the quiet
    zone), from the qrcode library Odoo ships."""
    import qrcode
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=max(0, int(border)))
    qr.add_data(data)
    qr.make(fit=True)
    return qr.get_matrix()


def draw_qr(canvas, layer):
    """A QR code layer: {data, size: % of the short edge (its quiet zone included), anchor, offset_x, offset_y,
    quiet: light modules round it}. Black on white, whole modules (sharp, it scans on any photo). Returns its box
    (x, y, side, modules) for the tests."""
    data = layer.get('data')
    if not data:
        return None
    matrix = qr_matrix(data, layer.get('quiet') if layer.get('quiet') is not None else 3)
    modules = len(matrix)
    W, H = canvas.size
    side = max(modules, int(round((layer.get('size') or 22) / 100.0 * min(W, H))))
    unit = max(1, side // modules)
    side = unit * modules
    code = Image.new('RGBA', (modules, modules), (255, 255, 255, 255))
    pixels = code.load()
    for row, line in enumerate(matrix):
        for col, dark in enumerate(line):
            if dark:
                pixels[col, row] = (0, 0, 0, 255)
    code = code.resize((side, side), Image.NEAREST)
    x, y = anchor_box(W, H, side, side, layer.get('anchor') or 'bottom-right',
                      layer.get('offset_x') if layer.get('offset_x') is not None else 4.0,
                      layer.get('offset_y') if layer.get('offset_y') is not None else 4.0)
    canvas.alpha_composite(code, (x, y))
    return x, y, side, modules


def draw_scrim(canvas, scrim):
    """A gradient from the edge(s): {where: none|top|bottom|both, color, opacity (at the edge), height (%)}."""
    where = (scrim or {}).get('where') or 'none'
    if where == 'none':
        return
    W, H = canvas.size
    height = max(1, int((scrim.get('height') or 40) / 100.0 * H))
    top_alpha = rgba(scrim.get('color'), '#000000', scrim.get('opacity') if scrim.get('opacity') is not None
                     else 0.7)
    ramp = Image.linear_gradient('L').resize((1, height))  # 0 at the top, 255 at the bottom
    ramp = ramp.point(lambda v: int(v * top_alpha[3] / 255.0))
    color = Image.new('RGBA', (W, height), top_alpha[:3] + (0,))
    if where in ('bottom', 'both'):
        color.putalpha(ramp.resize((W, height)))
        canvas.alpha_composite(color, (0, H - height))
    if where in ('top', 'both'):
        piece = Image.new('RGBA', (W, height), top_alpha[:3] + (0,))
        piece.putalpha(ImageOps.flip(ramp).resize((W, height)))
        canvas.alpha_composite(piece, (0, 0))


def photo_canvas(photo, shape, background='#222222', fit='cover', box=None):
    """The photo at full size, RGBA: ``fit`` "cover" (default): cropped to the shape (centred); "contain": whole, as
    large as fits ``box`` (left, top, right, bottom in % of the image; default the whole image), centred in it, on the
    ``background`` colour. No photo (or one that does not open): the background colour."""
    size = SIZES[shape]
    if photo:
        try:
            image = Image.open(io.BytesIO(photo))
            image = ImageOps.exif_transpose(image)
            image = image.convert('RGB')
            if fit != 'contain':
                return ImageOps.fit(image, size, Image.LANCZOS, centering=(0.5, 0.5)).convert('RGBA')
            W, H = size
            left, top, right, bottom = box or (0, 0, 100, 100)
            area = (int(left / 100.0 * W), int(top / 100.0 * H), int(right / 100.0 * W), int(bottom / 100.0 * H))
            room = (max(1, area[2] - area[0]), max(1, area[3] - area[1]))
            image = ImageOps.contain(image, room, Image.LANCZOS)
            canvas = Image.new('RGBA', size, rgba(background, '#222222'))
            canvas.paste(image.convert('RGBA'), (area[0] + (room[0] - image.width) // 2,
                                                  area[1] + (room[1] - image.height) // 2))
            return canvas
        except Exception:  # noqa: BLE001 - a broken photo: the background, never no post
            pass
    return Image.new('RGBA', size, rgba(background, '#222222'))


def render(photo, shape, layers, scrim=None, fmt='JPEG', preview_width=None, quality=90, fit='cover',
           background='#222222', box=None):
    """The overlay on ``photo`` (bytes or None) as image bytes (JPEG for a post: Instagram takes JPEG only; PNG for
    a preview). ``layers``: [{kind: text|logo, ...}] already filled (texts, fonts, logos as bytes), in order.
    ``preview_width``: the drawing made at full size, then made smaller (it matches the post exactly). ``fit``,
    ``background``, ``box``: ``photo_canvas``; the scrim is for a photo that fills the picture (cover) only."""
    canvas = photo_canvas(photo, shape, background=background, fit=fit, box=box)
    if fit != 'contain':
        draw_scrim(canvas, scrim)
    for layer in layers:
        if layer.get('kind') == 'logo':
            draw_logo(canvas, layer)
        elif layer.get('kind') == 'qr':
            draw_qr(canvas, layer)
        else:
            draw_text(canvas, layer)
    image = canvas.convert('RGB')
    if preview_width:
        image = image.resize((int(preview_width), int(image.height * preview_width / float(image.width))),
                             Image.LANCZOS)
    out = io.BytesIO()
    if fmt == 'PNG':
        image.save(out, format='PNG', optimize=True)
    else:
        image.save(out, format='JPEG', quality=quality, optimize=True, progressive=True)
    return out.getvalue()


def image_size(data):
    """(width, height) of image bytes (after EXIF rotation), (0, 0) when it does not open."""
    try:
        image = Image.open(io.BytesIO(data))
        image = ImageOps.exif_transpose(image)
        return image.size
    except Exception:  # noqa: BLE001
        return 0, 0


def domain_text(url):
    """A website's address as people type it: "https://www.example.com/" -> "example.com"."""
    from urllib.parse import urlparse
    url = (url or '').strip()
    if not url:
        return ''
    host = urlparse(url if '//' in url else '//' + url).hostname or ''
    return host[4:] if host.startswith('www.') else host
