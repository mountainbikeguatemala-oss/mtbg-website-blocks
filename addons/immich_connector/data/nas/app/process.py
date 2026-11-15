"""Tour photos: turn one day's originals into the files clients get.

For one album day it writes, into an output folder:
  web/0001.jpg ...  2048 px long edge, watermarked, q82, EXIF rotation applied, metadata stripped
  header.jpg        1200 px wide cover thumbnail for the email and the page section, watermarked
  day.zip           full-size watermarked copies (q90) for "Download day N"
  manifest.json     {"count", "photos": [{"file","w","h"}], "header": {...}, "zip": {...}}

Usage: python process.py <originals_dir> <out_dir> <watermark.png> [--cover NAME]
Originals: JPEG, PNG, HEIC/HEIF (iPhone), WebP. Video and other files are skipped.
"""
import argparse
import json
import os
import sys
import zipfile
from datetime import datetime
from zoneinfo import ZoneInfo

from PIL import Image, ImageOps

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:  # HEIC then unsupported; JPEG still works
    pass

_env = os.environ.get
WEB_EDGE = int(_env("WEB_LONG_EDGE") or 2048)          # web copies: long edge in px
HEADER_WIDTH = int(_env("HEADER_WIDTH") or 1200)        # day header (email + page section)
WEB_QUALITY = int(_env("WEB_QUALITY") or 82)
FULL_QUALITY = int(_env("ZIP_QUALITY") or 90)           # full-size copies in the download zip
WM_WIDTH = float(_env("WATERMARK_WIDTH") or 0.15)       # watermark width as a share of the photo width
WM_MARGIN = float(_env("WATERMARK_MARGIN") or 0.03)     # margin from the corner, share of the photo width
WM_OPACITY = float(_env("WATERMARK_OPACITY") or 0.85)
WM_CORNER = (_env("WATERMARK_CORNER") or "bottom-right").lower()  # bottom-right|bottom-left|top-right|top-left
TZ = ZoneInfo(_env("TIMEZONE") or _env("TZ") or "UTC")
EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"}


def load(path):
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)  # phones store rotation in EXIF
    return img.convert("RGB")


def watermark(img, wm):
    w = max(1, int(img.width * WM_WIDTH))
    h = max(1, int(wm.height * w / wm.width))
    mark = wm.resize((w, h), Image.LANCZOS)
    if WM_OPACITY < 1:
        alpha = mark.getchannel("A").point(lambda a: int(a * WM_OPACITY))
        mark.putalpha(alpha)
    m = int(img.width * WM_MARGIN)
    x = m if "left" in WM_CORNER else img.width - w - m
    y = m if "top" in WM_CORNER else img.height - h - m
    out = img.copy()
    out.paste(mark, (x, y), mark)
    return out


def fit(img, edge):
    if max(img.size) <= edge:
        return img
    scale = edge / max(img.size)
    return img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)


def exif_taken(path):
    """EXIF DateTimeOriginal as 'YYYY:MM:DD HH:MM:SS' (camera local time), or None."""
    try:
        exif = Image.open(path).getexif()
        return exif.get_ifd(0x8769).get(36867) or exif.get(306)
    except Exception:
        return None


def taken_iso(path):
    """Capture time as ISO 8601 with the tour time zone's offset (phones store local time without one)."""
    dt = exif_taken(path)
    if dt and len(dt) >= 19:
        try:
            return datetime.strptime(dt[:19], "%Y:%m:%d %H:%M:%S").replace(tzinfo=TZ).isoformat()
        except ValueError:
            return None
    return None


def capture_key(path):
    """Sort by capture time, then name; phones name files in order anyway."""
    dt = exif_taken(path)
    return (0, dt, os.path.basename(path)) if dt else (1, "", os.path.basename(path))


def process_day(src, out, wm_path, cover=None):
    wm = Image.open(wm_path).convert("RGBA")
    files = sorted(
        (os.path.join(src, f) for f in os.listdir(src) if os.path.splitext(f)[1].lower() in EXTS),
        key=capture_key,
    )
    if not files:
        raise SystemExit("no photos in %s" % src)
    os.makedirs(os.path.join(out, "web"), exist_ok=True)
    photos, skipped = [], []
    zpath = os.path.join(out, "day.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED) as z:  # JPEGs don't compress further
        for i, path in enumerate(files, 1):
            try:
                img = load(path)
            except Exception as e:
                skipped.append({"file": os.path.basename(path), "error": str(e)[:200]})
                continue
            name = "%04d.jpg" % i
            web = watermark(fit(img, WEB_EDGE), wm)
            web.save(os.path.join(out, "web", name), "JPEG", quality=WEB_QUALITY, optimize=True, progressive=True)
            photos.append({"file": "web/" + name, "width": web.width, "height": web.height,
                           "taken": taken_iso(path), "src": os.path.basename(path)})
            tmp = os.path.join(out, ".full.jpg")
            watermark(img, wm).save(tmp, "JPEG", quality=FULL_QUALITY, optimize=True)
            z.write(tmp, name)
            os.remove(tmp)
    if not photos:
        raise SystemExit("no readable photos in %s" % src)
    cover_src = next((p for p in photos if cover and p["src"] == cover), photos[0])
    head = load(os.path.join(src, cover_src["src"]))
    head = head.resize((HEADER_WIDTH, round(head.height * HEADER_WIDTH / head.width)), Image.LANCZOS)
    head = watermark(head, wm)
    head.save(os.path.join(out, "header.jpg"), "JPEG", quality=WEB_QUALITY, optimize=True, progressive=True)
    manifest = {
        "count": len(photos),
        "photos": [{k: p[k] for k in ("file", "width", "height", "taken", "src")} for p in photos],
        "header": {"file": "header.jpg", "width": head.width, "height": head.height, "src": cover_src["src"]},
        "zip": {"file": "day.zip", "bytes": os.path.getsize(zpath)},
        "skipped": skipped,
    }
    with open(os.path.join(out, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    return manifest


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("watermark")
    ap.add_argument("--cover")
    a = ap.parse_args()
    m = process_day(a.src, a.out, a.watermark, a.cover)
    print(json.dumps({"count": m["count"], "zip_mb": round(m["zip"]["bytes"] / 1e6, 1), "skipped": len(m["skipped"])}))
    sys.exit(0)
