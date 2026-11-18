"""The page's pictures as fast as the visitor's screen allows (page speed, phase 4), on the page sent to an anonymous
visitor (so Odoo's page cache and Cloudflare keep the result):

* the first picture of the main area loads at once (preloaded with high priority, as the copy of its srcset the
  screen takes; an <img> no longer lazy), and only it: the main area's other pictures wait for the page's layout;
* a section's background photo comes as its ready phone / tablet copy (the 'resize: <px>' WebP copies, only when
  lighter than the original: a picture without one stays as it is, never broken nor heavier), the original on
  computers;
* a photo of the content gets its width and height (no jump while it loads) and its ready smaller copies (srcset).
Only pictures the visitor may see anyway: public image attachments.

And the text first (0.3.0): the theme's font stylesheets, which the site's stylesheet only asks for once it has
arrived (``@import``), are fetched with it (a preload each), so the page's words show about half a second sooner on
a phone.

And the first screen first (0.7.7, models/first_screen.py): the rules of the site stylesheet the page uses in its head,
the whole stylesheet after it without holding the page.
"""
import html
import logging
import re
from urllib.parse import urlsplit

from odoo import models
from odoo.http import request

from .a11y import accessible, image_ids
from .first_screen import DONE as FIRST_DONE, bundle_of, first_screen

_logger = logging.getLogger(__name__)
MAIN = re.compile(rb'<main\b|id="wrap"')
# where a preload goes: after the head's charset (which must stay in its first 1024 bytes), else right after <head>
CHARSET = re.compile(rb'<meta\s+charset=[^>]*>', re.I)
# 0.9.1: ... and after the head's viewport (a phone reading a preload's imagesizes before it took the page as 980 px
# wide: a tour's cover preloaded its 1920 px original, 326 KB at high priority, besides the 800 px copy it shows)
VIEWPORT = re.compile(rb'<meta\s+name="viewport"[^>]*>', re.I)
HEAD_OPEN = re.compile(rb'<head\b[^>]*>', re.I)
IMG = re.compile(rb'<img\b[^>]*>')
# (the quotes as the editor saves them: &#34; &quot;, and &#39; &apos; (0.4.1: www's Contact us cover was missed))
BACKGROUND = re.compile(rb'background-image:\s*url\((?:&#34;|&quot;|&#39;|&apos;|["\'])?([^)"\'&]+?)'
                        rb'(?:&#34;|&quot;|&#39;|&apos;|["\'])?\)')
SRC = re.compile(rb'\bsrc="([^"]+)"')
LAZY = re.compile(rb'\sloading="lazy"')
EAGER = re.compile(rb'\sloading="eager"')
IMAGE_URL = re.compile(rb'^/web/image/(\d+)(?:-[0-9a-f]+)?(?:/([^/?#]+))?$')
SIZE = re.compile(rb'^\d+x\d+$')
DONE = b'rel="preload" as="image" fetchpriority="high"'
QUIET_BG_MEDIA = b'(min-width: 992px)'
# (media query, width of the copy): phones and tablets; computers keep the original
SCREENS = ((b'(max-width: 767.98px)', 800), (b'(min-width: 768px) and (max-width: 1279.98px)', 1280))
RESIZE = re.compile(r'^resize: (\d+)$')
STYLESHEET = re.compile(rb'<link[^>]*rel="stylesheet"[^>]*href="(/web/assets/[^"]*(?:web\.assets_frontend|mtbg_tours_page_speed\.assets_frontend_lean)(?:\.min)?\.css)"')
IMPORT = re.compile(r'@import\s+url\(\s*["\']?([^"\')]+)["\']?\s*\)')
FONTS_DONE = b'data-mtbg-fonts=""'
_imports = {}  # the site's stylesheet (its address: its version) -> its imported stylesheets


def attachment_id(url):
    """The attachment of an unsized /web/image address, else None (a sized one, a field's, another site's)."""
    found = IMAGE_URL.match(url)
    if not found or (found.group(2) and SIZE.match(found.group(2))):
        return None
    return int(found.group(1))


