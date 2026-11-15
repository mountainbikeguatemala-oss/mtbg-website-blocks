"""Tour photos sync job (NAS). Runs in a loop every SYNC_INTERVAL seconds.

1. Reads departures from the website API (GET /departures).
2. Makes one Immich album per departure day, owned by the "Tours" Immich account (this job's API key):
   "2026-11-14 · Tour name · Day 2" (one-day tours: no "· Day N"). Description holds the marker
   "[departure:<id> day:<n>]" so a renamed album is still found.
3. Photos come in through the office upload page (upload.py) and the cellular inbox (collect_inbox): guides
   multi-select what they send; each goes straight into its day album. The admin makes the final selection in
   Immich and sets the header with "Set as album cover". (Optional, off by default: SORT_PARTNER_PHOTOS=1 sorts
   partner-shared phone backups into albums by capture time.)
4. When a day is "ready" (guide/staff pressed "Photos ready" in the Staff App or on the record page; or "#ready"
   typed in the Immich album description), it calls POST uploading (ends the undo window), re-checks, resizes +
   watermarks (process.py), uploads to R2 under the departure's prefix, verifies every object, then calls
   POST /days/<n>/synced. The album description then shows "✓ synced <time> · <count> photos · <short link>".

Config: environment, normally from config.env (see config.env.example). State: /data/state.json.
"""
import json
import logging
import os
import re
import shutil
import time
import traceback
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

import zipfile

import process
from process import process_day
from r2 import R2Client

log = logging.getLogger("tour-photos")


def E(*names, default=None):
    """First non-empty setting among ``names`` (the generic name first, older names after)."""
    for n in names:
        v = (os.environ.get(n) or "").strip().strip('"').strip("'").strip()  # pasted values: spaces, CR, quotes
        if v:
            return v
    return default


TZ = ZoneInfo(E("TIMEZONE", "TZ", default="UTC"))  # where the tours happen; capture times are local
# Album marker namespace: "departure" for production. A dev/test run sets ALBUM_NS=dev-departure and ALBUM_PREFIX
# so test albums can never be taken for real departures (dev ids overlap real ids).
NS = E("ALBUM_NS", default="departure")
PREFIX = E("ALBUM_PREFIX", default="")
MARK_RE = re.compile(r"\[%s:(\d+) day:(\d+)\]" % re.escape(NS))
MARK_FMT = "[" + NS + ":%d day:%d]"
READY_RE = re.compile(r"#ready\b", re.I)
SYNCED_RE = re.compile(r"\n?✓ synced.*$", re.S)

IMMICH_BASE = E("IMMICH_URL", default="http://immich_server:2283").rstrip("/")
IMMICH = IMMICH_BASE + "/api"
IMMICH_PUBLIC = E("IMMICH_PUBLIC_URL", default=IMMICH_BASE).rstrip("/")  # what staff open (album links)
SITE = (E("WEBSITE_API_BASE") or (E("SITE_URL", default="").rstrip("/") + "/mtbg/photos/api/v1")).rstrip("/")
WORK = E("WORK_DIR", default="/work")
STATE = E("STATE_FILE", default="/data/state.json")
WATERMARK = E("WATERMARK_PATH", "WATERMARK", default="/data/watermark.png")
INTERVAL = int(float(E("POLL_MINUTES", default="0")) * 60) or int(E("SYNC_INTERVAL", default="300"))
DRY = E("DRY_RUN", default="0") == "1"


class Immich:
    def __init__(self, key):
        self.s = requests.Session()
        self.s.headers.update({"x-api-key": key, "Accept": "application/json"})

    def req(self, method, path, **kw):
        r = self.s.request(method, IMMICH + path, timeout=120, **kw)
        if r.status_code >= 400:
            raise RuntimeError("Immich %s %s -> %s %s" % (method, path, r.status_code, r.text[:300]))
        return r.json() if r.content and "json" in r.headers.get("content-type", "") else r

    def me(self):
        return self.req("GET", "/users/me")

    def users(self):
        """All users (needs an admin key); falls back to partners."""
        try:
            return self.req("GET", "/admin/users")
        except RuntimeError:
            return [p for p in self.req("GET", "/partners", params={"direction": "shared-with"})]

    def albums(self):
        return self.req("GET", "/albums")

    def album(self, aid):
        return self.req("GET", "/albums/%s" % aid)

    def create_album(self, name, desc):
        return self.req("POST", "/albums", json={"albumName": name, "description": desc})

    def update_album(self, aid, **fields):
        return self.req("PATCH", "/albums/%s" % aid, json=fields)

    def add_assets(self, aid, ids):
        for i in range(0, len(ids), 500):
            self.req("PUT", "/albums/%s/assets" % aid, json={"ids": ids[i:i + 500]})

    def search_day(self, day_start, day_end):
        """Photos (not video) taken in [day_start, day_end) visible to the Tours account (own + partners)."""
        out, page = [], 1
        while page:
            r = self.req("POST", "/search/metadata", json={
                "takenAfter": day_start.isoformat(), "takenBefore": day_end.isoformat(),
                "type": "IMAGE", "withExif": False, "size": 1000, "page": page})
            assets = r.get("assets", {})
            out += assets.get("items", [])
            page = assets.get("nextPage")
            page = int(page) if page else None
        return out

    def download(self, asset_id, path):
        with self.s.get(IMMICH + "/assets/%s/original" % asset_id, stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)


