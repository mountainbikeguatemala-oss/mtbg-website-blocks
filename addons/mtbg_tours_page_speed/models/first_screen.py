"""The first screen first (page speed 0.7.7, owner 2026-11-08: "yes" to splitting the stylesheet): a visitor's page
waited for the whole site stylesheet before showing anything (852 KB, 160 KB as sent: the only file Google's phone
test found holding the first paint, 1.8 s of it), though a page uses a small part of it.

On the visitors' pages that get the stylesheet without Odoo's extras (``assets_frontend_lean``, models/lean.py), the
page now carries, in its head, the rules of that stylesheet its own HTML can match (and as much for an extension's own
stylesheet that holds the page too, Booking Form's on a tour with its booking panel: each in its own place) (about 25 KB as sent instead of
160 KB), in the stylesheet's order, and the whole stylesheet comes right after without holding the page
(``media="print"``, switched on when it has arrived), at the same place, so once it is there every rule applies as
before. A rule is kept when every class, id and element its selector names is in the page (what a selector asks
inside :not(), :is(), :where(), :has() or an attribute is not required: such a rule is kept, never dropped by
mistake); @font-face, @keyframes and the other at-rules are kept whole. The theme's font stylesheets (the site
stylesheet's ``@import``s) are linked in the head instead, so the words show in the theme's fonts at once.

Logged-in users (the editor), the portal, checkout and payment pages keep Odoo's stylesheet (they never get the lean
one), and a page whose stylesheet is not built yet is left as it is. The rules are worked out once per stylesheet
version and page shape (cached), and Cloudflare keeps the result with the page."""
import html
import re
from collections import OrderedDict
from hashlib import sha1

LEAN = re.compile(rb'<link\b[^>]*\bhref="(/web/assets/[^"]*mtbg_tours_page_speed\.assets_frontend_lean(?:\.min)?\.css)"'
                  rb'[^>]*>')
DONE = b'data-mtbg-first-screen=""'
IMPORT = re.compile(r'@import\s+url\(\s*["\']?([^"\')]+)["\']?\s*\)')
COMMENT = re.compile(r'/\*.*?\*/', re.S)
PSEUDO_FN = re.compile(r':(?:not|is|where|has|matches|-webkit-any|-moz-any|host|host-context|nth-child|'
                       r'nth-last-child|nth-of-type|nth-last-of-type|lang|dir)\(')
TOKEN = re.compile(r'([.#])((?:\x01[0-9a-f]{6}|[\w-])+)|(?:^|(?<=[\s>+~(]))([a-zA-Z][\w-]*)')
ESCAPE = re.compile(r'\\(.)')
UNESCAPE = re.compile(r'\x01([0-9a-f]{6})')
CLASS_ATTR = re.compile(rb'\sclass\s*=\s*(?:"([^"]*)"|\'([^\']*)\')', re.I)
ID_ATTR = re.compile(rb'\sid\s*=\s*(?:"([^"]*)"|\'([^\']*)\')', re.I)
TAG = re.compile(rb'<([a-zA-Z][\w-]*)')
ATTR_NAME = re.compile(r'\[\s*(?:[\w*-]*\|(?!=))?([\w-]+)')
# a tag (its name, its attributes) or a comment, for walking a page's markup
MARKUP = re.compile(rb'<!--.*?-->|<(/?)([a-zA-Z][\w-]*)((?:[^>"\']|"[^"]*"|\'[^\']*\')*)>', re.S)
QUOTED = re.compile(rb'"[^"]*"|\'[^\']*\'')
NAMES = re.compile(rb'([a-zA-Z_:@][-\w:.@]*)')
VOID = {b'area', b'base', b'br', b'col', b'embed', b'hr', b'img', b'input', b'link', b'meta', b'source', b'track',
        b'wbr', b'param'}
RAW = {b'script', b'style', b'template', b'textarea', b'noscript'}
GROUPS = ('media', 'supports', 'layer', 'container', 'document', '-moz-document')
# the whole stylesheets (data-mtbg-late-href) asked for when the page has loaded (its photos in), or at once if it has
LATE_SCRIPT = (b'<script %s>(function(){function go(){[].forEach.call(document.querySelectorAll("link[data-mtbg-late-href]"),'
               b'function(l){l.href=l.getAttribute("data-mtbg-late-href");l.removeAttribute("data-mtbg-late-href")})}'
               b'if(document.readyState==="complete"){go()}else{window.addEventListener("load",go)}})();</script>' % DONE)
