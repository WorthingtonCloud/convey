// Design lint, the browser half: every run of visible text on the slide, what it sits on, and (second call) the
// pixels under it with the words hidden. Read by convey/design.py. Standard browser APIs only.
//
// window.conveyDesign.collect()  -> {variant, pattern, tokens, texts: [{id, bind, cls, text, words, size, weight,
//                                   color, rects, painted, ph}]} and hides the slide's words
// window.conveyDesign.sample(dataUrl) -> per text, its contrast against the drawn background
(() => {
  const slide = document.querySelector('.slide');
  const cv = document.createElement('canvas').getContext('2d');

  // Any CSS color as [r, g, b, a] (0-255, alpha 0-1): the canvas parses it, then we read back what it stored.
  function rgba(c) {
    cv.fillStyle = '#000000';
    cv.fillStyle = c;
    const s = cv.fillStyle;
    let m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(s);
    if (m) return [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16), 1];
    m = /^rgba?\(([^)]+)\)$/.exec(s);
    if (m) {
      const p = m[1].split(',').map(Number);
      return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1];
    }
    m = /^color\(srgb ([\d.e+-]+) ([\d.e+-]+) ([\d.e+-]+)(?: \/ ([\d.e+-]+))?\)$/.exec(s);
    if (m) return [m[1] * 255, m[2] * 255, m[3] * 255, m[4] === undefined ? 1 : +m[4]];
    return null;
  }

  function opacityOf(el) {
    let o = 1;
    for (let e = el; e && e !== document.documentElement; e = e.parentElement) o *= +getComputedStyle(e).opacity;
    return o;
  }

  // Did the slide itself paint something under this point (a panel, a band, a photo, a full-bleed ground), or does
  // the text sit straight on the template's own background (the layout picture, else the slide's ground)?
  function paintedUnder(el, x, y) {
    const stack = document.elementsFromPoint(x, y);
    let i = stack.findIndex(e => e === el || e.contains(el));
    if (i < 0) i = 0;
    for (; i < stack.length; i++) {
      const e = stack[i];
      if (e === slide || e.dataset?.underlay !== undefined || !slide.contains(e)) return false;
      if (e.tagName === 'IMG') return true;
      if (e instanceof SVGGraphicsElement && !(e instanceof SVGSVGElement)) {
        const f = getComputedStyle(e).fill;
        if (f && f !== 'none' && (rgba(f) || [0, 0, 0, 0])[3] > 0) return true;
        continue;
      }
      const cs = getComputedStyle(e);
      if (cs.backgroundImage !== 'none') return true;
      const bg = rgba(cs.backgroundColor);
      if (bg && bg[3] > 0) return true;
    }
    return false;
  }

  function collect() {
    if (!slide) return {error: 'no .slide'};
    const root = getComputedStyle(slide);
    const tokens = {};
    for (const k of ['ground', 'ink', 'body', 'muted', 'raised', 'rule', 'signal', 'data-1', 'data-2', 'data-3',
      'data-4', 'data-5', 'title-color', 'body-color']) {
      const v = root.getPropertyValue(`--brand-${k}`).trim();
      if (v) tokens[k] = rgba(v);
    }
    const texts = [];
    const walk = document.createTreeWalker(slide, NodeFilter.SHOW_TEXT);
    for (let n = walk.nextNode(); n; n = walk.nextNode()) {
      const t = n.textContent.replace(/\s+/g, ' ').trim();
      const el = n.parentElement;
      if (!t || !el || el.closest('svg, style, script, [data-underlay]')) continue;
      const cs = getComputedStyle(el);
      if (cs.visibility !== 'visible' || cs.display === 'none') continue;
      const r = document.createRange();
      r.selectNodeContents(n);
      const rects = [...r.getClientRects()].filter(q => q.width > 0.5 && q.height > 0.5)
        .map(q => ({x: q.left, y: q.top, w: q.width, h: q.height}));
      if (!rects.length) continue;
      const color = rgba(cs.color) || [0, 0, 0, 1];
      color[3] *= opacityOf(el);
      const owner = el.closest('[data-id]');
      const bound = el.closest('[data-bind]');
      const ph = el.closest('[data-ph]');
      const painted = rects.filter(q => paintedUnder(el, q.x + q.w / 2, q.y + q.h / 2)).length * 2 >= rects.length;
      texts.push({id: owner ? owner.dataset.id : el.tagName.toLowerCase(), bind: bound ? bound.dataset.bind : '',
        cls: (owner || el).className && typeof (owner || el).className === 'string' ? (owner || el).className : '',
        text: t, words: t.split(' ').length, size: parseFloat(cs.fontSize), weight: parseInt(cs.fontWeight, 10) || 400,
        color, rects, painted, ph: ph ? ph.dataset.ph : null});
    }
    // Hide the words (glyph fill only, so icons and borders drawn in currentColor stay): the next screenshot is
    // exactly what each line of text sits on.
    const st = document.createElement('style');
    st.textContent = '.slide, .slide * { -webkit-text-fill-color: transparent !important; ' +
      'text-decoration-color: transparent !important; } .slide ::marker { color: transparent !important; }';
    document.head.appendChild(st);
    return {pattern: slide.dataset.pattern || null, variant: slide.dataset.variant || null,
      slideId: slide.dataset.slide || null, tokens, texts};
  }

  const lum = c => {
    const f = v => { v /= 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
  };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const hex = c => '#' + c.slice(0, 3).map(v => Math.round(v).toString(16).padStart(2, '0')).join('').toUpperCase();

  // The glyphs fill roughly the middle of a text rect; sample that band on a 2 px grid. The score is the contrast
  // at the background's worst tenth, so one stray light pixel doesn't fail a line and a busy patch does.
  async function sample(dataUrl, texts) {
    const img = new Image();
    img.src = dataUrl;
    await img.decode();
    const c = document.createElement('canvas');
    c.width = img.width; c.height = img.height;
    const g = c.getContext('2d', {willReadFrequently: true});
    g.drawImage(img, 0, 0);
    const W = c.width, H = c.height;
    const px = g.getImageData(0, 0, W, H).data;
    return texts.map(t => {
      const out = [];
      for (const q of t.rects) {
        const x0 = Math.max(0, Math.floor(q.x)), x1 = Math.min(W - 1, Math.ceil(q.x + q.w));
        const y0 = Math.max(0, Math.floor(q.y + q.h * 0.2)), y1 = Math.min(H - 1, Math.ceil(q.y + q.h * 0.8));
        for (let y = y0; y <= y1; y += 2) for (let x = x0; x <= x1; x += 2) {
          const i = (y * W + x) * 4;
          const bg = [px[i], px[i + 1], px[i + 2]];
          const a = t.color[3];
          const fg = [0, 1, 2].map(k => t.color[k] * a + bg[k] * (1 - a));
          out.push([ratio(fg, bg), bg]);
        }
      }
      if (!out.length) return null;
      out.sort((p, q) => p[0] - q[0]);
      const worst = out[Math.floor(out.length * 0.1)];
      return {contrast: worst[0], at: hex(worst[1]), median: hex(out[Math.floor(out.length / 2)][1]), fg: hex(t.color)};
    });
  }

  window.conveyDesign = {collect, sample};
})();