class Site:
    def __init__(self, token):
        self.s = requests.Session()
        self.s.headers.update({"Authorization": "Bearer " + token, "Content-Type": "application/json"})

    def req(self, method, path, **kw):
        r = self.s.request(method, SITE + path, timeout=60, **kw)
        data = r.json() if r.content else {}
        if r.status_code >= 400 or not data.get("ok", False):
            raise RuntimeError("website %s %s -> %s %s" % (method, path, r.status_code, str(data)[:300]))
        return data

    def departures(self, date_from=None, date_to=None):
        params = {k: v for k, v in (("from", date_from), ("to", date_to)) if v}
        return self.req("GET", "/departures", params=params)["departures"]

    def album(self, dep_id, day, album_id):
        """Tell the website the day's Immich album (shown on the departure record). Idempotent."""
        return self.req("POST", "/departures/%d/days/%d/album" % (dep_id, day), json={
            "immich_album_id": album_id, "url": "%s/albums/%s" % (IMMICH_PUBLIC, album_id)})

    def uploading(self, dep_id, day):
        return self.req("POST", "/departures/%d/uploading" % dep_id, json={"day": day})

    def synced(self, dep_id, day, manifest):
        return self.req("POST", "/departures/%d/days/%d/synced" % (dep_id, day), json=manifest)


def load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"albums": {}, "synced": {}}


def save_state(st):
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, indent=1)
    os.replace(tmp, STATE)


def album_name(dep, day):
    name = "%s%s · %s" % (PREFIX, day["date"], dep["tour"])
    return name if len(dep["days"]) == 1 else "%s · Day %d" % (name, day["day"])


_album_cache = {}


def day_album(im, site, dep_id, day_no, fallback_name=None):
    """A departure day's album: found by its marker, or made now (the sync round may not have run yet)."""
    key = (int(dep_id), int(day_no))
    if key in _album_cache:
        return _album_cache[key]
    for a in im.albums():
        m = MARK_RE.search(a.get("description") or "")
        if m and (int(m.group(1)), int(m.group(2))) == key:
            _album_cache[key] = a["id"]
            return a["id"]
    dep = next((d for d in site.departures() if d["id"] == key[0]), None)
    if dep:
        name = album_name(dep, next(x for x in dep["days"] if x["day"] == key[1]))
    else:
        name = PREFIX + (fallback_name or "Departure %d · Day %d" % key)
    aid = im.create_album(name, MARK_FMT % key)["id"]
    _album_cache[key] = aid
    log.info("created album %s", name)
    try:
        site.album(key[0], key[1], aid)
    except Exception as e:  # the next sync round reports it again
        log.warning("album link not reported for %s: %s", key, e)
    return aid


def exif_time(path):
    try:
        from PIL import Image
        exif = Image.open(path).getexif()
        dt = exif.get_ifd(0x8769).get(36867) or exif.get(306)
        if dt and len(dt) >= 19:
            return datetime.strptime(dt[:19], "%Y:%m:%d %H:%M:%S").replace(tzinfo=TZ)
    except Exception:
        pass
    return None


def import_photo(im, path, filename, album_id, guide=None, taken=None, modified=None):
    """Upload one file to Immich (Tours account), note the guide, add it to the album. Returns created|duplicate.
    Photos are owned by the Tours account: Immich cannot upload into another user's account without that
    user's own key, so the guide goes in the description ("Uploaded by <name> (<email>)")."""
    modified = modified or datetime.now(timezone.utc)
    created = exif_time(path) or taken or modified
    with open(path, "rb") as f:
        r = im.s.post(IMMICH + "/assets", timeout=600, files={"assetData": (filename, f)}, data={
            "fileCreatedAt": created.isoformat(), "fileModifiedAt": modified.isoformat(), "filename": filename})
    if r.status_code >= 400:
        raise RuntimeError("Immich upload %s %s" % (r.status_code, r.text[:200]))
    res = r.json()  # {"id", "status": "created" | "duplicate"}
    guide = guide or {}
    if res.get("status") == "created" and (guide.get("name") or guide.get("email")):
        im.req("PUT", "/assets/%s" % res["id"], json={"description": "Uploaded by %s%s%s" % (
            guide.get("name") or "guide", " (%s)" % guide["email"] if guide.get("email") else "",
            " [staff:%s]" % guide["id"] if guide.get("id") else "")})
    im.add_assets(album_id, [res["id"]])
    return res.get("status", "created")