MAX_SHARE = 0.6   # a page that would carry more than this part of the stylesheet keeps the stylesheet as it is

_parsed = OrderedDict()   # url -> (rules, imports)
_kept = OrderedDict()     # (url, page shape) -> css


def _cache(store, key, size, make):
    if key in store:
        store.move_to_end(key)
        return store[key]
    value = store[key] = make()
    while len(store) > size:
        store.popitem(last=False)
    return value


def parse(css):
    """[(kind, prelude, body)] of a stylesheet: 'rule' (body: its declarations), 'group' (@media and the like, body:
    its own list), 'at' (any other at-rule, whole, in prelude); plus its @import addresses."""
    css = COMMENT.sub('', css)
    n = len(css)

    def close_of(start):
        depth, k = 0, start
        while k < n:
            c = css[k]
            if c in '"\'':
                end = css.find(c, k + 1)
                k = end + 1 if end >= 0 else n
                continue
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if not depth:
                    return k
            k += 1
        return n

    def walk(j, end):
        items = []
        while j < end:
            while j < end and css[j] in ' \t\r\n;':
                j += 1
            if j >= end:
                break
            brace, semi = css.find('{', j, end), css.find(';', j, end)
            if css[j] == '@' and (brace < 0 or 0 <= semi < brace):
                items.append(('at', css[j:semi + 1], None))
                j = semi + 1
                continue
            if brace < 0:
                break
            prelude, close = css[j:brace].strip(), close_of(brace)
            if prelude.startswith('@'):
                name = prelude[1:].split(None, 1)[0].lower() if len(prelude) > 1 else ''
                if name in GROUPS:
                    items.append(('group', prelude, walk(brace + 1, close)))
                else:
                    items.append(('at', css[j:close + 1], None))
            else:
                items.append(('rule', prelude, css[brace + 1:close]))
            j = close + 1
        return items
    items = walk(0, n)
    imports = [u for kind, text, _b in items if kind == 'at' and text.lower().startswith('@import')
               for u in IMPORT.findall(text)]
    return items, imports


def _selectors(prelude):
    parts, depth, cur = [], 0, []
    for c in prelude:
        depth += c in '(['
        depth -= c in ')]'
        if c == ',' and not depth:
            parts.append(''.join(cur))
            cur = []
        else:
            cur.append(c)
    parts.append(''.join(cur))
    return [p.strip() for p in parts if p.strip()]


def needs(selector):
    """The classes ('.x'), ids ('#x') and elements a selector requires in the page."""
    # (an escaped character, as in Bootstrap's or Tailwind's 'sm\:p-2', is part of its name, never a pseudo-class)
    selector = ESCAPE.sub(lambda m: '\x01%06x' % ord(m.group(1)), selector)
    out, depth, i = [], 0, 0
    while i < len(selector):
        found = PSEUDO_FN.match(selector, i) if not depth else None
        if found:
            depth, i = 1, found.end()
            continue
        c = selector[i]
        if depth:
            depth += c == '('
            depth -= c == ')'
        else:
            out.append(c)
        i += 1
    joined = ''.join(out)
    # (0.8.0: an attribute a selector asks for is required too, by its name: '[data-bs-theme="dark"]' only where some
    # element has a data-bs-theme; what it must equal is not checked, so such a rule is never dropped by mistake)
    required = {'[' + name.lower() for name in ATTR_NAME.findall(joined)}
    plain = re.sub(r'::?[\w-]+', ' ', re.sub(r'\[[^\]]*\]', ' ', joined))
    for m in TOKEN.finditer(plain):
        if m.group(1):
            required.add(m.group(1) + UNESCAPE.sub(lambda e: chr(int(e.group(1), 16)), m.group(2)))
        elif m.group(3):
            required.add(m.group(3).lower())
    return required


def page_tokens(page):
    """The classes, ids and elements of a page's HTML."""
    tokens = {'html', 'body', '*'}
    for m in CLASS_ATTR.finditer(page):
        tokens.update('.' + c for c in html.unescape((m.group(1) or m.group(2) or b'').decode('utf-8', 'replace'))
                      .split())
    for m in ID_ATTR.finditer(page):
        tokens.add('#' + html.unescape((m.group(1) or m.group(2) or b'').decode('utf-8', 'replace')).strip())
    tokens.update(t.decode().lower() for t in TAG.findall(page))
    for m in MARKUP.finditer(page):  # (0.8.0: the attributes' names, for the selectors that ask for one)
        if m.group(2) and not m.group(1):
            names = NAMES.findall(QUOTED.sub(b'', m.group(3)))
            tokens.update('[' + n.decode('utf-8', 'replace').lower() for n in names)
    return tokens


