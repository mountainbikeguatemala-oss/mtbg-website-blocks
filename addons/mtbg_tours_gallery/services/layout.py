"""Tiled gallery rows (Jetpack's "rectangular" style), laid out from the photos' stored sizes.

A row is a pattern of columns and a column holds one photo or two stacked ones. Every photo is cropped to fill its
cell, so the shares can be kept within limits: the big photo takes 55-70 % of its row, a pair 40-60 %, and a row is
never taller or flatter than the limits of its screen. Rows are saved as CSS (aspect ratio and column shares), so
nothing moves while the pictures load.
"""

# Jetpack's rhythm: big + two stacked, two stacked + big, then pairs
DESKTOP = ('big_left', 'big_right', 'pair', 'pair', 'pair')
# phones: one photo, a pair, one big + two stacked, a pair
PHONE = ('one', 'pair', 'big_left', 'pair')

SIZE = {'one': 1, 'pair': 2, 'big_left': 3, 'big_right': 3}
BIG_SHARE = (0.55, 0.70)
PAIR_SHARE = (0.40, 0.60)
# a row's width / height, at most and at least: desktop rows 25-48 % as tall as wide, phones 45-85 %
ROW_RATIO = {'desktop': (1 / 0.48, 1 / 0.25), 'phone': (1 / 0.85, 1 / 0.45)}


def _clamp(value, low, high):
    return min(high, max(low, value))


def patterns(count, cycle):
    """The row patterns for `count` photos: the cycle repeated, the last row cut to the photos left."""
    rows, used, step = [], 0, 0
    while used < count:
        pattern = cycle[step % len(cycle)]
        step += 1
        left = count - used
        if SIZE[pattern] > left:
            pattern = 'one' if left == 1 else 'pair' if left == 2 else pattern
        rows.append(pattern)
        used += SIZE[pattern]
    return rows


def _columns(pattern, photos):
    if pattern == 'one':
        return [photos]
    if pattern == 'pair':
        return [photos[:1], photos[1:]]
    if pattern == 'big_left':
        return [photos[:1], photos[1:]]
    return [photos[:2], photos[2:]]  # big_right


def _row(pattern, photos, screen):
    """{'ratio': width / height, 'columns': [{'share', 'cells': [{'photo', 'grow'}]}]}."""
    columns = _columns(pattern, photos)
    # a column's width / height: a photo's ratio, or for a stack 1 / sum(1 / ratio)
    ratios = [1 / sum(1 / p['ratio'] for p in col) for col in columns]
    total = sum(ratios)
    shares = [r / total for r in ratios]
    if len(columns) == 2:
        if pattern in ('big_left', 'big_right'):
            big = 0 if pattern == 'big_left' else 1
            shares[big] = _clamp(shares[big], *BIG_SHARE)
            shares[1 - big] = 1 - shares[big]
        else:
            shares[0] = _clamp(shares[0], *PAIR_SHARE)
            shares[1] = 1 - shares[0]
    return {
        'pattern': pattern,
        'ratio': _clamp(total, *ROW_RATIO[screen]),
        # stacked photos share the column's height by their own shape (a flatter photo gets less), as flex-grow
        # adding up to 100 (below 1 in total, flex would leave part of the column empty)
        'columns': [{'share': share, 'cells': [{'photo': p, 'grow': 100 / p['ratio'] / sum(1 / q['ratio'] for q in col)}
                                               for p in col]}
                    for share, col in zip(shares, columns)],
    }


def layout(photos, screen='desktop'):
    """Rows for photos [{'ratio': width / height, ...}] on 'desktop' or 'phone'."""
    rows, start = [], 0
    for pattern in patterns(len(photos), DESKTOP if screen == 'desktop' else PHONE):
        size = SIZE[pattern]
        rows.append(_row(pattern, photos[start:start + size], screen))
        start += size
    return rows


# ------------------------------------------------------------------ justified rows (19.0.0.6.2, 6.3)
# For any page (e.g. Tour Photos' client album), not the gallery block: each photo or video at its own shape, side by
# side in rows of equal height, so nothing is cropped (a few pixels at the gaps). Three screens (owner, 2026-11-15:
# "tiles are too small and the gifs are still cropped heavily"):
#   phone (< 576 px): big tiles, at most 2 a row: a landscape alone, full width; two portraits (or a portrait and a
#     tall video) share a row; a portrait left alone is centred, about 0.9 of the screen's width tall;
#   tablet (576-991 px): rows aimed at about 0.42 of the width tall, at most 3 a row;
#   desktop (>= 992 px): rows aimed at ~320 px tall (a ~1110 px page), at most 4 a row.
# A short last row keeps its height (narrower than the page, centred) instead of growing tall.
JUST_SCREENS = ('phone', 'tablet', 'desktop')
JUST_TARGET = {'tablet': 2.4, 'desktop': 3.5}  # a row's width / height aimed at
JUST_MOST = {'tablet': 3, 'desktop': 4}
PHONE_LANDSCAPE = 1.05  # wider than this: a row of its own on a phone
PHONE_LONE_HEIGHT = 0.9  # a lone portrait on a phone: this many screen widths tall (centred)


def _just_row(group, width=1.0):
    total = sum(r for _p, r in group)
    return {'pattern': 'justified', 'ratio': total, 'width': width,
            'columns': [{'share': r / total, 'cells': [{'photo': p, 'grow': 100}]} for p, r in group]}


def _phone_rows(items):
    rows, i = [], 0
    while i < len(items):
        photo, ratio = items[i]
        if ratio > PHONE_LANDSCAPE:
            rows.append(_just_row([items[i]]))
            i += 1
            continue
        nxt = items[i + 1] if i + 1 < len(items) else None
        if nxt and nxt[1] <= PHONE_LANDSCAPE:
            rows.append(_just_row([items[i], nxt]))
            i += 2
            continue
        # a portrait alone: centred, PHONE_LONE_HEIGHT widths tall
        rows.append(_just_row([items[i]], width=min(1.0, ratio * PHONE_LONE_HEIGHT)))
        i += 1
    return rows


def justified(photos, screen='desktop'):
    """Justified rows for photos [{'ratio': width / height, ...}] on 'phone', 'tablet' or 'desktop' (see above), in
    the Tiled Gallery's markup (rows of columns of one cell): [{'pattern': 'justified', 'ratio' (the row's width /
    height), 'width' (its share of the page: 1, or less for a short last row or a lone portrait on a phone),
    'columns': [{'share', 'cells': [{'photo', 'grow'}]}]}]. Every photo keeps its shape. Render inside
    ``.mtbg-tg.mtbg-tg-justified``, one ``.mtbg-tg-j-<screen>`` layout per screen, rows with the class
    ``mtbg-tg-just`` and their ``width`` when below 1."""
    items = [(p, max(0.2, min(5.0, float(p['ratio'])))) for p in photos if p.get('ratio')]
    if screen == 'phone':
        return _phone_rows(items)
    target, most = JUST_TARGET[screen], JUST_MOST[screen]
    groups, row, total = [], [], 0.0
    for item in items:
        row.append(item)
        total += item[1]
        if total >= target or len(row) >= most:
            groups.append(row)
            row, total = [], 0.0
    if row:
        groups.append(row)
    rows = []
    for i, group in enumerate(groups):
        total = sum(r for _p, r in group)
        last = i == len(groups) - 1
        rows.append(_just_row(group, min(1.0, total / target) if last and total < target * 0.75 else 1.0))
    return rows
