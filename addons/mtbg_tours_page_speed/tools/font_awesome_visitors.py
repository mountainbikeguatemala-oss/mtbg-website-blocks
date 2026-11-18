"""Builds the visitors' Font Awesome (page speed 0.7.11, owner 2026-11-12: "trim font awesome"). A developer's tool, not
loaded by the module (it needs fontTools, which the server does not have):

    python font_awesome_visitors.py ODOO_ADDONS_PATH

writes static/src/fonts/font_awesome_visitors.woff2 (only the icons below) and static/src/css/font_awesome_visitors.css
(Odoo's font-awesome.css with its @font-face split in two). The visitors' stylesheet (models/lean.py) carries that CSS
in place of Odoo's: a browser fetches a font only for the characters a page draws with it (unicode-range), so a page
whose icons are all below gets the small file, and a page with any other icon gets Odoo's whole font as before. No icon
can go missing; the list only decides which file is fetched.

The list: every icon found on a copy of the site on 2026-11-12, in the 328 pages of its sitemap (both languages), the
scripts visitors load (with the ones loaded on demand: booking sheet, chat tab, catalog, reviews...), the website's
templates and blocks, the tours', regions', locations', menus', cards' and journal posts' stored text, and the
stylesheets' own icons (content: "\\f..."). One name per icon (Odoo's first name for it)."""
import os
import re
import sys

ICONS = """
search envelope-o heart star star-o user th-large th check remove search-plus search-minus signal gear trash-o home
clock-o road download inbox play-circle-o rotate-right refresh lock headphones volume-off volume-up qrcode tag tags
bookmark print camera font bold italic align-right video-camera photo pencil map-marker edit check-square-o play stop
chevron-left chevron-right plus-circle minus-circle times-circle check-circle question-circle info-circle
check-circle-o arrow-left arrow-right expand compress plus minus exclamation-circle fire eye eye-slash warning plane
calendar comment chevron-up chevron-down folder folder-open twitter-square facebook-square camera-retro comments
thumbs-o-up heart-o sign-out linkedin-square thumb-tack external-link upload phone square-o twitter facebook-f github
credit-card arrow-circle-right globe tasks filter group chain copy paperclip save square navicon list-ul list-ol
strikethrough underline table magic truck pinterest money caret-down caret-up caret-right columns unsorted envelope
linkedin rotate-left legal dashboard comments-o flash sitemap paste exchange cloud-upload bell cutlery file-text-o
building-o angle-left angle-right angle-down desktop laptop tablet mobile-phone circle-o quote-right circle
mail-reply folder-o smile-o keyboard-o flag-o flag-checkered code star-half-empty crop unlink question exclamation
eraser microphone microphone-slash calendar-o rss-square level-down check-square compass toggle-right dollar file
file-text sort-amount-asc sort-numeric-asc sort-numeric-desc youtube youtube-play instagram long-arrow-right sun-o
moon-o bug institution google language building child cube automobile tree database file-photo-o circle-o-notch send
send-o history circle-thin header paragraph sliders share-alt newspaper-o bell-slash trash eyedropper paint-brush
area-chart line-chart bicycle bus angellist heartbeat whatsapp user-times hotel object-ungroup clone hourglass-2
hand-stop-o tripadvisor tv calendar-plus-o calendar-check-o industry map-o commenting commenting-o pause-circle-o
shopping-basket hashtag question-circle-o volume-control-phone deafness handshake-o address-book vcard user-circle-o
user-o drivers-license drivers-license-o window-maximize window-restore
""".split()
# the font's few characters outside its icons (a space, the copyright and trademark signs...): in the small file too,
# so text in an icon's element draws as it did
TEXT = (0x20, 0xa8, 0xa9, 0xae, 0xb4, 0xc6, 0xd8, 0x2122, 0x221e, 0x2260)
FACE = re.compile(r'@font-face\s*\{[^}]*\}')
ICON = re.compile(r'([^{}]+)\{\s*content:\s*"\\([0-9a-f]+)";?\s*\}')
WHOLE = '/web/static/src/libs/fontawesome/fonts/fontawesome-webfont'


def code_points(css):
    """{icon name: code point} of Odoo's font-awesome.css."""
    return {name: int(cp, 16) for sels, cp in ICON.findall(css) for name in re.findall(r'\.fa-([a-z0-9-]+):before', sels)}


def ranges(points):
    """'U+F000-F003, U+F005' for these code points."""
    out, points = [], sorted(points)
    for p in points:
        if out and p == out[-1][1] + 1:
            out[-1][1] = p
        else:
            out.append([p, p])
    return ', '.join('U+%X' % a if a == b else 'U+%X-%X' % (a, b) for a, b in out)


def faces(small, rest):
    face = """@font-face {
  font-family: 'FontAwesome';
  src: %s;
  font-weight: normal;
  font-style: normal;
  font-display: block;
  unicode-range: %s;
}"""
    return '\n'.join((
        "/* the visitors' icons (mtbg_tours_page_speed/tools/font_awesome_visitors.py): the small file for the icons "
        "the site uses */",
        face % ("url('../fonts/font_awesome_visitors.woff2') format('woff2')", ranges(small)),
        "/* every other icon: Odoo's whole font, fetched only by a page that draws one */",
        face % ("url('%s.woff2?v=4.7.0') format('woff2'), url('%s.woff?v=4.7.0') format('woff')" % (WHOLE, WHOLE),
                ranges(rest)),
    ))


def main(addons):
    from fontTools import subset
    from fontTools.ttLib import TTFont
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    lib = os.path.join(addons, 'web/static/src/libs/fontawesome')
    css = open(os.path.join(lib, 'css/font-awesome.css')).read()
    points = code_points(css)
    unknown = [n for n in ICONS if n not in points]
    assert not unknown, unknown
    small = {points[n] for n in ICONS} | set(TEXT)
    font = os.path.join(lib, 'fonts/fontawesome-webfont.ttf')
    every = set(TTFont(font).getBestCmap())
    options = subset.Options()
    options.flavor = 'woff2'
    options.layout_features = ['*']
    face = subset.load_font(font, options)
    sub = subset.Subsetter(options)
    sub.populate(unicodes=small)
    sub.subset(face)
    os.makedirs(os.path.join(here, 'static/src/fonts'), exist_ok=True)
    subset.save_font(face, os.path.join(here, 'static/src/fonts/font_awesome_visitors.woff2'), options)
    os.makedirs(os.path.join(here, 'static/src/css'), exist_ok=True)
    with open(os.path.join(here, 'static/src/css/font_awesome_visitors.css'), 'w') as out:
        out.write(FACE.sub(lambda m: faces(small & every, every - small), css, count=1))


if __name__ == '__main__':
    main(sys.argv[1])
