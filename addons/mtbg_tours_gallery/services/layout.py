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
