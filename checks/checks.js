/* Общият детектор: инжектира се в страницата на всяка платформа и връща проблемите на видимия екран.
   Мери МАСТИЛОТО на буквите (не кутията на реда): така хваща изрязано „У“ и застъпени редове,
   които getBoundingClientRect не вижда. Без зависимости, работи в Chrome, Edge, Firefox, Safari. */
window.__siteQA = function () {
  var out = [], W = innerWidth, H = innerHeight;
  var cv = document.createElement("canvas").getContext("2d");
  var path = function (el) { var p = [], e = el; for (var i = 0; e && e !== document.body && i < 4; i++, e = e.parentElement) { p.unshift(e.tagName.toLowerCase() + (typeof e.className === "string" && e.className ? "." + e.className.trim().split(/\s+/)[0] : "")); } return p.join(" > "); };
  var push = function (kind, el, text, extra) { out.push(Object.assign({ kind: kind, at: el ? path(el) : "", text: (text || "").trim().slice(0, 60) }, extra || {})); };
  var seen = function (el) { for (var e = el, o = 1; e && e.nodeType === 1; e = e.parentElement) { var c = getComputedStyle(e); if (c.visibility === "hidden" || c.display === "none") return 0; o *= parseFloat(c.opacity); } return o; };
  var SKIP = ".marquee,.cursor-label,.curtain,.sr,.sr-only,script,style,noscript,[data-qa-skip]";

  // 1. страницата не бива да се скролва настрани
  var sw = document.documentElement.scrollWidth, cw = document.documentElement.clientWidth;
  if (sw > cw + 1) push("overflow-x", document.body, "", { scrollWidth: sw, clientWidth: cw });

  // 2. мастилото на всеки видим знак
  var lines = [], tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT), n;
  while ((n = tw.nextNode())) {
    var txt = n.textContent; if (!txt.trim()) continue;
    var el = n.parentElement; if (!el || el.closest(SKIP)) continue;
    var op = seen(el); if (op < 0.5) continue;
    var cs = getComputedStyle(el), size = parseFloat(cs.fontSize); if (size < 9) continue;
    var r0 = document.createRange(); r0.selectNodeContents(n);
    var box = r0.getBoundingClientRect(); if (box.bottom < 0 || box.top > H || box.right < 0 || box.left > W) continue;
    cv.font = cs.fontStyle + " " + cs.fontWeight + " " + cs.fontSize + " " + cs.fontFamily;
    var upper = cs.textTransform === "uppercase";
    var fm = cv.measureText("Hg"), fa = fm.fontBoundingBoxAscent, fd = fm.fontBoundingBoxDescent;
    if (!isFinite(fa)) continue;
    for (var i = 0; i < txt.length; i++) {
      var ch = txt[i]; if (/\s/.test(ch)) continue;
      var r = document.createRange(); r.setStart(n, i); r.setEnd(n, i + 1);
      var b = r.getClientRects()[0]; if (!b || b.width < 0.5) continue;
      if (b.bottom < 0 || b.top > H) continue;
      var sc = b.height / (fa + fd) || 1;                       // трансформации (scale) на родителя
      var m = cv.measureText(upper ? ch.toUpperCase() : ch);
      var base = b.top + fa * sc;
      lines.push({ el: el, ch: ch, x1: b.left - m.actualBoundingBoxLeft * sc, x2: b.left + m.actualBoundingBoxRight * sc,
        y1: base - m.actualBoundingBoxAscent * sc, y2: base + m.actualBoundingBoxDescent * sc, base: base, size: size, txt: txt });
    }
  }
  // 2а. изрязано мастило: сравнява със всички предци, които режат
  var clipCache = new Map();
  var clipsOf = function (el) {
    if (clipCache.has(el)) return clipCache.get(el);
    var res = [];
    for (var e = el; e && e !== document.documentElement; e = e.parentElement) {
      var c = getComputedStyle(e);
      if (e !== document.body && (c.overflowX !== "visible" || c.overflowY !== "visible" || c.clipPath !== "none")) res.push({ e: e, r: e.getBoundingClientRect(), xclip: c.overflowX !== "visible", yclip: c.overflowY !== "visible", path: c.clipPath !== "none" });
      if (c.position === "fixed") break;
    }
    clipCache.set(el, res); return res;
  };
  var clipped = {};
  lines.forEach(function (g) {
    clipsOf(g.el).forEach(function (c) {
      if (c.path) return;
      var cut = 0, side = "";
      if (c.yclip && g.y2 > c.r.bottom + 0.6) { cut = g.y2 - c.r.bottom; side = "долу"; }
      if (c.yclip && g.y1 < c.r.top - 0.6) { cut = Math.max(cut, c.r.top - g.y1); side = side || "горе"; }
      var scroller = /auto|scroll/.test(getComputedStyle(c.e).overflowX) || c.e.matches(".hscroll,.hscroll *,.carousel,.carousel *");
      if (!scroller && c.xclip && g.x2 > c.r.right + 0.6 && g.x1 < c.r.right) { cut = Math.max(cut, g.x2 - c.r.right); side = side || "вдясно"; }
      if (!scroller && c.xclip && g.x1 < c.r.left - 0.6 && g.x2 > c.r.left) { cut = Math.max(cut, c.r.left - g.x1); side = side || "вляво"; }
      if (cut >= 1 && g.y2 > 0 && g.y1 < H && g.y2 > c.r.top && g.y1 < c.r.bottom) {
        // цял ред извън рамката е пагинация на скрита карта, не изрязване
        if (g.y1 >= c.r.bottom || g.y2 <= c.r.top) return;
        var k = path(g.el) + "|" + side; if (!clipped[k]) { clipped[k] = 1; push("clipped-ink", g.el, g.txt, { letter: g.ch, side: side, px: +cut.toFixed(1), by: path(c.e) }); }
      }
    });
  });
  // 2б. застъпено мастило: знаци от различни редове, които се докосват
  var over = {};
  var byBlock = new Map();
  lines.forEach(function (g) { var b = g.el.closest("h1,h2,h3,h4,p,li,a,button,span,div,figcaption") || g.el; var k = b.closest("h1,h2,h3,h4") || b; if (!byBlock.has(k)) byBlock.set(k, []); byBlock.get(k).push(g); });
  byBlock.forEach(function (gs, block) {
    if (gs.length > 400) return;
    for (var a = 0; a < gs.length; a++) for (var c = a + 1; c < gs.length; c++) {
      var A = gs[a], B = gs[c];
      if (Math.abs(A.base - B.base) < A.size * 0.5) continue;             // един и същи ред
      var ix = Math.min(A.x2, B.x2) - Math.max(A.x1, B.x1), iy = Math.min(A.y2, B.y2) - Math.max(A.y1, B.y1);
      if (ix > 1 && iy > 0.5) { var k = path(block); if (!over[k]) { over[k] = 1; push("overlap-lines", block, A.txt, { letters: A.ch + "/" + B.ch, px: +iy.toFixed(1) }); } }
    }
  });
  // 2в. застъпено между различни блокове: точка от мастилото, върху която лежи чужд текст
  var bigs = lines.filter(function (g, i) { return i % 3 === 0; });
  var pairs = {};
  for (var a = 0; a < bigs.length; a++) for (var c = a + 1; c < bigs.length; c++) {
    var A = bigs[a], B = bigs[c]; if (A.el === B.el || A.el.contains(B.el) || B.el.contains(A.el)) continue;
    if (A.el.closest("h1,h2,h3,h4,p,li") && A.el.closest("h1,h2,h3,h4,p,li") === B.el.closest("h1,h2,h3,h4,p,li")) continue;
    var ix = Math.min(A.x2, B.x2) - Math.max(A.x1, B.x1), iy = Math.min(A.y2, B.y2) - Math.max(A.y1, B.y1);
    if (ix > 2 && iy > 2) {
      var cx = (Math.max(A.x1, B.x1) + Math.min(A.x2, B.x2)) / 2, cy = (Math.max(A.y1, B.y1) + Math.min(A.y2, B.y2)) / 2;
      var top = document.elementFromPoint(cx, cy); if (!top) continue;
      var aT = top === A.el || A.el.contains(top) || top.contains(A.el), bT = top === B.el || B.el.contains(top) || top.contains(B.el);
      if (aT && bT) { var k = path(A.el) + "|" + path(B.el); if (!pairs[k]) { pairs[k] = 1; push("overlap-blocks", A.el, A.txt, { with: B.txt.trim().slice(0, 40), withAt: path(B.el), px: +iy.toFixed(1) }); } }
    }
  }
  // 3. текст, отрязан от контейнера (многоточие, скрито съдържание)
  document.querySelectorAll("h1,h2,h3,h4,p,li,a,button,span").forEach(function (el) {
    if (el.closest(SKIP) || el.closest(".carousel__track,.hscroll,.deck__stack,.btn,.carousel")) return;
    var c = getComputedStyle(el); if (c.overflowX === "visible" && c.overflowY === "visible") return;
    if (seen(el) < 0.5 || !el.textContent.trim()) return;
    var rr = el.getBoundingClientRect(); if (rr.bottom < 0 || rr.top > H) return;
    if (el.scrollWidth > el.clientWidth + 2 || el.scrollHeight > el.clientHeight + 2) push("truncated", el, el.textContent, { sw: el.scrollWidth, cw: el.clientWidth, sh: el.scrollHeight, ch: el.clientHeight });
  });
  // 4. липсващ шрифт: заглавия с резервен шрифт
  ["Oswald", "Montserrat"].forEach(function (f) { if (document.fonts && document.documentElement.innerHTML.indexOf(f) > -1 && !document.fonts.check('500 20px "' + f + '"', "Щ")) push("font-missing", null, f); });
  return out;
};
window.__siteQAFacts = function () {
  return { ua: navigator.userAgent, dpr: devicePixelRatio, w: innerWidth, h: innerHeight, cw: document.documentElement.clientWidth,
    sbw: innerWidth - document.documentElement.clientWidth, H: document.documentElement.scrollHeight,
    hover: matchMedia("(hover:hover) and (pointer:fine)").matches, reduce: matchMedia("(prefers-reduced-motion:reduce)").matches };
};
