# Истински телефон/симулатор без WebDriver: локален обратен прокси вкарва малък агент в страниците,
# браузърът на устройството се отваря с простата му команда, а Python го управлява през /__qa/*.
#   python remote.py <base-url> ios|android <out> [--pages a.html,b.html]
import sys, os, json, time, subprocess, threading, argparse, pathlib, queue, urllib.request, urllib.error, re
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
HERE = pathlib.Path(__file__).resolve().parent
CHECKS = (HERE.parent / "checks/checks.js").read_text(encoding="utf-8")
ap = argparse.ArgumentParser(); ap.add_argument("base"); ap.add_argument("plat"); ap.add_argument("out"); ap.add_argument("--pages", default=""); ap.add_argument("--port", type=int, default=8123)
ap.add_argument("--shots", default="index.html"); ap.add_argument("--wait", type=float, default=1.4)
a = ap.parse_args(); base = a.base.rstrip("/"); out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
AGENT = CHECKS + r"""
;(function(){var id=Math.random().toString(36).slice(2);
 function loop(){fetch('/__qa/cmd?id='+id).then(function(r){return r.json()}).then(function(c){if(c&&c.stop)throw 'stop';if(c&&c.js!=null){var res,err=null;try{res=(0,eval)(c.js)}catch(e){err=String(e)}
   return fetch('/__qa/res',{method:'POST',body:JSON.stringify({n:c.n,res:res===undefined?null:res,err:err})})}}).then(loop,function(e){if(e!=='stop')setTimeout(loop,500)})}
 window.addEventListener('error',function(e){fetch('/__qa/log',{method:'POST',body:'js: '+e.message})});
 fetch('/__qa/hello?id='+id,{method:'POST',body:location.pathname}).then(loop)})();
"""
current = [""]; cmds = queue.Queue(); results = {}; hello = threading.Event(); logs = []; counter = [0]
class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *x): pass
    def _send(self, code, body, ctype="application/json", extra=None):
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body))); self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0); raw = self.rfile.read(n).decode("utf-8", "ignore")
        if self.path.startswith("/__qa/hello"): current[0] = self.path.split("id=")[-1]; hello.set()
        elif self.path == "/__qa/res": d = json.loads(raw); results[d["n"]] = d
        elif self.path == "/__qa/log": logs.append(raw[:200])
        self._send(200, b"{}")
    def do_GET(self):
        if self.path.startswith("/__qa/cmd"):
            me = self.path.split("id=")[-1]; t0 = time.time(); c = {}
            while time.time() - t0 < 20:                    # кратки цикли: заявка на стара страница не бива да глътне команда
                if me != current[0]: return self._send(200, b'{"stop":1}')
                try: c = cmds.get(timeout=0.2); break
                except queue.Empty: pass
            return self._send(200, json.dumps(c).encode())
        url = base + self.path
        try:
            req = urllib.request.Request(url, headers={"User-Agent": self.headers.get("User-Agent", "site-qa"), "Accept-Encoding": "identity"})
            with urllib.request.urlopen(req, timeout=40) as r: body = r.read(); ct = r.headers.get("Content-Type", "application/octet-stream"); code = r.status
        except urllib.error.HTTPError as e:
            logs.append(f"http {e.code}: {self.path}"); return self._send(e.code, b"")
        if "text/html" in ct:
            s = body.decode("utf-8", "ignore"); tag = "<script>" + AGENT.replace("</script", "<\\/script") + "</script>"
            s = s.replace("</body>", tag + "</body>") if "</body>" in s else s + tag
            body = s.encode("utf-8")
        self._send(code, body, ct)
threading.Thread(target=ThreadingHTTPServer(("0.0.0.0", a.port), H).serve_forever, daemon=True).start()
def ev(js, timeout=30):
    counter[0] += 1; n = counter[0]; cmds.put({"n": n, "js": js}); t = time.time()
    while n not in results:
        if time.time() - t > timeout: raise TimeoutError(js[:60])
        time.sleep(0.03)
    r = results.pop(n)
    if r.get("err"): raise RuntimeError(r["err"])
    return r["res"]
