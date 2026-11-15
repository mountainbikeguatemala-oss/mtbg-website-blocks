"""Office upload page (NAS, LAN only): guides upload a departure day's photos from their phone.

The Staff App opens  http://<nas>:8090/upload?t=<ticket>  (ticket = one departure day, valid 12 h).
  GET  /upload?t=..        -> checks the ticket with the website, serves the page (EN/ES)
  PUT  /upload/file?t=..   -> body = the file; headers X-File-Name (URI-encoded), X-Last-Modified (ms)
                              -> Immich (Tours account) + the day's album; description "Uploaded by <guide>"
The browser sends one file per request (2 at a time) so each file has its own progress bar and a failed file can
be retried alone. Capture time: EXIF from the file (Immich reads it too); fileCreatedAt falls back to the phone's
last-modified time.
"""
import json
import logging
import os
import tempfile
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from sync import Immich, Site, day_album, import_photo, E

try:  # EXIF from HEIC (iPhone) files
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:
    pass

log = logging.getLogger("tour-photos-upload")
PORT = int(E("LISTEN_PORT", "UPLOAD_PORT", default="8090"))  # inside the container; compose maps UPLOAD_PORT
MAX_BYTES = int(E("UPLOAD_MAX_MB", default="300")) * 1024 * 1024
TMP = E("UPLOAD_TMP", default="/work/upload-tmp")

im = Immich(E("IMMICH_API_KEY", default=""))
site = Site(E("NAS_TOKEN", "WEBSITE_TOKEN", default=""))
_tickets, _lock = {}, threading.Lock()


def ticket(t):
    """Verified ticket (cached until it expires) or None."""
    if not t or len(t) > 200:
        return None
    now = time.time()
    with _lock:
        hit = _tickets.get(t)
        if hit and hit["_exp"] > now:
            return hit
    try:
        data = site.req("GET", "/tickets/%s" % t)
    except RuntimeError:
        return None
    exp = data.get("expires")
    try:
        data["_exp"] = datetime.fromisoformat(exp).timestamp() if exp else now + 3600
    except ValueError:
        data["_exp"] = now + 3600
    with _lock:
        _tickets[t] = data
    return data


def to_immich(path, filename, last_modified_ms, tk):
    modified = datetime.fromtimestamp(last_modified_ms / 1000, timezone.utc) if last_modified_ms else None
    with _lock:  # one album lookup/create at a time (two files arrive together)
        aid = day_album(im, site, tk["departure_id"], tk["day"],
                        "%s · %s · Day %s" % (tk.get("date"), tk.get("tour"), tk.get("day")))
    return import_photo(im, path, filename, aid, tk.get("guide"), modified=modified)


