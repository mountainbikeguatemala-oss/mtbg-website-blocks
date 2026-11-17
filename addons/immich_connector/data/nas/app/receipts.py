"""Receipts out of Immich into the accounting folder (owner 2026-11-16).

"Use Immich to auto filter expenses that look like receipts" / "physically move all the receipt files to their own
folder" / "remove receipts from Immich, and ignore duplicates" / receipts + payment screenshots, one big folder.

Every full sync round (only when RECEIPTS_DIR is set):
1. Finds receipt-like photos with Immich's own image model (CLIP): each photo's stored embedding (Immich database,
   table smart_search) against text descriptions embedded by Immich's machine-learning service. Two kinds:
   paper receipts / invoices / card slips, and payment screenshots (bank transfer confirmations, payment apps).
   - clear matches are moved (RECEIPT_AUTO / PAYMENT_AUTO distances);
   - borderline ones go to the Immich album "Receipts – check" once (never suggested again);
   - anything a person puts in the Immich album "Receipts" is moved too (the manual way, e.g. from the check album).
2. Move = the original file is copied into RECEIPTS_DIR as <YYYY-MM-DD>_<original name> (one big folder), checked,
   then the Immich asset goes to Immich's trash (restorable 30 days). Duplicates are not copied again: the same file
   content (SHA-256) only (Immich's duplicate groups are look-alikes: two different transfers look the same); they
   still leave Immich.
Photos in tour day albums ([departure:N day:M]) are never touched. RECEIPTS_DRY=1: only writes the plan
(/work/receipts_plan.txt), moves nothing.
"""
import hashlib
import json
import logging
import os
import re
from datetime import datetime

import requests

log = logging.getLogger("tour-photos")


def _env(name, default=""):
    return (os.environ.get(name) or "").strip().strip('"').strip("'").strip() or default


DIR = _env("RECEIPTS_DIR")                       # e.g. /receipts (the NAS share mounted into this container)
DRY = _env("RECEIPTS_DRY", "1") == "1"           # plan only until switched off
STATE = _env("RECEIPTS_STATE", "/data/receipts.json")
PLAN = _env("RECEIPTS_PLAN", "/work/receipts_plan.txt")
ML = _env("IMMICH_ML_URL", "http://immich_machine_learning:3003").rstrip("/")
MODEL = _env("CLIP_MODEL", "ViT-B-32__openai")
RECEIPT_AUTO = float(_env("RECEIPT_AUTO", "0.735"))
RECEIPT_CHECK = float(_env("RECEIPT_CHECK", "0.765"))
PAYMENT_AUTO = float(_env("PAYMENT_AUTO", "0.712"))
PAYMENT_CHECK = float(_env("PAYMENT_CHECK", "0.72"))
PER_ROUND = int(_env("RECEIPTS_PER_ROUND", "40"))
OWNER = _env("RECEIPTS_OWNER", "1000:10")         # uid:gid of moved files (the NAS user, so they can be renamed)
ALBUM = _env("RECEIPTS_ALBUM", "Receipts")
CHECK_ALBUM = _env("RECEIPTS_CHECK_ALBUM", "Receipts – check")
TOUR_MARK = re.compile(r"\[[a-z-]*departure:\d+ day:\d+\]")

QUERIES = {
    "receipt": ["a photo of a paper receipt", "a store receipt with prices and total"],
    "payment": ["a phone screenshot of a bank transfer confirmation",
                "a screenshot of a mobile payment app showing an amount paid"],
}


def enabled():
    return bool(DIR)


def _load():
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(rs):
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rs, f, indent=1)
    os.replace(tmp, STATE)