def _attr(tag, name):
    found = re.search(rb'\s' + name + rb'="([^"]*)"', tag)
    return found.group(1) if found else None


def _copy_for(info, width):
    """The smallest ready copy at least ``width`` wide and lighter than the original: (url, width), else None."""
    for copy_width, copy_id, copy_size in sorted(info['copies']):
        if copy_width >= width and copy_size < info['size']:
            return b'/web/image/%d' % copy_id, copy_width
    return None


DESKTOP = (b'(min-width: 1280px)', 1920)   # computers: a 1920 px copy at q70, when clearly lighter (0.7.1)
DESKTOP_GAIN = 0.8
PHONE_CAP = b'(max-width: 767.98px) 50vw, '  # (0.7.1: the first picture's phone choice: its ~800 px copy)


def _desktop_copy(info):
    """The 1920 px (or the photo's own width) copy for computers, when at most 80 % of the photo: (url, width)."""
    target = min(DESKTOP[1], info.get('width') or DESKTOP[1])
    for copy_width, copy_id, copy_size in sorted(info['copies']):
        if copy_width >= target and copy_size <= info['size'] * DESKTOP_GAIN:
            return b'/web/image/%d' % copy_id, copy_width
    return None


STYLE_WIDTH = re.compile(rb'(?:^|;)\s*width:\s*(\d+)px', re.I)
COLUMN = re.compile(rb'class="[^"]*\bcol-(lg|md)-(\d{1,2})\b')
CONTAINER = {b'lg': (1140, 960), b'md': (720,)}


def shown_sizes(page, img_start, tag):
    """The sizes of a picture whose srcset says "100vw" (0.4.2: pictures shown 250 px wide fetched their 1920 px
    original): its styled width, else its column's share of the page's container, else the container."""
    style = _attr(tag, b'style') or b''
    found = STYLE_WIDTH.search(style)
    if found:
        px = int(found.group(1))
        return b'(max-width: %dpx) 100vw, %dpx' % (px, px)
    column = None
    for match in reversed(list(COLUMN.finditer(page, max(0, img_start - 3000), img_start))):
        tag_start = page.rfind(b'<', 0, match.start())
        between = page[tag_start:img_start]
        if between.startswith(b'<div') and between.count(b'<div') > between.count(b'</div>'):
            column = match  # (the nearest column the picture is still inside)
            break
    if column:
        share = int(column.group(2)) / 12
        if column.group(1) == b'lg':
            return b'(min-width: 1200px) %dpx, (min-width: 992px) %dpx, 100vw' % (1140 * share, 960 * share)
        return b'(min-width: 768px) %dpx, 100vw' % (720 * share)
    return b'(min-width: 1200px) 1140px, 100vw'


# A video block's player (Odoo builds its <iframe> when the page is read, at once, wherever the video is: a tour's,
# far below its cover, fetched 1.3 MB of YouTube's scripts during Google's phone test, 2026-11-12): here the page
# carries the iframe Odoo would build, the same, but loading="lazy", so the browser fetches the player only when the
# video comes near the screen; Odoo's video block then finds its iframe there and keeps it (autoplay and all). Only an
# empty block with a video address from the sites Odoo plays (website/static/src/js/content/generate_video_iframe.js),
# never with the cookies approval (its player waits for the visitor's choice: Odoo's own way).
VIDEO = re.compile(rb'<div\b(?=[^>]*\bclass="[^"]*\bmedia_iframe_video\b)[^>]*?\bdata-oe-expression="([^"]+)"[^>]*>'
                   rb'(?=</div>)')
VIDEO_DOMAINS = (b'youtu.be', b'youtube.com', b'youtube-nocookie.com', b'instagram.com', b'player.vimeo.com',
                 b'vimeo.com', b'dailymotion.com')
VIDEO_FRAME = (b'<div class="css_editable_mode_display"></div><div class="media_iframe_video_size"></div>'
               b'<iframe frameborder="0" allowfullscreen="allowfullscreen" referrerpolicy="strict-origin-when-cross-origin"'
               b' loading="lazy" src="%s"></iframe>')


