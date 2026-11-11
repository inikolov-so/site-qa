# Преходите между страниците (т.6 от Иво, 11.11.2026): завесата, назад/напред (с и без bfcache), презареждане,
# котви към друга страница, двоен клик, клик по време на прехода, менюто на телефон, разходката и тестето след връщане.
# Мери числа (покритие на екрана от завесата за всеки кадър, scrollY, кадъра на canvas, грешки), не само снимки.
#   python nav_test.py <адрес на сайта> [--engine chromium|webkit|firefox] [--device mac|win|hd|iphone|pixel]
#                      [--channel chrome] [--bf] [--headed] [--shots <папка>]
#   --bf: Chromium с включен bfcache (Playwright го изключва по подразбиране; WebKit и Firefox в Playwright нямат bfcache).
# Изход 0 = всичко ДА. Пример: python nav_test.py http://127.0.0.1:8000 --engine webkit --device mac
import sys, json, asyncio, argparse, pathlib
from playwright.async_api import async_playwright

ap = argparse.ArgumentParser(); ap.add_argument("base"); ap.add_argument("--engine", default="chromium"); ap.add_argument("--channel", default=None)
ap.add_argument("--device", default="mac"); ap.add_argument("--bf", action="store_true"); ap.add_argument("--headed", action="store_true")
ap.add_argument("--shots", default=""); ap.add_argument("--only", default="", help="само тези раздели, напр. chain,back,scroll,clicks,anchors,menu,reduce")
a = ap.parse_args()
BASE = a.base.rstrip("/").removesuffix("/index.html") + "/"
PAGES = ["index.html", "books.html", "biznes-konsultacii.html", "blagoev-community.html", "sales-masterclass.html",
         "resources.html", "kontakti.html", "triplepilot.html", "havnijokera2.html"]
ANCHORS = ["triplepilot.html#razgovor", "biznes-konsultacii.html#kalendar", "sales-masterclass.html#zapisvane", "blagoev-community.html#zayavka"]
DESK = {"mac": (1512, 860, 2), "win": (1536, 730, 1.25), "hd": (1920, 1080, 1)}
SHOTS = pathlib.Path(a.shots) if a.shots else None
if SHOTS: SHOTS.mkdir(parents=True, exist_ok=True)

# На всеки кадър (rAF) от началото на документа: колко от екрана покрива завесата (cov 0..1), видимо ли е логото (mk).
# Покривалото до тръгването на site.js е html.is-entering::after; без него cov е само от .curtain.
# При pagehide кадрите отиват в sessionStorage, за да се види и излизането.
PROBE = r"""(()=>{if(window.__nav||window.top!==window)return;const N=window.__nav={s:[],t0:performance.now()};
const vis=r=>Math.max(0,Math.min(innerHeight,r.bottom)-Math.max(0,r.top))/innerHeight;
function cov(){const h=document.documentElement;if(!h)return 0;
 if(h.classList.contains('is-entering')){const ps=getComputedStyle(h,'::after');if(ps.content&&ps.content!=='none'&&ps.content!=='normal'&&ps.position==='fixed')return 1}
 const c=document.querySelector('.curtain');return c?+vis(c.getBoundingClientRect()).toFixed(3):0}
function mk(){const m=document.documentElement&&document.querySelector('.curtain__mark');if(!m)return 0;const o=+getComputedStyle(m).opacity;return o>.05&&vis(m.getBoundingClientRect())>0?1:0}
let last='';function tick(){const v=[+(performance.now()-N.t0).toFixed(1),cov(),mk()];const k=v[1]+'|'+v[2];if(k!==last){N.s.push(v);last=k}requestAnimationFrame(tick)}requestAnimationFrame(tick);
addEventListener('pageshow',e=>{N.s.push(['pageshow',e.persisted?1:0,+(performance.now()-N.t0).toFixed(1)]);last=''});
addEventListener('pagehide',()=>{try{sessionStorage.setItem('__navPrev',JSON.stringify({url:location.href,tc:N.tc||0,s:N.s.slice(-80)}))}catch(e){}});
// банерът за бисквитки (consent.js) не е част от прехода: съгласие „само нужните“, иначе закрива менюто на телефона
try{if(!localStorage.getItem('rb-consent'))localStorage.setItem('rb-consent',JSON.stringify({v:1,id:'site-qa',t:new Date().toISOString(),media:false,stats:false,marketing:false}))}catch(e){}
})();"""
WALK = """(()=>{const w=document.querySelector('[data-walk]');if(!w)return null;const st=w.querySelector('.walk__stage'),c=w.querySelector('.walk__canvas');
let lum=null;if(c&&c.width&&+c.style.opacity>0){const d=c.getContext('2d').getImageData(c.width*.3|0,c.height*.3|0,64,64).data;let t=0;for(let i=0;i<d.length;i+=4)t+=d[i]+d[i+1]+d[i+2];lum=Math.round(t/(d.length/4)/3)}
const top=w.getBoundingClientRect().top+scrollY,end=top+w.offsetHeight-st.offsetHeight;
return {top,end,s:+(w._s||0).toFixed(3),lum,frames:w.classList.contains('has-frames'),pan:[...w.querySelectorAll('.walk__panel')].map(p=>+(+p.style.opacity||0).toFixed(2))}})()"""
STATE = """(()=>({y:Math.round(scrollY),H:document.documentElement.scrollHeight,url:location.pathname.split('/').pop()+location.hash,
 sts:window.ScrollTrigger?ScrollTrigger.getAll().length:0,
 pins:window.ScrollTrigger?ScrollTrigger.getAll().filter(s=>s.pin).map(s=>Math.round(s.pin.getBoundingClientRect().top)):[],
 menu:!!document.querySelector('.menu.open'),drawer:!!document.querySelector('.drawer.open'),
 lenisStopped:window.__lenis?!!__lenis.isStopped:false,entering:document.documentElement.classList.contains('is-entering')}))()"""