def collect_inbox(im, site, r2, st):
    """Photos guides sent over cellular from the Staff App sit in R2 under inbox/. Bring them into Immich, then
    tell the website (it deletes the inbox objects). Runs at most every INBOX_INTERVAL seconds."""
    if r2 is None or time.time() - st.get("inbox_at", 0) < int(float(E("INBOX_MINUTES", default="15")) * 60):
        return
    st["inbox_at"] = time.time()
    items = site.req("GET", "/inbox").get("items", [])
    if not items:
        return
    os.makedirs(os.path.join(WORK, "inbox"), exist_ok=True)
    done, total = [], 0
    for it in items:
        path = os.path.join(WORK, "inbox", os.path.basename(it["key"]) or "photo.jpg")
        try:
            r2.get_file(it["key"], path)
            taken = datetime.fromisoformat(it["taken"]) if it.get("taken") else None
            aid = day_album(im, site, it["departure_id"], it["day"])
            import_photo(im, path, os.path.basename(it["key"]), aid, it.get("guide"), taken)
            done.append(it["key"])
            total += 1
        except Exception as e:
            log.error("inbox %s failed: %s", it.get("key"), e)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        if len(done) >= 50:  # report in batches so a crash doesn't re-import much
            site.req("POST", "/inbox/collected", json={"keys": done})
            done = []
    if done:
        site.req("POST", "/inbox/collected", json={"keys": done})
    log.info("inbox: collected %d of %d", total, len(items))


def ensure_albums(im, site, deps, st):
    """One album per departure day (found by its marker, so re-runs never duplicate); every album's link is
    reported to the website once (again if the album changed). Returns {(dep_id, day): album_id}."""
    existing = {}
    for a in im.albums():
        m = MARK_RE.search(a.get("description") or "")
        if m:
            existing[(int(m.group(1)), int(m.group(2)))] = a["id"]
    reported = st.setdefault("reported", {})
    out, made = {}, 0
    for dep in deps:
        for day in dep["days"]:
            key = (dep["id"], day["day"])
            aid = existing.get(key)
            if not aid:
                if DRY:
                    log.info("DRY create album %s", album_name(dep, day))
                    continue
                aid = im.create_album(album_name(dep, day), MARK_FMT % key)["id"]
                made += 1
                log.info("created album %s", album_name(dep, day))
            out[key] = aid
            _album_cache[key] = aid
            sk = "%d:%d" % key
            st["albums"][sk] = aid
            if reported.get(sk) != aid and not DRY:
                try:
                    site.album(key[0], key[1], aid)
                    reported[sk] = aid
                except Exception as e:
                    log.warning("album link not reported for %s: %s", sk, e)
    if made:
        log.info("created %d albums", made)
    return out


CANCELLED = " (cancelled)"


def retire_album(im, album, why):
    """A day that no longer exists (departure cancelled, or fewer days): delete if empty, else mark it."""
    if not album:
        return
    if (album.get("assetCount") or 0) == 0:
        im.req("DELETE", "/albums/%s" % album["id"])
        log.info("deleted empty album %s (%s)", album["albumName"], why)
    elif CANCELLED not in album["albumName"]:
        im.update_album(album["id"], albumName=album["albumName"] + CANCELLED)
        log.info("marked album %s%s (%s, has photos)", album["albumName"], CANCELLED, why)


def apply_changes(im, site, st):
    """Owner 2026-11-14: albums as soon as a departure is created. Polls GET /departures?changed_since every
    round: new departures get their day albums; a new date or tour name renames them (only names this job set,
    so a staff rename survives until the departure changes); days that no longer exist and cancelled departures
    lose their albums (deleted if empty, "(cancelled)" if they have photos)."""
    since = st.get("since")
    if not since:  # first run: start from now; the backfill / the -3..+30 sweep cover the past
        st["since"] = datetime.now(TZ).isoformat(timespec="seconds")
        return
    data = site.req("GET", "/departures", params={"changed_since": since})
    deps, cancelled = data.get("departures", []), data.get("cancelled", [])
    if deps or cancelled:
        by_id = {}
        for a in im.albums():
            m = MARK_RE.search(a.get("description") or "")
            if m:
                by_id[(int(m.group(1)), int(m.group(2)))] = a
        names = st.setdefault("names", {})
        for dep in deps:
            days = {d["day"] for d in dep["days"]}
            for (dep_id, n), a in list(by_id.items()):  # days the departure no longer has
                if dep_id == dep["id"] and n not in days:
                    retire_album(im, a, "departure now has %d days" % len(days))
                    st["albums"].pop("%d:%d" % (dep_id, n), None)
                    _album_cache.pop((dep_id, n), None)
            for day in dep["days"]:
                key, want = (dep["id"], day["day"]), album_name(dep, day)
                sk = "%d:%d" % key
                a = by_id.get(key)
                if a and a["albumName"] != want and names.get(sk, a["albumName"]) != want \
                        and CANCELLED not in a["albumName"]:
                    im.update_album(a["id"], albumName=want)
                    log.info("renamed album %s -> %s", a["albumName"], want)
                names[sk] = want
            ensure_albums(im, site, [dep], st)  # creates missing days, reports links
        for dep_id in cancelled:
            for (d_id, n), a in list(by_id.items()):
                if d_id == int(dep_id):
                    retire_album(im, a, "departure cancelled")
                    st["albums"].pop("%d:%d" % (d_id, n), None)
                    _album_cache.pop((d_id, n), None)
    st["since"] = data.get("now") or since