def _vectors(rs):
    """One averaged text embedding per kind, from Immich's ML service (kept in the state)."""
    vec = rs.get("vectors") or {}
    if vec.get("model") == MODEL and all(k in vec for k in QUERIES):
        return vec
    vec = {"model": MODEL}
    for kind, texts in QUERIES.items():
        embs = []
        for t in texts:
            r = requests.post(ML + "/predict", timeout=60, data={
                "entries": json.dumps({"clip": {"textual": {"modelName": MODEL}}}), "text": t})
            r.raise_for_status()
            v = r.json()["clip"]
            embs.append(json.loads(v) if isinstance(v, str) else v)
        vec[kind] = [sum(e[i] for e in embs) / len(embs) for i in range(len(embs[0]))]
    rs["vectors"] = vec
    return vec


def _db():
    import pg8000.native
    return pg8000.native.Connection(user=_env("DB_USERNAME", "postgres"), password=_env("DB_PASSWORD"),
                                    database=_env("DB_DATABASE_NAME", "immich"),
                                    host=_env("DB_HOSTNAME", "database"), port=int(_env("DB_PORT", "5432")))


def _lit(v):
    return "[" + ",".join("%.7f" % x for x in v) + "]"


def candidates(vec, owner):
    """[(asset_id, kind, distance, auto, file_created, original_name, duplicate_id)] of images not in a tour album."""
    con = _db()
    try:
        rows = con.run("""
            select a.id::text, (s.embedding <=> cast(:r as vector)) dr, (s.embedding <=> cast(:p as vector)) dp,
                   a."fileCreatedAt", a."originalFileName", a."duplicateId"::text,
                   coalesce((select string_agg(coalesce(al.description, ''), ' ') from album_asset aa
                             join album al on al.id = aa."albumId" where aa."assetId" = a.id), '')
            from smart_search s join asset a on a.id = s."assetId"
            where a."deletedAt" is null and a.type = 'IMAGE' and a."ownerId"::text = :owner
              and ((s.embedding <=> cast(:r as vector)) <= :rc or (s.embedding <=> cast(:p as vector)) <= :pc)
            """, r=_lit(vec["receipt"]), p=_lit(vec["payment"]), rc=RECEIPT_CHECK, pc=PAYMENT_CHECK, owner=owner)
    finally:
        con.close()
    out = []
    for aid, dr, dp, created, name, dup, album_desc in rows:
        if TOUR_MARK.search(album_desc or ""):
            continue
        kind, d = ("receipt", dr) if dr - RECEIPT_AUTO <= dp - PAYMENT_AUTO else ("payment", dp)
        auto = dr <= RECEIPT_AUTO or dp <= PAYMENT_AUTO
        out.append((aid, kind, float(d), auto, created, name or "receipt.jpg", dup))
    out.sort(key=lambda c: c[2])
    return out


def _album(im, name, desc):
    for a in im.albums():
        if a.get("albumName") == name:
            return a["id"]
    return im.create_album(name, desc)["id"]


def _album_assets(im, aid):
    return [a for a in (im.album(aid).get("assets") or []) if not a.get("isTrashed")]


def _safe_name(created, name):
    day = created.strftime("%Y-%m-%d") if isinstance(created, datetime) else str(created)[:10]
    base = re.sub(r"[^\w.\-() ]+", "_", os.path.basename(name)).strip() or "receipt.jpg"
    return "%s_%s" % (day, base)