# 0.8.0 (owner 2026-11-16, fix A: "the cover paints first"): the first screen's rules are the rules of what the first
# screen shows, not of the whole page (a tour page carried 156 KB of them, nearly the whole stylesheet, parsed before
# the cover could paint): the header and what is above the page's content, and the content's first FOLD bytes of
# markup. What is hidden until a visitor opens it (a closed dropdown or mega menu, the phone menu, a modal, an element
# with the hidden attribute or Bootstrap's d-none) brings its own element's rules (those that hide it), not its
# content's. The rest of the page gets its rules with the whole stylesheet, asked for when the page has loaded (and
# the visitors' scripts wait for it: static/src/js/lazyloader.js).
FOLD = 15000
HIDING = re.compile(r'^(?:dropdown-menu|offcanvas|modal|d-none|mtbg-tip)$')
# 0.9.1 (owner 2026-11-17, "inline only the CSS of the first screen"): the content's first FOLD_TEXT bytes of markup
# are counted without its long attribute values (a tour's stats inlined a 20 KB icon in a style: it filled the budget),
# and a rating's popup (.mtbg-tip, shown on hover) is hidden content too. (A smaller budget let a short tour's booking
# panel in only in part: its contact form came up unstyled into a phone's first screen, and moved when the whole
# stylesheet came: a layout shift.)
FOLD_TEXT = 15000
LONG_VALUE = re.compile(rb'(\s(?:style|srcset|src|href|data-[\w-]+)\s*=\s*)(?:"[^"]{120,}"|\'[^\']{120,}\')', re.I)
SHOWING = re.compile(r'^d-(?:\w+-)?(?:block|flex|inline|inline-block|inline-flex|grid|table|table-cell|table-row|'
                     r'contents)$')
MAIN_OPEN = re.compile(rb'<main\b')


def _hides(attrs):
    """An element hidden until a visitor or a script opens it (its own rules still count)."""
    bare = QUOTED.sub(b'""', attrs)
    if re.search(rb'(?:^|\s)hidden(?:[\s=/]|$)', bare):
        return True
    found = CLASS_ATTR.search(attrs)
    if not found:
        return False
    classes = html.unescape((found.group(1) or found.group(2) or b'').decode('utf-8', 'replace')).split()
    hides = [c for c in classes if HIDING.match(c)]
    # ('d-none d-lg-block': shown on a computer; 'offcanvas-lg' and the like are not 'offcanvas')
    return bool(hides) and not (hides == ['d-none'] and any(SHOWING.match(c) for c in classes))


def shown(page, start, end, budget=None, hidden_tags=None):
    """The markup of ``page[start:end]`` a first screen can show: without the content of hidden elements (their own
    tag stays, and is added to ``hidden_tags`` when given), of scripts, styles and templates; at most ``budget`` bytes
    of it."""
    out, kept, at, pos = [], 0, start, start
    while True:
        m = MARKUP.search(page, pos, end)
        if not m:
            out.append(page[at:end])
            break
        if budget is not None and kept + m.end() - at > budget:
            out.append(page[at:m.end()])
            break
        close, name, attrs = m.group(1), (m.group(2) or b'').lower(), m.group(3) or b''
        pos = m.end()
        if not name or close or name in VOID or attrs.rstrip().endswith(b'/'):
            continue
        hidden = _hides(attrs)
        if name not in RAW and not hidden:
            continue
        # (skip to its end: its own tag kept)
        if hidden and hidden_tags is not None:
            hidden_tags.append(m.group(0))
        out.append(page[at:m.end()])
        kept += m.end() - at
        if name in RAW and not hidden:
            closing = re.compile(rb'</' + re.escape(name) + rb'\s*>', re.I).search(page, pos, end)
            pos = closing.end() if closing else end
        else:
            pos = element_end(page, pos, end)
        at = pos
    return b''.join(out)