def backfill(im, site, st, date_from):
    """Owner 2026-11-14: albums for every departure since ``date_from`` (empty; old photos are not sorted in).
    Safe to re-run: albums are found by marker, links re-posted only when missing."""
    to = (datetime.now(TZ).date() + timedelta(days=30)).isoformat()
    deps = site.departures(date_from, to)
    log.info("backfill %s..%s: %d departures, %d days", date_from, to, len(deps),
             sum(len(d["days"]) for d in deps))
    ensure_albums(im, site, deps, st)
    save_state(st)


def sort_photos(im, deps, albums, email_to_user, st):
    """Add each guide's photos of a day to that day's album (only days that are not synced yet)."""
    today = datetime.now(TZ).date()
    by_date = {}
    for dep in deps:
        for day in dep["days"]:
            if day["state"] in ("synced", "uploading") or (dep["id"], day["day"]) not in albums:
                continue
            if datetime.strptime(day["date"], "%Y-%m-%d").date() > today:
                continue
            by_date.setdefault(day["date"], []).append((dep, day))
    for date, entries in by_date.items():
        start = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=TZ)
        assets = im.search_day(start, start + timedelta(days=1))
        if not assets:
            continue
        for dep, day in entries:
            guide_ids = {email_to_user.get((g.get("email") or "").lower()) for g in dep["guides"]} - {None}
            alone = len(entries) == 1
            aid = albums[(dep["id"], day["day"])]
            have = {a["id"] for a in im.album(aid).get("assets", [])}
            done = set(st.setdefault("sorted", {}).get(aid, []))  # removed by staff -> never re-added
            pick = [a["id"] for a in assets
                    if a["id"] not in have and a["id"] not in done
                    and (a.get("ownerId") in guide_ids or (alone and not guide_ids))]
            if pick and not DRY:
                im.add_assets(aid, pick)
                log.info("album %s: +%d photos", album_name(dep, day), len(pick))
            st["sorted"][aid] = sorted(done | set(pick) | have)


def still_marked(site, dep_id, n):
    """After POST uploading: the day must now be 'uploading' (staff could undo 'ready' until that call)."""
    for d in site.departures():
        if d["id"] == dep_id:
            return next((x["state"] for x in d["days"] if x["day"] == n), None) == "uploading"
    return False


SITE_WM = os.path.join(os.path.dirname(STATE), "watermark-site.png")


def refresh_watermark(site, st):
    """API section 12/12b: the watermark uploaded on the website wins over config. Checked every round; the PNG is
    downloaded only when its version changes. 404 = none uploaded -> WATERMARK_PATH (or no watermark)."""
    try:
        r = site.s.get(SITE + "/watermark", timeout=30)
        if r.status_code == 404:
            if st.get("wm"):
                log.info("website watermark removed: using the NAS file")
            st["wm"] = None
            return
        r.raise_for_status()
        info = r.json()
        if not info.get("ok"):
            return
        if not st.get("wm") or st["wm"].get("version") != info.get("version") or not os.path.exists(SITE_WM):
            url = info.get("url") or "/mtbg/photos/api/v1/watermark.png"
            png = site.s.get(url if url.startswith("http") else SITE.split("/mtbg/")[0] + url, timeout=60)
            png.raise_for_status()
            tmp = SITE_WM + ".tmp"
            with open(tmp, "wb") as f:
                f.write(png.content)
            from PIL import Image
            Image.open(tmp).verify()  # a real image, not an error page
            os.replace(tmp, SITE_WM)
            log.info("website watermark %s downloaded (%s, %s%% of short edge)", str(info.get("version"))[:8],
                     info.get("anchor"), info.get("size_pct"))
        st["wm"] = {k: info.get(k) for k in ("version", "anchor", "offset_x_pct", "offset_y_pct", "size_pct",
                                             "opacity")}
    except Exception as e:  # keep the last good one
        log.warning("watermark check failed: %s", e)


def refresh_quality(site, st):
    """Quality settings from the website (GET /quality); 404 = not set there -> config defaults."""
    import process
    try:
        r = site.s.get(SITE + "/quality", timeout=30)
        if r.status_code == 404:
            return
        r.raise_for_status()
        q = r.json()
        if q.get("ok"):
            if (st.get("quality") or {}).get("version") != q.get("version"):
                log.info("quality settings from the website: photos %spx q%s, videos %spx crf %s max %skbps",
                         (q.get("photo") or {}).get("long_edge"), (q.get("photo") or {}).get("jpeg_quality"),
                         (q.get("video") or {}).get("long_edge"), (q.get("video") or {}).get("crf"),
                         (q.get("video") or {}).get("max_bitrate_kbps"))
            st["quality"] = q
            process.set_quality(q)
    except Exception as e:  # keep the last values
        log.warning("quality check failed: %s", e)
        if st.get("quality"):
            process.set_quality(st["quality"])