def video_domain(src):
    """The site of a video block's address ('youtube-nocookie.com'), as Odoo checks it (no "www."), or None."""
    found = re.match(rb'^(?:https?:)?//([^/?#]+)', html.unescape(src.decode('utf-8', 'replace')).encode())
    return found and re.sub(rb'^www\.', b'', found.group(1))


EAGER_BACKGROUNDS = 2   # the first section backgrounds (the first screen) load at once; the others when near (0.7.0)
LAZY_RULE = b'[data-mtbg-lazy-bg]{background-image:none!important}'
# the later sections' backgrounds: fetched when the section comes within 400 px of the screen; a carousel's slides
# together when the carousel does (a hidden slide never comes into view by itself)
LAZY_SCRIPT = (b'<script data-mtbg-lazy-bg-js="">(function(){function go(){var els=[].slice.call(document.'
               b'querySelectorAll("[data-mtbg-lazy-bg]"));function show(e){e.removeAttribute("data-mtbg-lazy-bg")}'
               b'if(!("IntersectionObserver" in window)){els.forEach(show);return}var groups=new Map();'
               b'els.forEach(function(e){var t=e.closest(".carousel")||e;if(!groups.has(t)){groups.set(t,[])}'
               b'groups.get(t).push(e)});var io=new IntersectionObserver(function(es){es.forEach(function(x){'
               b'if(x.isIntersecting){(groups.get(x.target)||[]).forEach(show);io.unobserve(x.target)}})},'
               b'{rootMargin:"400px 0px"});groups.forEach(function(v,t){io.observe(t)})}'
               b'if(document.readyState==="loading"){document.addEventListener("DOMContentLoaded",go)}else{go()}})();'
               b'</script>')