def element_end(page, pos, end=None):
    """Where the element whose opening tag ends at ``pos`` ends (after its closing tag), else ``end``."""
    end = len(page) if end is None else end
    depth = 1
    while depth and pos < end:
        inner = MARKUP.search(page, pos, end)
        if not inner:
            return end
        pos = inner.end()
        name = (inner.group(2) or b'').lower()
        if not name or name in VOID or (inner.group(3) or b'').rstrip().endswith(b'/'):
            continue
        if name in RAW and not inner.group(1):
            closing = re.compile(rb'</' + re.escape(name) + rb'\s*>', re.I).search(page, pos, end)
            pos = closing.end() if closing else end
            continue
        depth += -1 if inner.group(1) else 1
    return pos if not depth else end


# 0.8.0 (fix A, "the cover earlier in the page"): the menus' hidden content (the computer's mega menus, the phone
# menu) came before the page's content: ~70-90 KB of markup a browser read before it reached the cover. It is sent
# after the content now, in <template>s, and put back in its place by a small script as soon as the content is read
# (before any of the visitors' scripts runs, which find every menu where it always was). Only hidden elements without
# a script of their own move (a closed dropdown or mega menu, the phone menu), only above the content.
MOVE_MIN = 1500
MOVE = re.compile(r'^(?:dropdown-menu|offcanvas)$')
LATER = b'data-mtbg-later'
LATER_SCRIPT = (b'<script %s="">(function(){[].forEach.call(document.querySelectorAll("template[data-mtbg-later]"),'
                b'function(t){var s=document.querySelector(\'template[data-mtbg-slot="\''
                b'+t.getAttribute("data-mtbg-later")'
                b'+\'"]\');if(s){s.parentNode.replaceChild(t.content,s)}t.parentNode.removeChild(t)})})();</script>'
                % LATER)


# 0.8.0 (fix A, the logo as the LCP): a header logo is the first picture of the page's body (the phone header's is
# drawn 229 x 36 px by the site's rules, not 95 x 40) and, at normal priority, it arrived and painted before the cover
# (every local phone run: the logo a candidate ~0.3-2 s before the cover), so a Lighthouse run that missed the
# cover's paint kept the logo as the page's LCP. The header's logos now ask for low priority: the cover (preloaded with
# high priority) comes first, and a logo painted after it is never a candidate (it is smaller). Never lazy.
LOGO = re.compile(rb'(<a\b[^>]*\bclass="[^"]*\bnavbar-brand\b[^"]*"[^>]*>(?:(?!</a>).){0,600}?)'
                  rb'<img\b(?![^>]*fetchpriority=)', re.S)


def logo_low(page):
    """The header's logos (before the page's content) at low priority, when the page preloads its first picture."""
    main = MAIN_OPEN.search(page)
    if not main or b'rel="preload" as="image" fetchpriority="high"' not in page[:page.find(b'</head>')]:
        return page
    head = LOGO.sub(lambda m: m.group(1) + b'<img fetchpriority="low"', page[:main.start()])
    return head + page[main.start():]


def menus_later(page):
    """The page with the menus' hidden content after its main content (put back at once by LATER_SCRIPT)."""
    if LATER in page:
        return page
    body = re.search(rb'<body\b', page)
    main = body and MAIN_OPEN.search(page, body.start())
    main_end = main and page.find(b'</main>', main.start())
    if not main or main_end < 0:
        return page
    moves, pos = [], body.end()
    while True:
        m = MARKUP.search(page, pos, main.start())
        if not m:
            break
        pos = m.end()
        name, attrs = (m.group(2) or b'').lower(), m.group(3) or b''
        if not name or m.group(1) or name in VOID:
            continue
        if name in RAW:
            pos = element_end(page, pos, main.start())
            continue
        found = CLASS_ATTR.search(attrs)
        classes = html.unescape((found.group(1) or found.group(2) or b'').decode('utf-8', 'replace')).split() \
            if found else []
        if not any(MOVE.match(c) for c in classes):
            continue
        stop = element_end(page, pos, main.start())
        inner = page[pos:stop]
        close = inner.rfind(b'</')
        if close < 0 or stop - pos < MOVE_MIN or b'<script' in inner or b'<template' in inner:
            pos = stop
            continue
        moves.append((pos, pos + close))   # (its content; its own tag stays: its rules and Bootstrap's find it)
        pos = stop
    if not moves:
        return page
    out, later, last = [], [], 0
    for n, (start, stop) in enumerate(moves):
        out += [page[last:start], b'<template data-mtbg-slot="%d"></template>' % n]
        later.append(b'<template %s="%d">%s</template>' % (LATER, n, page[start:stop]))
        last = stop
    main_end += len(b'</main>')
    out += [page[last:main_end], b''.join(later), LATER_SCRIPT, page[main_end:]]
    return b''.join(out)