def watermark_for(st):
    """(path, placement) to use now: the website's, else config's."""
    import process
    wm = st.get("wm")
    if wm and os.path.exists(SITE_WM):
        process.set_watermark(wm.get("anchor"), wm.get("offset_x_pct"), wm.get("offset_y_pct"), wm.get("size_pct"),
                              wm.get("opacity"))
        return SITE_WM
    return WATERMARK if os.path.exists(WATERMARK) else None


def manifest_item(p, key):
    """One photos[] item of the synced manifest (API section 3 + 10)."""
    item = {"type": p["type"], "key": key(p["file"]), "width": p["width"], "height": p["height"],
            "taken": p["taken"]}
    if p["type"] == "video":
        item.update(poster_key=key(p["poster"]), preview_key=key(p["preview"]), duration=p["duration"],
                    bytes=p["bytes"])
    return item


# ---------------------------------------------------------------------------------------------------------------
# Staging (owner 2026-11-15): every photo/video is processed and uploaded as soon as it is in a day album, under
# staging/<id>-<random>/day-N/ (no lifecycle clock running for clients). "Publish day" then only copies the staged
# files to tours/... inside R2, builds the header + zip from copies kept on the NAS, and tells the website.
# Items removed/archived/hidden in Immich are deleted from staging. Watermark/quality changes re-stage items.
STAGE_BUDGET = int(float(E("STAGE_MINUTES", default="4")) * 60)   # processing time per sync round
CACHE = os.path.join(WORK, "cache")
VIDEO_TYPES = {".mp4": "video/mp4", ".jpg": "image/jpeg", ".webp": "image/webp"}


UPLOADER_RE = re.compile(r"Uploaded by .*?(?:\(([^)\s]+@[^)\s]+)\))?\s*(?:\[staff:(\d+)\])?\s*$", re.M)


def uploaded_by(a):
    """{"id", "email"} of the staff member who uploaded an asset (from its "Uploaded by" description), or None."""
    desc = (a.get("exifInfo") or {}).get("description") or a.get("description") or ""
    m = UPLOADER_RE.search(desc)
    if not m or not (m.group(1) or m.group(2)):
        return None
    return {"id": int(m.group(2)) if m.group(2) else None, "email": m.group(1)}


def visible_assets(info):
    """Album items that get published: photos/videos not trashed, archived, hidden or locked (the moving part of a
    Live Photo is a hidden asset, so it is left out too)."""
    return [a for a in info.get("assets", []) if a.get("type") in ("IMAGE", "VIDEO") and not a.get("isTrashed")
            and not a.get("isArchived") and a.get("visibility", "timeline") == "timeline"]


def stage_prefix(dep, n):
    """The website's staging_prefix (API section 13) when given, else derived the same way."""
    base = dep.get("staging_prefix") or "staging/" + (dep["prefix"][len("tours/"):] if dep["prefix"].startswith("tours/")
                                                      else dep["prefix"])
    return "%sday-%d/" % (base if base.endswith("/") else base + "/", n)


def item_files(item):
    """Files of a processed item that go to R2 (relative to its cache dir)."""
    return [item["file"], item["poster"], item["preview"]] if item["type"] == "video" else [item["file"]]


def drop_staged(r2, day_cache, meta):
    for f in meta.get("files", []):
        try:
            if r2:
                r2.delete(meta["prefix"] + os.path.basename(f))
        except Exception as e:
            log.warning("staging delete %s: %s", f, e)
    for f in meta.get("files", []) + ([meta["item"].get("full")] if meta.get("item", {}).get("full") else []):
        try:
            os.remove(os.path.join(day_cache, f))
        except OSError:
            pass


def stage_asset(im, r2, a, dep, n, day_cache, sig, wm_path):
    """Download the original, process it, upload its web files to staging. Returns the staged meta."""
    tmp = os.path.join(WORK, "dl")
    os.makedirs(tmp, exist_ok=True)
    ext = (os.path.splitext(a.get("originalFileName") or "")[1] or ".jpg").lower()
    src = os.path.join(tmp, a["id"] + ext)
    try:
        im.download(a["id"], src)
        item = process.process_item(src, day_cache, a["id"], wm_path)
    finally:
        try:
            os.remove(src)
        except OSError:
            pass
    pre = stage_prefix(dep, n)
    files = item_files(item) + ([item["thumb"]] if item.get("thumb") else [])
    if r2:
        for f in files:
            path = os.path.join(day_cache, f)
            r2.put_file(pre + os.path.basename(f), path, VIDEO_TYPES.get(os.path.splitext(f)[1], "image/jpeg"))
    if not item.get("taken"):
        item["taken"] = a.get("localDateTime") or a.get("fileCreatedAt")
    return {"sig": sig, "item": item, "files": files, "prefix": pre, "uploaded": bool(r2), "by": uploaded_by(a),
            "name": a.get("originalFileName")}


