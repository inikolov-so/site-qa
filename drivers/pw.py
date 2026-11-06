# Драйверът за настолни браузъри и за телефони в емулация (Playwright).
#   python pw.py <base-url> <платформа> <out> [--pages a.html,b.html] [--channel chrome|msedge] [--engine chromium|firefox|webkit] [--headed]
# Минава всяка страница на всеки размер, скролва на стъпки, на всяка стъпка пуска checks.js и снима.
import sys, json, asyncio, pathlib, argparse, re, urllib.request
from playwright.async_api import async_playwright
HERE = pathlib.Path(__file__).resolve().parent
CHECKS = (HERE.parent / "checks/checks.js").read_text(encoding="utf-8")
VIEWS = {
  "windows": [("1536x730@1.25", 1536, 730, 1.25), ("1920x950@1", 1920, 950, 1), ("1366x650@1", 1366, 650, 1), ("1280x600@1.5", 1280, 600, 1.5)],
  "mac": [("1440x790@2", 1440, 790, 2), ("1512x860@2", 1512, 860, 2), ("1920x1000@1", 1920, 1000, 1)],
}
ap = argparse.ArgumentParser(); ap.add_argument("base"); ap.add_argument("plat"); ap.add_argument("out")
ap.add_argument("--pages", default=""); ap.add_argument("--channel", default=None); ap.add_argument("--engine", default="chromium")
ap.add_argument("--headed", action="store_true"); ap.add_argument("--shots", default="index.html"); ap.add_argument("--wait", type=int, default=1200)
a = ap.parse_args()
base = a.base.rstrip("/"); out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)

def page_list():
    if a.pages: return a.pages.split(",")
    html = urllib.request.urlopen(urllib.request.Request(base + "/index.html", headers={"User-Agent": "site-qa"})).read().decode("utf-8", "ignore")
    found = sorted(set(re.findall(r'href="([a-z0-9\-]+\.html)"', html)))
    return ["index.html"] + [p for p in found if p != "index.html"]

async def run_view(browser, label, w, h, dpr, pages, report):
    for pg_name in pages:
        ctx = await browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=dpr, locale="bg-BG")
        pg = await ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append("js: " + str(e)[:200]))
        pg.on("console", lambda m: errs.append("console: " + m.text[:200]) if m.type == "error" else None)
        pg.on("response", lambda r: errs.append(f"http {r.status}: {r.url[:120]}") if r.status >= 400 else None)
        try:
            await pg.goto(base + "/" + pg_name, wait_until="load", timeout=90000)
        except Exception as e:
            report.append({"page": pg_name, "view": label, "kind": "load-failed", "text": str(e)[:200]}); await ctx.close(); continue
        await pg.add_script_tag(content=CHECKS)
        await pg.wait_for_timeout(2200)
        facts = await pg.evaluate("__siteQAFacts()")
        if pg_name == pages[0]: print(label, json.dumps(facts, ensure_ascii=False), flush=True)
        H = facts["H"]; y = 0; step = int(h * 0.72); i = 0; shoot = pg_name in a.shots.split(",")
        seen = set()
        while True:
            await pg.evaluate(f"window.scrollTo({{top:{y},behavior:'instant'}});window.__lenis&&window.__lenis.scrollTo({y},{{immediate:true,force:true}})")
            await pg.wait_for_timeout(a.wait)
            found = await pg.evaluate("__siteQA()")
            for f in found:
                k = (f["kind"], f.get("at"), f.get("text"))
                if k in seen: continue
                seen.add(k); f.update(page=pg_name, view=label, y=y); report.append(f)
            if shoot:
                await pg.screenshot(path=str(out / f"{pg_name[:-5]}_{label}_{i:03d}.png"))
            H = await pg.evaluate("document.documentElement.scrollHeight")
            if y >= H - h: break
            y = min(y + step, H - h); i += 1
            if i > 220: break
        for e in sorted(set(errs)): report.append({"page": pg_name, "view": label, "kind": "error", "text": e})
        await ctx.close()

async def main():
    report = []; pages = page_list(); print(len(pages), "страници", flush=True)
    async with async_playwright() as p:
        eng = getattr(p, a.engine)
        kw = {"headless": not a.headed}
        if a.channel: kw["channel"] = a.channel
        if a.headed and a.engine == "chromium": kw["ignore_default_args"] = ["--hide-scrollbars"]
        b = await eng.launch(**kw)
        # първите два размера минават всички страници, останалите само началната и страниците със снимки
        for n, (label, w, h, dpr) in enumerate(VIEWS[a.plat]):
            ps = pages if n < 2 else [p for p in pages if p in a.shots.split(",")] or pages[:1]
            await run_view(b, label, w, h, dpr, ps, report)
            (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        await b.close()
    kinds = {}
    for r in report: kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    print("ОБЩО:", kinds)
asyncio.run(main())