ok = []; fails = []
def check(name, cond, info=""):
    ok.append(bool(cond)); print(("ДА " if cond else "НЕ "), name, info, flush=True)
    if not cond: fails.append(name)

def monotone(seq, up, tol=0.02):
    """seq от cov: up=True → само расте (излизане), up=False → само намалява (влизане)."""
    for x, y in zip(seq, seq[1:]):
        if (up and y < x - tol) or (not up and y > x + tol): return False
    return True

async def main():
  async with async_playwright() as p:
    eng = getattr(p, a.engine); kw = {"headless": not a.headed}
    if a.channel: kw["channel"] = a.channel
    if a.bf:
        if a.engine != "chromium": print("--bf е само за chromium"); sys.exit(2)
        kw.setdefault("channel", "chromium"); kw["ignore_default_args"] = ["--disable-back-forward-cache"]
    b = await eng.launch(**kw)
    mobile = a.device in ("iphone", "pixel")
    if mobile: cfg = dict(p.devices["iPhone 13" if a.device == "iphone" else "Pixel 7"])
    else:
        w, h, d = DESK[a.device]; cfg = dict(viewport={"width": w, "height": h}, device_scale_factor=d)
    if a.engine == "firefox": cfg.pop("is_mobile", None)
    label = f"{a.engine}{'+bf' if a.bf else ''} {a.device}"
    print("==", label, BASE, flush=True)

    async def new_ctx(**extra):
        ctx = await b.new_context(locale="bg-BG", **cfg, **extra); await ctx.add_init_script(PROBE)
        # site.js идва 250 мс по-късно, както от мрежата на живо (локално всичко е в кеша и браузърът не стига да
        # нарисува страницата преди завесата; на живо стига: Safari до ~200 мс съдържание без завеса)
        async def slow(route):
            await asyncio.sleep(0.25); await route.continue_()
        if not a.bf: await ctx.route("**/assets/site.js*", slow)   # прихващането на заявки изключва bfcache в Chromium
        pg = await ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
        return ctx, pg, errs

    async def settle(pg, ms=700):
        # завесата е долу или горе извън екрана и покривалото го няма
        try: await pg.wait_for_function("(()=>{const c=document.querySelector('.curtain');if(!c||document.documentElement.classList.contains('is-entering'))return false;const r=c.getBoundingClientRect();return r.top>=innerHeight-1||r.bottom<=1})()", timeout=6000)
        except Exception: pass
        await pg.wait_for_timeout(ms)

    async def goto(pg, url, **kw):
        # goto може да падне с ERR_ABORTED, ако предишната страница още навигира сама (завесата): един опит отново
        try: await pg.goto(url, **kw)
        except Exception:
            await pg.wait_for_timeout(1500); await pg.goto(url, **kw)

    async def arrived(pg):
        # от bfcache няма нов DOMContentLoaded: чакаме го кратко, после завесата
        try: await pg.wait_for_load_state("domcontentloaded", timeout=4000)
        except Exception: pass

    async def samples(pg): return await pg.evaluate("window.__nav?__nav.s:[]")
    async def prev(pg): return await pg.evaluate("(()=>{try{return JSON.parse(sessionStorage.getItem('__navPrev')||'null')}catch(e){return null}})()")

    def arrival_ok(s, name):
        """Влизане: първият кадър е покрит, после покритието само намалява до 0, логото не остава."""
        cv = [x[1] for x in s if not isinstance(x[0], str)]
        if not cv: return False, "няма кадри"
        start = 0
        for i, x in enumerate(s):                     # след bfcache: от pageshow нататък
            if x[0] == "pageshow" and x[1] == 1: start = i + 1
        cv2 = [x[1] for x in s[start:] if not isinstance(x[0], str)]
        if not cv2: cv2 = cv[-1:]
        first_ok = start > 0 or cv2[0] >= 0.99
        mono = monotone(cv2, up=False)
        end = cv2[-1] <= 0.001
        stuck = [x for x in s[start:] if not isinstance(x[0], str) and x[1] <= 0.001 and x[2]]
        bad = []
        if not first_ok: bad.append(f"първи кадър покрит {cv2[0]}")
        if not mono: bad.append("мига " + str([round(v, 2) for v in cv2[:14]]))
        if not end: bad.append(f"остава покрита {cv2[-1]}")
        if stuck: bad.append("логото остава")
        return not bad, "; ".join(bad) or f"{len(cv2)} кадъра {cv2[0]}→{cv2[-1]}"

    def leave_ok(pv):
        if not pv: return False, "няма данни за излизането"
        s = [x for x in pv["s"] if not isinstance(x[0], str)]
        i0 = max([i for i, x in enumerate(s) if x[1] <= 0.001] or [0])   # последният непокрит кадър = кликът
        cv = [x[1] for x in s[i0:]]
        return monotone(cv, up=True) and cv[-1] >= 0.99, str([round(v, 2) for v in cv[:16]])

    async def click_to(pg, href):
        # линк в самата страница (през обработчика на site.js, както при истински клик); tc = времето на клика
        await pg.evaluate("h=>{if(window.__nav)__nav.tc=performance.now()-__nav.t0;const a=document.createElement('a');a.href=h;a.textContent='.';a.style.cssText='position:fixed;left:0;top:0;opacity:0';document.body.appendChild(a);a.click();a.remove()}", href)

    async def put(pg, y):
        await pg.evaluate("y=>{if(window.__lenis)__lenis.scrollTo(y,{immediate:true,force:true});else scrollTo(0,y)}", y)

    sec = lambda n: not a.only or n in a.only.split(",")
    ctx, pg, errs = await new_ctx()
    await goto(pg, BASE + "index.html", wait_until="load"); await settle(pg, 1500)
    ok0, info = arrival_ok(await samples(pg), "index")
    check("първо зареждане: без мигане, завесата се вдига", ok0, info)

    # ---------- 1. верига по страниците: клик → влизане ----------
    if sec("chain"):
        cur = "index.html"; bad_in, bad_out, jumps = [], [], []
        LAY = "[...document.querySelectorAll('main > *')].slice(0,6).map(e=>Math.round(e.getBoundingClientRect().top+scrollY))"
        for nxt in PAGES[1:]:
            await click_to(pg, nxt); await pg.wait_for_url("**/" + nxt, timeout=15000); await pg.wait_for_load_state("load")
            l0 = await pg.evaluate(LAY); await settle(pg); await pg.wait_for_timeout(1200); l1 = await pg.evaluate(LAY)
            # разкриването на заглавията (SplitText с маска → revert) не бива да мести нищо под тях
            if any(abs(x - y) > 2 for x, y in zip(l0, l1)): jumps.append(f"{nxt}: {l0} → {l1}")
            o1, i1 = arrival_ok(await samples(pg), nxt); o2, i2 = leave_ok(await prev(pg))
            if not o1: bad_in.append(f"{nxt}: {i1}")
            if not o2: bad_out.append(f"{cur}→{nxt}: {i2}")
            if SHOTS: await pg.screenshot(path=str(SHOTS / f"{label.replace(' ', '_')}_{nxt[:-5]}.png"))
            cur = nxt
        check(f"влизане в {len(PAGES) - 1} страници: покрито от първия кадър, после само се вдига", not bad_in, bad_in[:3])
        check("излизане: завесата само се спуска до край (без скок)", not bad_out, bad_out[:3])
        check("след влизане разделите не подскачат (заглавията се разкриват без смяна на височината)", not jumps, jumps[:2])

    # ---------- 2. назад / напред многократно ----------
    if sec("back") and sec("chain"):
        bad = []; seq = ["back"] * 4 + ["fwd"] * 2 + ["back"] * 3 + ["fwd"]; restored = 0
        for step in seq:
            if step == "back": await pg.go_back(wait_until="commit")
            else: await pg.go_forward(wait_until="commit")
            await arrived(pg); await settle(pg)
            sm = await samples(pg); o, i = arrival_ok(sm, step); st = await pg.evaluate(STATE)
            restored += any(x[0] == "pageshow" and x[1] == 1 for x in sm)
            if not o: bad.append(f"{step} {st['url']}: {i}")
            if st["entering"]: bad.append(f"{step} {st['url']}: is-entering остава")
        check(f"назад/напред ×{len(seq)}{' (bfcache)' if a.bf else ''}: завесата се вдига, не мига, не остава", not bad, bad[:3])
        if a.bf: check("bfcache наистина е ползван", restored >= len(seq) // 2, f"{restored} от {len(seq)} от паметта")

    # ---------- 3. връщане назад към място по средата: скрол, разходка, тестето ----------
    if sec("scroll"):
        async def roundtrip(page, place, how="back", tag=""):
            await goto(pg, BASE + page, wait_until="load"); await settle(pg, 1800)
            y = await pg.evaluate(place) if isinstance(place, str) else place
            if "отгоре" in tag:                         # идва отдолу: посоката е назад, магнитът не тегли напред
                await put(pg, y + 700); await pg.wait_for_timeout(600)
            await put(pg, y); await pg.wait_for_timeout(1500)
            before = await pg.evaluate(STATE); wb = await pg.evaluate(WALK) if page == "index.html" else None
            if how == "reload": await pg.reload(wait_until="commit")
            else:
                await click_to(pg, "kontakti.html"); await pg.wait_for_url("**/kontakti.html"); await pg.wait_for_load_state("load"); await settle(pg, 300)
                await pg.go_back(wait_until="commit")
            await arrived(pg); await settle(pg, 2200)
            after = await pg.evaluate(STATE); wa = await pg.evaluate(WALK) if page == "index.html" else None
            return before, after, wb, wa
        walk_r = lambda r: f"(()=>{{const w=document.querySelector('[data-walk]'),s=w.querySelector('.walk__stage');const t=w.getBoundingClientRect().top+scrollY;return t+(w.offsetHeight-s.offsetHeight)*{r}/4}})()"
        deck = "(()=>{const t=ScrollTrigger.getAll().find(s=>s.pin&&s.pin.classList.contains('deck'));return t?Math.round(t.start+(t.end-t.start)*.45):Math.round(document.documentElement.scrollHeight*.5)})()"
        deep = "Math.round((document.documentElement.scrollHeight-innerHeight)*.86)"
        cases = [("index.html", walk_r(1.5), "back", "разходката по средата на прехода"), ("index.html", walk_r(2), "back", "разходката на спирка 2"),
                 ("index.html", deck, "back", "тестето по средата"), ("index.html", deep, "back", "главната дълбоко долу"),
                 ("index.html", deck, "reload", "презареждане по средата на тестето"), ("books.html", "Math.round(document.documentElement.scrollHeight*.6)", "back", "книгите на 60%"),
                 ("sales-masterclass.html", "Math.round(document.documentElement.scrollHeight*.45)", "reload", "Master Class презареждане"),
                 ("index.html", walk_r(1.79), "back", "разходката малко преди спирка 2, дошъл отгоре")]
        for page, place, how, name in cases:
            bfr, aft, wb, wa = await roundtrip(page, place, how, name)
            dy = aft["y"] - bfr["y"]; dH = aft["H"] - bfr["H"]
            info = f"y {bfr['y']}→{aft['y']} (Δ{dy}), H Δ{dH}, пинове {bfr['pins']}→{aft['pins']}"
            good = abs(dy) <= 40 and abs(dH) <= 40 and aft["url"].startswith(page)
            if wb and wa and "разходката" in name:
                info += f", s {wb['s']}→{wa['s']}, canvas {wa['lum']}, текст {wa['pan']}"
                good = good and abs(wa["s"] - wb["s"]) < 0.01 and wa["pan"] == wb["pan"] and (wa["lum"] is None or wa["lum"] > 6 or (wb["lum"] or 0) <= 6)
            check(f"{'назад' if how == 'back' else 'презареждане'}: {name} → същото място", good, info)
        check("без JS грешки (връщане и презареждане)", not errs, errs[:2])

    # ---------- 4. кликове: двоен, втори линк, клик по време на вдигането ----------
    if sec("clicks"):
        navs = []
        # replaceState (site.js пише ключа за скрола в history.state) също е framenavigated: броим само смяна на адреса
        pg.on("framenavigated", lambda f: navs.append(f.url) if f == pg.main_frame and (not navs or navs[-1] != f.url) else None)
        await goto(pg, BASE + "privacy-policy.html", wait_until="load"); await settle(pg); navs.clear()
        await pg.evaluate("""()=>{const a=document.createElement('a');a.href='books.html';a.textContent='.';a.style.cssText='position:fixed;left:0;top:0;width:40px;height:40px;z-index:99';a.id='__t';document.body.appendChild(a)}""")
        await pg.dblclick("#__t"); await pg.wait_for_url("**/books.html"); await pg.wait_for_load_state("load"); await settle(pg)
        o, i = leave_ok(await prev(pg))
        check("двоен клик: завесата не започва отначало, една навигация", o and len(navs) == 1, f"{i} навигации {len(navs)}")
        navs.clear()
        await click_to(pg, "kontakti.html"); await pg.wait_for_timeout(300); await click_to(pg, "resources.html")
        await pg.wait_for_timeout(2500); await settle(pg)
        o, i = leave_ok(await prev(pg))
        check("втори линк след 300 мс: без скок на завесата, една навигация към последния", o and len(navs) == 1 and pg.url.endswith("resources.html"), f"{i} → {pg.url.split('/')[-1]}, навигации {len(navs)}")
        for delay in (250, 550):
            await goto(pg, BASE + "privacy-policy.html", wait_until="commit")
            await pg.wait_for_function("document.querySelector('.curtain')"); await pg.wait_for_timeout(delay)
            await click_to(pg, "books.html"); await pg.wait_for_url("**/books.html"); await pg.wait_for_load_state("load"); await settle(pg)
            pv = await prev(pg) or {"s": [], "tc": 0}
            # от клика нататък покритието само расте: старият код скачаше от „почти покрито“ на „открито“ (завесата отначало)
            fr = [x for x in pv["s"] if not isinstance(x[0], str)]; tc = pv.get("tc", 0)
            pre = [x[1] for x in fr if x[0] < tc][-1:]          # последният кадър преди клика
            s = [x[1] for x in fr if x[0] >= tc]
            first_ok = not pre or not s or s[0] >= pre[0] - 0.1   # един кадър вдигане до клика е допустим
            check(f"клик {delay} мс след влизане (завесата още се вдига): без скок", s and first_ok and monotone(s, up=True) and s[-1] >= 0.99, str([round(v, 2) for v in pre + s[:16]]))

    # ---------- 5. котви от друга страница ----------
    if sec("anchors"):
        bad = []
        for href in ANCHORS:
            await goto(pg, BASE + "kontakti.html", wait_until="load"); await settle(pg, 300); errs.clear()
            await click_to(pg, href); await pg.wait_for_url("**/" + href.split("#")[0] + "*"); await pg.wait_for_load_state("load"); await settle(pg, 1800)
            top = await pg.evaluate("id=>{const e=document.getElementById(id);return e?Math.round(e.getBoundingClientRect().top):null}", href.split("#")[1])
            hdr = 88
            if top is None and not errs: print("   ", href, "няма такава цел на страницата, прескачам"); continue
            if top is None or not (hdr - 30 <= top <= hdr + 30) or errs: bad.append(f"{href}: горе {top} px{' грешка ' + errs[0][:60] if errs else ''}")
            else: print("   ", href, "горе", top, "px")
        check("котва от друга страница: целта е под хедъра (~88 px), без грешки", not bad, bad[:4])

    # ---------- 6. bfcache: меню/количка остават отворени, назад по време на излизане ----------
    if sec("menu") and a.bf and not mobile:
        await goto(pg, BASE + "books.html", wait_until="load"); await settle(pg); await pg.mouse.move(600, 400)
        await pg.evaluate("RB.cart.add('3308',1);RB.cart.open()"); await pg.wait_for_timeout(600)
        await click_to(pg, "checkout.html"); await pg.wait_for_url("**/checkout.html"); await pg.wait_for_load_state("load"); await settle(pg, 300)
        await pg.go_back(wait_until="commit"); await settle(pg)
        st = await pg.evaluate(STATE); y0 = st["y"]; await pg.mouse.wheel(0, 500); await pg.wait_for_timeout(900); y1 = await pg.evaluate("scrollY")
        check("bfcache: количката е затворена след „назад“ и страницата скролва", not st["drawer"] and not st["lenisStopped"] and y1 > y0 + 100, f"{st['drawer']=} {st['lenisStopped']=} скрол {y0}→{round(y1)}")
        await pg.evaluate("RB.cart.clear()")
        await goto(pg, BASE + "privacy-policy.html", wait_until="load"); await settle(pg)
        await click_to(pg, "books.html"); await pg.wait_for_url("**/books.html"); await pg.wait_for_load_state("load"); await settle(pg)
        await click_to(pg, "kontakti.html"); await pg.wait_for_timeout(200)
        await pg.evaluate("history.back()"); await pg.wait_for_url("**/privacy-policy.html", wait_until="commit"); await settle(pg)
        await pg.go_forward(wait_until="commit"); await pg.wait_for_timeout(2500); await settle(pg)
        st = await pg.evaluate(STATE); o, i = arrival_ok(await samples(pg), "fwd")
        check("„назад“ по време на излизане, после „напред“: страницата стои, не отива сама нататък", st["url"] == "books.html" and o, f"{st['url']} {i}")
    if sec("menu") and mobile:
        await goto(pg, BASE + "books.html", wait_until="load"); await settle(pg)
        await pg.tap(".menu-btn"); await pg.wait_for_timeout(900)
        await pg.tap(".menu__links a[href='kontakti.html']"); await pg.wait_for_url("**/kontakti.html"); await pg.wait_for_load_state("load"); await settle(pg)
        o1, i1 = leave_ok(await prev(pg)); o2, i2 = arrival_ok(await samples(pg), "kontakti")
        check("телефон: от менюто към страница — завесата без скок, влизането без мигане", o1 and o2, f"{i1} | {i2}")
        await pg.go_back(wait_until="commit"); await settle(pg)
        st = await pg.evaluate(STATE); o, i = arrival_ok(await samples(pg), "back")
        check("телефон: назад след менюто → менюто е затворено, завесата се вдига", not st["menu"] and o, f"меню {st['menu']} {i}")
        if SHOTS: await pg.screenshot(path=str(SHOTS / f"{label.replace(' ', '_')}_menu_back.png"))

    check("без JS грешки", not errs, errs[:2])
    await ctx.close()

    # ---------- 7. prefers-reduced-motion ----------
    if sec("reduce"):
        ctx, pg, errs = await new_ctx(reduced_motion="reduce")
        await goto(pg, BASE + "books.html", wait_until="load"); await pg.wait_for_timeout(800)
        s0 = await samples(pg)
        await put(pg, 1500); await pg.wait_for_timeout(300)
        await click_to(pg, "kontakti.html"); await pg.wait_for_url("**/kontakti.html", timeout=3000); await pg.wait_for_load_state("load"); await pg.wait_for_timeout(500)
        s1 = await samples(pg)
        anycov = [x for x in s0 + s1 if not isinstance(x[0], str) and x[1] > 0.01]
        await pg.go_back(wait_until="commit"); await arrived(pg); await pg.wait_for_timeout(1200); y = await pg.evaluate("scrollY")
        check("намалено движение: без завеса и покривало, назад на същото място", not anycov and abs(y - 1500) <= 40 and not errs, f"покрити кадри {len(anycov)}, y {round(y)}, грешки {errs[:1]}")
        await ctx.close()
    await b.close()
  print("РЕЗУЛТАТ:", sum(ok), "/", len(ok), "·", label, flush=True)
  if fails: print("НЕ:", " | ".join(fails))
  sys.exit(0 if all(ok) else 1)

asyncio.run(main())