def first_screen_html(page, hidden_tags=None):
    """What the first screen can show of a page: its body above the content (the header, a notice), and the content's
    first FOLD_TEXT bytes of markup, hidden things without their content (their own tags in ``hidden_tags``)."""
    body = re.search(rb'<body\b', page)
    if not body:
        return page
    main = MAIN_OPEN.search(page, body.start())
    if not main:
        rest = _short_values(page[body.start():])
        return shown(rest, 0, len(rest), FOLD, hidden_tags)
    html_tag = re.search(rb'<html\b[^>]*>', page[:body.start()])
    content = _short_values(page[main.start():])
    return ((html_tag.group(0) if html_tag else b'') + shown(page, body.start(), main.start(), None, hidden_tags)
            + shown(content, 0, len(content), FOLD_TEXT, hidden_tags))


def hidden_only(screen, hidden_tags):
    """The classes and ids found only on the first screen's hidden elements (a closed menu, the phone menu, a popup):
    a rule for what is inside one of them draws nothing on the first screen (0.9.1)."""
    rest = screen
    for tag in hidden_tags:
        rest = rest.replace(tag, b'', 1)
    return frozenset(t for t in page_tokens(b''.join(hidden_tags)) - page_tokens(rest) if t[:1] in '.#')


# what changes nothing on the first paint (0.9.1): transitions (and so none starts when the whole stylesheet comes),
# the pointer's look, tap highlights, hints to the browser
LATER_DECL = re.compile(r'(?:transition|cursor|-webkit-tap-highlight-color|will-change)[\w-]*\s*:', re.I)
# a hidden element's declarations kept on the first screen (0.9.1): where it is, its size and whether it shows
BOX = re.compile(r'(?:display|visibility|position|inset|top|right|bottom|left|float|clear|transform|translate|opacity|'
                 r'z-index|content|width|height|min-width|min-height|max-width|max-height|overflow(?:-[xy])?|margin|'
                 r'padding|border-width|box-sizing|flex|order|grid|align-self|justify-self|clip|clip-path|'
                 r'font-size|line-height|aspect-ratio|contain|--)[\w-]*\s*:', re.I)


def _subject(selector):
    """A selector's last compound (what it styles): '.a > .b:hover' -> '.b:hover'."""
    depth, last = 0, 0
    for i, c in enumerate(selector):
        depth += c in '(['
        depth -= c in ')]'
        if not depth and c in ' >+~':
            last = i + 1
    return selector[last:]


COMBINATOR = re.compile(r'\s*([>+~])\s*|\s+')


def _compounds(selector):
    """[(compound, combinator after it)] of a selector, the last with ''."""
    parts, depth, cur, i = [], 0, [], 0
    while i < len(selector):
        c = selector[i]
        depth += c in '(['
        depth -= c in ')]'
        if not depth:
            found = COMBINATOR.match(selector, i)
            if found and (cur or found.group(1)):
                parts.append((''.join(cur), found.group(1) or ' '))
                cur = []
                i = found.end()
                continue
        cur.append(c)
        i += 1
    parts.append((''.join(cur), ''))
    return [(compound, combinator) for compound, combinator in parts if compound or combinator]


def _inside(selector, hidden):
    """Whether a selector reaches into an element of ``hidden`` (one of its classes or ids is in the selector, before
    a descendant or child combinator: ``.offcanvas .nav-link``; never its own rules, nor a sibling's)."""
    return bool(hidden) and any(combinator in ' >' and combinator and needs(compound) & hidden
                                for compound, combinator in _compounds(selector) if compound)


ELEMENT = re.compile(r'^([a-zA-Z][\w-]*)')


def nesting(screen):
    """{element: how deep it is nested in itself at most} in the first screen's markup ('ul': 2, a list in a list)."""
    open_names, deepest = [], {}
    for m in MARKUP.finditer(screen):
        name = (m.group(2) or b'').lower()
        if not name or name in VOID or (m.group(3) or b'').rstrip().endswith(b'/'):
            continue
        if m.group(1):
            if name in open_names:
                del open_names[len(open_names) - 1 - open_names[::-1].index(name):]
            continue
        open_names.append(name)
        count = open_names.count(name)
        key = name.decode('utf-8', 'replace')
        if count > deepest.get(key, 0):
            deepest[key] = count
    return deepest