def stage_day(im, r2, dep, day, aid, st, deadline=None, force_all=False):
    """Bring a day's staging in line with its album. Returns (assets, staged dict) for publishing."""
    n = day["day"]
    key = "%d:%d" % (dep["id"], n)
    staged = st.setdefault("staged", {}).setdefault(key, {})
    day_cache = os.path.join(CACHE, "%d-day-%d" % (dep["id"], n))
    info = im.album(aid)
    assets = visible_assets(info)
    ids = {a["id"] for a in assets}
    for gone in [x for x in staged if x not in ids]:          # removed / archived / hidden in Immich
        drop_staged(r2, day_cache, staged.pop(gone))
    wm_path = watermark_for(st)
    sig = process.settings_sig(wm_path)
    for a in sorted(assets, key=lambda a: a.get("fileCreatedAt") or ""):
        meta = staged.get(a["id"])
        if meta and meta.get("sig") == sig and (meta.get("uploaded") or not r2):
            continue
        if deadline and time.time() > deadline and not force_all:
            break
        if meta:                                               # settings changed: redo
            drop_staged(r2, day_cache, meta)
        try:
            staged[a["id"]] = stage_asset(im, r2, a, dep, n, day_cache, sig, wm_path)
            log.info("staged %s (%s) for departure %s day %s", a.get("originalFileName"), a.get("type"), dep["id"], n)
        except Exception as e:
            log.error("staging %s failed: %s", a.get("originalFileName"), e)
            if force_all:
                raise
        save_state(st)
    return info, assets, staged, day_cache


def report_staged(site, r2, dep, day, info, assets, staged, day_cache, st):
    """Tell the website what a day would look like if sent now (for "Preview album"; owner 2026-11-15).
    Same manifest shape as /synced, but keys under staging/. The header is staged too. Sent only on change."""
    n = day["day"]
    items = [dict(staged[a["id"]]["item"], _id=a["id"]) for a in assets
             if a["id"] in staged and staged[a["id"]].get("uploaded")]
    items.sort(key=lambda it: (it.get("taken") or "9999", it["_id"]))
    pre = stage_prefix(dep, n)
    photos = [it for it in items if it["type"] == "photo"]
    cov = next((it for it in photos if it["_id"] == info.get("albumThumbnailAssetId")), photos[0] if photos else None)
    sig = repr(([it["_id"] for it in items], cov and cov["_id"], len(assets),
                [staged[it["_id"]].get("sig") for it in items]))
    rep = st.setdefault("staged_report", {})
    k = "%d:%d" % (dep["id"], n)
    if rep.get(k) == sig:
        return
    head = None
    if items:
        head_src = os.path.join(day_cache, cov["file"] if cov else items[0]["poster"])
        hp = os.path.join(day_cache, "header.jpg")
        head = process.make_header(head_src, hp)
        r2.put_file(pre + "cover.jpg", hp, "image/jpeg")
    key = lambda f: pre + os.path.basename(f)  # noqa: E731
    done_ids = {it["_id"] for it in items}
    pending = [{"asset_id": a["id"], "uploaded_by": uploaded_by(a), "name": a.get("originalFileName")}
               for a in assets if a["id"] not in done_ids]
    photos = []
    for it in items:
        m = manifest_item(it, key)
        m.update(asset_id=it["_id"], uploaded_by=staged[it["_id"]].get("by"),
                 thumb_key=key(it["thumb"]) if it.get("thumb") else None)
        photos.append(m)
    body = {"date": day["date"], "count": len(items), "pending": len(pending), "pending_items": pending,
            "cover": {"key": pre + "cover.jpg", "width": head["width"], "height": head["height"]} if head else None,
            "photos": photos}
    r = site.s.post(SITE + "/departures/%d/days/%d/staged" % (dep["id"], n), json=body, timeout=60)
    if r.status_code == 404 and "No such departure" not in r.text:
        if not st.get("staged_route_missing"):
            log.info("website has no /staged route yet: preview data not sent (staging continues)")
        st["staged_route_missing"] = True
        return
    st.pop("staged_route_missing", None)
    if r.status_code == 422 and not st.get("staged_extra_off"):
        log.warning("website refused the extra /staged fields (422): resending without them")
        st["staged_extra_off"] = True
    if r.status_code == 422 or st.get("staged_extra_off"):
        for ph in body["photos"]:
            for f in ("asset_id", "uploaded_by", "thumb_key"):
                ph.pop(f, None)
        body.pop("pending_items", None)
        r = site.s.post(SITE + "/departures/%d/days/%d/staged" % (dep["id"], n), json=body, timeout=60)
    if r.ok:
        rep[k] = sig
        log.info("preview updated for departure %s day %s: %d items (%d still processing)", dep["id"], n,
                 len(items), body["pending"])
    else:
        log.warning("staged report %s day %s: %s %s", dep["id"], n, r.status_code, r.text[:200])