def speed_up(page, pictures=lambda ids: {}):
    """The page with its pictures sped up. ``pictures(ids)`` -> {id: {'width', 'height', 'size', 'copies':
    [(width, copy id, size)]}} for the public image attachments among ``ids`` (the others are left as they are).
    Only ready copies lighter than the original replace it: a picture without one stays as it is."""
    if DONE in page:
        return page  # (done already: a page served again from Odoo's page cache)
    main = MAIN.search(page)
    head_end = page.find(b'</head>')
    if not main or head_end < 0:
        return page
    start = page.rfind(b'<', 0, main.start())  # (its own tag: a tour page's background is in #wrap's style)
    imgs = list(IMG.finditer(page, start))
    backgrounds = list(BACKGROUND.finditer(page, start))
    ids = {i for i in (attachment_id(m.group(1)) for m in backgrounds) if i}
    for img in imgs:
        src = SRC.search(img.group(0))
        ident = src and attachment_id(src.group(1))
        if ident:
            ids.add(ident)
    known = pictures(ids) if ids else {}

    edits = []      # (start, end, replacement), applied from the end
    rules = []
    head = []
    preloads = []   # (0.7.10: at the top of the head, before the page's inlined first-screen rules, not after them)
    first = min([(m.start(), 'img', m) for m in imgs[:1]] + [(m.start(), 'bg', m) for m in backgrounds[:1]],
                default=None, key=lambda f: f[0])

    def preload(href, media=None, srcset=None, sizes=None, urgent=True):
        def attr(name, value):
            value = value and html.escape(html.unescape(value.decode('utf-8', 'replace')), quote=True).encode()
            return b' %s="%s"' % (name, value) if value else b''
        # (a picture with smaller copies: the copy the screen takes, never the original besides it)
        preloads.append(b'<link rel="preload" as="image"%s%s%s%s%s/>' % (
            b' fetchpriority="high"' if urgent else b'', attr(b'media', media), attr(b'imagesrcset', srcset),
            attr(b'imagesizes', srcset and sizes), attr(b'href', href)))

    # the sections' background photos: a ready phone and tablet copy where there is one
    lazy = 0
    # (0.7.10: a background after the page's first photo is never in the first screen (a tour page: the sections of its
    # description, far below its cover): it waits too, whatever its rank, instead of sharing the line with the cover)
    photo_at = next((m.start() for m in imgs
                     if (found := SRC.search(m.group(0))) and not found.group(1).startswith(b'data:')), None)
    page_bg = False   # (the first background is the page's own: in <main>'s or #wrap's style, a tour's page background)
    if backgrounds:
        own = page[page.rfind(b'<', 0, backgrounds[0].start()):backgrounds[0].start()]
        page_bg = b'>' not in own and (own.startswith(b'<main') or b'id="wrap"' in own)
    # 0.9.1 (owner 2026-11-17): a page background behind the page's photo (a tour's tile) is never urgent: the photo
    # alone is asked for with high priority; the background is preloaded for computers only (phones show a tour's
    # background below its top section, mtbg_tours_website), without priority, when it has no screen copies
    quiet_bg = page_bg and photo_at is not None
    for n, bg in enumerate(backgrounds):
        tag_start = page.rfind(b'<', 0, bg.start())
        in_tag = tag_start >= 0 and b'>' not in page[tag_start:bg.start()]  # (an element's style, not a <style>)
        is_first = bool(first and first[1] == 'bg' and first[2] is bg)
        later = n >= EAGER_BACKGROUNDS or (photo_at is not None and bg.start() > photo_at)
        if in_tag and later and not is_first and not page.startswith(b'<style', tag_start):
            name_tag = re.compile(rb'<[a-zA-Z0-9]+').match(page, tag_start)
            if name_tag:
                edits.append((name_tag.end(), name_tag.end(), b' data-mtbg-lazy-bg=""'))
                lazy += 1
        ident = attachment_id(bg.group(1))
        info = known.get(ident) if ident else None
        screens = [(media, _copy_for(info, width)) for media, width in SCREENS] if info else []
        screens = [(media, copy) for media, copy in screens if copy]
        desk = _desktop_copy(info) if info else None
        if not screens and not desk:
            continue
        tag_start = page.rfind(b'<', 0, bg.start())
        name_end = re.compile(rb'<[a-zA-Z0-9]+').match(page, tag_start)
        if not name_end:
            continue
        key = b'%d' % n
        edits.append((name_end.end(), name_end.end(), b' data-mtbg-bg="' + key + b'"'))
        if desk:
            screens.append((DESKTOP[0], desk))
        for media, (url, _width) in screens:
            # (0.9.1: a page background's copy in --mtbg-page-bg too, where a phone's tour page paints it from)
            extra = b';--mtbg-page-bg:url("%s")!important' % url if page_bg and n == 0 else b''
            rules.append(b'@media %s{[data-mtbg-bg="%s"]{background-image:url("%s")!important%s}}'
                         % (media, key, url, extra))
        if first and first[1] == 'bg' and first[2] is bg and quiet_bg:
            first = None  # (its screen copies come with the page's rules, never ahead of its photo)
        if first and first[1] == 'bg' and first[2] is bg:
            for media, (url, _width) in screens:
                preload(url, media)
            others = [media for media, _w in SCREENS + (DESKTOP,) if media not in dict(screens)]
            if others:
                preload(bg.group(1), b', '.join(others))
            first = None  # (preloaded per screen)

    if first and first[1] == 'bg':  # (a background without ready copies: preloaded as it is)
        if quiet_bg:
            preload(first[2].group(1), QUIET_BG_MEDIA, urgent=False)
        else:
            preload(first[2].group(1))
        first = None
    if page_bg and photo_at is not None:
        # (0.7.10: a page background (a tour's, in #wrap's own style) is behind the whole page, not its largest
        # picture: the page's first photo (the tour's cover, its LCP on a phone) is preloaded too)
        first = next(('', 'img', m) for m in imgs if m.start() == photo_at)

    # the content's photos: no lazy for the first, their size, their ready smaller copies
    for img in imgs:
        tag = img.group(0)
        new = tag
        src = SRC.search(tag)
        if not src or src.group(1).startswith(b'data:'):
            continue
        ident = attachment_id(src.group(1))
        info = known.get(ident) if ident else None
        is_first = first and first[1] == 'img' and first[2] is img
        if is_first:
            new = LAZY.sub(b'', new)
            if b'fetchpriority=' not in new:
                new = new.replace(b'<img', b'<img fetchpriority="high"', 1)
        elif EAGER.search(new) and b'fetchpriority="high"' not in new:
            # (only the first picture before the page's text: the others, a row of cards on a computer, come as
            # soon as the page is laid out and shows them, instead of slowing its stylesheet down on a phone)
            new = EAGER.sub(b' loading="lazy"', new)
        sizes = _attr(new, b'sizes')
        if _attr(new, b'srcset') and (sizes is None or sizes.strip() == b'100vw'):
            better = shown_sizes(page, img.start(), tag)
            new = re.sub(rb'\ssizes="[^"]*"', b'', new, count=1).replace(b'<img', b'<img sizes="' + better + b'"', 1)
        if info and info['width'] and info['height']:
            classes = (_attr(tag, b'class') or b'').split()
            style = _attr(tag, b'style') or b''
            if (b'img-fluid' in classes and _attr(tag, b'width') is None and _attr(tag, b'height') is None
                    and b'height' not in style):
                new = new.replace(b'<img', b'<img width="%d" height="%d"' % (info['width'], info['height']), 1)
            lighter = sorted({(w, c) for w, c, size in info['copies'] if w < info['width'] and size < info['size']})
            if lighter and _attr(tag, b'srcset') is None:
                srcset = b', '.join([b'/web/image/%d %dw' % (c, w) for w, c in lighter]
                                    + [src.group(1) + b' %dw' % info['width']])
                new = new.replace(b'<img', b'<img srcset="' + srcset + b'" sizes="' + shown_sizes(page, img.start(), tag)
                                  + b'"', 1)
        srcset = _attr(new, b'srcset')
        if info and srcset:
            desk = _desktop_copy(info)
            if desk:
                # (computers: the photo's lighter 1920 copy instead of the photo itself in its srcset)
                parts = []
                for part in srcset.split(b','):
                    url, _sep, descriptor = part.strip().partition(b' ')
                    if attachment_id(url) == ident and descriptor.strip().endswith(b'w'):
                        part = desk[0] + b' ' + descriptor.strip()
                    parts.append(part.strip())
                new = new.replace(b'srcset="' + srcset + b'"', b'srcset="' + b', '.join(parts) + b'"', 1)
        if is_first and srcset and re.search(rb'\s[5-9]\d\dw', srcset):
            # (phones: the first picture's ~800 px copy, not the 1280 one a 2.6x screen would take: half the bytes)
            sizes = _attr(new, b'sizes') or b'100vw'
            if PHONE_CAP not in sizes:
                capped = PHONE_CAP + sizes
                if _attr(new, b'sizes') is not None:
                    new = re.sub(rb'(\ssizes=")[^"]*(")', lambda m: m.group(1) + capped + m.group(2), new, count=1)
                else:
                    new = new.replace(b'<img', b'<img sizes="' + capped + b'"', 1)
        if is_first:
            preload(src.group(1), srcset=_attr(new, b'srcset'), sizes=_attr(new, b'sizes') or b'100vw')
        if new != tag:
            edits.append((img.start(), img.end(), new))

    # the videos of the page's text: their player only when they come near the screen (0.7.10)
    if b'data-need-cookies-approval' not in page:
        for video in VIDEO.finditer(page, start):
            if video_domain(video.group(1)) in VIDEO_DOMAINS:
                edits.append((video.end(), video.end(), VIDEO_FRAME % video.group(1)))

    if lazy:
        rules.append(LAZY_RULE)  # (after the phone and tablet copies' rules: it wins over them)
    if rules:
        head.append(b'<style data-mtbg-page-speed="">' + b''.join(rules) + b'</style>')
    if lazy:
        head.append(LAZY_SCRIPT)
    if not edits and not head and not preloads:
        return page
    for edit_start, edit_end, text in sorted(edits, key=lambda e: e[0], reverse=True):
        page = page[:edit_start] + text + page[edit_end:]
    head_end = page.find(b'</head>')
    page = page[:head_end] + b''.join(head) + page[head_end:]
    if preloads:
        # the first photo asked for as soon as the head starts: a tour page's head carries ~200 KB of inlined rules
        # (first_screen), and a preload after them reached a slow phone only once they had (a tour page: 1.6 s)
        head_end = page.find(b'</head>')
        top = (VIEWPORT.search(page, 0, head_end) or CHARSET.search(page, 0, head_end)
               or HEAD_OPEN.search(page))
        at = top.end() if top else page.find(b'</head>')
        page = page[:at] + b''.join(preloads) + page[at:]
    return page