def _too_deep(selector, depths):
    """Whether a selector asks for an element inside more of its kind than the first screen has (Bootstrap's
    'ul ul ul ...' list resets: one list in the header)."""
    if depths is None:
        return False
    chain = {}
    for compound, combinator in _compounds(selector):
        found = ELEMENT.match(compound)
        if found:
            name = found.group(1).lower()
            chain[name] = chain.get(name, 0) + 1
            if chain[name] > max(depths.get(name, 0), 1):
                return True
        if combinator in '+~' and combinator:
            chain = {}
    return False


def _short_values(markup):
    """The markup with its long style, src, srcset, href and data-* values emptied (an inlined picture, a srcset):
    they hold nothing a rule asks for, and are not what the first screen shows."""
    return LONG_VALUE.sub(lambda m: m.group(1) + b'""', markup)


VAR_USE = re.compile(r'var\(\s*(--[\w-]+)')


def page_vars(page):
    """The custom properties a page's own HTML uses (its style attributes, its own style elements)."""
    return frozenset(v.decode() for v in re.findall(rb'var\(\s*(--[\w-]+)', page))


def _declarations(body):
    """A rule's declarations (split at its top-level semicolons, never inside a string or parentheses)."""
    parts, depth, quote, cur = [], 0, None, []
    for c in body:
        if quote:
            quote = None if c == quote else quote
        elif c in '"\'':
            quote = c
        elif c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        elif c == ';' and not depth:
            parts.append(''.join(cur))
            cur = []
            continue
        cur.append(c)
    parts.append(''.join(cur))
    return [p for p in parts if p.strip()]


def _tight(declaration):
    """'  color: red ' -> 'color:red' (its value as it is inside)."""
    name, colon, value = declaration.partition(':')
    return name.strip() + colon + value.strip() if colon else declaration.strip()


def _prune_vars(rules, used):
    """0.8.0: the custom properties (--x: ...) of the kept rules that nothing kept uses (a kept rule, a used custom
    property's value, the page's own HTML): ``:root`` alone declares ~2,500 of them. The scripts wait for the whole
    stylesheet, so a script reading one still finds it."""
    decls = []   # (rule index or path, [declarations])

    def collect(parts):
        for kind, value in parts:
            if kind == 'group':
                collect(value[1])
            elif kind == 'rule':
                brace = value.index('{')
                decls.append(_declarations(value[brace + 1:-1]))
            elif kind == 'at':
                used.update(VAR_USE.findall(value))
    collect(rules)
    defined = {}
    for parts in decls:
        for d in parts:
            name, colon, rest = d.partition(':')
            name = name.strip()
            if colon and name.startswith('--'):
                defined.setdefault(name, []).append(rest)
            else:
                used.update(VAR_USE.findall(d))
    todo = list(used)
    while todo:
        for rest in defined.get(todo.pop(), ()):
            for v in VAR_USE.findall(rest):
                if v not in used:
                    used.add(v)
                    todo.append(v)

    def keep(parts):
        out = []
        for kind, value in parts:
            if kind == 'group':
                inner = keep(value[1])
                if inner:
                    out.append(('group', (value[0], inner)))
            elif kind == 'rule':
                brace = value.index('{')
                body = [_tight(d) for d in _declarations(value[brace + 1:-1])
                        if not d.strip().startswith('--') or d.partition(':')[0].strip() in used]
                if body:
                    out.append(('rule', value[:brace].strip() + '{' + ';'.join(body) + '}'))
            else:
                out.append((kind, value))
        return out
    return keep(rules)


KEYFRAMES = re.compile(r'@(?:-[a-z]+-)?keyframes\s+([^\s{]+)', re.I)
WORD = re.compile(r'[\w-]+')


# 0.9.1: a selector for what a visitor does (hover, focus, a press) never draws the first screen: such rules come with
# the whole stylesheet (asked for when the page has loaded). Only where the state is the selector's own (outside
# :not(), :is() and the like: ".x:not(:hover)" draws the first screen).
ACTION = re.compile(r':(?:hover|focus|focus-visible|focus-within|active)(?![\w-])', re.I)
PRINT = re.compile(r'^@media\s+(?:only\s+)?print\s*$', re.I)
NESTED = re.compile(r'\([^()]*\)')


def acted(selector):
    """Whether a selector matches only while a visitor hovers, focuses or presses something."""
    while True:
        bare = NESTED.sub('', selector)
        if bare == selector:
            break
        selector = bare
    return bool(ACTION.search(selector))


