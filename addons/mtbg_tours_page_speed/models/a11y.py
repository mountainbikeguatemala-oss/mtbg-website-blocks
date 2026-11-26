"""Accessibility at render time (page speed 0.4.0, owner's search plan 2026-11-03), on the page sent to an anonymous
visitor, without touching what is stored (pictures and links inside posts, blocks and imported descriptions):

* a picture without an alt gets one: its file's name in words ("lake-atitlan-sunset_2.jpg": "Lake atitlan sunset"),
  else the page's title; a picture with alt="" (decoration) keeps it;
* the header logo is not lazy (it is the first thing seen);
* a link with nothing to say (an icon, a picture without words) gets a name: its picture's, else what it opens
  ("Open photo", the site or page it leads to);
* a link whose words say nothing ("Learn more", "Read more") is told where it leads for screen readers.

In the page's language (0.12.0, owner 2026-11-26: "every text on the Spanish site must be Spanish"): the words made
here ("Open photo", "Open the map", "Home") come translated (``labels``), and on a page in another language than the
website's own (``words=False``) a file's or an address's words (English, "Cal white", "5 stars 300px") are never used:
a picture takes its figure's caption, else its section's heading, else the heading it is under, else the page's
title; a picture inside a link
or button that has words is a decoration (alt=""); a link with nothing to say takes the words of another link to the
same page ("the card's title"), else the page's title. A picture's own alt (stored, translated) always stays.
"""
import bisect
import html
import re
from urllib.parse import unquote, urlsplit

IMG = re.compile(rb'<img\b[^>]*>')
ALT = re.compile(rb'\salt="')
EMPTY_ALT = re.compile(rb'\salt=""')
TITLE_ATTR = re.compile(rb'\stitle="([^"]*)"')
PHOTO_SRC = re.compile(rb'^(?:https?://[^/]+)?/web/image/\d+')
DECORATIVE = re.compile(rb'\s(?:role="presentation"|role="none"|aria-hidden="true")|\bclass="[^"]*\b(?:icon|flag|logo)\b')
SRC = re.compile(rb'\s(?:src|data-src)="([^"]*)"')
LINK = re.compile(rb'<a\b([^>]*)>(.*?)</a>', re.S)
TAGS = re.compile(rb'<[^>]*>')
HREF = re.compile(rb'\shref="([^"]*)"')
LABELLED = re.compile(rb'\s(?:aria-label|aria-labelledby|title)="[^"]')
IMG_ALT = re.compile(rb'<img\b[^>]*\salt="([^"]+)"')
NAMED_CHILD = re.compile(rb'\s(?:aria-label|title)="([^"]+)"')
TITLE = re.compile(rb'<title>(.*?)</title>', re.S)
LOGO_LINK = re.compile(rb'<a\b[^>]*class="[^"]*\bnavbar-brand\b[^"]*"[^>]*>.*?</a>', re.S)
LAZY = re.compile(rb'\sloading="lazy"')
IMAGE_HREF = re.compile(rb'^(?:/web/image/|/web/content/|/hotels/photo/)|\.(?:jpe?g|png|webp|gif|avif)(?:\?|$)', re.I)
VAGUE = re.compile(r'^(?:learn more|read more|more|click here|here|see more|more info|details|ver más|leer más|'
                   r'más información|aquí)$', re.I)
CAMERA = re.compile(r'^(?:img|dsc|dscn|pxl|gopr|dji|p|mvimg|screenshot|image|photo|foto|untitled)?[\s\d]*$', re.I)
WP_SIZE = re.compile(r'(?:[-_ ]\d{2,5}x\d{2,5}|[-_ ]scaled|[-_ ]e\d{10,}|[-_ ]\d{1,2})+$', re.I)
UNIQUE_ID = re.compile(r'^[0-9a-f]{7,}[-_ ]', re.I)
MAIN_OPEN = re.compile(rb'<main\b')
MAIN_CLOSE = re.compile(rb'</main>')
HEADING = re.compile(rb'<h[1-6]\b[^>]*>(.*?)</h[1-6]>', re.S)
FIGURE_OPEN = re.compile(rb'<figure\b')
FIGURE_CLOSE = re.compile(rb'</figure>')
SECTION_OPEN = re.compile(rb'<section\b')
SECTION_CLOSE = re.compile(rb'</section>')
FIGCAPTION = re.compile(rb'<figcaption\b[^>]*>(.*?)</figcaption>', re.S)
CONTROL_OPEN = re.compile(rb'<(a|button)\b[^>]*>')
CONTROL_CLOSE = re.compile(rb'</(?:a|button)>')
# the words this extension writes, in English; ``labels`` gives them in the page's language (models/ir_http.py)
LABELS = {'photo': 'Open photo', 'map': 'Open the map', 'home': 'Home'}