# 0.9.1 (owner 2026-11-17, "serve the header logo fast"): the website's logo at an address ending in its file type
# (/web/image/website/1/logo/logo.svg?unique=...), the same picture: Cloudflare keeps such a file at its edge (an
# address without one, the logo's "/logo/<site name>", went to the server on every visit); its version stays in it.
LOGO_URL = re.compile(rb'(/web/image/website/\d+/logo)(?:/[^"?\s]*)?(\?unique=[0-9a-f]+)"')
LOGO_TYPES = {'image/svg+xml': b'svg', 'image/png': b'png', 'image/webp': b'webp', 'image/jpeg': b'jpg',
              'image/gif': b'gif'}


def logo_cached(page, extension):
    """The page with its website logo's addresses ending in ``extension`` (b'svg'), the version kept."""
    if not extension:
        return page
    return LOGO_URL.sub(lambda m: m.group(1) + b'/logo.' + extension + m.group(2) + b'"', page)


def _logo_extension(env, website):
    """The file type of the website's logo (b'svg', b'png'...), None when it has none or another."""
    if not website:
        return None
    found = env['ir.attachment'].sudo().search_read(
        [('res_model', '=', 'website'), ('res_field', '=', 'logo'), ('res_id', '=', website.id)], ['mimetype'], limit=1)
    return found and LOGO_TYPES.get(found[0]['mimetype'] or '')


