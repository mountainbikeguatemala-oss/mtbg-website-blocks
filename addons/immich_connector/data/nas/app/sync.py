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

from process import process_day
from r2 import R2Client

log = logging.getLogger("tour-photos")


def E(*names, default=None):
    """First non-empty setting among ``names`` (the generic name first, older names after)."""
    for n in names:
        v = os.environ.get(n)
        if v not in (None, ""):
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
        im.req("PUT", "/assets/%s" % res["id"], json={"description": "Uploaded by %s%s" % (
            guide.get("name") or "guide", " (%s)" % guide["email"] if guide.get("email") else "")})
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


def publish_day(im, site, r2, dep, day, aid, st):
    info = im.album(aid)
    # Publish the album exactly as the admin left it: removed photos are not in the album; archived, hidden,
    # locked or trashed ones are skipped.
    assets = [a for a in info.get("assets", []) if a.get("type") == "IMAGE" and not a.get("isTrashed")
              and not a.get("isArchived") and a.get("visibility", "timeline") == "timeline"]
    if not assets:
        log.warning("album %s is ready but has no photos", info["albumName"])
        return
    n = day["day"]
    if not DRY:
        site.uploading(dep["id"], n)  # from here staff can no longer undo "ready"
        if not still_marked(site, dep["id"], n):
            log.info("departure %s day %s: ready was undone, skipping", dep["id"], n)
            return
    work = os.path.join(WORK, "%d-day-%d" % (dep["id"], n))
    shutil.rmtree(work, ignore_errors=True)
    src, out = os.path.join(work, "src"), os.path.join(work, "out")
    os.makedirs(src)
    cover_name = None
    for a in assets:
        ext = os.path.splitext(a.get("originalFileName") or "")[1] or ".jpg"
        fname = a["id"] + ext.lower()
        im.download(a["id"], os.path.join(src, fname))
        if a["id"] == info.get("albumThumbnailAssetId"):
            cover_name = fname
    m = process_day(src, out, WATERMARK, cover_name)
    prefix = dep["prefix"]
    day_prefix = "%sday-%d/" % (prefix, n)
    uploads = [(os.path.join(out, p["file"]), day_prefix + os.path.basename(p["file"]), "image/jpeg")
               for p in m["photos"]]
    uploads.append((os.path.join(out, "header.jpg"), day_prefix + "cover.jpg", "image/jpeg"))
    uploads.append((os.path.join(out, "day.zip"), "%sday-%d.zip" % (prefix, n), "application/zip"))
    if DRY:
        log.info("DRY would upload %d objects under %s", len(uploads), day_prefix)
        return
    for path, key, ctype in uploads:
        r2.put_file(key, path, ctype)
    for path, key, _ctype in uploads:  # verify every object before telling the website
        h = r2.head(key)
        if not h or h["size"] != os.path.getsize(path):
            raise RuntimeError("R2 verify failed for %s" % key)
    manifest = {
        "date": day["date"],
        "count": m["count"],
        "cover": {"key": day_prefix + "cover.jpg", "width": m["header"]["width"], "height": m["header"]["height"]},
        "zip": {"key": "%sday-%d.zip" % (prefix, n), "bytes": m["zip"]["bytes"]},
        "photos": [{"key": day_prefix + os.path.basename(p["file"]), "width": p["width"], "height": p["height"],
                    "taken": p["taken"]} for p in m["photos"]],
    }
    res = site.synced(dep["id"], n, manifest)
    stamp = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
    desc = SYNCED_RE.sub("", info.get("description") or "")
    desc += "\n✓ synced %s · %d photos · %s" % (stamp, m["count"], res.get("short_url", ""))
    im.update_album(aid, description=desc)
    st["synced"]["%d:%d" % (dep["id"], n)] = {"at": stamp, "count": m["count"]}
    log.info("published %s: %d photos, state=%s", info["albumName"], m["count"], res.get("photos_state"))
    shutil.rmtree(work, ignore_errors=True)


def run_once(im, site, r2, st):
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
            if ready:
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
    r2 = None if DRY else R2Client(E("R2_ACCOUNT_ID"), E("R2_ACCESS_KEY_ID"), E("R2_SECRET_ACCESS_KEY"),
                                   E("R2_BUCKET", default="tour-photos"))
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