def _esc(text):
    return html.escape(text, quote=True).encode()


def words_of_file(name):
    """A file's name in words ("lake-atitlan-sunset_2-1024x683.jpg": "Lake atitlan sunset"); '' for a camera's
    name (IMG_1234, DSC0042) or one without words."""
    name = unquote(name or '').rsplit('/', 1)[-1].split('?')[0]
    name = re.sub(r'\.(?:jpe?g|png|webp|gif|avif|svg|bmp|tiff?)$', '', name, flags=re.I)
    name = UNIQUE_ID.sub('', WP_SIZE.sub('', name))
    words = ' '.join(re.sub(r'[-_+.]+', ' ', name).split())
    if CAMERA.match(words) or len(re.sub(r'[^A-Za-zÀ-ÿ]', '', words)) < 3:
        return ''
    return words[:1].upper() + words[1:]


def page_title(page, site=''):
    found = TITLE.search(page)
    title = html.unescape(TAGS.sub(b'', found.group(1)).decode('utf-8', 'replace')).strip() if found else ''
    for sep in (' | ', ' – ', ' - '):
        if sep in title:
            title = title.split(sep)[0].strip()
            break
    return title or site


def _words(fragment):
    """The words of an HTML fragment (bytes), tags out, spaces folded."""
    return ' '.join(html.unescape(TAGS.sub(b' ', fragment).decode('utf-8', 'replace')).split())


class _Context:
    """Where a picture is (a page in another language than the website's): its figure's caption, the heading it is
    under in the page's main area, the link or button with words it is part of."""

    def __init__(self, page):
        self.page = page
        main = MAIN_OPEN.search(page)
        end = main and MAIN_CLOSE.search(page, main.end())
        self.main = (main.start(), end.start() if end else len(page)) if main else (0, len(page))
        self.headings = [(m.start(), _words(m.group(1))) for m in HEADING.finditer(page, *self.main)]
        self.heading_starts = [pos for pos, _ in self.headings]

    def _inside(self, opener, closer, pos):
        """The end of the opening tag of the innermost ``opener`` element around ``pos`` (none closed between), and
        where it closes; else None."""
        start = None
        for found in opener.finditer(self.page, max(0, pos - 4000), pos):
            start = found
        if not start or closer.search(self.page, start.end(), pos):
            return None
        close = closer.search(self.page, pos)
        return (start.end(), close.start()) if close else None

    def caption(self, start, end):
        figure = self._inside(FIGURE_OPEN, FIGURE_CLOSE, start)
        if not figure:
            return ''
        found = FIGCAPTION.search(self.page, figure[0], figure[1])
        return _words(found.group(1)) if found else ''

    def heading(self, start):
        """The heading of the section the picture is in (a banner's title after its picture), else the last one
        before it in the main area."""
        if not self.main[0] <= start < self.main[1]:
            return ''
        section = self._inside(SECTION_OPEN, SECTION_CLOSE, start)
        if section:
            for found in HEADING.finditer(self.page, section[0], section[1]):
                if _words(found.group(1)):
                    return _words(found.group(1))
        i = bisect.bisect_left(self.heading_starts, start)
        while i > 0:
            i -= 1
            if self.headings[i][1]:
                return self.headings[i][1]
        return ''

    def in_words_control(self, start, end):
        """True for a picture inside a link or button that has words of its own (an icon beside them)."""
        control = self._inside(CONTROL_OPEN, CONTROL_CLOSE, start)
        if not control:
            return False
        return bool(_words(self.page[control[0]:start] + self.page[end:control[1]]))

    def neutral(self, start, end, title):
        return self.caption(start, end) or self.heading(start) or title


def _src_name(src, names):
    """The words for a picture at ``src``: its file name in the address, else its attachment's name."""
    src = html.unescape(src.decode('utf-8', 'replace'))
    path = urlsplit(src).path
    found = re.match(r'^/web/image/(\d+)(?:-[0-9a-f]+)?(?:/([^/]+))?$', path)
    if found:
        if found.group(2) and not re.match(r'^\d+x\d+$', found.group(2)):
            words = words_of_file(found.group(2))
            if words:
                return words
        return words_of_file(names.get(int(found.group(1)), ''))
    return words_of_file(path)


def image_ids(page):
    """The attachments of the pictures without an alt, or alt="" (their name may be all there is)."""
    ids = set()
    for img in IMG.finditer(page):
        if ALT.search(img.group(0)) and not EMPTY_ALT.search(img.group(0)):
            continue
        src = SRC.search(img.group(0))
        found = src and re.match(rb'^/web/image/(\d+)', src.group(1))
        if found:
            ids.add(int(found.group(1)))
    return ids