def fonts_early(page, imports_of=lambda url: []):
    """The page with the stylesheets its site stylesheet imports (``imports_of(url)``: the theme's fonts) preloaded in
    its head, so they come with it instead of after it."""
    if FONTS_DONE in page:
        return page
    sheet = STYLESHEET.search(page)
    head_end = page.find(b'</head>')
    if not sheet or head_end < 0:
        return page
    links = []
    for url in imports_of(sheet.group(1).decode()):
        href = html.escape(url, quote=True).encode()
        if url.startswith('https://fonts.googleapis.com/') and b'//fonts.gstatic.com' not in page[:head_end]:
            # (its font files come from fonts.gstatic.com: the connection opened at once)
            links.append(b'<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin=""/>')
        links.append(b'<link rel="preload" as="style" href="%s" %s/>' % (href, FONTS_DONE))
    if not links:
        return page
    return page[:head_end] + b''.join(dict.fromkeys(links)) + page[head_end:]


def _stylesheet_imports(env):
    """imports_of(url): the stylesheets the site stylesheet at ``url`` imports, read once per version."""
    def imports_of(url):
        if url not in _imports:
            attachment = env['ir.attachment'].sudo().search([('url', '=', url)], limit=1)
            if not attachment:
                return []  # (not made yet: the page's first visitor asks for it next)
            text = (attachment.raw or b'').decode('utf-8', 'replace')
            if len(_imports) > 50:
                _imports.clear()
            _imports[url] = [u for u in IMPORT.findall(text[:20000]) if u.startswith(('https://', '/'))]
        return _imports[url]
    return imports_of


_compiled = {}  # url -> the stylesheet's text (stored by Odoo, or compiled here while it was not), per worker


