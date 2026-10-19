// Runs inside the page. Measures the rendered slide and returns the scene graph.
// Coordinates are CSS pixels relative to the slide's top-left corner.
// Paint order is the order elements appear in `elements`.
//
// errors   = things that cannot convert faithfully (lint failures; export should refuse)
// warnings = things that convert, with a caveat
(() => {
  const slide = document.querySelector('.slide');
  if (!slide) return { error: 'no .slide element' };
  const S = slide.getBoundingClientRect();
  const warnings = [];
  const notes = [];  // advice for the agent (lint -v): never graded as a conversion problem
  const errors = [];
  const elements = [];
  const texts = [];  // each text element with its node, for the checks that need the page (panels, charts)
  let auto = 0;
  const ids = new WeakMap();

  const px = v => parseFloat(v) || 0;

  // rgb()/rgba(), or color(srgb r g b / a): what the browser computes for a brand color mixed with transparency,
  // color-mix(in srgb, var(--brand-data-2) 50%, transparent), so a token color can carry its own alpha.
  function color(c, where) {
    if (!c || c === 'transparent' || c === 'none') return null;
    const srgb = c.match(/^color\(srgb\s+([^)]+)\)$/);
    const m = srgb || c.match(/^rgba?\(([^)]+)\)$/);
    if (!m) { errors.push(`${where || 'color'}: unsupported color syntax ${c}`); return null; }
    const p = m[1].split(/[\s,\/]+/).filter(Boolean).map(Number);
    if (srgb) for (let i = 0; i < 3; i++) p[i] *= 255;
    const a = p.length > 3 ? p[3] : 1;
    if (a === 0) return null;
    return { hex: p.slice(0, 3).map(n => Math.round(n).toString(16).padStart(2, '0')).join(''), a };
  }

  // One CSS gradient as a box's fill: linear (an angle or "to <side>") or radial ("circle at X% Y%" or plain
  // "circle"/"ellipse", sized to the farthest corner), with color stops at % positions. Anything else is refused.
  // PowerPoint draws both natively (a:gradFill); the bench proves each against PowerPoint's own PDF.
  function splitTop(s) {
    const out = []; let depth = 0, cur = '';
    for (const ch of s) {
      if (ch === '(') depth++;
      if (ch === ')') depth--;
      if (ch === ',' && depth === 0) { out.push(cur.trim()); cur = ''; } else cur += ch;
    }
    if (cur.trim()) out.push(cur.trim());
    return out;
  }
  function gradientOf(bg, r, where) {
    if (!bg || bg === 'none') return null;
    const m = bg.match(/^(linear|radial)-gradient\((.*)\)$/s);
    if (!m || /\)\s*,\s*(?:repeating-)?(?:linear|radial|conic)-gradient|url\(/.test(bg)) return { bad: 'only one linear or radial gradient converts' };
    const parts = splitTop(m[2]);
    const g = { kind: m[1], stops: [] };
    const first = parts[0];
    if (g.kind === 'linear') {
      g.angle = 180;
      const deg = first.match(/^(-?[\d.]+)(deg|turn|rad|grad)$/);
      const to = first.match(/^to\s+(.+)$/);
      if (deg) {
        const v = parseFloat(deg[1]);
        g.angle = deg[2] === 'deg' ? v : deg[2] === 'turn' ? v * 360 : deg[2] === 'rad' ? v * 180 / Math.PI : v * 0.9;
        parts.shift();
      } else if (to) {
        const k = to[1].split(/\s+/).sort().join(' ');
        const corner = Math.atan2(r.h, r.w) * 180 / Math.PI;  // CSS: perpendicular to the other diagonal
        const map = { 'top': 0, 'right': 90, 'bottom': 180, 'left': 270, 'right top': corner, 'bottom right': 180 - corner,
                      'bottom left': 180 + corner, 'left top': 360 - corner };
        if (!(k in map)) return { bad: `gradient direction "${first}"` };
        g.angle = map[k];
        parts.shift();
      }
      g.angle = ((g.angle % 360) + 360) % 360;
    } else {
      g.cx = 50; g.cy = 50; g.shape = 'ellipse';
      if (!/^(?:rgba?|color)\(/.test(first)) {
        const at = first.match(/^(circle|ellipse)?\s*(?:farthest-corner)?\s*(?:at\s+([\d.]+)%\s+([\d.]+)%)?$/);
        if (!at) return { bad: `radial gradient shape "${first}" (use circle or ellipse, at X% Y%, farthest corner)` };
        if (at[1]) g.shape = at[1];
        if (at[2]) { g.cx = parseFloat(at[2]); g.cy = parseFloat(at[3]); }
        parts.shift();
      }
    }
    if (g.kind === 'radial') {
      // PowerPoint's radial is a circle around the shape's centre: off-centre or stretched (CSS ellipse, its default)
      // it falls off at each edge instead (bench d02, Oct 18, 2026).
      if (Math.abs(g.cx - 50) > 0.5 || Math.abs(g.cy - 50) > 0.5)
        return { bad: 'a radial gradient converts only centred: put an off-centre glow in its own square box, centred on the glow' };
      if (g.shape === 'ellipse' && Math.abs(r.w - r.h) > 1)
        return { bad: 'a radial gradient on a non-square box converts only as a circle: write radial-gradient(circle, ...)' };
    }
    for (const p of parts) {
      const sm = p.match(/^((?:rgba?|color)\([^)]*\))\s*(?:(-?[\d.]+)%)?$/);
      if (!sm) return { bad: `gradient stop "${p}" (a color and a % position only)` };
      const c = color(sm[1], where) || { hex: '000000', a: 0 };
      g.stops.push({ ...c, pos: sm[2] === undefined ? null : parseFloat(sm[2]) });
    }
    if (g.stops.length < 2) return { bad: 'a gradient needs two color stops' };
    if (g.stops[0].pos === null) g.stops[0].pos = 0;
    if (g.stops[g.stops.length - 1].pos === null) g.stops[g.stops.length - 1].pos = 100;
    for (let i = 1; i < g.stops.length - 1; i++) if (g.stops[i].pos === null) {  // spread unplaced stops evenly
      let j = i; while (g.stops[j].pos === null) j++;
      const a = g.stops[i - 1].pos, b = g.stops[j].pos;
      for (let k = i; k < j; k++) g.stops[k].pos = a + (b - a) * (k - i + 1) / (j - i + 1);
    }
    for (let i = 1; i < g.stops.length; i++) g.stops[i].pos = Math.max(g.stops[i].pos, g.stops[i - 1].pos);
    return g;
  }

  // One outer CSS shadow, no spread: PowerPoint's own soft shadow (a:outerShdw) draws it.
  function shadowOf(v) {
    if (!v || v === 'none') return null;
    if (splitTop(v).length > 1) return { bad: 'only one shadow converts' };
    if (/\binset\b/.test(v)) return { bad: 'inset shadows don\'t convert' };
    const m = v.match(/^((?:rgba?|color)\([^)]*\))\s+(-?[\d.]+)px\s+(-?[\d.]+)px\s+([\d.]+)px(?:\s+(-?[\d.]+)px)?$/);
    if (!m) return { bad: `shadow "${v}" (write x y blur color)` };
    if (m[5] && Math.abs(parseFloat(m[5])) > 0.01) return { bad: 'shadow spread doesn\'t convert (use a bigger blur, or a bigger box)' };
    const c = color(m[1]);
    return c ? { color: c, x: parseFloat(m[2]), y: parseFloat(m[3]), blur: parseFloat(m[4]) } : null;
  }

  function opacityOf(el) {
    let o = 1;
    for (let e = el; e && e !== slide.parentElement; e = e.parentElement) o *= parseFloat(getComputedStyle(e).opacity);
    return o;
  }

  function rel(r) { return { x: r.left - S.left, y: r.top - S.top, w: r.width, h: r.height }; }

  // Elements without a data-id get an automatic name; lint messages add a locator for those.
  const hints = {};
  function nameOf(el) {
    if (!ids.has(el)) {
      const n = el.dataset.id || `${el.tagName.toLowerCase()}-${++auto}`;
      ids.set(el, n);
      if (!el.dataset.id) {
        const cls = typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).join('.') : '';
        const t = (el.textContent || '').replace(/\s+/g, ' ').trim();
        hints[n] = `<${el.tagName.toLowerCase()}${cls}>` + (t ? ` "${t.length > 32 ? t.slice(0, 32) + '…' : t}"` : '');
      }
    }
    return ids.get(el);
  }

  // ---------- rotation: measure rotated elements unrotated, record the angle ----------
  const rotated = new Map();
  for (const el of slide.querySelectorAll('*')) {
    if (el instanceof SVGElement && el.tagName.toLowerCase() !== 'svg') continue;
    const cs = getComputedStyle(el);
    if (cs.transform === 'none') continue;
    const m = new DOMMatrix(cs.transform);
    const sx = Math.hypot(m.a, m.b), sy = Math.hypot(m.c, m.d);
    const [ox, oy] = cs.transformOrigin.split(' ').map(px);
    const centered = Math.abs(ox - el.offsetWidth / 2) < 0.5 && Math.abs(oy - el.offsetHeight / 2) < 0.5;
    if (Math.abs(sx - 1) < 1e-3 && Math.abs(sy - 1) < 1e-3 && Math.abs(m.e) < 1e-3 && Math.abs(m.f) < 1e-3 && centered) {
      rotated.set(el, { angle: Math.atan2(m.b, m.a) * 180 / Math.PI, inline: el.style.getPropertyValue('transform') });
      el.style.setProperty('transform', 'none', 'important');
    } else {
      errors.push(`${nameOf(el)}: transform ${cs.transform} (only rotation about the center converts)`);
    }
  }

  // ---------- lint: effects PowerPoint can't reproduce as native objects ----------
  function lint(el, cs) {
    const n = nameOf(el);
    if (cs.backgroundImage !== 'none') {
      const g = /gradient\(/.test(cs.backgroundImage) ? gradientOf(cs.backgroundImage, (b => ({ w: b.width, h: b.height }))(el.getBoundingClientRect()), n) : { bad: 'background image (use an <img>)' };
      if (g && g.bad) errors.push(`${n}: background: ${g.bad}`);
      if ((cs.backgroundClip || cs.webkitBackgroundClip) === 'text') errors.push(`${n}: gradient text (background-clip: text) doesn't convert`);
    }
    if (cs.boxShadow !== 'none') {
      const sh = shadowOf(cs.boxShadow);
      if (sh.bad) errors.push(`${n}: box-shadow: ${sh.bad}`);
      else if (el.tagName !== 'IMG' && !(color(cs.backgroundColor) || cs.backgroundImage !== 'none' || ['Top', 'Right', 'Bottom', 'Left'].some(k => px(cs[`border${k}Width`]) > 0 && cs[`border${k}Style`] !== 'none')))
        errors.push(`${n}: box-shadow on a box with no fill or border (PowerPoint would shadow its letters instead)`);
    }
    if (cs.textShadow !== 'none') errors.push(`${n}: text-shadow`);
    if (cs.filter !== 'none') errors.push(`${n}: filter`);
    if (cs.backdropFilter && cs.backdropFilter !== 'none') errors.push(`${n}: backdrop-filter`);
    if (cs.clipPath !== 'none') errors.push(`${n}: clip-path`);
    if ((cs.maskImage || cs.webkitMaskImage || 'none') !== 'none') errors.push(`${n}: mask`);
    if (cs.mixBlendMode !== 'normal') errors.push(`${n}: blend mode`);
    if (cs.outlineStyle !== 'none' && px(cs.outlineWidth) > 0) errors.push(`${n}: outline (use a border)`);
    if (cs.writingMode !== 'horizontal-tb') errors.push(`${n}: vertical writing mode`);
    for (const s of ['Top', 'Right', 'Bottom', 'Left']) {
      const st = cs[`border${s}Style`];
      if (px(cs[`border${s}Width`]) > 0 && !['solid', 'none', 'hidden'].includes(st)) errors.push(`${n}: ${st} border (use an SVG line for dashes)`);
    }
    for (const p of ['::before', '::after']) {
      const c = getComputedStyle(el, p).content;
      if (c && c !== 'none' && c !== 'normal') errors.push(`${n}: ${p} content can't be measured; use a real element`);
    }
  }

  const isInlineEl = el => el.nodeType === 1 && (el.tagName === 'BR' || getComputedStyle(el).display === 'inline');

  function isTextBlock(el) {
    let hasText = false;
    for (const n of el.childNodes) {
      if (n.nodeType === 3) { if (n.textContent.trim()) hasText = true; }
      else if (n.nodeType === 1) {
        if (!isInlineEl(n)) return false;
        if (n.textContent.trim()) hasText = true;
      }
    }
    return hasText;
  }

  // Words with their rendered boxes, for the line-break and position checks.
  function wordsOf(el) {
    const out = [];
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = walker.nextNode())) {
      const re = /\S+/g; let m;
      while ((m = re.exec(n.textContent))) {
        const r = document.createRange();
        r.setStart(n, m.index); r.setEnd(n, m.index + m[0].length);
        const rects = [...r.getClientRects()];
        if (!rects.length) continue;
        const w = { t: m[0], ...rel(rects[0]) };
        // A word the browser breaks at its hyphen or dash ("go-|live") ends on the next line: keep where, so the line
        // count sees that line. Counted as one line, the export turned wrapping off and PowerPoint ran "go-live." past
        // its box (design range, Oct 18, 2026); with wrapping on, PowerPoint breaks there too.
        const end = rects[rects.length - 1];
        if (end.top > rects[0].top + rects[0].height / 2) { const e = rel(end); w.next = { x: e.x, y: e.y, w: e.w, h: e.h }; }
        out.push(w);
      }
    }
    return out;
  }

  const fontOf = cs => cs.fontFamily.split(',')[0].replace(/["']/g, '').trim();

  function runsOf(block) {
    const runs = [];
    const walk = node => {
      for (const n of node.childNodes) {
        if (n.nodeType === 3) {
          const cs = getComputedStyle(n.parentElement);
          // White space collapses as the browser does it; a no-break space stays one (it holds two words together).
          const text = n.textContent.replace(/[^\S\u00a0]+/g, ' ');
          if (!text) continue;
          runs.push({
            text,
            font: fontOf(cs),
            size: px(cs.fontSize),
            weight: parseInt(cs.fontWeight, 10),
            italic: cs.fontStyle === 'italic',
            color: color(cs.color, nameOf(block)),
            spacing: cs.letterSpacing === 'normal' ? 0 : px(cs.letterSpacing),
            upper: cs.textTransform === 'uppercase',
            underline: cs.textDecorationLine.includes('underline'),
          });
        } else if (n.nodeType === 1) {
          if (n.tagName === 'BR') runs.push({ br: true });
          else walk(n);
        }
      }
    };
    walk(block);
    for (let i = 0; i < runs.length; i++) {
      if (runs[i].br) continue;
      if (i === 0 || runs[i - 1].br) runs[i].text = runs[i].text.replace(/^ +/, '');
      if (i === runs.length - 1 || runs[i + 1].br) runs[i].text = runs[i].text.replace(/ +$/, '');
    }
    for (let i = 1; i < runs.length; i++) {
      if (runs[i].br || runs[i - 1].br) continue;
      if (runs[i - 1].text.endsWith(' ') && runs[i].text.startsWith(' ')) runs[i].text = runs[i].text.slice(1);
    }
    return runs.filter(r => r.br || r.text);
  }

  function boxStyle(el, cs, r) {
    const sides = ['Top', 'Right', 'Bottom', 'Left'].map(s => ({
      w: px(cs[`border${s}Width`]),
      style: cs[`border${s}Style`],
      color: color(cs[`border${s}Color`], nameOf(el)),
    })).map(b => (b.style === 'none' || b.style === 'hidden' || !b.color || b.w === 0) ? null : b);
    const [rxs, rys] = (cs.borderTopLeftRadius + ' ' + cs.borderTopLeftRadius).split(' ');
    const rv = (v, d) => v.endsWith('%') ? parseFloat(v) / 100 * d : px(v);
    const rx = Math.min(rv(rxs, r.w), r.w / 2), ry = Math.min(rv(rys, r.h), r.h / 2);
    const radius = Math.min(rx, ry);
    const ellipse = rx >= r.w / 2 - 0.5 && ry >= r.h / 2 - 0.5;
    if (!ellipse && Math.abs(rx - ry) > 1) warnings.push(`${nameOf(el)}: elliptical corners become circular`);
    const radii = ['TopLeft', 'TopRight', 'BottomRight', 'BottomLeft'].map(k => cs[`border${k}Radius`]);
    if (new Set(radii).size > 1) errors.push(`${nameOf(el)}: corners with different radii`);
    const g = cs.backgroundImage !== 'none' ? gradientOf(cs.backgroundImage, r, nameOf(el)) : null;
    // Chrome's PDF draws a gradient under an element's opacity as one flat color (a soft glow became a hard disc),
    // so the export report, which reads that PDF, can't check it. PowerPoint draws it fine (design range, Oct 18, 2026).
    if (g && !g.bad && opacityOf(el) < 0.999)
      errors.push(`${nameOf(el)}: opacity on a gradient: put the transparency in the stops instead, color-mix(in srgb, <color> 50%, transparent)`);
    const sh = cs.boxShadow !== 'none' ? shadowOf(cs.boxShadow) : null;
    return { fill: color(cs.backgroundColor, nameOf(el)), gradient: g && !g.bad ? g : null, shadow: sh && !sh.bad ? sh : null,
             borders: sides, radius, ellipse };
  }

  // One paragraph: runs, line height, where its lines sit.
  function paraInfo(el, cs) {
    let lh = cs.lineHeight;
    if (lh === 'normal') { errors.push(`${nameOf(el)}: line-height normal; set it in px`); lh = px(cs.fontSize) * 1.2; }
    // PowerPoint never applies OpenType kerning, so the browser must not either.
    if (cs.fontKerning !== 'none') errors.push(`${nameOf(el)}: font-kerning ${cs.fontKerning}; set font-kerning: none`);
    // In px whatever else is wrong: --force exports a refused slide, and a "29px" string crashed it (Oct 18, 2026).
    if (typeof lh !== 'number') lh = px(lh);
    const words = wordsOf(el);
    const cr = el.getBoundingClientRect();
    if (words.some(w => w.x + w.w > cr.right - S.left - px(cs.paddingRight) + 0.5 || w.x < cr.left - S.left + px(cs.paddingLeft) - 0.5))
      errors.push(`${nameOf(el)}: text overflows its box`);
    let top = null, bottom = null, lines = 0, lastY = null, minX = null, maxX = null;
    if (words.length) {
      const first = words[0], last = words[words.length - 1];
      top = first.y - (lh - first.h) / 2;
      const end = last.next || last;
      bottom = end.y + end.h + (lh - end.h) / 2;
    }
    for (const w of words) {
      if (lastY === null || Math.abs(w.y - lastY) > 4) { lines++; lastY = w.y; }
      if (w.next) { lines++; lastY = w.next.y; }
      minX = minX === null ? w.x : Math.min(minX, w.x);
      maxX = maxX === null ? w.x + w.w : Math.max(maxX, w.x + w.w);
    }
    // Lines that don't fit the box's height spill over whatever sits below (or above, when the text sits at the
    // bottom): PowerPoint would draw them outside the shape too.
    if (top !== null && cr.height > 0 && cs.display !== 'inline') { // an inline run's box is its letters, not a container
      const below = bottom - (cr.bottom - S.top), above = (cr.top - S.top) - top;
      if (below > 1 || above > 1)
        errors.push(`${nameOf(el)}: text runs past the ${below > 1 ? 'bottom' : 'top'} of its box (${lines} line${lines === 1 ? '' : 's'} need ${Math.round(bottom - top)}px; the box is ${Math.round(cr.height)}px)`);
    }
    // PowerPoint draws exact line spacing in whole points (skald/lines.py): on a fractional one every line after the
    // first drifts, 0.67 px per line at worst. A note, so the agent can pick the nearest whole point.
    const pt = lh * 0.75;
    if (lines > 1 && Math.abs(pt - Math.round(pt)) > 0.01) {
      const down = Math.round(Math.ceil(pt - 0.5) / 0.75 * 100) / 100, up = Math.round(Math.floor(pt + 0.5) / 0.75 * 100) / 100;
      notes.push(`${nameOf(el)}: line-height ${Math.round(lh * 100) / 100}px is ${Math.round(pt * 100) / 100}pt; PowerPoint draws whole points, so line ${lines} lands up to ${Math.round(Math.abs(up - lh) * (lines - 1) * 100) / 100}px off: use ${down}px${up !== down ? ` or ${up}px` : ''}`);
    }
    return {
      runs: runsOf(el),
      align: cs.textAlign === 'start' ? 'left' : cs.textAlign === 'end' ? 'right' : cs.textAlign,
      lineHeight: lh, top, bottom, lines, minX, maxX, words,
      left: cr.left - S.left + px(cs.paddingLeft) + px(cs.borderLeftWidth),
    };
  }

  const measureCtx = document.createElement('canvas').getContext('2d');

  // A list item's marker, measured: Chrome places an outside marker so it ends where the
  // item's text begins. The marker text includes its trailing space.
  function markerOf(li, cs, index) {
    const type = cs.listStyleType;
    if (type === 'none' || cs.listStylePosition !== 'outside') return null;
    const mcs = getComputedStyle(li, '::marker');
    let text, kind;
    if (type.startsWith('"')) { text = JSON.parse(type); kind = 'char'; }
    else if (type === 'disc' || type === 'circle' || type === 'square') {
      // Chrome draws these as vector dots, not font glyphs; PowerPoint's bullet is a glyph.
      errors.push(`${nameOf(li)}: list-style-type ${type} is drawn as a shape by the browser; use a text marker such as list-style-type: "•  "`);
      text = '• '; kind = 'char';
    }
    else if (type === 'decimal') { text = `${index}. `; kind = 'number'; }
    else { errors.push(`${nameOf(li)}: list-style-type ${type}`); return null; }
    measureCtx.font = `${mcs.fontWeight} ${mcs.fontSize} "${fontOf(mcs)}"`;
    measureCtx.letterSpacing = mcs.letterSpacing === 'normal' ? '0px' : mcs.letterSpacing;
    const width = measureCtx.measureText(text).width;
    const p = li.getBoundingClientRect().left - S.left + px(cs.paddingLeft);
    return {
      kind, char: text.trim(), start: index, x: p - width, width,
      font: fontOf(mcs), size: px(mcs.fontSize), weight: parseInt(mcs.fontWeight, 10),
      color: color(mcs.color, nameOf(li)),
      words: [{ t: text.trim(), x: p - width, y: null, w: measureCtx.measureText(text.trim()).width, h: null }],
    };
  }

  function textInfo(el, cs, paras) {
    const pad = {
      l: px(cs.paddingLeft) + px(cs.borderLeftWidth), r: px(cs.paddingRight) + px(cs.borderRightWidth),
      t: px(cs.paddingTop) + px(cs.borderTopWidth), b: px(cs.paddingBottom) + px(cs.borderBottomWidth),
    };
    const first = paras[0], last = paras[paras.length - 1];
    for (let i = 1; i < paras.length; i++) paras[i].spaceBefore = paras[i].top - paras[i - 1].bottom;
    const words = paras.flatMap(p => p.words);
    const xs = paras.filter(p => p.minX !== null);
    return {
      paras,
      // first paragraph's values, for single-paragraph code paths
      runs: first.runs, align: first.align, lineHeight: first.lineHeight,
      lines: paras.reduce((s, p) => s + p.lines, 0),
      minX: xs.length ? Math.min(...xs.map(p => p.minX)) : null,
      maxX: xs.length ? Math.max(...xs.map(p => p.maxX)) : null,
      pad, textTop: first.top, textBottom: last.bottom, words,
    };
  }

  // A list whose items are all plain text becomes one text box with one paragraph per item.
  function listParas(el) {
    const kids = [...el.children];
    if (!kids.length || !kids.every(k => k.tagName === 'LI' && isTextBlock(k))) return null;
    const start = el.tagName === 'OL' ? (parseInt(el.getAttribute('start'), 10) || 1) : 1;
    return kids.map((li, i) => {
      const lcs = getComputedStyle(li);
      lint(li, lcs);
      const p = paraInfo(li, lcs);
      p.bullet = markerOf(li, lcs, start + i);
      if (p.bullet && p.words.length) {
        p.bullet.words[0].y = p.words[0].y;
        p.bullet.words[0].h = p.words[0].h;
      }
      return p;
    });
  }

  function markerInfo(id, sw) {
    const mk = id && document.getElementById(id);
    if (!mk) return null;
    const units = mk.getAttribute('markerUnits') || 'strokeWidth';
    const mw = parseFloat(mk.getAttribute('markerWidth') || 3), mh = parseFloat(mk.getAttribute('markerHeight') || 3);
    const vb = mk.viewBox && mk.viewBox.baseVal;
    const vw = vb && vb.width ? vb.width : mw, vh = vb && vb.height ? vb.height : mh;
    const k = units === 'strokeWidth' ? sw : 1;
    const s = Math.min(mw * k / vw, mh * k / vh);
    const shape = mk.querySelector('path,polygon');
    if (!shape) return null;
    const bb = shape.getBBox();
    const refX = parseFloat(mk.getAttribute('refX') || 0);
    // PowerPoint heads are 2, 3 or 5 times the line width (never less than 2pt = 2.667px).
    const base = Math.max(sw, 8 / 3);
    const len = bb.width * s, width = bb.height * s;
    const pick = v => { const r = v / base; const best = [2, 3, 5].reduce((a, b) => Math.abs(b - r) < Math.abs(a - r) ? b : a); return { mult: best, off: Math.abs(best - r) / best }; };
    const L = pick(len), W = pick(width);
    // PowerPoint draws a filled triangle in the line's own color; nothing else converts.
    const nums = (shape.getAttribute(shape.tagName.toLowerCase() === 'path' ? 'd' : 'points') || '').match(/-?[\d.]+(e-?\d+)?/gi) || [];
    const triangle = mk.querySelectorAll('*').length === 1 && nums.length === 6
      && (shape.tagName.toLowerCase() === 'polygon' || /^\s*M[^A-Za-z]*L[^A-Za-z]*L[^A-Za-z]*z\s*$/i.test(shape.getAttribute('d')));
    const fill = color(getComputedStyle(shape).fill, 'arrowhead');
    return { len, width, tip: (bb.x + bb.width - refX) * s, lenMult: L.mult, widthMult: W.mult, fits: L.off < 0.12 && W.off < 0.12,
             triangle, fill };
  }

  function svgShape(el, parentGroup) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    const n = nameOf(el);
    for (const p of ['clipPath', 'mask', 'filter']) if (cs[p] && cs[p] !== 'none') errors.push(`${n}: SVG ${p}`);
    if (/url\(/.test(cs.fill) || /url\(/.test(cs.stroke)) errors.push(`${n}: SVG gradient or pattern paint`);
    const m = el.getScreenCTM();
    const tag = el.tagName.toLowerCase();
    const attrs = {};
    for (const a of ['x', 'y', 'width', 'height', 'rx', 'ry', 'cx', 'cy', 'r', 'x1', 'y1', 'x2', 'y2', 'points', 'd']) {
      if (el.hasAttribute(a)) attrs[a] = el.getAttribute(a);
    }
    const mid = v => (v && v !== 'none') ? v.replace(/^url\(["']?#?|["']?\)$/g, '').replace(/^.*#/, '') : null;
    const sw = px(cs.strokeWidth) * Math.sqrt(Math.abs(m.a * m.d - m.b * m.c));
    const ms = markerInfo(mid(cs.markerStart), sw), me = markerInfo(mid(cs.markerEnd), sw);
    for (const [k, mk] of [['start', ms], ['end', me]]) {
      if (mk && !mk.fits) errors.push(`${n}: ${k} arrowhead ${mk.len.toFixed(1)}x${mk.width.toFixed(1)}px is not a PowerPoint size (2, 3 or 5 x the line width)`);
      if (mk && Math.abs(mk.tip) > 0.5) errors.push(`${n}: ${k} arrowhead tip is not at the line's end (set refX to the tip)`);
      if (mk && !mk.triangle) errors.push(`${n}: ${k} arrowhead must be one filled triangle (M x y L x y L x y z, or a 3-point polygon)`);
    }
    const strokeC = color(cs.stroke === 'none' ? null : cs.stroke, n);
    for (const [k, mk] of [['start', ms], ['end', me]]) {
      if (mk && mk.triangle && (!mk.fill || !strokeC || mk.fill.hex !== strokeC.hex || mk.fill.a !== strokeC.a))
        errors.push(`${n}: ${k} arrowhead color differs from the line's (PowerPoint draws it in the line color)`);
    }
    const bb = el.getBBox();
    const sr = el.getBoundingClientRect();
    elements.push({
      id: n, kind: 'svg', tag, group: parentGroup,
      matrix: [m.a, m.b, m.c, m.d, m.e - S.left, m.f - S.top],
      attrs,
      bbox: { x: bb.x, y: bb.y, w: bb.width, h: bb.height },
      ...rel(sr),
      fill: color(cs.fill === 'none' ? null : cs.fill, n),
      fillOpacity: px(cs.fillOpacity || 1),
      stroke: color(cs.stroke === 'none' ? null : cs.stroke, n),
      strokeWidth: px(cs.strokeWidth),
      strokeOpacity: px(cs.strokeOpacity || 1),
      dash: cs.strokeDasharray === 'none' ? null : cs.strokeDasharray,
      cap: cs.strokeLinecap,
      join: cs.strokeLinejoin,
      markerStart: ms, markerEnd: me,
      opacity: opacityOf(el),
      from: el.dataset.from || null,
      to: el.dataset.to || null,
    });
  }

  function walkSvg(node, group) {
    for (const c of node.children) {
      const t = c.tagName.toLowerCase();
      if (['defs', 'marker', 'title', 'desc', 'style', 'clippath', 'mask', 'lineargradient', 'radialgradient', 'pattern', 'filter'].includes(t)) continue;
      if (t === 'g') {
        const gid = c.dataset.group !== undefined || c.dataset.id ? nameOf(c) : null;
        if (gid) elements.push({ id: gid, kind: 'group', group });
        walkSvg(c, gid || group);
      } else if (['rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon', 'path'].includes(t)) {
        svgShape(c, group);
      } else {
        errors.push(`${nameOf(c)}: SVG <${t}> is not converted (use HTML text / <img>)`);
      }
    }
  }

  function walk(el, group) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    const tag = el.tagName;
    if (['CANVAS', 'VIDEO', 'IFRAME', 'OBJECT', 'EMBED', 'AUDIO'].includes(tag)) {
      errors.push(`${nameOf(el)}: <${tag.toLowerCase()}> can't become a native object`);
      return;
    }
    if (tag === 'STYLE' || tag === 'SCRIPT') return;
    // A picture of the company layout under the slide, for the browser only: export writes the
    // slide onto that layout, which draws it for real.
    if (el.dataset.underlay !== undefined) return;
    const r = rel(el.getBoundingClientRect());
    const rot = rotated.has(el) ? rotated.get(el).angle : 0;

    if (tag === 'svg') {
      lint(el, cs);
      // The skill's icons are drawn for 32 px and up; smaller, their strokes run together.
      if (el.dataset.icon !== undefined && Math.min(r.w, r.h) < 31.5)
        errors.push(`${nameOf(el)}: icon is ${Math.round(Math.min(r.w, r.h))}px; icons are drawn for 32px and up`);
      const gid = el.dataset.group !== undefined || el.dataset.id ? nameOf(el) : null;
      if (gid) elements.push({ id: gid, kind: 'group', group });
      walkSvg(el, gid || group);
      return;
    }
    if (el.dataset.chart !== undefined) {
      // A chart: drawn in the page by chart.js from this spec; exported as a native chart.
      if (!el.dataset.resolved) errors.push(`${nameOf(el)}: chart was not drawn (load chart.js on the slide)`);
      else if (el.dataset.plot) {
        // PowerPoint turns a category label that is wider than its column on its side, or cuts it to a letter
        // ("R…"); the browser would still draw it flat. Seen on a real deck, Oct 16, 2026.
        const sp = JSON.parse(el.dataset.resolved), P = JSON.parse(el.dataset.plot);
        if (Array.isArray(sp.categories) && sp.categories.length && sp.type !== 'doughnut') {
          measureCtx.font = `${sp.fontWeight || 400} ${sp.fontSize}px "${sp.font}"`;
          // The browser cuts a value label that starts left of the figure; PowerPoint draws it whole.
          if (sp.axis && window.skaldChartTicks && sp.type !== 'bar') {
            const room = P.x - (sp.valueLabelGap || 0);
            const cut = window.skaldChartTicks(sp).find(t => measureCtx.measureText(t).width > room + 0.5);
            if (cut) errors.push(`${nameOf(el)}: chart value label "${cut}" needs ${Math.ceil(measureCtx.measureText(cut).width + (sp.valueLabelGap || 0))}px left of the plot but plot.l gives ${Math.round(P.x)}px; the browser cuts it and PowerPoint doesn't: drop plot.l (chart.js then fits it) or raise it`);
          }
          const cw = sp.type === 'bar' ? P.x - (sp.valueLabelGap || 0) + 4 : P.w / sp.categories.length;  // bar: the room left of the plot
          const wide = sp.categories.filter(c => measureCtx.measureText(String(c)).width > cw - 4);
          if (wide.length)
            errors.push(`${nameOf(el)}: chart category label "${wide[0]}"${wide.length > 1 ? ` (and ${wide.length - 1} more)` : ''} is wider than its ${Math.round(cw)}px column; PowerPoint turns or cuts it: shorten the labels, use a smaller chart font, or widen the chart`);
        }
      }
      elements.push({ id: nameOf(el), kind: 'chart', group, ...r,
                      spec: JSON.parse(el.dataset.resolved || el.dataset.chart),
                      plot: el.dataset.plot ? JSON.parse(el.dataset.plot) : null });
      return;
    }
    lint(el, cs);
    if (tag === 'IMG') {
      elements.push({
        id: nameOf(el), kind: 'image', group, ...r, rot, src: el.currentSrc || el.src, opacity: opacityOf(el),
        natural: { w: el.naturalWidth, h: el.naturalHeight }, fit: cs.objectFit, position: cs.objectPosition,
        box: boxStyle(el, cs, r),  // a background or border behind the picture (letterbox bars)
      });
      return;
    }

    const box = boxStyle(el, cs, r);
    const drawsBox = !!(box.fill || box.gradient || box.borders.some(Boolean));
    const textBlock = isTextBlock(el);
    const list = (tag === 'UL' || tag === 'OL') ? listParas(el) : null;
    let gid = null;
    if (el.dataset.group !== undefined) {
      gid = nameOf(el);
      elements.push({ id: gid, kind: 'group', group });
    }
    if (drawsBox || textBlock || list) {
      const e = {
        id: el.dataset.group !== undefined ? `${gid}-box` : nameOf(el),
        kind: 'box', group: gid || group, ...r, ...box, rot,
        opacity: opacityOf(el),
        role: el.dataset.role || null,
        bind: el.dataset.bind || null,
        ph: el.dataset.ph !== undefined ? Number(el.dataset.ph) : null,
        overlapOk: el.dataset.overlap !== undefined || !!el.closest('[data-overlap]'),
      };
      if (textBlock) e.text = textInfo(el, cs, [paraInfo(el, cs)]);
      else if (list) e.text = textInfo(el, cs, list);
      if (e.text) texts.push({ e, el });
      if (rot && e.text) e.text.rotated = true;
      elements.push(e);
    }
    if (textBlock || list) return;
    if (rot && el.children.length) errors.push(`${nameOf(el)}: rotation on an element with children (rotate single elements)`);
    walkChildren(el, gid || group);
  }

  // Paint order: siblings sort by z-index (auto = 0), ties keep DOM order.
  function walkChildren(el, group) {
    const z = k => { const v = getComputedStyle(k).zIndex; return v === 'auto' ? 0 : parseInt(v, 10); };
    [...el.children].map((k, i) => ({ k, i, z: z(k) }))
      .sort((a, b) => a.z - b.z || a.i - b.i)
      .forEach(({ k }) => walk(k, group));
  }

  const scs = getComputedStyle(slide);
  if (scs.backgroundImage !== 'none') errors.push('slide: background image or gradient');
  try {
    walkChildren(slide, null);
    // Text printed over other text: two elements' words share ink (a wrapped label running into the note under it).
    // Each word is cut to the middle 60% of its height, so tightly stacked lines that merely touch still pass.
    const inked = [];
    for (const e of elements) {
      if (!e.text || e.text.rotated) continue;
      for (const p of e.text.paras || []) for (const w of p.words || [])
        inked.push({ id: e.id, t: w.t, x0: w.x, x1: w.x + w.w, y0: w.y + w.h * 0.2, y1: w.y + w.h * 0.8 });
    }
    const clash = new Set();
    for (let i = 0; i < inked.length; i++) for (let j = i + 1; j < inked.length; j++) {
      const a = inked[i], b = inked[j];
      if (a.id === b.id) continue;
      if (Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0) > 2 && Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0) > 2) {
        const k = [a.id, b.id].sort().join('|');
        if (!clash.has(k)) { clash.add(k); errors.push(`${a.id}: text overlaps ${b.id}'s text ("${a.t}" over "${b.t}")`); }
      }
    }
    // Text boxes laid over each other: each text's outline (its words' boxes, trimmed 15% top and bottom so tight
    // stacks pass) must not cross another's. The ink rule above misses lines that interleave: two lists placed on the
    // same spot, their lines alternating, letters colliding at the ascenders (seen on a real deck, Oct 18, 2026).
    // A design that means it (a big faded number behind a heading) marks one of the two with data-overlap.
    const outline = e => {
      const ws = (e.text.paras || []).flatMap(p => p.words || []);
      if (!ws.length) return null;
      const y0 = Math.min(...ws.map(w => w.y + w.h * 0.15)), y1 = Math.max(...ws.map(w => w.y + w.h * 0.85));
      return { x0: Math.min(...ws.map(w => w.x)), x1: Math.max(...ws.map(w => w.x + w.w)), y0, y1 };
    };
    const outlines = elements.filter(e => e.text && !e.text.rotated && !e.overlapOk).map(e => ({ e, o: outline(e) })).filter(x => x.o);
    for (let i = 0; i < outlines.length; i++) for (let j = i + 1; j < outlines.length; j++) {
      const a = outlines[i], b = outlines[j], k = [a.e.id, b.e.id].sort().join('|');
      if (clash.has(k)) continue;
      const w = Math.min(a.o.x1, b.o.x1) - Math.max(a.o.x0, b.o.x0), h = Math.min(a.o.y1, b.o.y1) - Math.max(a.o.y0, b.o.y0);
      if (w > 4 && h > 4) {
        clash.add(k);
        errors.push(`${a.e.id}: text box overlaps ${b.e.id}'s text box by ${Math.round(w)}x${Math.round(h)}px: move one, or mark a deliberate overlap with data-overlap`);
      }
    }
    // Collisions no text-on-text rule sees (Oct 18, 2026 stress test: a callout on a chart's year labels,
    // a takeaway run out of its panel, a legend drawn under the panel beside it). Looking caught all three; lint now does.
    const wordsOf = e => (e.text.paras || []).flatMap(p => p.words || []);
    const meets = (w, b) => Math.min(w.x + w.w, b.x + b.w) - Math.max(w.x, b.x) > 2 &&
      Math.min(w.y + w.h * 0.85, b.y + b.h) - Math.max(w.y + w.h * 0.15, b.y) > 2;
    const said = new Set();
    const say = (k, msg) => { if (!said.has(k)) { said.add(k); errors.push(msg); } };
    for (const c of elements.filter(x => x.kind === 'chart' && x.plot && x.spec && x.spec.type !== 'doughnut')) {
      const P = c.plot, fs = c.spec.fontSize || 16;
      // The labels' own bands, not the figure's spare room: a line of type left of the plot, and one and a half under it.
      const bands = [{ x: c.x, y: c.y + P.y - 8, w: P.x, h: P.h + 16 },                 // value ticks (bar: categories)
                     { x: c.x + P.x - 8, y: c.y + P.y + P.h, w: P.w + 16, h: Math.min(c.h - P.y - P.h, fs * 1.5) }];
      for (const { e, el } of texts) {
        if (e.overlapOk || el.closest('[data-chart],[data-legend-for]') || e.id.startsWith(c.id + '-')) continue;
        if (wordsOf(e).some(w => bands.some(b => b.w > 0 && b.h > 0 && meets(w, b))))
          say(`axis|${e.id}`, `${e.id}: text sits on ${c.id}'s axis labels: move it off the chart's edges (into the plot, or clear of it)`);
      }
    }
    for (const { e, el } of texts) {
      if (e.overlapOk) continue;
      let p = el.parentElement;
      while (p && p !== slide) {
        const pc = getComputedStyle(p);
        if (color(pc.backgroundColor) || pc.backgroundImage !== 'none') break;
        p = p.parentElement;
      }
      if (!p || p === slide) continue;
      const b = rel(p.getBoundingClientRect()), ws = wordsOf(e);
      const out = ws.some(w => w.y + w.h * 0.85 > b.y + b.h + 2) ? 'bottom' : ws.some(w => w.x + w.w > b.x + b.w + 2) ? 'right'
        : ws.some(w => w.x < b.x - 2) ? 'left' : ws.some(w => w.y + w.h * 0.15 < b.y - 2) ? 'top' : null;
      if (out) say(`panel|${e.id}`, `${e.id}: text runs past the ${out} edge of the panel it sits in (${nameOf(p)}): give it room or less text`);
    }
    elements.forEach((b, j) => {
      if (b.kind !== 'box' || !b.fill || b.fill.a < 0.99 || b.overlapOk) return;
      for (const { e } of texts) {
        const i = elements.indexOf(e);
        if (i < 0 || i >= j || e.overlapOk) continue;
        if (wordsOf(e).some(w => meets(w, b)))
          say(`under|${e.id}|${b.id}`, `${e.id}: text is drawn under ${b.id}, a box painted over it: move one`);
      }
    });
  } finally {
    for (const [el, v] of rotated) {
      if (v.inline) el.style.setProperty('transform', v.inline); else el.style.removeProperty('transform');
    }
  }
  return {
    width: S.width, height: S.height,
    background: color(scs.backgroundColor, 'slide'),
    title: document.title,
    pattern: slide.dataset.pattern || null,
    slideId: slide.dataset.slide || null,
    layout: slide.dataset.layout || null,
    elements, warnings, notes,
    errors: errors.map(e => { const k = e.split(':')[0]; return hints[k] ? `${k} ${hints[k]}${e.slice(k.length)}` : e; }),
  };
})()