def _move(im, rs, aid, created, name, dup):
    """Copy the original into DIR (unless it is a duplicate), then send the asset to Immich's trash."""
    tmp = os.path.join(DIR, ".incoming-%s" % aid)
    im.download(aid, tmp)
    h = hashlib.sha256()
    with open(tmp, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    sha = h.hexdigest()
    files = rs.setdefault("files", {})
    if sha in files:                              # same file content only: Immich duplicate groups are look-alikes
        os.remove(tmp)                            # (two different bank transfers look the same), never trusted here
        what = "duplicate of %s" % files[sha]
    else:
        target = _safe_name(created, name)
        stem, ext = os.path.splitext(target)
        n = 2
        while os.path.exists(os.path.join(DIR, target)):
            target = "%s-%d%s" % (stem, n, ext)
            n += 1
        os.replace(tmp, os.path.join(DIR, target))
        path = os.path.join(DIR, target)
        try:
            uid, gid = (int(x) for x in OWNER.split(":"))
            os.chown(path, uid, gid)
            os.chmod(path, 0o664)
        except (OSError, ValueError):
            pass
        if isinstance(created, datetime):
            ts = created.timestamp()
            os.utime(path, (ts, ts))
        files[sha] = target
        what = "copied as %s" % target
    rs.setdefault("moved", {})[aid] = {"sha": sha, "at": datetime.now().isoformat(timespec="seconds")}
    _save(rs)                                     # the file is safe before the photo leaves Immich
    im.req("DELETE", "/assets", json={"ids": [aid], "force": False})
    return what


def _undo_lookalike_skips(im, rs):
    """First live round (2026-11-16) skipped photos that were only in the same Immich duplicate group as one already
    copied: different payments that look alike. Bring them back from the trash so they are copied like the rest."""
    files = set(rs.get("files", {}))
    moved = rs.get("moved", {})
    back = [aid for aid, m in moved.items() if m.get("sha") not in files]
    if not back:
        return
    im.req("POST", "/trash/restore/assets", json={"ids": back})
    for aid in back:
        moved.pop(aid, None)
    rs.pop("dup_groups", None)
    _save(rs)
    log.info("receipts: %d look-alike skip(s) restored from the Immich trash, to be copied", len(back))


def run(im):
    """One round (called from the sync loop's full rounds)."""
    if not enabled():
        return
    if not os.path.isdir(DIR):
        log.warning("receipts: %s is not mounted: nothing moved", DIR)
        return
    rs = _load()
    _undo_lookalike_skips(im, rs)
    vec = _vectors(rs)
    cands = candidates(vec, im.me()["id"])   # only this account's photos (it can trash only those)
    moved, suggested = rs.setdefault("moved", {}), rs.setdefault("suggested", {})
    album_id = _album(im, ALBUM, "Anything put here is moved to the receipts folder and leaves Immich.") \
        if not DRY else None
    manual = [(a["id"], a.get("fileCreatedAt") or "", a.get("originalFileName") or "receipt.jpg", a.get("duplicateId"))
              for a in (_album_assets(im, album_id) if album_id else [])]
    auto = [(c[0], c[4], c[5], c[6]) for c in cands if c[3] and c[0] not in moved]
    check = [c for c in cands if not c[3] and c[0] not in moved and c[0] not in suggested]
    if DRY:
        with open(PLAN, "w") as f:
            f.write("# receipts plan %s: %d to move, %d to the check album\n" % (
                datetime.now().isoformat(timespec="seconds"), len(auto), len(check)))
            for c in cands:
                f.write("%s\t%s\t%.4f\t%s\t%s\n" % ("MOVE" if c[3] else "CHECK", c[1], c[2], c[0], c[5]))
        log.info("receipts (dry run): %d would move, %d would go to '%s'; plan in %s", len(auto), len(check),
                 CHECK_ALBUM, PLAN)
        _save(rs)
        return
    if check:
        cid = _album(im, CHECK_ALBUM, "Possible receipts. Put the real ones in the album '%s'; the rest can stay."
                     % ALBUM)
        im.add_assets(cid, [c[0] for c in check])
        for c in check:
            suggested[c[0]] = datetime.now().isoformat(timespec="seconds")
        log.info("receipts: %d possible receipt(s) added to '%s'", len(check), CHECK_ALBUM)
    done = 0
    seen = set()
    for aid, created, name, dup in manual + auto:
        if aid in seen or aid in moved or done >= PER_ROUND:
            continue
        seen.add(aid)
        if isinstance(created, str) and created:
            try:
                created = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except ValueError:
                pass
        try:
            what = _move(im, rs, aid, created, name, dup)
            done += 1
            log.info("receipt %s: %s, sent to Immich trash", name, what)
        except Exception as e:
            log.error("receipt %s (%s) not moved: %s", name, aid, e)
            try:
                os.remove(os.path.join(DIR, ".incoming-%s" % aid))
            except OSError:
                pass
    _save(rs)