def _stylesheet_text(env):
    """css_of(url): the text of the stylesheet at ``url`` (the visitors' site stylesheet, an extension's own). Odoo
    stores a stylesheet when its address is first asked for, after the page: one not stored yet is compiled here, in
    memory (a page's transaction is read-only: nothing is written), so the very first visitor's page, which Cloudflare
    keeps, has its first screen too; None when it cannot be had (the page stays as it is)."""
    def css_of(url):
        if url in _compiled:
            return _compiled[url]
        try:
            with env.cr.savepoint(flush=False):
                attachment = env['ir.attachment'].sudo().search([('url', '=', url)], limit=1)
                if attachment:
                    text = (attachment.raw or b'').decode('utf-8', 'replace')
                else:
                    name = bundle_of(url)
                    if not name:
                        return None
                    bundle = env['ir.qweb'].sudo()._get_asset_bundle(name, css=True, js=False)
                    if bundle.get_link('css') != url:
                        return None  # (another version or language direction: left as it is)
                    text = bundle.preprocess_css()
                    if bundle.css_errors:
                        return None
                if not text:
                    return None
        except Exception:  # noqa: BLE001 - never in the way of the page
            _logger.exception("Page speed: the stylesheet %s could not be read for its first screen", url)
            return None
        if len(_compiled) > 6:
            _compiled.clear()
        _compiled[url] = text
        return text
    return css_of


def _public_pictures(env):
    """{id: {width, height, size, copies}} of the public image attachments, with their ready 'resize: <px>' WebP
    copies (public ones)."""
    def pictures(ids):
        Attachment = env['ir.attachment'].sudo()
        sized = 'mtbg_width' in Attachment._fields
        out = {}
        for att in Attachment.browse(sorted(ids)).exists():
            if att.public and (att.mimetype or '').startswith('image/') and att.mimetype != 'image/svg+xml':
                out[att.id] = {'width': (att.mtbg_width or 0) if sized else 0,
                               'height': (att.mtbg_height or 0) if sized else 0,
                               'size': att.file_size or 0, 'copies': []}
        if out and 'original_id' in Attachment._fields:
            for copy in Attachment.search([('original_id', 'in', list(out)), ('public', '=', True),
                                           ('description', '=like', 'resize: %'), ('mimetype', '=', 'image/webp')]):
                found = RESIZE.match(copy.description or '')
                if found and copy.file_size:
                    out[copy.original_id.id]['copies'].append((int(found.group(1)), copy.id, copy.file_size))
        return out
    return pictures


def _names(env, ids):
    """{id: name} of the public attachments among ``ids`` (the words of a picture without an alt)."""
    if not ids:
        return {}
    found = env['ir.attachment'].sudo().search_read([('id', 'in', list(ids)), ('public', '=', True)], ['name'])
    return {row['id']: row['name'] for row in found}


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _post_dispatch(cls, response):
        super()._post_dispatch(response)
        if (request and request.httprequest.method == 'GET' and getattr(response, 'status_code', 0) == 200
                and getattr(response, 'mimetype', '') == 'text/html' and getattr(request, 'is_frontend', False)
                and request.env.user._is_public() and not request.session.debug):
            if hasattr(response, 'flatten'):
                response.flatten()
            page = response.get_data()
            faster = speed_up(page, _public_pictures(request.env))
            if b'/web/image/website/' in faster:
                faster = logo_cached(faster, _logo_extension(request.env, request.website))
            if request.env['mtbg.page.speed.lean']._mtbg_first_screen_on():
                faster = first_screen(faster, _stylesheet_text(request.env))
            if FIRST_DONE not in faster:  # (with the first screen first, the fonts are linked in the head already)
                faster = fonts_early(faster, _stylesheet_imports(request.env))
            faster = accessible(faster, _names(request.env, image_ids(faster)), request.website.name or '',
                                (request.httprequest.host, urlsplit(request.website.domain or '').netloc
                                 or request.website.domain or ''))
            if faster is not page:
                response.set_data(faster)