def process_deletions(im, site, r2, deps, albums, st):
    """API section 14: deletions asked for on the website (guide: own uploads; admin: any). Each asset leaves the
    day album and goes to Immich's trash (restorable 30 days); its staged files go; the preview is re-sent."""
    r = site.s.get(SITE + "/deletions", timeout=30)
    if r.status_code == 404:
        if not st.get("deletions_route_missing"):
            log.info("website has no /deletions route yet")
        st["deletions_route_missing"] = True
        return
    st.pop("deletions_route_missing", None)
    r.raise_for_status()
    items = r.json().get("items") or []
    if not items:
        return
    done, touched = [], set()
    for d in items:
        try:
            dep_id, n, asset = int(d["departure_id"]), int(d["day"]), d["asset_id"]
            aid = albums.get((dep_id, n)) or day_album(im, site, dep_id, n)
            try:
                im.req("DELETE", "/albums/%s/assets" % aid, json={"ids": [asset]})
            except RuntimeError as e:
                log.warning("remove %s from album: %s", asset, e)
            im.req("DELETE", "/assets", json={"ids": [asset], "force": False})   # to Immich trash
            k = "%d:%d" % (dep_id, n)
            meta = st.get("staged", {}).get(k, {}).pop(asset, None)
            if meta:
                drop_staged(r2, os.path.join(CACHE, "%d-day-%d" % (dep_id, n)), meta)
            st.get("staged_report", {}).pop(k, None)   # force a fresh preview for that day
            touched.add((dep_id, n))
            done.append(d["id"])
            log.info("deleted asset %s from departure %s day %s (in Immich trash)", asset, dep_id, n)
        except Exception as e:
            log.error("deletion %s failed: %s", d, e)
    for dep in deps:                                   # re-send the preview of the days that changed
        for day in dep["days"]:
            if (dep["id"], day["day"]) in touched and albums.get((dep["id"], day["day"])):
                info, assets, staged, day_cache = stage_day(im, r2, dep, day, albums[(dep["id"], day["day"])], st,
                                                            time.time() + 60)
                report_staged(site, r2, dep, day, info, assets, staged, day_cache, st)
    if done:
        site.req("POST", "/deletions/done", json={"ids": done})
    save_state(st)


def stage_round(im, site, r2, deps, albums, st):
    """Background: stage what's new in albums of days not published yet (time-boxed per round)."""
    deadline = time.time() + STAGE_BUDGET
    for dep in deps:
        for day in dep["days"]:
            if time.time() > deadline:
                return
            aid = albums.get((dep["id"], day["day"]))
            if not aid or day["state"] in ("synced", "uploading", "ready"):
                continue                       # ready/uploading days are handled by publish_day
            try:
                info, assets, staged, day_cache = stage_day(im, r2, dep, day, aid, st, deadline)
                if assets or staged:
                    report_staged(site, r2, dep, day, info, assets, staged, day_cache, st)
            except Exception as e:
                log.warning("staging departure %s day %s: %s", dep["id"], day["day"], e)