def _rules(items, tokens, hidden=frozenset(), depths=None):
    """[(kind, text)] of the rules the page can match ('rule', 'at', or 'group' with its own list), in their order;
    a selector named twice in one list once (0.7.12); none for what a visitor does (0.9.1)."""
    out = []
    for kind, prelude, body in items:
        if kind == 'at':
            if not prelude.lower().startswith('@import'):
                out.append(('at', prelude))
        elif kind == 'group':
            if PRINT.match(prelude):
                continue  # (0.9.1: what a printed page looks like)
            inner = _rules(body, tokens, hidden, depths)
            if inner:
                out.append(('group', (prelude, inner)))
        else:
            selectors = list(dict.fromkeys(s for s in _selectors(prelude)
                                           if not acted(s) and needs(s) <= tokens and not _inside(s, hidden)
                                           and not _too_deep(s, depths)))
            if selectors and LATER_DECL.search(body):
                body = ';'.join(d for d in _declarations(body) if not LATER_DECL.match(d.strip()))
            if selectors and hidden and all(needs(_subject(s)) & hidden for s in selectors):
                # (0.9.1: a hidden element's own rules: what places, sizes and hides it; its colours, fonts and the
                # like come with the whole stylesheet, before anyone opens it)
                body = ';'.join(d for d in _declarations(body) if BOX.match(d.strip()))
            if selectors and body.strip():
                out.append(('rule', ','.join(selectors) + '{' + body + '}'))
    return out


def page_animations(page):
    """The names a page's own HTML gives an animation (its style attributes)."""
    return frozenset(w.decode('utf-8', 'replace') for value in re.findall(rb'animation[\w-]*\s*:([^;"\'>]*)', page)
                     for w in re.findall(rb'[\w-]+', value))


def kept(items, tokens, animations=(), variables=None, fonts=None, hidden=frozenset(), depths=None):
    """The stylesheet's rules the page can match, in their order (its @imports left out: linked in the head).
    0.7.12: an animation's @keyframes only where a kept rule (or the page itself) names it: the others come with the
    whole stylesheet, before any script can start one."""
    rules = _rules(items, tokens, hidden, depths)
    if variables is not None:
        rules = _prune_vars(rules, set(variables))
    named = set()

    def names(parts):
        for kind, text in parts:
            if kind == 'group':
                names(text[1])
            elif kind == 'rule':
                named.update(WORD.findall(text[text.index('{'):]))
    names(rules)
    named.update(animations)

    # (0.9.1: the text of the kept rules' declarations, custom properties included: where a font's family is named)
    declared = []

    def bodies(parts):
        for kind, text in parts:
            if kind == 'group':
                bodies(text[1])
            elif kind == 'rule':
                declared.append(text[text.index('{'):].lower())
    bodies(rules)
    declared = '\n'.join(declared)

    def used_family(family):
        return fonts is None or family in fonts or bool(family) and (
            '"%s"' % family in declared or "'%s'" % family in declared
            or re.search(r'[\s:,]%s\s*[,;}!]' % re.escape(family), declared) is not None)
    # (0.9.1: one @font-face per family, style, weight and range: the last, as the browser keeps it)
    last_face = {}

    def faces(parts):
        for kind, value in parts:
            if kind == 'group':
                faces(value[1])
            elif kind == 'at' and FONT_FACE.match(value):
                last_face[_face_key(value)] = value
    faces(rules)

    def text(parts):
        out = []
        for kind, value in parts:
            if kind == 'group':
                inner = text(value[1])
                if inner:
                    out.append(value[0] + '{' + inner + '}')
            elif kind == 'at':
                frames = KEYFRAMES.match(value)
                if FONT_FACE.match(value):
                    # (0.9.1: a font only where a kept rule or the page names its family; the others come with the
                    # whole stylesheet)
                    key = _face_key(value)
                    if last_face.get(key) is value and used_family(key[0]):
                        out.append(value)
                elif not frames or frames.group(1).strip('"\'') in named:
                    out.append(value)
            else:
                out.append(value)
        return ''.join(out)
    return text(rules)


FONT_FACE = re.compile(r'@font-face\b', re.I)
FACE_PART = re.compile(r'(?:^|[{;])\s*(font-family|font-style|font-weight|unicode-range)\s*:([^;}]*)', re.I)


def _family(name):
    return name.strip().strip('"\'').strip().lower()


