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
MAX_PHOTO = int(float(E("UPLOAD_MAX_PHOTO_MB", "UPLOAD_MAX_MB", default="200")) * 1024 * 1024)
MAX_VIDEO = int(float(E("UPLOAD_MAX_VIDEO_MB", default="2048")) * 1024 * 1024)
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".3gp", ".3g2", ".mkv", ".webm", ".avi", ".mts", ".m2ts", ".mpg", ".mpeg",
             ".wmv", ".flv", ".hevc", ".h265", ".h264"}
# Every format is accepted (owner 2026-11-15); type is decided by extension first, the browser's MIME second
# (iOS/Android often send "" or application/octet-stream for HEIC/DNG).
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


def site_root():
    return (E("SITE_URL") or sync_site().split("/mtbg/")[0]).rstrip("/")


def sync_site():
    import sync
    return sync.SITE


def back_url(r):
    """Where "Back to the Staff App" / "Done" go: the Staff App page that opened us (?r=), only when it is under
    <SITE_URL>/staff/; otherwise <SITE_URL>/staff."""
    root = site_root()
    r = (r or "").strip()
    if r and r.startswith(root + "/staff/") and not any(c in r for c in "\r\n\"<>\\") and len(r) < 2000:
        return r
    return root + "/staff"


_route_missing = {"uploaded": False}


def report_uploaded(t, n):
    try:
        r = site.s.post(site_api() + "/tickets/%s/uploaded" % t, json={"count": n}, timeout=20)
        if r.status_code == 404 and "ticket" not in r.text.lower():
            if not _route_missing["uploaded"]:
                log.info("website has no /tickets/<t>/uploaded route yet: upload counts not sent")
            _route_missing["uploaded"] = True
        elif r.ok:
            _route_missing["uploaded"] = False
            log.info("reported %d uploaded files for ticket %s...", n, t[:6])
        else:
            log.warning("upload count report: %s %s", r.status_code, r.text[:200])
    except Exception as e:
        log.warning("upload count report failed: %s", e)