def publish_day(im, site, r2, dep, day, aid, st):
    n = day["day"]
    info = im.album(aid)
    if not visible_assets(info):
        log.warning("album %s is ready but has no photos", info["albumName"])
        return
    if not DRY:
        site.uploading(dep["id"], n)  # from here staff can no longer undo "ready"
        if not still_marked(site, dep["id"], n):
            log.info("departure %s day %s: ready was undone, skipping", dep["id"], n)
            return
    # Anything not staged yet (or staged with old settings) is done now.
    info, assets, staged, day_cache = stage_day(im, r2, dep, day, aid, st, force_all=True)
    items = [dict(staged[a["id"]]["item"], _id=a["id"]) for a in assets if a["id"] in staged]
    if not items:
        raise RuntimeError("nothing could be processed for this day")
    items.sort(key=lambda it: (it.get("taken") or "9999", it["_id"]))
    prefix = dep["prefix"]
    day_prefix = "%sday-%d/" % (prefix, n)
    pre = stage_prefix(dep, n)
    # 1. copy staged files into the client gallery (inside R2, nothing re-uploaded)
    copies = [(pre + os.path.basename(f), day_prefix + os.path.basename(f), os.path.join(day_cache, f))
              for it in items for f in item_files(it)]
    for src_key, dst_key, _p in copies:
        r2.copy(src_key, dst_key)
    # 2. header: the album cover if it is a photo, else the first photo, else the first video's poster
    photos = [it for it in items if it["type"] == "photo"]
    cov = next((it for it in photos if it["_id"] == info.get("albumThumbnailAssetId")), photos[0] if photos else None)
    head_src = os.path.join(day_cache, cov["file"] if cov else items[0]["poster"])
    header_path = os.path.join(day_cache, "header.jpg")
    head = process.make_header(head_src, header_path)
    # 3. zip of the photos (copies kept on the NAS), numbered in display order
    zip_path = os.path.join(day_cache, "day.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as z:
        for i, it in enumerate(photos, 1):
            z.write(os.path.join(day_cache, it["full"]), "%04d.jpg" % i)
    uploads = [(header_path, day_prefix + "cover.jpg", "image/jpeg"),
               (zip_path, "%sday-%d.zip" % (prefix, n), "application/zip")]
    for path, k, ctype in uploads:
        r2.put_file(k, path, ctype)
    # 4. verify every object before telling the website
    for _s, k, path in copies + [(None, k, p) for p, k, _c in uploads]:
        h = r2.head(k)
        if not h or h["size"] != os.path.getsize(path):
            raise RuntimeError("R2 verify failed for %s" % k)
    key = lambda f: day_prefix + os.path.basename(f)  # noqa: E731
    manifest = {
        "date": day["date"],
        "count": len(items),
        "cover": {"key": day_prefix + "cover.jpg", "width": head["width"], "height": head["height"]},
        "zip": {"key": "%sday-%d.zip" % (prefix, n), "bytes": os.path.getsize(zip_path)},
        "photos": [manifest_item(it, key) for it in items],
    }
    res = site.synced(dep["id"], n, manifest)
    stamp = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
    desc = SYNCED_RE.sub("", info.get("description") or "")
    videos = sum(1 for it in items if it["type"] == "video")
    what = "%d photos" % (len(items) - videos) + (" · %d videos" % videos if videos else "")
    desc += "\n✓ synced %s · %s · %s" % (stamp, what, res.get("short_url", ""))
    im.update_album(aid, description=desc)
    st["synced"]["%d:%d" % (dep["id"], n)] = {"at": stamp, "count": len(items)}
    log.info("published %s: %s, state=%s", info["albumName"], what, res.get("photos_state"))
    # 5. clean up: staging objects and the NAS copies of this day
    thumbs = [pre + os.path.basename(it["thumb"]) for it in items if it.get("thumb")]
    for src_key in [c[0] for c in copies] + thumbs + [pre + "cover.jpg"]:
        try:
            r2.delete(src_key)
        except Exception:
            pass
    st["staged"].pop("%d:%d" % (dep["id"], n), None)
    st.get("staged_report", {}).pop("%d:%d" % (dep["id"], n), None)
    shutil.rmtree(day_cache, ignore_errors=True)
    save_state(st)


def run_once(im, site, r2, st):
    refresh_watermark(site, st)
    refresh_quality(site, st)
    try:
        apply_changes(im, site, st)
    except Exception:
        log.error("changes round failed:\n%s", traceback.format_exc())
    try:
        collect_inbox(im, site, r2, st)
    except Exception:
        log.error("inbox round failed:\n%s", traceback.format_exc())
    deps = site.departures()  # the -3..+30 sweep: safety net for albums + the days to publish
    albums = ensure_albums(im, site, deps, st)
    users = im.users()
    email_to_user = {(u.get("email") or "").lower(): u["id"] for u in users}
    if E("SORT_PARTNER_PHOTOS", default="0") == "1":  # off: guides choose what they upload (office page / cellular)
        sort_photos(im, deps, albums, email_to_user, st)
    if r2 is not None:
        try:
            process_deletions(im, site, r2, deps, albums, st)
        except Exception:
            log.error("deletions round failed:\n%s", traceback.format_exc())
        try:
            stage_round(im, site, r2, deps, albums, st)
        except Exception:
            log.error("staging round failed:\n%s", traceback.format_exc())
    for dep in deps:
        for day in dep["days"]:
            aid = albums.get((dep["id"], day["day"]))
            if not aid or day["state"] == "synced":
                continue
            # Ready = Staff App / record page ("ready"), or "#ready" in the Immich album description.
            # "uploading" = a previous round started but did not finish (crash, restart): resume it.
            # "uploaded" (guides pressed Done) is NOT approval: only the admin's "Publish day" (state "ready") or
            # "#ready" typed in the album (Tours-account albums: only admins can edit them) starts processing.
            ready = day["state"] in ("ready", "uploading") or (
                day["state"] in ("none", "uploaded") and READY_RE.search(im.album(aid).get("description") or ""))
            if ready and r2 is None:
                log.warning("departure %s day %s is ready, but R2 is not set up: publishing waits",
                            dep["id"], day["day"])
            elif ready:
                try:
                    publish_day(im, site, r2, dep, day, aid, st)
                except Exception:
                    log.error("publish failed for departure %s day %s:\n%s", dep["id"], day["day"],
                              traceback.format_exc())
    save_state(st)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    im = Immich(E("IMMICH_API_KEY", default=""))
    site = Site(E("NAS_TOKEN", "WEBSITE_TOKEN", default=""))
    r2 = None
    if not DRY:
        try:
            r2 = R2Client(E("R2_ACCOUNT_ID"), E("R2_ACCESS_KEY_ID"), E("R2_SECRET_ACCESS_KEY"),
                          E("R2_BUCKET", default="tour-photos"))
        except Exception as e:  # albums, upload page and sorting still work; publishing waits for R2
            log.warning("R2 not set up (%s): albums run, publishing and the mobile inbox wait for R2 keys", e)
    log.info("tour-photos sync as Immich user %s, website %s, every %ss%s",
             im.me().get("email"), SITE, INTERVAL, " (DRY RUN)" if DRY else "")
    st = load_state()
    if E("BACKFILL_FROM"):  # one-off: python sync.py with BACKFILL_FROM=2026-07-01
        backfill(im, site, st, E("BACKFILL_FROM"))
        return
    while True:
        try:
            run_once(im, site, r2, st)
        except Exception:
            log.error("sync round failed:\n%s", traceback.format_exc())
        if E("ONCE") == "1":
            break
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