class Handler(BaseHTTPRequestHandler):
    server_version = "tour-photos"

    def log_message(self, fmt, *args):
        log.info("%s %s", self.address_string(), fmt % args)

    def send(self, code, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/health":
            return self.send(200, '{"ok":true}')
        if u.path != "/upload":
            return self.send(404, PAGE_ERROR, "text/html")
        tk = ticket(parse_qs(u.query).get("t", [""])[0])
        if not tk:
            return self.send(403, PAGE_ERROR, "text/html")
        info = {k: tk.get(k) for k in ("tour", "date", "day")}
        info["guide"] = (tk.get("guide") or {}).get("name") or ""
        return self.send(200, PAGE.replace("__INFO__", json.dumps(info)), "text/html")

    def do_PUT(self):
        u = urlparse(self.path)
        if u.path != "/upload/file":
            return self.send(404, '{"ok":false}')
        tk = ticket(parse_qs(u.query).get("t", [""])[0])
        if not tk:
            return self.send(403, '{"ok":false,"error":"ticket"}')
        size = int(self.headers.get("Content-Length") or 0)
        if size <= 0 or size > MAX_BYTES:
            return self.send(413, '{"ok":false,"error":"size"}')
        name = os.path.basename(unquote(self.headers.get("X-File-Name") or "photo.jpg"))[:200] or "photo.jpg"
        try:
            lm = int(self.headers.get("X-Last-Modified") or 0)
        except ValueError:
            lm = 0
        os.makedirs(TMP, exist_ok=True)
        fd, path = tempfile.mkstemp(dir=TMP, suffix=os.path.splitext(name)[1])
        try:
            with os.fdopen(fd, "wb") as f:
                left = size
                while left:
                    chunk = self.rfile.read(min(left, 1 << 20))
                    if not chunk:
                        raise IOError("connection closed")
                    f.write(chunk)
                    left -= len(chunk)
            status = to_immich(path, name, lm, tk)
            return self.send(200, json.dumps({"ok": True, "status": status}))
        except Exception as e:
            log.error("upload %s failed: %s", name, e)
            return self.send(500, json.dumps({"ok": False, "error": str(e)[:200]}))
        finally:
            try:
                os.remove(path)
            except OSError:
                pass


PAGE_ERROR = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,
initial-scale=1"><title>Tour photos</title><style>body{font-family:system-ui,sans-serif;margin:0;padding:32px 16px;
background:#f6f6f4;color:#222;text-align:center}</style></head><body><h2>Link expired / Enlace vencido</h2>
<p>Open "Upload photos" again in the Staff App.<br>Vuelve a abrir "Subir fotos" en la Staff App.</p>
<p style="color:#777">Only works on the office wifi. / Solo funciona en el wifi de la oficina.</p></body></html>"""

PAGE = r"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tour photos</title>
<style>
:root{--bg:#f6f6f4;--fg:#1f1f1f;--muted:#6b6b6b;--card:#fff;--line:#e3e3df;--accent:#d35400;--ok:#2e7d32;--bad:#c62828}
@media (prefers-color-scheme:dark){:root{--bg:#161616;--fg:#eee;--muted:#9a9a9a;--card:#222;--line:#333}}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--fg)}
main{max-width:560px;margin:0 auto;padding:20px 16px 40px}
h1{font-size:20px;margin:0 0 4px}.sub{color:var(--muted);margin:0 0 20px}
.pick{display:block;width:100%;padding:22px;font-size:20px;font-weight:600;border:0;border-radius:14px;
background:var(--accent);color:#fff;text-align:center;cursor:pointer}
.sum{margin:18px 0 10px;font-weight:600}.bar{height:6px;background:var(--line);border-radius:3px;overflow:hidden}
.bar i{display:block;height:100%;width:0;background:var(--accent);transition:width .2s}
ul{list-style:none;padding:0;margin:14px 0 0}li{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:10px 12px;margin:0 0 8px}.row{display:flex;justify-content:space-between;gap:8px;font-size:14px}
.n{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.s{flex:none;color:var(--muted)}
.done .s{color:var(--ok)}.err .s{color:var(--bad)}li .bar{margin-top:6px}
button.retry{margin-top:12px;width:100%;padding:12px;border-radius:10px;border:1px solid var(--line);
background:var(--card);color:var(--fg);font-size:16px}
</style></head><body><main>
<h1 id="t"></h1><p class="sub" id="d"></p>
<label class="pick"><span id="pickl"></span><input id="f" type="file" accept="image/*" multiple hidden></label>
<p class="sub" id="hint" style="margin-top:10px"></p>
<div id="prog" hidden><div class="sum" id="sum"></div><div class="bar"><i id="tot"></i></div>
<button class="retry" id="retry" hidden></button><ul id="list"></ul></div>
</main><script>
const INFO=__INFO__, T=new URLSearchParams(location.search).get("t");
const es=(navigator.language||"").toLowerCase().startsWith("es");
const L=es?{day:"Día",by:"Guía",pick:"Elegir fotos",hint:"Mantén esta página abierta hasta que termine. Solo en el wifi de la oficina.",
 up:"Subiendo",of:"de",done:"Listo",dup:"Ya estaba",fail:"Error",wait:"En espera",retry:"Reintentar las fallidas",all:"¡Todas las fotos subidas!"}
:{day:"Day",by:"Guide",pick:"Choose photos",hint:"Keep this page open until it finishes. Office wifi only.",
 up:"Uploading",of:"of",done:"Done",dup:"Already there",fail:"Failed",wait:"Waiting",retry:"Retry failed",all:"All photos uploaded!"};
document.getElementById("t").textContent=INFO.tour;
document.getElementById("d").textContent=INFO.date+" · "+L.day+" "+INFO.day+(INFO.guide?" · "+L.by+": "+INFO.guide:"");
document.getElementById("pickl").textContent=L.pick;document.getElementById("hint").textContent=L.hint;
document.getElementById("retry").textContent=L.retry;
let items=[],running=0;const MAX=2;
function render(){const ok=items.filter(i=>i.st=="done"||i.st=="dup").length,bad=items.filter(i=>i.st=="err").length;
 const bytes=items.reduce((a,i)=>a+i.f.size,0)||1,sent=items.reduce((a,i)=>a+(i.st=="done"||i.st=="dup"?i.f.size:i.sent||0),0);
 document.getElementById("tot").style.width=(100*sent/bytes)+"%";
 document.getElementById("sum").textContent=ok==items.length?L.all:L.up+" "+ok+" "+L.of+" "+items.length+(bad?" · "+L.fail+": "+bad:"");
 document.getElementById("retry").hidden=!(bad&&!running);}
function add(files){document.getElementById("prog").hidden=false;const ul=document.getElementById("list");
 for(const f of files){const li=document.createElement("li");li.innerHTML='<div class="row"><span class="n"></span><span class="s"></span></div><div class="bar"><i></i></div>';
  li.querySelector(".n").textContent=f.name;const it={f,li,st:"wait",sent:0};items.push(it);ul.appendChild(li);label(it);}
 pump();}
function label(it){it.li.className=it.st=="done"||it.st=="dup"?"done":it.st=="err"?"err":"";
 it.li.querySelector(".s").textContent={wait:L.wait,up:Math.round(100*it.sent/(it.f.size||1))+"%",done:L.done,dup:L.dup,err:L.fail}[it.st];
 it.li.querySelector("i").style.width=(it.st=="done"||it.st=="dup"?100:100*it.sent/(it.f.size||1))+"%";}
function pump(){while(running<MAX){const it=items.find(i=>i.st=="wait");if(!it)break;send(it);}render();}
function send(it){running++;it.st="up";it.sent=0;label(it);const x=new XMLHttpRequest();
 x.open("PUT","/upload/file?t="+encodeURIComponent(T));x.setRequestHeader("X-File-Name",encodeURIComponent(it.f.name));
 x.setRequestHeader("X-Last-Modified",String(it.f.lastModified||0));
 x.upload.onprogress=e=>{it.sent=e.loaded;label(it);render();};
 x.onload=()=>{let r={};try{r=JSON.parse(x.responseText)}catch(e){}it.st=x.status==200&&r.ok?(r.status=="duplicate"?"dup":"done"):"err";fin(it);};
 x.onerror=()=>{it.st="err";fin(it);};x.send(it.f);}
function fin(it){running--;label(it);pump();}
document.getElementById("f").onchange=e=>{add(e.target.files);e.target.value="";};
document.getElementById("retry").onclick=()=>{items.filter(i=>i.st=="err").forEach(i=>{i.st="wait";label(i)});pump();};
window.addEventListener("beforeunload",e=>{if(running){e.preventDefault();e.returnValue="";}});
</script></body></html>"""


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log.info("upload page on :%d", PORT)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