def sh(c, **k): return subprocess.run(c, shell=True, text=True, capture_output=True, **k)
HOST = "127.0.0.1" if a.plat == "ios" else "10.0.2.2"
opened = [False]
def open_url(u):
    hello.clear()
    if opened[0]:                                     # същият раздел: иначе телефонът трупа раздели
        counter[0] += 1; cmds.put({"n": counter[0], "js": f"location.href={json.dumps(u)};1"})
        if hello.wait(45): return
        print("в същия раздел не стана, нов раздел", flush=True); hello.clear()
    opened[0] = True
    if a.plat == "ios": print(sh(f'xcrun simctl openurl booted "{u}"').stderr[:200])
    else: print(sh(f'adb shell am start -a android.intent.action.VIEW -d "{u}" -n com.android.chrome/com.google.android.apps.chrome.Main').stdout[:120])
    if not hello.wait(180): opened[0] = False; raise TimeoutError("страницата не отговори: " + u)
def shot(name):
    p = out / name
    if a.plat == "ios": sh(f'xcrun simctl io booted screenshot "{p}"')
    else:
        with open(p, "wb") as f: subprocess.run("adb exec-out screencap -p", shell=True, stdout=f)
def swipe(dy):  # само Android: истински жест на пръста
    sh(f"adb shell input swipe 500 {1500 if dy>0 else 900} 500 {1500-dy if dy>0 else 900-dy} 260")
def pages():
    if a.pages: return a.pages.split(",")
    html = urllib.request.urlopen(urllib.request.Request(base + "/index.html", headers={"User-Agent": "site-qa"})).read().decode("utf-8", "ignore")
    f = sorted(set(re.findall(r'href="([a-z0-9\-]+\.html)"', html)))
    return ["index.html"] + [p for p in f if p != "index.html"]
report = []
ps = pages(); print(len(ps), "страници")
for pg in ps:
    try:
        open_url(f"http://{HOST}:{a.port}/{pg}")
        time.sleep(5 if pg == ps[0] else 3)
        facts = ev("JSON.stringify(__siteQAFacts())", 60); facts = json.loads(facts)
        if pg == ps[0]: print(a.plat, facts, flush=True)
        y = 0; i = 0; h = facts["h"]; seen = set(); shoot = pg in a.shots.split(",")
        while True:
            ev(f"window.scrollTo(0,{y});1"); time.sleep(a.wait)
            for f in json.loads(ev("JSON.stringify(__siteQA())", 40)):
                k = (f["kind"], f.get("at"), f.get("text"))
                if k in seen: continue
                seen.add(k); f.update(page=pg, view=a.plat, y=y); report.append(f)
            if shoot: shot(f"{pg[:-5]}_{a.plat}_{i:03d}.png")
            H = ev("document.documentElement.scrollHeight")
            if y >= H - h: break
            y = min(y + int(h * 0.72), H - h); i += 1
            if i > 160: break
    except Exception as e:
        report.append({"page": pg, "view": a.plat, "kind": "load-failed", "text": str(e)[:200]}); print("!!", pg, e, flush=True)
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
# зъбното колело с истински пръст (Android)
if a.plat == "android":
    res = []
    def check(n, c, i=""): res.append([n, bool(c), i]); print("ДА " if c else "НЕ ", n, i, flush=True)
    try:
        open_url(f"http://{HOST}:{a.port}/index.html"); time.sleep(6)
        info = json.loads(ev("(function(){var w=document.querySelector('[data-walk]'),s=w.querySelector('.walk__stage');var t=w.getBoundingClientRect().top+scrollY;return JSON.stringify({top:t,end:t+w.offsetHeight-s.offsetHeight,n:w.querySelectorAll('.walk__frame').length,frames:w.classList.contains('has-frames')})})()"))
        print(info); stop = lambda i: info["top"] + (info["end"] - info["top"]) * i / (info["n"] - 1)
        def Y():
            # чака края на прехода: емулаторът няма видеокарта и е в пъти по-бавен от телефон
            time.sleep(1.2); t = time.time()
            while time.time() - t < 25 and ev("document.querySelector('[data-walk]').classList.contains('is-moving')"): time.sleep(0.4)
            time.sleep(0.9); return ev("scrollY")
        for i in (1, 2, 3):
            swipe(420); y = Y(); check(f"един жест → спирка {i}", abs(y - stop(i)) < 6, round(y)); shot(f"detent_{i}.png")
        swipe(-420); y = Y(); check("жест нагоре → спирка 2", abs(y - stop(2)) < 6, round(y))
        swipe(1100); y = Y(); check("дълъг силен жест → само спирка 3", abs(y - stop(3)) < 6, round(y))
    except Exception as e: check("тест на жестовете", False, str(e)[:160])
    (out / "detent.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
for l in sorted(set(logs)): report.append({"page": "", "view": a.plat, "kind": "error", "text": l})
(out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
kinds = {}
for r in report: kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
print("ОБЩО:", kinds)