def site_api():
    import sync
    return sync.SITE


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
        info["back"] = back_url(parse_qs(u.query).get("r", [""])[0])
        page = PAGE.replace("__INFO__", json.dumps(info)).replace("__MAXPHOTO__", str(MAX_PHOTO)) \
            .replace("__MAXVIDEO__", str(MAX_VIDEO))
        return self.send(200, page, "text/html")

    def do_POST(self):
        """POST /upload/batch?t=..  {"count": n} after each finished batch -> the website adds n to the guide's
        upload count for this ticket (owner 2026-11-15: the guide's task completes from upload counts)."""
        u = urlparse(self.path)
        if u.path != "/upload/batch":
            return self.send(404, '{"ok":false}')
        t = parse_qs(u.query).get("t", [""])[0]
        if not ticket(t):
            return self.send(403, '{"ok":false,"error":"ticket"}')
        try:
            n = int(json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 1000)) or b"{}")
                    .get("count", 0))
        except (ValueError, TypeError):
            n = 0
        if n > 0:
            report_uploaded(t, n)
        return self.send(200, '{"ok":true}')

    def do_PUT(self):
        u = urlparse(self.path)
        if u.path != "/upload/file":
            return self.send(404, '{"ok":false}')
        tk = ticket(parse_qs(u.query).get("t", [""])[0])
        if not tk:
            return self.send(403, '{"ok":false,"error":"ticket"}')
        size = int(self.headers.get("Content-Length") or 0)
        name = os.path.basename(unquote(self.headers.get("X-File-Name") or "photo.jpg"))[:200] or "photo.jpg"
        ext = os.path.splitext(name)[1].lower()
        is_video = ext in VIDEO_EXT or (not ext and (self.headers.get("X-File-Type") or "").startswith("video/"))
        if not ext:  # keep a usable extension when the phone sent none
            name += ".mp4" if is_video else ".jpg"
        if size <= 0 or size > (MAX_VIDEO if is_video else MAX_PHOTO):
            return self.send(413, '{"ok":false,"error":"size"}')
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
:root{--bg:#f6f6f4;--fg:#1f1f1f;--muted:#6b6b6b;--card:#fff;--line:#e3e3df;--accent:#007bff;--ok:#007bff;--bad:#c62828;--tile:#e9e7e2}
@media (prefers-color-scheme:dark){:root{--bg:#161616;--fg:#eee;--muted:#9a9a9a;--card:#222;--line:#333;--tile:#2b2b2b}}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--fg)}
main{max-width:720px;margin:0 auto;padding:16px 16px 110px}
h1{font-size:20px;margin:0 0 4px}.sub{color:var(--muted);margin:0 0 16px}
button{font:inherit;cursor:pointer}
.back{display:block;margin:0 0 14px;padding:10px 14px;border-radius:10px;border:1px solid var(--line);background:var(--card);color:var(--fg);font-size:16px;font-weight:600}
.pick{display:block;width:100%;padding:22px;font-size:20px;font-weight:600;border:0;border-radius:14px;background:var(--accent);color:#fff;text-align:center;cursor:pointer}
/* review */
.bar{position:sticky;top:0;z-index:3;background:var(--bg);padding:10px 0;display:flex;flex-wrap:wrap;gap:8px;align-items:center;border-bottom:1px solid var(--line);margin-bottom:10px}
.bar .count{flex:1 1 100%;font-weight:700}
.chip{padding:8px 12px;border-radius:999px;border:1px solid var(--line);background:var(--card);color:var(--fg);font-size:14px}
#more{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}
@media (min-width:600px){.grid{grid-template-columns:repeat(4,1fr)}}
.tile{position:relative;aspect-ratio:1/1;background:var(--tile);border-radius:8px;overflow:hidden;outline:3px solid transparent;transition:opacity .15s}
.tile.on{outline-color:var(--accent)}
.tile:not(.on){opacity:.45}
.tile canvas{width:100%;height:100%;object-fit:cover;display:block}
.tile .ph{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:6px;font-size:11px;color:var(--muted);word-break:break-all}
.tile .ph b{font-size:22px;margin-bottom:4px}
.tile .cb{position:absolute;top:6px;left:6px;width:28px;height:28px;border-radius:50%;border:2px solid #fff;background:rgba(0,0,0,.35);display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:16px;box-shadow:0 1px 4px rgba(0,0,0,.4)}
.tile.on .cb{background:var(--accent)}
.tile .rm{position:absolute;top:6px;right:6px;width:28px;height:28px;border-radius:50%;border:0;background:rgba(0,0,0,.55);color:#fff;font-size:15px;line-height:28px;padding:0}
.tile .vid{position:absolute;bottom:6px;left:6px;background:rgba(0,0,0,.6);color:#fff;border-radius:6px;padding:2px 6px;font-size:12px;font-weight:600}
.tile .big{position:absolute;inset:auto 0 0 0;background:var(--bad);color:#fff;font-size:11px;text-align:center;padding:3px}
.go{position:fixed;left:0;right:0;bottom:0;z-index:4;padding:12px 16px calc(12px + env(safe-area-inset-bottom));background:linear-gradient(transparent,var(--bg) 30%)}
.go button{display:block;width:100%;max-width:720px;margin:0 auto;padding:18px;border:0;border-radius:14px;background:var(--accent);color:#fff;font-size:19px;font-weight:700}
.go button:disabled{opacity:.4}
/* lightbox */
.lb{position:fixed;inset:0;z-index:10;background:rgba(0,0,0,.92);display:flex;align-items:center;justify-content:center}
.lb img,.lb video{max-width:100%;max-height:100%}
.lb .x{position:absolute;top:12px;right:12px;width:44px;height:44px;border-radius:50%;border:0;background:rgba(255,255,255,.18);color:#fff;font-size:22px}
.lb .nm{position:absolute;left:12px;bottom:12px;right:70px;color:#ddd;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
/* progress */
.total{position:sticky;top:0;z-index:2;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin:6px 0 12px;box-shadow:0 2px 10px rgba(0,0,0,.08)}
.bigbar{height:18px;background:var(--line);border-radius:9px;overflow:hidden}.bigbar i{display:block;height:100%;width:0;background:var(--accent);transition:width .3s}
.pct{font-size:28px;font-weight:700;font-variant-numeric:tabular-nums}
.stats{display:flex;justify-content:space-between;gap:8px;margin-top:8px;font-size:14px;color:var(--muted);font-variant-numeric:tabular-nums;flex-wrap:wrap}
.head{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px}
.done-all .bigbar i{background:var(--ok)}.done-all .pct{color:var(--ok)}
ul{list-style:none;padding:0;margin:0}li{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:9px 12px;margin:0 0 8px}
.row{display:flex;justify-content:space-between;gap:8px;font-size:14px}.n{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.s{flex:none;color:var(--muted)}
li.done .s{color:var(--ok)}li.err .s{color:var(--bad)}.bar5{height:5px;background:var(--line);border-radius:3px;overflow:hidden;margin-top:6px}.bar5 i{display:block;height:100%;width:0;background:var(--accent)}
.btn2{margin-top:10px;width:100%;padding:12px;border-radius:10px;border:1px solid var(--line);background:var(--card);color:var(--fg);font-size:16px}
#again{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:700;padding:16px;font-size:18px}
.donebtn{margin-top:12px;width:100%;padding:16px;border-radius:12px;border:0;background:var(--ok);color:#fff;font-size:18px;font-weight:700}
[hidden]{display:none!important}
</style></head><body><main>
<button class="back" id="back"></button>
<h1 id="t"></h1><p class="sub" id="d"></p>
<input id="f" type="file" accept="image/*,image/heic,image/heif,image/avif,image/webp,image/tiff,image/x-adobe-dng,.heic,.heif,.avif,.dng,video/*,.mov,.mp4,.m4v,.hevc" multiple hidden>
<section id="vPick"><label class="pick" for="f" id="pickl"></label><p class="sub" id="hint" style="margin-top:10px"></p></section>
<section id="vReview" hidden>
 <div class="bar"><span class="count" id="count"></span>
  <button class="chip" id="all"></button><button class="chip" id="none"></button><label class="chip" for="f" id="more"></label></div>
 <div class="grid" id="grid"></div>
</section>
<section id="vProg" hidden>
 <div class="total" id="total"><div class="head"><span class="pct" id="pct">0%</span><span id="files"></span></div>
  <div class="bigbar"><i id="tot"></i></div><div class="stats"><span id="mb"></span><span id="eta"></span></div>
  <button class="btn2" id="retry" hidden></button><button class="btn2" id="again" hidden></button>
  <button class="donebtn" id="done" hidden></button></div>
 <ul id="list"></ul>
</section>
</main>
<div class="go" id="goBar" hidden><button id="go"></button></div>
<script>
const INFO=__INFO__, T=new URLSearchParams(location.search).get("t");
const MAXP=__MAXPHOTO__, MAXV=__MAXVIDEO__;
const es=(navigator.language||"").toLowerCase().startsWith("es");
const L=es?{day:"Día",by:"Guía",pick:"Elegir fotos y videos",hint:"Primero verás las fotos para elegir cuáles subir. Solo en el wifi de la oficina.",
 sel:"seleccionadas",all:"Todas",none:"Ninguna",more:"+ Agregar más",up:"Subir",big:"Muy grande",
 files:"archivos",of:"de",done:"Listo",dup:"Ya estaba",fail:"Error",wait:"En espera",retry:"Reintentar los fallidos",again:"+ Subir más",
 alldone:"¡Todo subido!",left:"quedan",min:"min",sec:"s",calc:"calculando…",leave:"La subida sigue en curso.",
 back:"‹ Volver a la app",stop:"Hay subidas en curso: ¿detenerlas y volver?",discard:"Hay archivos elegidos sin subir: ¿salir de todos modos?"}
:{day:"Day",by:"Guide",pick:"Choose photos & videos",hint:"You'll see the photos first and choose which to upload. Office wifi only.",
 sel:"selected",all:"Select all",none:"Select none",more:"+ Add more",up:"Upload",big:"Too large",
 files:"files",of:"of",done:"Done",dup:"Already there",fail:"Failed",wait:"Waiting",retry:"Retry failed",again:"+ Upload more",
 alldone:"All uploaded!",left:"left",min:"min",sec:"s",calc:"calculating…",leave:"Upload still in progress.",
 back:"‹ Back to the Staff App",stop:"Uploads still running: stop and go back?",discard:"Picked files are not uploaded yet: leave anyway?"};
const $=id=>document.getElementById(id);
$("t").textContent=INFO.tour;
$("d").textContent=INFO.date+" · "+L.day+" "+INFO.day+(INFO.guide?" · "+L.by+": "+INFO.guide:"");
$("back").textContent=L.back;$("pickl").textContent=L.pick;$("hint").textContent=L.hint;$("all").textContent=L.all;$("none").textContent=L.none;
$("more").textContent=L.more;$("retry").textContent=L.retry;$("again").textContent=L.again;$("done").textContent=L.done;
const mb=b=>(b/1048576).toFixed(b<10485760?1:0);
const VEXT=/\.(mp4|mov|m4v|3gp|3g2|mkv|webm|avi|mts|m2ts|mpg|mpeg|wmv|flv|hevc|h265|h264)$/i;
const isVid=f=>VEXT.test(f.name)||(!/\.[a-z0-9]{2,5}$/i.test(f.name)&&(f.type||"").startsWith("video/"));
const ftype=f=>{const m=/\.([a-z0-9]{2,5})$/i.exec(f.name);return m?m[1].toUpperCase():(f.type||"file");};
const tooBig=f=>f.size>(isVid(f)?MAXV:MAXP);
const fmtDur=t=>{t=Math.max(0,Math.round(t||0));return (t/60|0)+":"+String(t%60).padStart(2,"0");};
let picked=[], items=[], running=0, t0=0, sent0=0, leaving=false, xhrs=new Set(), seq=0, batchOk=0; const MAX=2;
function reportBatch(){ if(batchOk<1) return; const n=batchOk; batchOk=0;
 fetch("/upload/batch?t="+encodeURIComponent(T),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({count:n}),keepalive:true}).catch(()=>{}); }
function show(v){["vPick","vReview","vProg"].forEach(x=>$(x).hidden=x!==v);$("goBar").hidden=v!=="vReview";}

/* ---------------- review grid ---------------- */
const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){io.unobserve(e.target);thumb(e.target.__p);}}),{rootMargin:"300px"});
function addFiles(list){
 for(const f of list){const p={id:++seq,f,sel:!tooBig(f)};picked.push(p);$("grid").appendChild(tile(p));}
 show("vReview");count();
}
function tile(p){
 const el=document.createElement("div");el.className="tile"+(p.sel?" on":"");el.__p=p;p.el=el;
 el.innerHTML='<div class="ph"><b>'+(isVid(p.f)?"🎬":"🖼")+'</b><span></span></div><span class="cb">✓</span><button class="rm" aria-label="remove">✕</button>';
 el.querySelector(".ph span").textContent=p.f.name+" · "+ftype(p.f)+" · "+mb(p.f.size)+" MB";
 if(tooBig(p.f)){const b=document.createElement("div");b.className="big";b.textContent=L.big;el.appendChild(b);}
 el.querySelector(".cb").onclick=e=>{e.stopPropagation();toggle(p);};
 el.querySelector(".rm").onclick=e=>{e.stopPropagation();remove(p);};
 el.onclick=()=>lightbox(p);
 io.observe(el);return el;
}
function toggle(p){if(tooBig(p.f))return;p.sel=!p.sel;p.el.classList.toggle("on",p.sel);count();}
function remove(p){io.unobserve(p.el);p.el.remove();picked=picked.filter(x=>x!==p);count();if(!picked.length)show(items.length?"vProg":"vPick");}
function count(){const s=picked.filter(p=>p.sel);const bytes=s.reduce((a,p)=>a+p.f.size,0);
 $("count").textContent=s.length+" "+L.sel+" · "+mb(bytes)+" MB";$("go").textContent=L.up+" "+s.length;$("go").disabled=!s.length;}
$("all").onclick=()=>{picked.forEach(p=>{if(!tooBig(p.f)){p.sel=true;p.el.classList.add("on");}});count();};
$("none").onclick=()=>{picked.forEach(p=>{p.sel=false;p.el.classList.remove("on");});count();};
function canvasFrom(src,w,h){const k=Math.min(1,300/Math.max(w,h)),c=document.createElement("canvas");
 c.width=Math.max(1,w*k|0);c.height=Math.max(1,h*k|0);c.getContext("2d").drawImage(src,0,0,c.width,c.height);return c;}
function putThumb(p,c){const ph=p.el.querySelector(".ph");if(ph)ph.remove();p.el.prepend(c);}
function thumb(p){
 const url=URL.createObjectURL(p.f);
 if(isVid(p.f)){
  const v=document.createElement("video");v.muted=true;v.playsInline=true;v.preload="metadata";v.src=url;
  const fail=()=>{URL.revokeObjectURL(url);};
  v.onloadedmetadata=()=>{const b=document.createElement("span");b.className="vid";b.textContent="▶ "+fmtDur(v.duration);p.el.appendChild(b);
   try{v.currentTime=Math.min(0.5,(v.duration||1)/2);}catch(e){fail();}};
  v.onseeked=()=>{try{putThumb(p,canvasFrom(v,v.videoWidth,v.videoHeight));}catch(e){}v.removeAttribute("src");v.load();URL.revokeObjectURL(url);};
  v.onerror=fail;
 }else{
  const img=new Image();img.onload=()=>{try{putThumb(p,canvasFrom(img,img.naturalWidth,img.naturalHeight));}catch(e){}URL.revokeObjectURL(url);};
  img.onerror=()=>URL.revokeObjectURL(url);  /* HEIC etc.: keep the neutral tile with name + size */
  img.src=url;
 }
}
function lightbox(p){
 const url=URL.createObjectURL(p.f),lb=document.createElement("div");lb.className="lb";
 const m=isVid(p.f)?Object.assign(document.createElement("video"),{src:url,controls:true,playsInline:true,autoplay:true}):Object.assign(document.createElement("img"),{src:url});
 m.onerror=()=>{m.replaceWith(Object.assign(document.createElement("div"),{textContent:p.f.name+" · "+ftype(p.f)+" · "+mb(p.f.size)+" MB",style:"color:#ddd;padding:20px;text-align:center"}));};
 const x=Object.assign(document.createElement("button"),{className:"x",textContent:"✕"}),nm=Object.assign(document.createElement("div"),{className:"nm",textContent:p.f.name});
 const close=()=>{if(m.pause)m.pause();lb.remove();URL.revokeObjectURL(url);};
 x.onclick=close;lb.onclick=e=>{if(e.target===lb)close();};lb.append(m,x,nm);document.body.appendChild(lb);
}

/* ---------------- upload + progress ---------------- */
$("go").onclick=()=>{const s=picked.filter(p=>p.sel);if(!s.length)return;
 picked.forEach(p=>io.unobserve(p.el));picked=[];$("grid").innerHTML="";
 show("vProg");if(!running){t0=Date.now();sent0=items.reduce((a,i)=>a+(fin(i)?i.f.size:0),0);}
 for(const p of s){const li=document.createElement("li");li.innerHTML='<div class="row"><span class="n"></span><span class="s"></span></div><div class="bar5"><i></i></div>';
  li.querySelector(".n").textContent=(isVid(p.f)?"🎬 ":"")+p.f.name+" · "+mb(p.f.size)+" MB";
  const it={f:p.f,li,st:"wait",sent:0};items.push(it);$("list").appendChild(li);label(it);}
 pump();};
const fin=i=>i.st=="done"||i.st=="dup";
function busy(){return running>0||items.some(i=>i.st=="wait");}
function eta(sec){if(!isFinite(sec)||sec<0)return L.calc;sec=Math.round(sec);return (sec>=60?Math.floor(sec/60)+" "+L.min+" ":"")+(sec%60)+" "+L.sec+" "+L.left;}
function render(){const ok=items.filter(fin).length,bad=items.filter(i=>i.st=="err").length;
 const bytes=items.reduce((a,i)=>a+i.f.size,0)||1,sent=items.reduce((a,i)=>a+(fin(i)?i.f.size:i.sent||0),0),p=Math.min(100,Math.floor(100*sent/bytes));
 $("tot").style.width=p+"%";const all=ok==items.length&&items.length>0;$("pct").textContent=(all?L.alldone+" ":"")+p+"%";
 $("files").textContent=ok+" "+L.of+" "+items.length+" "+L.files+(bad?" · "+L.fail+": "+bad:"");$("mb").textContent=mb(sent)+" "+L.of+" "+mb(bytes)+" MB";
 const el=(Date.now()-t0)/1000,rate=(sent-sent0)/Math.max(el,0.5);$("eta").textContent=running?(el>3&&rate>0?eta((bytes-sent)/rate):L.calc):"";
 $("total").classList.toggle("done-all",all);$("retry").hidden=!(bad&&!running);$("again").hidden=busy();$("done").hidden=!(items.length&&!busy());}
function label(it){it.li.className=fin(it)?"done":it.st=="err"?"err":"";
 it.li.querySelector(".s").textContent={wait:L.wait,up:Math.round(100*it.sent/(it.f.size||1))+"%",done:L.done,dup:L.dup,err:L.fail}[it.st];
 it.li.querySelector("i").style.width=(fin(it)?100:100*it.sent/(it.f.size||1))+"%";}
function pump(){while(running<MAX){const it=items.find(i=>i.st=="wait");if(!it)break;send(it);}render();}
function send(it){running++;it.st="up";it.sent=0;label(it);const x=new XMLHttpRequest();
 x.open("PUT","/upload/file?t="+encodeURIComponent(T));x.setRequestHeader("X-File-Name",encodeURIComponent(it.f.name));
 x.setRequestHeader("X-File-Type",it.f.type||"");x.setRequestHeader("X-Last-Modified",String(it.f.lastModified||0));
 x.upload.onprogress=e=>{it.sent=e.loaded;label(it);render();};
 x.onload=()=>{let r={};try{r=JSON.parse(x.responseText)}catch(e){}it.st=x.status==200&&r.ok?(r.status=="duplicate"?"dup":"done"):"err";if(fin(it))batchOk++;end(it);};
 x.onerror=x.onabort=()=>{it.st="err";end(it);};xhrs.add(x);x.onloadend=()=>xhrs.delete(x);x.send(it.f);}
function end(it){running--;label(it);pump();if(!busy())reportBatch();}
$("retry").onclick=()=>{t0=Date.now();sent0=items.reduce((a,i)=>a+(fin(i)?i.f.size:0),0);items.filter(i=>i.st=="err").forEach(i=>{i.st="wait";label(i)});pump();};
$("again").onclick=()=>$("f").click();
setInterval(()=>{if(running)render();},1000);

/* ---------------- picking + leaving ---------------- */
$("f").onchange=e=>{if(e.target.files.length)addFiles(e.target.files);e.target.value="";};
function goBack(){
 if(busy()){if(!confirm(L.stop))return;items.forEach(i=>{if(i.st=="wait")i.st="err";});xhrs.forEach(x=>{try{x.abort()}catch(e){}});}
 else if(picked.some(p=>p.sel)&&!confirm(L.discard))return;
 reportBatch();leaving=true;try{window.close();}catch(e){}setTimeout(()=>{if(!window.closed)location.href=INFO.back;},300);
}
$("back").onclick=goBack;$("done").onclick=goBack;
window.addEventListener("beforeunload",e=>{if(!leaving&&(busy()||picked.some(p=>p.sel))){e.preventDefault();e.returnValue=L.leave;return L.leave;}});
show("vPick");
</script></body></html>"""


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log.info("upload page on :%d", PORT)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
