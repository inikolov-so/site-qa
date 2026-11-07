# Скрол-филмът в режим Soft (Иво, 07.11.2026): филмът върви само докато човекът скролва, на спирките
# кадърът и текстът стоят за част от скрола, малко след спирката скролът леко се връща в нея.
# python detent_test.py <url> [--engine webkit]
import sys, asyncio, argparse
from playwright.async_api import async_playwright
ap = argparse.ArgumentParser(); ap.add_argument("url"); ap.add_argument("--engine", default="chromium"); ap.add_argument("--channel", default="chrome")
ap.add_argument("--headed", action="store_true"); ap.add_argument("--w", type=int, default=1536); ap.add_argument("--h", type=int, default=730); ap.add_argument("--dpr", type=float, default=1.25); a = ap.parse_args()
# снимката на спирката на canvas: изрезът трябва да е цялата ширина или височина на истинските пиксели.
# <img srcset> дава naturalWidth, разделен на плътността → изрез ~0,6 от снимката към горния ляв ъгъл (Retina, Windows 125%)
LOG = """window.__filmTrace=[];(()=>{const o=CanvasRenderingContext2D.prototype.drawImage;window.__stillDraws=[];CanvasRenderingContext2D.prototype.drawImage=function(s,...r){
if(s instanceof HTMLImageElement&&r.length>=8)window.__stillDraws.push([s.srcset||'',s.naturalWidth,s.naturalHeight,r[2],r[3]]);return o.call(this,s,...r)}})()"""
HASH = """(()=>{const c=document.querySelector('[data-walk] .walk__canvas');if(!c||!c.width)return 0;const d=c.getContext('2d').getImageData(c.width*.3|0,c.height*.3|0,96,96).data;let h=0;for(let i=0;i<d.length;i+=5)h=(h*31+d[i])|0;return h})()"""
ok = []
def check(name, cond, info=""):
    ok.append(bool(cond)); print(("ДА " if cond else "НЕ "), name, info, flush=True)
