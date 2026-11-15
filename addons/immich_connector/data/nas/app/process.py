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
import subprocess
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
FULL_QUALITY = int(_env("ZIP_QUALITY") or 90)           # copies in the download zip
ZIP_EDGE = int(_env("ZIP_LONG_EDGE") or 0)              # zip copies: long edge in px, 0 = full size
# Watermark placement (API section 12b, same maths as the website preview). The website's settings override
# these; these are the fallback when no watermark is uploaded there.
WM_ANCHOR = (_env("WATERMARK_ANCHOR") or _env("WATERMARK_CORNER") or "bottom-right").lower()
WM_SIZE_PCT = float(_env("WATERMARK_SIZE_PCT") or 22)       # watermark width = % of the photo's SHORT edge
WM_OFF_X_PCT = float(_env("WATERMARK_OFFSET_X_PCT") or 3)   # inward from the anchored side, % of photo width
WM_OFF_Y_PCT = float(_env("WATERMARK_OFFSET_Y_PCT") or 3)   # inward from the anchored side, % of photo height
WM_OPACITY = float(_env("WATERMARK_OPACITY") or 0.85)       # multiplier on the PNG's own alpha
TZ = ZoneInfo(_env("TIMEZONE") or _env("TZ") or "UTC")
EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"}


def load(path):
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)  # phones store rotation in EXIF
    return img.convert("RGB")


def set_watermark(anchor=None, offset_x_pct=None, offset_y_pct=None, size_pct=None, opacity=None):
    """Placement from the website's Tour photos settings (API section 12b)."""
    global WM_ANCHOR, WM_OFF_X_PCT, WM_OFF_Y_PCT, WM_SIZE_PCT, WM_OPACITY
    if anchor:
        WM_ANCHOR = str(anchor).lower()
    if offset_x_pct is not None:
        WM_OFF_X_PCT = float(offset_x_pct)
    if offset_y_pct is not None:
        WM_OFF_Y_PCT = float(offset_y_pct)
    if size_pct:
        WM_SIZE_PCT = float(size_pct)
    if opacity is not None:
        WM_OPACITY = float(opacity)


def wm_box(W, H, mw, mh):
    """Watermark (width, height, x, y) on a W x H picture for a mw x mh mark: width = size_pct % of the short
    edge (aspect kept); start at the anchor and move inward from the anchored edges by offset_x_pct % of W and
    offset_y_pct % of H; a centred axis is centred and ignores its offset."""
    w = max(1, int(round(WM_SIZE_PCT / 100.0 * min(W, H))))
    h = max(1, int(round(w * mh / float(mw))))
    a = WM_ANCHOR
    if "left" in a:
        x = WM_OFF_X_PCT / 100.0 * W
    elif "right" in a:
        x = W - w - WM_OFF_X_PCT / 100.0 * W
    else:
        x = (W - w) / 2.0
    if a.startswith("top"):
        y = WM_OFF_Y_PCT / 100.0 * H
    elif a.startswith("bottom"):
        y = H - h - WM_OFF_Y_PCT / 100.0 * H
    else:
        y = (H - h) / 2.0
    return w, h, int(round(x)), int(round(y))


def watermark(img, wm):
    if wm is None:  # no watermark set anywhere: publish clean copies
        return img
    w, h, x, y = wm_box(img.width, img.height, wm.width, wm.height)
    mark = wm.resize((w, h), Image.LANCZOS)
    if WM_OPACITY < 1:
        alpha = mark.getchannel("A").point(lambda v: int(v * WM_OPACITY))
        mark.putalpha(alpha)
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


# ---- Videos (owner 2026-11-14): web MP4 + poster + looping animated WebP preview; not in the day zip ----------
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".3gp", ".mkv", ".webm", ".avi"}
VIDEO_EDGE = int(_env("WEB_VIDEO_LONG_EDGE") or 1280)
VIDEO_BITRATE = _env("VIDEO_BITRATE") or "2M"            # owner: heavy compression, 720p; this is the cap
VIDEO_CRF = _env("VIDEO_CRF") or "28"                     # quality target (higher = smaller); capped by bitrate
PREVIEW_SECONDS = float(_env("PREVIEW_SECONDS") or 3)
PREVIEW_WIDTH = int(_env("PREVIEW_WIDTH") or 480)
AUDIO_KBPS = int(_env("VIDEO_AUDIO_KBPS") or 96)


