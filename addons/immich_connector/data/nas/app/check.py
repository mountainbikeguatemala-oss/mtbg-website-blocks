"""Setup check: run after filling in config.env.

    docker compose run --rm photos-sync /app/check.py

Tests each connection and prints OK / PROBLEM with what to fix. Changes nothing except one tiny test file in
R2 (written, read back, deleted).
"""
import os
import sys
import time

from PIL import Image

import office_tls
import sync
from r2 import R2Client

ok = True


def report(name, good, detail=""):
    global ok
    ok = ok and good
    print("%-10s %s  %s" % (name, "OK     " if good else "PROBLEM", detail))


def main():
    print("Photo service setup check\n")
    # Immich
    try:
        me = sync.Immich(sync.E("IMMICH_API_KEY", default="")).me()
        report("Immich", True, "signed in as %s (%s)" % (me.get("name"), me.get("email")))
    except Exception as e:
        report("Immich", False, "check IMMICH_URL and IMMICH_API_KEY (%s)" % str(e)[:120])
    # Website
    try:
        deps = sync.Site(sync.E("NAS_TOKEN", "WEBSITE_TOKEN", default="")).departures()
        report("Website", True, "%d departures in the next 30 days (%s)" % (len(deps), sync.SITE))
    except Exception as e:
        report("Website", False, "check SITE_URL and NAS_TOKEN (%s)" % str(e)[:120])
    # R2
    try:
        r2 = R2Client(sync.E("R2_ACCOUNT_ID"), sync.E("R2_ACCESS_KEY_ID"), sync.E("R2_SECRET_ACCESS_KEY"),
                      sync.E("R2_BUCKET", default="tour-photos"))
        key = "inbox/_setup-check-%d.txt" % int(time.time())
        r2.put_bytes(key, b"setup check", "text/plain")
        good = r2.get_bytes(key) == b"setup check"
        r2.delete(key)
        report("R2", good, "bucket %s: write, read, delete" % r2.bucket)
    except Exception as e:
        report("R2", False, "check R2_ACCOUNT_ID, R2_BUCKET and the token keys; the token needs Object Read & "
                            "Write on this bucket (%s)" % str(e)[:120])
    # Watermark
    try:
        wm = Image.open(sync.WATERMARK)
        report("Watermark", wm.mode in ("RGBA", "LA", "P"), "%s %sx%s %s" % (
            sync.WATERMARK, wm.width, wm.height, "" if wm.mode in ("RGBA", "LA", "P") else
            "(no transparency: use a PNG with a transparent background)"))
    except Exception as e:
        report("Watermark", False, "put your PNG logo at WATERMARK_PATH (%s)" % str(e)[:120])
    # Secure office address (tls/): only with NAS_HOSTNAME
    try:
        tls = office_tls.check()
        if tls is None:
            report("Secure", True, "NAS_HOSTNAME not set: no secure office address (phones use mobile data)")
        else:
            report("Secure", tls["ping_ok"], "https://%s:%s/ping %s" % (
                office_tls.settings() + ("answers, certificate until %s" % tls.get("cert_expires", "?")
                                         if tls["ping_ok"] else tls.get("ping_error", ""),)))
    except Exception as e:
        report("Secure", False, str(e)[:120])
    # Time zone
    report("Time zone", True, "%s (now %s)" % (sync.TZ, sync.datetime.now(sync.TZ).strftime("%Y-%m-%d %H:%M %z")))
    print("\nAll good." if ok else "\nFix the PROBLEM lines, then run this check again.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
