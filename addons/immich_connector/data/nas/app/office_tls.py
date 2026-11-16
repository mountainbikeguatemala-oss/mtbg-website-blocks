"""The secure office address check (the https front in tls/): does https://NAS_HOSTNAME:NAS_HTTPS_PORT/ping answer
here, on the office network, as it would for a phone? And until when is its certificate good?

Only when NAS_HOSTNAME is set (config.env). A background thread checks every 15 minutes (never blocking the sync);
the latest result rides along, as the ``X-Office-Tls`` header (JSON), on every call this service makes to the website,
which keeps the new ones (by ``checked_at``) and warns its staff when the address stops working:

    {"ping_ok": true, "cert_expires": "2027-02-14", "checked_at": "2026-11-16T15:00:00+00:00"}
    {"ping_ok": false, "ping_error": "...", "cert_expires": "2027-02-14", "checked_at": "..."}

The name is resolved as a phone would (the office network's DNS); when that fails, or the https front doesn't answer
at the address it resolves to, the check also connects to the photo server's own office address (NAS_LAN_IP, else the
host of IMMICH_URL, else the Docker host) with the same name (SNI): the error then says which part is broken.
"""
import ipaddress
import json
import logging
import os
import socket
import ssl
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

log = logging.getLogger("tour-photos")

EVERY = 15 * 60  # seconds between checks
TIMEOUT = 8      # seconds for each connection

_latest = None
_lock = threading.Lock()
_thread = None


def _env(name, default=""):
    return (os.environ.get(name) or "").strip().strip('"').strip("'").strip() or default


def settings():
    """(hostname, port): ('', 443) when NAS_HOSTNAME is not set."""
    try:
        port = int(_env("NAS_HTTPS_PORT", "443"))
    except ValueError:
        port = 443
    return _env("NAS_HOSTNAME").lower().rstrip("."), port


def _ipv4(value):
    try:
        return str(ipaddress.IPv4Address((value or "").strip()))
    except ValueError:
        return ""


def _gateway():
    """The Docker host as seen from this container (the default route), '' when unknown."""
    try:
        with open("/proc/net/route") as f:
            for line in f.readlines()[1:]:
                parts = line.split()
                if len(parts) > 2 and parts[1] == "00000000":
                    return socket.inet_ntoa(bytes.fromhex(parts[2])[::-1])
    except (OSError, ValueError):
        pass
    return ""


def lan_addresses():
    """The photo server's own addresses to try with the name (SNI), in order, without repeats."""
    seen = []
    for ip in (_ipv4(_env("NAS_LAN_IP")), _ipv4(urlsplit(_env("IMMICH_URL")).hostname or ""), _gateway()):
        if ip and ip not in seen:
            seen.append(ip)
    return seen


def _context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001 - the system's CA certificates then
        return ssl.create_default_context()


def _reason(error):
    if isinstance(error, ssl.SSLCertVerificationError):
        return "certificate: %s" % (error.verify_message or error.reason or error)
    if isinstance(error, socket.timeout):
        return "no answer within %ss" % TIMEOUT
    if isinstance(error, ConnectionRefusedError):
        return "connection refused (is tour-photos-tls running?)"
    return str(error)[:200] or error.__class__.__name__


def probe(host, port, address=None):
    """GET https://host:port/ping, connecting to ``address`` (default: the name) with the name for SNI and the
    certificate check. (ok, error, cert_expires 'YYYY-MM-DD' or None)."""
    expires = None
    try:
        with socket.create_connection((address or host, port), timeout=TIMEOUT) as raw:
            with _context().wrap_socket(raw, server_hostname=host) as tls:
                cert = tls.getpeercert() or {}
                if cert.get("notAfter"):
                    expires = datetime.fromtimestamp(ssl.cert_time_to_seconds(cert["notAfter"]),
                                                     timezone.utc).date().isoformat()
                name = host if port == 443 else "%s:%d" % (host, port)
                tls.sendall(("GET /ping HTTP/1.1\r\nHost: %s\r\nUser-Agent: tour-photos-check\r\n"
                             "Connection: close\r\n\r\n" % name).encode())
                answer = b""
                while len(answer) < 4096:
                    chunk = tls.recv(4096)
                    if not chunk:
                        break
                    answer += chunk
    except (OSError, ssl.SSLError) as error:
        return False, _reason(error), expires
    status = answer.split(b"\r\n", 1)[0].decode("latin-1", "replace")
    parts = status.split()
    if len(parts) < 2 or not parts[1].startswith("2"):
        return False, "/ping answered %s" % (status[:80] or "nothing"), expires
    return True, None, expires


def check():
    """One check now: the report (dict), None when NAS_HOSTNAME is not set."""
    host, port = settings()
    if not host:
        return None
    report = {"checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}
    resolved, error = [], None
    try:
        resolved = sorted({info[4][0] for info in socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)})
    except socket.gaierror as e:
        error = "the name %s does not resolve on the office network (the router's DNS rebind protection, or the " \
                "DNS record?): %s" % (host, e.strerror or e)
    ok, expires = False, None
    if resolved:
        ok, error, expires = probe(host, port)
        if not ok:
            error = "%s at %s: %s" % (host, ", ".join(resolved), error)
    if not ok:
        error = error or "the name %s does not resolve on the office network" % host
        for address in lan_addresses():
            if address in resolved:
                continue
            direct_ok, direct_error, direct_expires = probe(host, port, address)
            expires = expires or direct_expires
            if direct_ok:
                error += "; the https front answers at the photo server's own address %s" % address
                break
            error += "; at %s: %s" % (address, direct_error)
    report["ping_ok"] = ok
    if not ok:
        report["ping_error"] = error[:500]
    if expires:
        report["cert_expires"] = expires
    return report


def latest():
    with _lock:
        return dict(_latest) if _latest else None


def header():
    """The latest report as the X-Office-Tls header value, '' before the first check."""
    report = latest()
    return json.dumps(report, separators=(",", ":")) if report else ""


def _loop():
    global _latest
    while True:
        try:
            report = check()
            with _lock:
                _latest = report
            if report and not report["ping_ok"]:
                log.warning("secure office address: %s", report.get("ping_error"))
        except Exception as e:  # noqa: BLE001 - never stops the service
            log.warning("secure office address check failed: %s", e)
        time.sleep(EVERY)


def start():
    """The background check (once per process), only when NAS_HOSTNAME is set."""
    global _thread
    if _thread is None and settings()[0]:
        _thread = threading.Thread(target=_loop, name="office-tls", daemon=True)
        _thread.start()
    return _thread