def set_quality(q):
    """Quality from the website's Tour photos settings (GET /quality); config values stay the fallback."""
    global WEB_EDGE, WEB_QUALITY, ZIP_EDGE, FULL_QUALITY, VIDEO_EDGE, VIDEO_CRF, VIDEO_BITRATE, AUDIO_KBPS, \
        PREVIEW_SECONDS, PREVIEW_WIDTH
    ph, zp, vd, pv = (q.get(k) or {} for k in ("photo", "zip", "video", "preview"))
    WEB_EDGE = int(ph.get("long_edge") or WEB_EDGE)
    WEB_QUALITY = int(ph.get("jpeg_quality") or WEB_QUALITY)
    if zp.get("long_edge") is not None:
        ZIP_EDGE = int(zp["long_edge"])
    FULL_QUALITY = int(zp.get("jpeg_quality") or FULL_QUALITY)
    VIDEO_EDGE = int(vd.get("long_edge") or VIDEO_EDGE)
    VIDEO_CRF = str(vd.get("crf") or VIDEO_CRF)
    if vd.get("max_bitrate_kbps"):
        VIDEO_BITRATE = "%dk" % int(vd["max_bitrate_kbps"])
    AUDIO_KBPS = int(vd.get("audio_kbps") or AUDIO_KBPS)
    PREVIEW_SECONDS = float(pv.get("seconds") or PREVIEW_SECONDS)
    PREVIEW_WIDTH = int(pv.get("width") or PREVIEW_WIDTH)
PREVIEW_MAX_BYTES = int(float(_env("PREVIEW_MAX_MB") or 1.5) * 1024 * 1024)
FFMPEG, FFPROBE = _env("FFMPEG") or "ffmpeg", _env("FFPROBE") or "ffprobe"
VAAPI = _env("VAAPI_DEVICE") or "/dev/dri/renderD128"   # Intel graphics: decode + shrink big camera video


def _run(cmd):
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3600)
    if r.returncode:
        raise RuntimeError("%s failed: %s" % (os.path.basename(cmd[0]), r.stderr.decode(errors="ignore")[-400:]))
    return r.stdout


