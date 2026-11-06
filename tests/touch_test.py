# Жест с пръст през DevTools (Chrome): истински touch събития, браузърът решава дали да скролне.
import sys, asyncio, json
from playwright.async_api import async_playwright
url=sys.argv[1]; S=sys.argv[2]
async def main():
  async with async_playwright() as p:
    b=await p.chromium.launch(channel="chrome")
    ctx=await b.new_context(**p.devices["Pixel 7"]); pg=await ctx.new_page()
    errs=[]; pg.on("pageerror",lambda e:errs.append(str(e)[:200]))
    await pg.goto(url,wait_until="load"); await pg.wait_for_timeout(3500)
    c=await ctx.new_cdp_session(pg)
    info=await pg.evaluate("(()=>{const w=document.querySelector('[data-walk]'),s=w.querySelector('.walk__stage');const t=w.getBoundingClientRect().top+scrollY;return {top:t,end:t+w.offsetHeight-s.offsetHeight,n:w.querySelectorAll('.walk__frame').length,vh:innerHeight,vw:innerWidth,fr:w.classList.contains('has-frames')}})()"); print(info)
    stop=lambda i:info["top"]+(info["end"]-info["top"])*i/(info["n"]-1)
    async def swipe(dist,steps=10,ms=16):
      x=info["vw"]/2; y0=info["vh"]*.7 if dist>0 else info["vh"]*.3
      await c.send("Input.dispatchTouchEvent",{"type":"touchStart","touchPoints":[{"x":x,"y":y0}]})
      for i in range(1,steps+1):
        await c.send("Input.dispatchTouchEvent",{"type":"touchMove","touchPoints":[{"x":x,"y":y0-dist*i/steps}]}); await pg.wait_for_timeout(ms)
      await c.send("Input.dispatchTouchEvent",{"type":"touchEnd","touchPoints":[]})
    res=[]
    def chk(n,ok,i=""): res.append(ok); print("ДА " if ok else "НЕ ",n,i,flush=True)
    await pg.screenshot(path=S+"-0.png")
    for i in (1,2,3):
      await swipe(300); await pg.wait_for_timeout(2500); y=await pg.evaluate("scrollY"); chk(f"жест → спирка {i}",abs(y-stop(i))<4,round(y)); await pg.screenshot(path=f"{S}-{i}.png")
    await swipe(-300); await pg.wait_for_timeout(2500); y=await pg.evaluate("scrollY"); chk("жест нагоре → спирка 2",abs(y-stop(2))<4,round(y))
    await swipe(500,6); await pg.wait_for_timeout(2500); y=await pg.evaluate("scrollY"); chk("силен жест → спирка 3",abs(y-stop(3))<4,round(y))
    await swipe(300); await pg.wait_for_timeout(2500); y=await pg.evaluate("scrollY"); chk("→ спирка 4",abs(y-stop(4))<4,round(y)); await pg.screenshot(path=S+"-4.png")
    await pg.wait_for_timeout(700); await swipe(300); await pg.wait_for_timeout(1500); y=await pg.evaluate("scrollY"); chk("от последната излиза надолу",y>info["end"]+20,round(y))
    tapd=await pg.evaluate("(()=>{window.scrollTo(0,0);return 1})()")
    chk("без JS грешки",not errs,errs[:2]); await b.close(); print("РЕЗУЛТАТ",sum(res),"/",len(res))
asyncio.run(main())