def _face_key(face):
    """(family, style, weight, range) of an @font-face."""
    parts = {k.lower(): v.strip() for k, v in FACE_PART.findall(face)}
    return (_family(parts.get('font-family', '')), parts.get('font-style', 'normal').lower(),
            parts.get('font-weight', '400').lower(), parts.get('unicode-range', '').lower())


def page_fonts(page):
    """The font families a page's own HTML names (its style attributes and elements)."""
    return frozenset(_family(name.decode('utf-8', 'replace'))
                     for value in re.findall(rb'font(?:-family)?\s*:([^;"\'>}]*)', page)
                     for name in value.split(b','))


SHEET = re.compile(rb'<link\b[^>]*\brel="stylesheet"[^>]*>')
HREF = re.compile(rb'\bhref="(/web/assets/[^"]+\.css)"')
BUNDLE = re.compile(r'^/web/assets/(?:\d+/)?[^/]+/([\w.]+?)(?:\.min)?\.css$')


def bundle_of(url):
    """The asset bundle a stylesheet address is for ('mtbg_tours_booking_form.assets_booking'), or None."""
    found = BUNDLE.match(url)
    return found and found.group(1)


def _one(url, css):
    """(its version key, (its parsed rules, its imports)): a stylesheet read once per version."""
    version = (url, len(css), sha1(css[:4096].encode()).hexdigest())
    return version, _cache(_parsed, version, 12, lambda: parse(css))


def first_screen(page, css_of=lambda url: None):
    """The visitor's lean page with, in place of each stylesheet that holds it (the site's, and an extension's own,
    like Booking Form's), the rules of that stylesheet the page uses, and the whole stylesheet right after it, not
    holding the page (``css_of(url)``: a stylesheet's text, None while it cannot be had: that one stays as it is)."""
    if DONE in page or not LEAN.search(page):
        return page
    head_end = page.find(b'</head>')
    if head_end < 0:
        return page
    hidden_tags = []
    screen = first_screen_html(page, hidden_tags)
    tokens = page_tokens(screen)   # (0.8.0: what the first screen shows, not the whole page)
    hidden = hidden_only(screen, hidden_tags)
    depths = nesting(screen)
    animations = page_animations(page)
    variables = page_vars(page)
    fonts = page_fonts(page)
    shape = sha1((' '.join(sorted(tokens)) + '|' + ' '.join(sorted(animations)) + '|' + ' '.join(sorted(variables))
                  + '|' + ' '.join(sorted(fonts)) + '|' + ' '.join(sorted(hidden))
                  + '|' + ' '.join('%s%d' % d for d in sorted(depths.items()))).encode()).hexdigest()
    out, last, preconnect = [], 0, False
    for link in SHEET.finditer(page, 0, head_end):
        tag = link.group(0)
        href = HREF.search(tag)
        if not href or b' media=' in tag or page[max(0, link.start() - 10):link.start()].endswith(b'<noscript>'):
            continue
        url = href.group(1).decode()
        css = css_of(url)
        if not css:
            continue
        version, (items, imports) = _one(url, css)
        rules = _cache(_kept, (version, shape), 300,
                       lambda: kept(items, tokens, animations, variables, fonts, hidden, depths))
        if len(rules) > MAX_SHARE * len(css):
            continue
        quoted = html.escape(url, quote=True).encode()
        swap = []
        for font in imports:
            if not font.startswith(('https://', '/')):
                continue
            if font.startswith('https://fonts.googleapis.com/') and not preconnect:
                swap.append(b'<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin=""/>')
                preconnect = True
            swap.append(b'<link rel="stylesheet" href="%s" %s/>' % (html.escape(font, quote=True).encode(), DONE))
        if rules:
            swap.append(b'<style %s>%s</style>' % (DONE, rules.replace('</', '<\\/').encode()))
        # (0.7.10: the whole stylesheet once the page has loaded, not while its first photo is still coming: the
        # page's own HTML has its rules already; only what scripts add later needs the rest)
        swap.append(b'<link rel="stylesheet" data-mtbg-late-href="%s" media="print" onload="this.media=\'all\'" %s/>'
                    % (quoted, DONE))
        swap.append(b'<noscript><link rel="stylesheet" href="%s"/></noscript>' % quoted)
        out += [page[last:link.start()], b''.join(swap)]
        last = link.end()
    if not out:
        return page
    page = b''.join(out) + page[last:]
    head_end = page.find(b'</head>')
    return logo_low(menus_later(page[:head_end] + LATE_SCRIPT + page[head_end:]))
