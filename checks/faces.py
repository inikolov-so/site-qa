# Отрязани лица: за всяка снимка на страницата, на всеки размер, смята какво точно се вижда след
# object-fit: cover + object-position и проверява дали лицата (с челото и брадичката) са вътре.
#   python checks/faces.py <base-url> <out> [--pages index.html,a.html] [--views phones|all]
# Изход: <out>/faces.json + <out>/faces.png (лист с проблемните изрези, лицето в червено) и код 1 при проблем.
# Модел: YuNet (OpenCV, models/face_detection_yunet_2023mar.onnx), работи локално, без интернет.
import sys, json, asyncio, pathlib, argparse, re, io, urllib.request, os
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
import cv2, numpy as np
from PIL import Image, ImageDraw
from playwright.async_api import async_playwright

HERE = pathlib.Path(__file__).resolve().parent
MODEL = str(HERE.parent / "models/face_detection_yunet_2023mar.onnx")
VIEWS = [  # име, ширина, височина, dpr, телефон
    ("iPhone SE 320", 320, 568, 2, True), ("iPhone 13 390", 390, 844, 3, True), ("Android 412", 412, 915, 2.6, True),
    ("iPad 768", 768, 1024, 2, True), ("лаптоп 1366", 1366, 768, 1, False), ("Mac 1440", 1440, 900, 2, False),
    ("десктоп 1920", 1920, 1080, 1, False),
]
TOP, BOTTOM, SIDE = 0.40, 0.15, 0.10     # главата около лицето: чело/коса, брадичка, страни (дял от лицето)
NEED = 0.88                              # колко от главата трябва да се вижда

ap = argparse.ArgumentParser(); ap.add_argument("base"); ap.add_argument("out")
ap.add_argument("--pages", default="index.html"); ap.add_argument("--views", default="all")
a = ap.parse_args()
base = a.base.rstrip("/"); out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
views = [v for v in VIEWS if a.views == "all" or v[4]]

_faces, _imgs = {}, {}
def faces_of(url):
    if url in _faces: return _faces[url], _imgs[url]
    raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "site-qa"}), timeout=60).read()
    im = Image.open(io.BytesIO(raw)).convert("RGB"); W, H = im.size
    s = min(1.0, 1280 / max(W, H)); sm = im.resize((max(1, int(W * s)), max(1, int(H * s))))
    bgr = cv2.cvtColor(np.array(sm), cv2.COLOR_RGB2BGR)
    d = cv2.FaceDetectorYN_create(MODEL, "", (bgr.shape[1], bgr.shape[0]), 0.8, 0.3, 5000)
    _, f = d.detect(bgr)
    res = [] if f is None else [dict(x=float(r[0] / s / W), y=float(r[1] / s / H), w=float(r[2] / s / W), h=float(r[3] / s / H)) for r in f if r[2] / s / W > 0.02]
    _faces[url], _imgs[url] = res, im
    return res, im

def pos_frac(token, free_px):   # object-position по една ос → дял (0..1) от свободното място
    token = token.strip()
    if token.endswith("%"): return float(token[:-1]) / 100
    if token in ("left", "top"): return 0.0
    if token in ("right", "bottom"): return 1.0
    if token == "center": return 0.5
    if token.endswith("px"): return float(token[:-2]) / free_px if free_px else 0.5
    return 0.5

JS = """() => [...document.images].map(im => {
  const cs = getComputedStyle(im), w = im.clientWidth, h = im.clientHeight;
  let hidden = false; for (let e = im; e; e = e.parentElement) { const c = getComputedStyle(e); if (c.display === 'none') { hidden = true; break; } }
  return { src: im.currentSrc || im.src, nw: im.naturalWidth, nh: im.naturalHeight, w, h, fit: cs.objectFit, pos: cs.objectPosition,
           sel: (im.id ? '#' + im.id : '') + (im.className ? '.' + String(im.className).split(' ').join('.') : '') || im.getAttribute('src'),
           alt: im.alt || '', hidden };
})"""

