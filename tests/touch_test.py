# Жест с пръст през DevTools (Chrome), режим Soft: филмът върви с пръста, спирките задържат, нищо не тръгва само.
import sys, asyncio
from playwright.async_api import async_playwright
url=sys.argv[1]; S=sys.argv[2]
async def main():
  async with async_playwright() as p:
    b=await p.chromium.launch(channel="chrome")
    ctx=await b.new_context(**p.devices["Pixel 7"]); pg=await ctx.new_page()
    await pg.add_init_script("""(()=>{const o=CanvasRenderingContext2D.prototype.drawImage;window.__stillDraws=[];CanvasRenderingContext2D.prototype.drawImage=function(s,...r){if(s instanceof HTMLImageElement&&r.length>=8)window.__stillDraws.push([s.srcset||'',s.naturalWidth,s.naturalHeight,r[2],r[3]]);return o.call(this,s,...r)}})()""")
    errs=[]; pg.on("pageerror",lambda e:errs.append(str(e)[:200]))
    await pg.goto(url,wait_until="load"); await pg.wait_for_timeout(3500)
    c=await ctx.new_cdp_session(pg)
    info=await pg.evaluate("(()=>{const w=document.querySelector('[data-walk]'),s=w.querySelector('.walk__stage');const t=w.getBoundingClientRect().top+scrollY;return {top:t,end:t+w.offsetHeight-s.offsetHeight,n:w.querySelectorAll('.walk__frame').length,vh:innerHeight,vw:innerWidth,fr:w.classList.contains('has-frames')}})()"); print(info)
    Sv=lambda: pg.evaluate("document.querySelector('[data-walk]')._s")
    async def swipe(dist,steps=10,ms=16):
      x=info["vw"]/2; y0=info["vh"]*.75 if dist>0 else info["vh"]*.25
      await c.send("Input.dispatchTouchEvent",{"type":"touchStart","touchPoints":[{"x":x,"y":y0}]})
      for i in range(1,steps+1):
        await c.send("Input.dispatchTouchEvent",{"type":"touchMove","touchPoints":[{"x":x,"y":y0-dist*i/steps}]}); await pg.wait_for_timeout(ms)
      await c.send("Input.dispatchTouchEvent",{"type":"touchEnd","touchPoints":[]})
    res=[]
    def chk(n,ok,i=""): res.append(ok); print("ДА " if ok else "НЕ ",n,i,flush=True)
    near=lambda s,i: abs(s-i)<1e-3
    await pg.screenshot(path=S+"-0.png")
    await swipe(90,10,30); await pg.wait_for_timeout(1500); s=await Sv(); chk("малък жест на спирка 0 → кадърът стои",near(s,0),round(s,3))
    seen=[]
    for _ in range(7):
      await swipe(260,10,30); await pg.wait_for_timeout(1400); seen.append(round(await Sv(),3))
    print("   s след всеки жест:",seen)
    chk("филмът върви с пръста на стъпки",len(set(seen))>=4 and all(b2>=a2-1e-3 for a2,b2 in zip(seen,seen[1:])))
    chk("един жест не прелита повече от спирка",all(b2-a2<=1.05 for a2,b2 in zip([0]+seen,seen)))
    await pg.screenshot(path=S+"-1.png")
    for _ in range(2): await swipe(-260,10,30); await pg.wait_for_timeout(1400)
    s2=await Sv(); chk("жестове нагоре връщат филма",s2<seen[-1],(seen[-1],round(s2,3)))
    await pg.evaluate(f"scrollTo(0,{info['end']})"); await pg.wait_for_timeout(600)
    await swipe(400); await pg.wait_for_timeout(1500); y=await pg.evaluate("scrollY"); chk("от последната излиза надолу",y>info["end"]+20,round(y))
    sd=await pg.evaluate("__stillDraws"); bad=[x for x in sd if x[0] or max(x[3]/x[1],x[4]/x[2])<0.97]
    chk("снимката на спирката в истинските си пиксели",sd and not bad,f"{len(sd)} рисувания, лоши {len(bad)}")
    chk("без JS грешки",not errs,errs[:2]); await b.close(); print("РЕЗУЛТАТ",sum(res),"/",len(res))
asyncio.run(main())
