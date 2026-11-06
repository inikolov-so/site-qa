# Поведението на зъбното колело с истински събития: python detent_test.py <url> [--engine webkit]
import sys, asyncio, json, argparse
from playwright.async_api import async_playwright
ap = argparse.ArgumentParser(); ap.add_argument("url"); ap.add_argument("--engine", default="chromium"); ap.add_argument("--channel", default="chrome")
ap.add_argument("--headed", action="store_true"); ap.add_argument("--w", type=int, default=1536); ap.add_argument("--h", type=int, default=730); ap.add_argument("--dpr", type=float, default=1.25); a = ap.parse_args()
LOG = """(()=>{const o=CanvasRenderingContext2D.prototype.drawImage;window.__draws=[];window.__filmTrace=[];CanvasRenderingContext2D.prototype.drawImage=function(s,...r){window.__draws.push([performance.now(),s.width,r[0],r[1],r[2]]);return o.call(this,s,...r)};
window.__rafs=[];(function t(x){window.__rafs.push(x);requestAnimationFrame(t)})(0)})()"""
ok = []; 
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
    await pg.goto(a.url, wait_until="load"); await pg.wait_for_timeout(3000)
    await pg.mouse.move(a.w/2, a.h/2)
    info = await pg.evaluate("""()=>{const w=document.querySelector('[data-walk]'),s=w.querySelector('.walk__stage');return {top:w.getBoundingClientRect().top+scrollY,end:w.getBoundingClientRect().top+scrollY+w.offsetHeight-s.offsetHeight,n:w.querySelectorAll('.walk__frame').length,frames:w.classList.contains('has-frames')}}""")
    print(info); check("кадрите са заредени", info["frames"])
    stop = lambda i: info["top"] + (info["end"]-info["top"])*i/(info["n"]-1)
    Y = lambda: pg.evaluate("scrollY")
    # чака края на прехода: на бавна машина той е по-дълъг, логиката се мери, не хронометърът
    async def idle(extra=300, limit=9000):
        await pg.wait_for_timeout(250); t = 0
        while t < limit and await pg.evaluate("document.querySelector('[data-walk]').classList.contains('is-moving')"):
            await pg.wait_for_timeout(120); t += 120
        await pg.wait_for_timeout(extra)
    async def at(i): 
        y = await Y(); return abs(y-stop(i)) < 3, round(y)
    await pg.evaluate("__draws.length=0;__rafs.length=0;__filmTrace.length=0")
    # 1. един щрак на колелото
    await pg.mouse.wheel(0, 100); await idle()
    r = await at(1); check("1 щрак → спирка 1", r[0], r[1])
    d = await pg.evaluate("__draws"); xs = [x[0] for x in d]
    gaps = [round(b-a,1) for a,b in zip(xs,xs[1:])]
    print("   нарисувани кадри", len(d), "най-дълга пауза мс", max(gaps) if gaps else None)
    rf = await pg.evaluate("__rafs"); fg=[b-a for a,b in zip(rf,rf[1:])]; print("   кадри на браузъра", len(rf), "над 34 мс:", sum(1 for g in fg if g>34), "max", round(max(fg),1))
    tr = await pg.evaluate("__filmTrace"); idx=[(k*1000+i) for k,i,e in tr]; back=sum(1 for a,b in zip(idx,idx[1:]) if b<a); same=sum(1 for a,b in zip(idx,idx[1:]) if a==b); miss=sum(1 for k,i,e in tr if not e); big=max([b-a for a,b in zip(idx,idx[1:])] or [0])
    print("   кадри от видеото", len(tr), "назад:", back, "повторени:", same, "неточни:", miss, "най-голям скок:", big)
    check("филмът върви само напред, без неточни кадри", back==0 and miss==0, f"най-голям скок {big}")
    # 2. бързо въртене: спира на следващата, не прелита
    await pg.wait_for_timeout(700)
    # върти, докато филмът стигне, и още 1,2 сек: колелото още се върти след щрака. Мери логиката, не скоростта на машината.
    async def spin(fn, after=1200, limit=12000):
        import time
        t0 = time.monotonic(); seen = False; done = None
        while (time.monotonic() - t0) * 1000 < limit:
            await fn(); await pg.wait_for_timeout(45)
            mv = await pg.evaluate("document.querySelector('[data-walk]').classList.contains('is-moving')")
            seen = seen or mv
            if seen and not mv and done is None: done = time.monotonic()
            if done is not None and (time.monotonic() - done) * 1000 >= after: break
    async def notch(): await pg.mouse.wheel(0, 100)
    await spin(notch); await idle()
    r = await at(2); check("бързо въртене (26 щрака) → само спирка 2", r[0], r[1])
    # 3. тракпад: едно плъзване с дълга инерция
    await pg.wait_for_timeout(800)
    v = [60.0]
    async def inertia():
        await pg.mouse.wheel(0, v[0]); v[0] = max(0.6, v[0]*0.965)
    await spin(inertia, after=1500); await idle()
    r = await at(3); check("тракпад с инерция → само спирка 3", r[0], r[1])
    # 4. малко докосване не мести
    await pg.wait_for_timeout(900); await pg.mouse.wheel(0, 6); await pg.wait_for_timeout(900)
    r = await at(3); check("дребно докосване не мести", r[0], r[1])
    # 5. нагоре
    await pg.mouse.wheel(0, -100); await idle()
    r = await at(2); check("нагоре → спирка 2", r[0], r[1])
    # 6. обръщане в движение
    await pg.wait_for_timeout(800); await pg.mouse.wheel(0, 100); await pg.wait_for_timeout(500); await pg.mouse.wheel(0, -100); await idle()
    r = await at(2); check("обръщане по средата → обратно на 2", r[0], r[1])
    # 7. клавиатура
    await pg.wait_for_timeout(800); await pg.keyboard.press("PageDown"); await idle()
    r = await at(3); check("PageDown → спирка 3", r[0], r[1])
    await pg.wait_for_timeout(800); await pg.keyboard.press("ArrowDown"); await idle()
    r = await at(4); check("стрелка → спирка 4 (последна)", r[0], r[1])
    # 8. излизане и връщане
    await pg.wait_for_timeout(800)
    for _ in range(4): await pg.mouse.wheel(0, 100); await pg.wait_for_timeout(120)
    await pg.wait_for_timeout(1000); y = await Y(); check("от последната спирка излиза надолу", y > info["end"]+50, round(y))
    await pg.wait_for_timeout(300)
    for _ in range(14): await pg.mouse.wheel(0, -120); await pg.wait_for_timeout(50)
    await pg.wait_for_timeout(1200)
    r = await at(4); check("връщане отдолу се хваща на последната спирка", r[0], r[1])
    # 9. релсата и прескачането
    await pg.wait_for_timeout(700); await pg.click(".walk__rail button:nth-child(2)"); await idle()
    r = await at(1); check("релсата води до спирка 1", r[0], r[1])
    await pg.wait_for_timeout(300); await pg.click(".walk__skip"); await pg.wait_for_timeout(1900)
    y = await Y(); check("„Прескочи“ излиза от филма", y > info["end"], round(y))
    check("без JS грешки", not errs, errs[:2])
    await b.close()
  print("РЕЗУЛТАТ:", sum(ok), "/", len(ok)); sys.exit(0 if all(ok) else 1)
asyncio.run(main())