def default_alts(page, title, names=None, words=True):
    """``words``: a file's name may give the alt (a page in the website's own language); else the alt is the
    picture's caption, heading or the page's title (``_Context``)."""
    names = names or {}
    where = None if words else _Context(page)

    def name_of(img, src):
        if where is None:
            return (src and _src_name(src.group(1), names)) or title
        if where.in_words_control(img.start(), img.end()):
            return None  # (a decoration: alt="")
        return where.neutral(img.start(), img.end(), title)

    def fix(img):
        tag = img.group(0)
        if EMPTY_ALT.search(tag):
            # (0.4.1: alt="" is a decoration, except a picture with a title, or a photo of the content (the editor
            # leaves alt="" on the photos it adds): search engines and the crawl count those as without one)
            title_attr = TITLE_ATTR.search(tag)
            src = SRC.search(tag)
            if title_attr and title_attr.group(1).strip():
                return EMPTY_ALT.sub(b' alt="' + title_attr.group(1) + b'"', tag, count=1)
            if src and PHOTO_SRC.match(src.group(1)) and not DECORATIVE.search(tag):
                alt = name_of(img, src)
                return EMPTY_ALT.sub(b' alt="' + _esc(alt) + b'"', tag, count=1) if alt else tag
            return tag
        if ALT.search(tag):
            return tag
        alt = name_of(img, SRC.search(tag))
        if alt is None:
            return tag.replace(b'<img', b'<img alt=""', 1)
        return tag.replace(b'<img', b'<img alt="' + _esc(alt) + b'"', 1) if alt else tag
    return IMG.sub(fix, page)


def eager_logo(page):
    return LOGO_LINK.sub(lambda m: LAZY.sub(b'', m.group(0)), page)


def _own_host(netloc, own_hosts):
    """The site's own host (its address, with or without www.), never a business name in the code."""
    host = netloc.lower().split(':')[0].removeprefix('www.')
    return any(host == (h or '').lower().split(':')[0].removeprefix('www.') for h in own_hosts if h)


def _where(href, title, own_hosts=(), labels=None, same=None):
    """What a link opens, in words. ``labels``: this extension's words in the page's language; ``same``: {address:
    the words of a link to it} on a page in another language than the website's (an address's words are not used)."""
    labels = labels or LABELS
    href = html.unescape(href.decode('utf-8', 'replace')).strip()
    if not href or href.startswith(('javascript:', '#')):
        return ''
    if IMAGE_HREF.search(href.encode()):
        return labels['photo']
    parts = urlsplit(href)
    if parts.netloc and not _own_host(parts.netloc, own_hosts):
        host = parts.netloc.lower().removeprefix('www.')
        if 'maps' in host or host.startswith('goo.gl'):
            return labels['map']
        return host
    if same is not None:
        return same.get(href, '') or title
    if parts.path in ('', '/'):
        return labels['home']
    last = [p for p in parts.path.split('/') if p][-1]
    return words_of_file(re.sub(r'-\d+$', '', last)) or title


def _same_links(page):
    """{address: the words of the first link to it that has words, not vague ones}."""
    out = {}
    for link in LINK.finditer(page):
        href = HREF.search(link.group(1))
        if not href:
            continue
        key = html.unescape(href.group(1).decode('utf-8', 'replace')).strip()
        text = _words(link.group(2))
        if key not in out and text and not VAGUE.match(text):
            out[key] = text
    return out


def link_names(page, title, own_hosts=(), labels=None, words=True):
    labels = labels or LABELS
    same = None if words else _same_links(page)

    def fix(link):
        attrs, inner = link.group(1), link.group(2)
        if LABELLED.search(attrs):
            return link.group(0)
        text = html.unescape(TAGS.sub(b'', inner).decode('utf-8', 'replace')).strip()
        href = HREF.search(attrs)
        if text:
            if not VAGUE.match(' '.join(text.split())) or not href:
                return link.group(0)
            where = _where(href.group(1), '', own_hosts, labels, same)
            label = '%s: %s' % (' '.join(text.split()), where) if where and where != labels['photo'] else ''
        else:
            if IMG_ALT.search(inner) or NAMED_CHILD.search(inner):
                return link.group(0)
            label = _where(href.group(1), title, own_hosts, labels, same) if href else ''
        if not label:
            return link.group(0)
        return b'<a aria-label="' + _esc(label) + b'"' + attrs + b'>' + inner + b'</a>'
    return LINK.sub(fix, page)


def accessible(page, names=None, site='', own_hosts=(), labels=None, words=True):
    """The page with the fixes above; ``names``: {attachment id: its name} for the pictures without an alt;
    ``own_hosts``: the site's own addresses (a link there is one of its pages, not another site); ``labels``: this
    extension's words in the page's language (``LABELS``' keys); ``words``: False on a page in another language than
    the website's own (no file's or address's words)."""
    title = page_title(page, site)
    return link_names(eager_logo(default_alts(page, title, names, words)), title, own_hosts, labels, words)