def probe(path):
    """Display width/height (rotation applied), duration and creation time of a video."""
    d = json.loads(_run([FFPROBE, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", path]))
    v = next(s for s in d["streams"] if s.get("codec_type") == "video")
    w, h = int(v["width"]), int(v["height"])
    rot = 0
    try:
        rot = int(float(v.get("tags", {}).get("rotate", 0)))
    except ValueError:
        pass
    for sd in v.get("side_data_list", []):
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
    if abs(rot) % 180 == 90:
        w, h = h, w
    tags = dict(d.get("format", {}).get("tags", {}), **v.get("tags", {}))
    dur = float(d.get("format", {}).get("duration") or v.get("duration") or 0)
    return {"width": w, "height": h, "duration": dur, "created": tags.get("creation_time"), "rotation": rot,
            "audio": any(s.get("codec_type") == "audio" for s in d["streams"])}


def even(n):
    return max(2, int(round(n / 2.0)) * 2)


def video_taken(info):
    """creation_time is UTC in phone videos -> local ISO 8601 in the tour time zone."""
    ct = info.get("created")
    if not ct:
        return None
    try:
        return datetime.fromisoformat(ct.replace("Z", "+00:00")).astimezone(TZ).isoformat(timespec="seconds")
    except ValueError:
        return None


def process_video(path, out, name, wm_path):
    """web/<name>.mp4 (H.264/AAC, long edge VIDEO_EDGE, faststart, watermark), web/<name>-poster.jpg (~1 s),
    web/<name>-preview.webp (looping, muted, PREVIEW_SECONDS, PREVIEW_WIDTH wide, <= PREVIEW_MAX_BYTES)."""
    info = probe(path)
    scale = min(1.0, VIDEO_EDGE / float(max(info["width"], info["height"])))
    w, h = even(info["width"] * scale), even(info["height"] * scale)
    if wm_path:
        with Image.open(wm_path) as m:
            mw, mh = m.size
        wm_w, wm_h, x, y = wm_box(w, h, mw, mh)
    mp4 = os.path.join(out, "web", name + ".mp4")
    if not wm_path:
        fc = "[0:v]scale=%d:%d,setsar=1,format=yuv420p[out]" % (w, h)
    else:
        fc = ("[0:v]scale=%d:%d,setsar=1[v];[1:v]scale=%d:%d,format=rgba,colorchannelmixer=aa=%.3f[wm];"
              "[v][wm]overlay=%d:%d,format=yuv420p[out]" % (w, h, wm_w, wm_h, WM_OPACITY, x, y))
    tail = []
    if info["audio"]:
        tail += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "%dk" % AUDIO_KBPS, "-ac", "2"]
    cap = VIDEO_BITRATE
    buf = "%dk" % (2 * int(float(cap[:-1]) * (1000 if cap[-1].upper() == "M" else 1))) if cap[-1].isalpha() else cap
    tail += ["-c:v", "libx264", "-preset", "medium", "-profile:v", "high", "-crf", VIDEO_CRF,
             "-maxrate", cap, "-bufsize", buf, "-r", "30", "-movflags", "+faststart", "-map_metadata", "-1", mp4]
    wm_in = ["-i", wm_path] if wm_path else []
    soft = [FFMPEG, "-y", "-v", "error", "-i", path] + wm_in + ["-filter_complex", fc, "-map", "[out]"] + tail
    # Fast path: the Intel graphics chip decodes and shrinks (5K H.265 off action cams is the slow part on the
    # CPU); only the small result is watermarked and encoded on the CPU. Rotated phone video takes the CPU path.
    if os.path.exists(VAAPI) and not info.get("rotation"):
        hw_scale = "[0:v]scale_vaapi=w=%d:h=%d:format=nv12,hwdownload,format=nv12,setsar=1" % (w, h)
        hfc = fc.replace("[0:v]scale=%d:%d,setsar=1" % (w, h), hw_scale, 1)
        hw = [FFMPEG, "-y", "-v", "error", "-hwaccel", "vaapi", "-hwaccel_device", VAAPI,
              "-hwaccel_output_format", "vaapi", "-i", path] + wm_in + ["-filter_complex", hfc, "-map", "[out]"] + tail
        try:
            _run(hw)
        except Exception:
            _run(soft)
    else:
        _run(soft)
    t = min(1.0, max(0.0, info["duration"] / 3))  # ~1 s in, or earlier for very short clips
    poster = os.path.join(out, "web", name + "-poster.jpg")
    _run([FFMPEG, "-y", "-v", "error", "-ss", "%.2f" % t, "-i", mp4, "-frames:v", "1", "-q:v", "3", poster])
    preview = os.path.join(out, "web", name + "-preview.webp")
    start = "%.2f" % (min(1.0, max(0.0, info["duration"] - PREVIEW_SECONDS)) if info["duration"] else 0)
    for fps, q in ((12, 60), (10, 45), (8, 35), (6, 25)):  # shrink until it fits the size budget
        _run([FFMPEG, "-y", "-v", "error", "-ss", start, "-t", "%.2f" % PREVIEW_SECONDS, "-i", mp4, "-an",
              "-vf", "fps=%d,scale=%d:-2:flags=lanczos" % (fps, PREVIEW_WIDTH), "-c:v", "libwebp",
              "-loop", "0", "-lossless", "0", "-q:v", str(q), "-compression_level", "6", preview])
        if os.path.getsize(preview) <= PREVIEW_MAX_BYTES:
            break
    return {"type": "video", "file": "web/%s.mp4" % name, "width": w, "height": h,
            "poster": "web/%s-poster.jpg" % name, "preview": "web/%s-preview.webp" % name,
            "duration": round(info["duration"], 1), "bytes": os.path.getsize(mp4), "taken": video_taken(info),
            "src": os.path.basename(path)}


def item_time(path):
    """Capture time for ordering photos and videos together."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in VIDEO_EXTS:
            return video_taken(probe(path)) or ""
        return taken_iso(path) or ""
    except Exception:
        return ""


def is_video(path):
    return os.path.splitext(path)[1].lower() in VIDEO_EXTS


def settings_sig(wm_path):
    """Changes whenever the output would change: watermark file/placement or quality settings."""
    import hashlib
    try:
        st = os.stat(wm_path) if wm_path else None
        wm_id = (wm_path, st.st_size, int(st.st_mtime)) if st else None
    except OSError:
        wm_id = None
    parts = (wm_id, WM_ANCHOR, WM_SIZE_PCT, WM_OFF_X_PCT, WM_OFF_Y_PCT, WM_OPACITY, WEB_EDGE, WEB_QUALITY, ZIP_EDGE,
             FULL_QUALITY, VIDEO_EDGE, VIDEO_CRF, VIDEO_BITRATE, AUDIO_KBPS, PREVIEW_SECONDS, PREVIEW_WIDTH)
    return hashlib.sha1(repr(parts).encode()).hexdigest()[:16]


def process_item(path, out, name, wm_path):
    """One photo or video -> files under out/ (web/<name>.jpg + full/<name>.jpg for the zip; or the video set).
    Used for staging each item as soon as it lands in an album (owner 2026-11-15)."""
    wm_path = wm_path if wm_path and os.path.exists(wm_path) else None
    os.makedirs(os.path.join(out, "web"), exist_ok=True)
    if is_video(path):
        item = process_video(path, out, name, wm_path)
        make_thumb(os.path.join(out, item["poster"]), os.path.join(out, "web", name + "-thumb.jpg"))
        item["thumb"] = "web/%s-thumb.jpg" % name
        return item
    wm = Image.open(wm_path).convert("RGBA") if wm_path else None
    img = load(path)
    web = watermark(fit(img, WEB_EDGE), wm)
    web.save(os.path.join(out, "web", name + ".jpg"), "JPEG", quality=WEB_QUALITY, optimize=True, progressive=True)
    os.makedirs(os.path.join(out, "full"), exist_ok=True)
    big = fit(img, ZIP_EDGE) if ZIP_EDGE else img
    watermark(big, wm).save(os.path.join(out, "full", name + ".jpg"), "JPEG", quality=FULL_QUALITY, optimize=True)
    make_thumb(os.path.join(out, "web", name + ".jpg"), os.path.join(out, "web", name + "-thumb.jpg"))
    return {"type": "photo", "file": "web/%s.jpg" % name, "full": "full/%s.jpg" % name, "thumb": "web/%s-thumb.jpg" % name,
            "width": web.width, "height": web.height, "taken": taken_iso(path), "src": os.path.basename(path)}


def make_thumb(src_jpg, dest, size=400):
    """~400 px staff thumbnail (already watermarked: made from the web copy / video poster)."""
    im = Image.open(src_jpg).convert("RGB")
    im.thumbnail((size, size), Image.LANCZOS)
    im.save(dest, "JPEG", quality=78, optimize=True, progressive=True)


def make_header(src_jpg, dest):
    """Day header (email + page section) from an already watermarked web copy or video poster."""
    head = Image.open(src_jpg).convert("RGB")
    if head.width > HEADER_WIDTH:
        head = head.resize((HEADER_WIDTH, round(head.height * HEADER_WIDTH / head.width)), Image.LANCZOS)
    head.save(dest, "JPEG", quality=WEB_QUALITY, optimize=True, progressive=True)
    return {"width": head.width, "height": head.height}


def process_day(src, out, wm_path, cover=None):
    wm = Image.open(wm_path).convert("RGBA") if wm_path and os.path.exists(wm_path) else None
    wm_path = wm_path if wm is not None else None
    files = [os.path.join(src, f) for f in os.listdir(src) if os.path.splitext(f)[1].lower() in EXTS | VIDEO_EXTS]
    files.sort(key=lambda p: (item_time(p) or "9999", os.path.basename(p)))
    if not files:
        raise SystemExit("no photos or videos in %s" % src)
    os.makedirs(os.path.join(out, "web"), exist_ok=True)
    items, skipped = [], []
    zpath = os.path.join(out, "day.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED) as z:  # JPEGs don't compress further; no videos
        for i, path in enumerate(files, 1):
            name = "%04d" % i
            if os.path.splitext(path)[1].lower() in VIDEO_EXTS:
                try:
                    items.append(process_video(path, out, name, wm_path))
                except Exception as e:
                    skipped.append({"file": os.path.basename(path), "error": str(e)[:200]})
                continue
            try:
                img = load(path)
            except Exception as e:
                skipped.append({"file": os.path.basename(path), "error": str(e)[:200]})
                continue
            web = watermark(fit(img, WEB_EDGE), wm)
            web.save(os.path.join(out, "web", name + ".jpg"), "JPEG", quality=WEB_QUALITY, optimize=True,
                     progressive=True)
            items.append({"type": "photo", "file": "web/%s.jpg" % name, "width": web.width, "height": web.height,
                          "taken": taken_iso(path), "src": os.path.basename(path)})
            tmp = os.path.join(out, ".full.jpg")
            big = fit(img, ZIP_EDGE) if ZIP_EDGE else img
            watermark(big, wm).save(tmp, "JPEG", quality=FULL_QUALITY, optimize=True)
            z.write(tmp, name + ".jpg")
            os.remove(tmp)
    if not items:
        raise SystemExit("no readable photos or videos in %s" % src)
    # Header: the album cover if it is a photo, else the first photo; only videos -> the first video's poster.
    photos = [p for p in items if p["type"] == "photo"]
    cover_src = next((p for p in photos if cover and p["src"] == cover), photos[0] if photos else None)
    if cover_src:
        head = load(os.path.join(src, cover_src["src"]))
    else:
        cover_src = items[0]
        head = Image.open(os.path.join(out, cover_src["poster"])).convert("RGB")
    head = head.resize((HEADER_WIDTH, round(head.height * HEADER_WIDTH / head.width)), Image.LANCZOS)
    head = watermark(head, wm)
    head.save(os.path.join(out, "header.jpg"), "JPEG", quality=WEB_QUALITY, optimize=True, progressive=True)
    manifest = {
        "count": len(items),
        "photos": items,
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