async def main():
  async with async_playwright() as p:
    eng = getattr(p, a.engine); kw = {}
    if a.engine == "chromium": kw["channel"] = a.channel
    if a.headed: kw["headless"] = False
    b = await eng.launch(**kw)
    ctx = await b.new_context(viewport={"width": a.w, "height": a.h}, device_scale_factor=a.dpr)
    pg = await ctx.new_page(); await pg.add_init_script(LOG)
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)[:300]))
    await pg.goto(a.url, wait_until="load"); await pg.wait_for_timeout(3500)
    await pg.mouse.move(a.w/2, a.h/2)
    info = await pg.evaluate("""()=>{const w=document.querySelector('[data-walk]'),s=w.querySelector('.walk__stage');return {top:w.getBoundingClientRect().top+scrollY,end:w.getBoundingClientRect().top+scrollY+w.offsetHeight-s.offsetHeight,n:w.querySelectorAll('.walk__frame').length,frames:w.classList.contains('has-frames')}}""")
    print(info); check("кадрите са заредени", info["frames"])
    S = lambda: pg.evaluate("document.querySelector('[data-walk]')._s")
    yR = lambda r: info["top"] + (info["end"]-info["top"])*r/(info["n"]-1)
    async def put(r):   # слага скрола точно на r (суровото положение) и чака
        await pg.evaluate(f"(()=>{{const y={yR(r)};if(window.__lenis)__lenis.scrollTo(y,{{immediate:true,force:true}});else scrollTo(0,y)}})()")
    near = lambda s, i: abs(s - i) < 1e-3
    # 1. на спирка 0 леко движение не мести филма, кадърът стои
    h0 = await pg.evaluate(HASH)
    await pg.mouse.wheel(0, 100); await pg.wait_for_timeout(1200)
    s = await S(); h1 = await pg.evaluate(HASH)
    check("1 щрак на спирка 0 → кадърът стои (задържане)", near(s, 0), round(s, 3))
    # 2. филмът върви с колелото на стъпки, не скача сам до следващата спирка
    seen = []
    for _ in range(14):
        await pg.mouse.wheel(0, 100); await pg.wait_for_timeout(260); seen.append(round(await S(), 3))
    mids = sorted(set(x for x in seen if 0.02 < (x % 1) < 0.98))
    print("   s след всеки щрак:", seen)
    check("филмът върви с колелото на стъпки (≥5 междинни положения)", len(mids) >= 5, len(mids))
    check("при скрол напред филмът не се връща назад", all(b2 >= a2 - 1e-3 for a2, b2 in zip(seen, seen[1:])))
    tr = await pg.evaluate("__filmTrace"); idx = [k*1000+i for k, i, e in tr]
    check("кадрите от видеото вървят само напред", all(y2 >= x2 for x2, y2 in zip(idx, idx[1:])), f"{len(tr)} кадъра")
    # 3. спрял по средата: нищо не се мести само
    await put(1.5); await pg.wait_for_timeout(300); s0 = await S(); await pg.wait_for_timeout(1500); s1 = await S()
    check("спрял по средата на прехода → филмът не мърда сам", abs(s1 - s0) < 1e-3, (round(s0, 3), round(s1, 3)))
    # 4. малко след спирката не дърпа назад (иначе малки движения с пауза не излизат); съвсем близо преди → довлиза
    await put(2.0); await pg.wait_for_timeout(300)
    # колкото ще са движенията зависи от височината на екрана (задържането е в vh); паузата след всяко е 1 сек
    for m in range(1, 9):
        await pg.mouse.wheel(0, 100); await pg.wait_for_timeout(1000); s = await S()
        if s > 2.02: break
    check("малки движения с пауза излизат от спирка 2", s > 2.02, f"s={round(s, 3)} след {m} движения")
    await put(2.78); await pg.wait_for_timeout(200); await pg.mouse.wheel(0, 40); await pg.wait_for_timeout(1800); s = await S()
    check("съвсем близо преди спирка 3 → довлиза в 3", near(s, 3), round(s, 3))
    # 5. на спирката кадърът стои неподвижен, и при леко колело
    h0 = await pg.evaluate(HASH); y0 = await pg.evaluate("scrollY")
    await pg.mouse.wheel(0, 90); await pg.wait_for_timeout(900); s = await S(); h1 = await pg.evaluate(HASH)
    check("на спирка 3 лек щрак → кадърът стои неподвижен (без зуум)", near(s, 3) and h0 == h1, (round(s, 3), h0 == h1))
    # 6. релсата и „Прескочи“
    await pg.click(".walk__rail button:nth-child(2)"); await pg.wait_for_timeout(3200); s = await S()
    check("релсата води до спирка 1", near(s, 1), round(s, 3))
    await pg.click(".walk__skip"); await pg.wait_for_timeout(1800); y = await pg.evaluate("scrollY")
    check("„Прескочи“ излиза от филма", y > info["end"], round(y))
    # 7. от последната спирка излиза надолу, без да заключва
    await put(4); await pg.wait_for_timeout(400)
    for _ in range(8): await pg.mouse.wheel(0, 100); await pg.wait_for_timeout(120)
    await pg.wait_for_timeout(1000); y = await pg.evaluate("scrollY"); check("от последната спирка излиза надолу", y > info["end"] + 50, round(y))
    sd = await pg.evaluate("__stillDraws"); bad = [x for x in sd if x[0] or max(x[3]/x[1], x[4]/x[2]) < 0.97]
    check("снимката на спирката се рисува в истинските си пиксели (без зуум към ъгъла)", sd and not bad, f"{len(sd)} рисувания, лоши {len(bad)} {bad[:1]}")
    check("без JS грешки", not errs, errs[:2])
    await b.close()
  print("РЕЗУЛТАТ:", sum(ok), "/", len(ok)); sys.exit(0 if all(ok) else 1)
asyncio.run(main())