async def main():
    report, bad_shots = [], []
    async with async_playwright() as pw:
        br = await pw.chromium.launch()
        for name, w, h, dpr, mobile in views:
            for pg_name in a.pages.split(","):
                ctx = await br.new_context(viewport={"width": w, "height": h}, device_scale_factor=dpr, is_mobile=mobile and w < 700, has_touch=mobile)
                pg = await ctx.new_page()
                await pg.goto(base + "/" + pg_name, wait_until="load", timeout=90000)
                await pg.wait_for_timeout(1500)
                H = await pg.evaluate("document.documentElement.scrollHeight")
                for y in range(0, H, int(h * 0.8)):              # мързеливите снимки се зареждат
                    await pg.evaluate(f"window.scrollTo(0,{y})"); await pg.wait_for_timeout(60)
                await pg.wait_for_timeout(1500)
                items = await pg.evaluate(JS)
                await ctx.close()
                for it in items:
                    if it["hidden"] or it["w"] < 40 or it["h"] < 40 or not it["nw"] or not it["src"] or it["fit"] != "cover": continue
                    try: fs, im = faces_of(it["src"])
                    except Exception as e: report.append(dict(view=name, page=pg_name, img=it["src"], kind="fetch-failed", text=str(e)[:120])); continue
                    if not fs: continue
                    nw, nh, bw, bh = it["nw"], it["nh"], it["w"], it["h"]
                    k = max(bw / nw, bh / nh); vw, vh = bw / k / nw, bh / k / nh     # видимото като дял от снимката
                    toks = it["pos"].split()
                    px = pos_frac(toks[0], (nw * k - bw)); py = pos_frac(toks[1] if len(toks) > 1 else "50%", (nh * k - bh))
                    x0, y0 = (1 - vw) * px, (1 - vh) * py
                    heads = []
                    for f in fs:
                        hx0, hx1 = f["x"] - SIDE * f["w"], f["x"] + f["w"] * (1 + SIDE)
                        hy0, hy1 = f["y"] - TOP * f["h"], f["y"] + f["h"] * (1 + BOTTOM)
                        hx0, hy0, hx1, hy1 = max(0, hx0), max(0, hy0), min(1, hx1), min(1, hy1)   # извън снимката по начало: не е наша вина
                        ix = max(0, min(hx1, x0 + vw) - max(hx0, x0)); iy = max(0, min(hy1, y0 + vh) - max(hy0, y0))
                        seen = ix * iy / max(1e-9, (hx1 - hx0) * (hy1 - hy0))
                        heads.append((hx0, hy0, hx1, hy1, seen))
                    worst = min(hd[4] for hd in heads)
                    if worst >= NEED: continue
                    # предложение: главите (всички) в средата на видимото, по осите, където има изрязване
                    ux0, uy0 = min(hd[0] for hd in heads), min(hd[1] for hd in heads); ux1, uy1 = max(hd[2] for hd in heads), max(hd[3] for hd in heads)
                    sx = 50 if vw >= 0.999 else round(100 * min(1, max(0, ((ux0 + ux1) / 2 - vw / 2) / (1 - vw))))
                    sy = 50 if vh >= 0.999 else round(100 * min(1, max(0, min(uy0 - 0.02, (uy0 + uy1) / 2 - vh / 2) / (1 - vh))))
                    r = dict(view=name, page=pg_name, kind="face-cut", img=it["src"].split("?")[0].replace(base, ""), sel=it["sel"], alt=it["alt"][:60],
                             box=f"{bw}x{bh}", pos=it["pos"], seen=round(worst, 2), suggest=f"{sx}% {sy}%")
                    report.append(r)
                    W, Hh = im.size; crop = im.crop((int(x0 * W), int(y0 * Hh), int((x0 + vw) * W), int((y0 + vh) * Hh))).copy()
                    dr = ImageDraw.Draw(crop)
                    for hd in heads: dr.rectangle([(hd[0] - x0) * W, (hd[1] - y0) * Hh, (hd[2] - x0) * W, (hd[3] - y0) * Hh], outline=(230, 30, 30), width=max(3, W // 200))
                    crop.thumbnail((360, 360)); bad_shots.append((f"{name} · {r['img'].split('/')[-1]}", crop))
        await br.close()
    (out / "faces.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    if bad_shots:
        cols = 5; cw, ch = 380, 400; rows = (len(bad_shots) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cw, rows * ch), "white"); d = ImageDraw.Draw(sheet)
        for i, (t, c) in enumerate(bad_shots):
            x, y = (i % cols) * cw + 10, (i // cols) * ch + 10; sheet.paste(c, (x, y + 22)); d.text((x, y), t, fill=(0, 0, 0))
        sheet.save(out / "faces.png")
    seen_keys = {}
    for r in report:
        if r["kind"] == "face-cut": seen_keys.setdefault((r["img"], r["sel"]), []).append(f"{r['view']} ({int(r['seen']*100)} % от главата, предложение {r['suggest']})")
    for (img, sel), vs in seen_keys.items(): print("ОТРЯЗАНО ЛИЦЕ", img, sel, "→", "; ".join(vs))
    print("ОБЩО:", len(seen_keys), "снимки с отрязани лица" if seen_keys else "лицата се виждат навсякъде")
    sys.exit(1 if seen_keys else 0)

asyncio.run(main())
