// Draws charts in the page from a spec in data-chart, following PowerPoint's own chart geometry,
// so the native PowerPoint chart built from the same spec lands in the same place.
// <figure data-chart='{"type":"column", ...}' style="position:absolute; left:..; top:..; width:..; height:..">
(() => {
  const NS = 'http://www.w3.org/2000/svg';
  // Neutral geometry defaults. Font, label color and grid color come from the figure's own CSS
  // (font-family, font-weight, color, --chart-grid), so the deck's styles decide the look.
  const D = {
    fontSize: 12, gridWidth: 1, gap: 80, lineWidth: 2.5, hole: 60,
    plot: { l: 40, t: 10, r: 10, b: 28 },
  };
  const hex = c => {
    const m = c.match(/^rgba?\(([^)]+)\)$/);
    if (!m) return c.trim();
    return '#' + m[1].split(/[\s,\/]+/).slice(0, 3).map(n => Math.round(+n).toString(16).padStart(2, '0')).join('');
  };
  function styleOf(fig) {
    const cs = getComputedStyle(fig);
    const labelColor = hex(cs.color);
    const grid = cs.getPropertyValue('--chart-grid').trim();
    // The brand's measured label offsets (convey brand calibrate): "size dy dx, ...". PowerPoint places axis labels by
    // the font's own metrics, so the constants below, measured on one font, sit 2.3 px high in Trebuchet MS at 16 px.
    const cal = cs.getPropertyValue('--brand-chart-labels').replace(/["']/g, '').trim();
    return {
      font: cs.fontFamily.split(',')[0].replace(/["']/g, '').trim(),
      fontWeight: parseInt(cs.fontWeight, 10),
      labelColor,
      gridColor: grid ? hex(grid) : labelColor,
      labelCal: cal ? cal.split(',').map(t => t.trim().split(/\s+/).map(Number)).filter(t => t.length === 3) : [],
    };
  }
  // The measured offset for the nearest label size: [dy for bottom-axis labels, dx for left-axis labels].
  const shift = o => {
    if (!o.labelCal || !o.labelCal.length) return [0, 0];
    const t = o.labelCal.reduce((a, b) => Math.abs(b[0] - o.fontSize) < Math.abs(a[0] - o.fontSize) ? b : a);
    return [t[1], t[2]];
  };
  // Where PowerPoint puts axis labels relative to the plot area, measured on the bench
  // (Oct 15, 2026): value labels end 6px + 0.39em left of the plot, category labels start
  // 4px + 0.23em below it.
  const gaps = o => ({ valueLabelGap: 6 + 0.39 * o.fontSize, categoryLabelGap: 4 + 0.23 * o.fontSize });

  function el(tag, attrs, parent) {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    parent.appendChild(e);
    return e;
  }

  function text(svg, s, x, y, anchor, o) {
    const t = el('text', {
      x, y, 'text-anchor': anchor, 'dominant-baseline': 'central', fill: o.labelColor,
      'font-family': o.font, 'font-size': o.fontSize, 'font-weight': o.fontWeight,
    }, svg);
    t.style.fontKerning = 'none';
    t.textContent = s;
    return t;
  }

  const lum = c => {
    const m = /^#([0-9a-f]{6})$/i.exec(c || '');
    if (!m) return null;
    const [R, G, B] = [0, 2, 4].map(i => parseInt(m[1].slice(i, i + 2), 16) / 255)
      .map(v => v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
    return 0.2126 * R + 0.7152 * G + 0.0722 * B;
  };
  const readable = c => { const L = lum(c); return L === null || (1.05 / (L + 0.05)) >= ((L + 0.05) / 0.05) ? '#ffffff' : '#000000'; };
  // Colors in the spec may be CSS variables ("var(--brand-data-1)"), resolved on the figure, so a
  // chart template carries no brand values.
  function colorsOf(spec, fig) {
    const cs = getComputedStyle(fig);
    const r = c => {
      const m = typeof c === 'string' && c.match(/^var\((--[\w-]+)\)$/);
      return m ? hex(cs.getPropertyValue(m[1]).trim()) : c;
    };
    // Type on a segment: the brand's own on-color for that fill (--brand-on-data-1 for --brand-data-1), else white or
    // black, whichever reads better (white on a mid teal was 3.1:1, Oct 19, 2026).
    const on = c => {
      const m = typeof c === 'string' && c.match(/^var\(--brand-([\w-]+)\)$/);
      const own = m ? cs.getPropertyValue(`--brand-on-${m[1]}`).trim() : '';
      return own ? hex(own) : readable(r(c));
    };
    return {
      ...spec,
      series: (spec.series || []).map(s => ({ ...s, color: r(s.color), on: on(s.color) })),
      ...(spec.colors ? { colors: spec.colors.map(r) } : {}),
    };
  }

  // The plot's margins: a side the spec sets is kept as given; any other side grows from the default until the
  // axis labels fit inside the figure (a fixed 40px left margin cut "$500K" to "00K", Oct 18, 2026). The extractor
  // reads the final plot, so the native chart moves with it.
  const ctx = document.createElement('canvas').getContext('2d');
  const labelWidth = (s, o) => { ctx.font = `${o.fontWeight} ${o.fontSize}px "${o.font}"`; return ctx.measureText(s).width; };
  // An axis label as PowerPoint's number format writes it: the minus goes before the whole format ("-$100K").
  const fmt = (v, o) => (v < 0 ? '-' : '') + (o.axis.format || '{v}').replace('{v}', Math.abs(+v.toFixed(6)));
  const ticks = o => {
    const out = [];
    for (let v = o.axis.min; v <= o.axis.max + 1e-9; v += o.axis.step) out.push(fmt(v, o));
    return out;
  };
  function fitPlot(o, given, legend) {
    const p = { ...D.plot, ...given };
    if (legend && given.t === undefined) p.t = Math.max(p.t, legend.offsetHeight + Math.round(o.fontSize * 0.6) + 14);
    if (o.type === 'doughnut' || !o.axis) return p;
    const widest = Math.max(...(o.type === 'bar' ? o.categories.map(String) : ticks(o)).map(t => labelWidth(t, o)));
    // PowerPoint shrinks its plot when it thinks an axis label lacks room (its text runs a hair wider): leave it some.
    // Where the brand's calibration says PowerPoint ends these labels further left (dx < 0), it wants that much more
    // room too: with 2 px, Trebuchet MS at 16 px slid the plot 2.5 px right (Berlin, Oct 18, 2026).
    const lean = Math.max(0, -shift(o)[1]);
    if (given.l === undefined) p.l = Math.max(p.l, Math.ceil(widest + o.valueLabelGap + (o.type === 'bar' ? 12 : 2) + lean));
    if (given.t === undefined) p.t = Math.max(p.t, Math.ceil(o.fontSize * 0.6 + 1));
    // Under the plot, half a line more than the labels take: with Trebuchet MS at 16 px PowerPoint judged 1.2 lines too
    // little and lifted the whole plot 1.5 px (Berlin, Oct 18, 2026); at 1.7 lines it keeps the plot where it's put.
    if (given.b === undefined) p.b = Math.max(p.b, Math.ceil(o.categoryLabelGap + o.fontSize * 1.7 + 2));
    // Horizontal bars: the last value label is centred on the plot's right edge, so half of it needs room there.
    if (o.type === 'bar' && given.r === undefined) p.r = Math.max(p.r, Math.ceil(Math.max(...ticks(o).map(t => labelWidth(t, o))) / 2 + 14));
    return p;
  }

  // A figure placed on a fractional box (a template's margins come in EMUs: Berlin's content is 1009.33 px wide) drew
  // its bars a fraction off PowerPoint's, and the export report graded their edges red (Oct 18, 2026).
  // An absolutely placed figure snaps to whole pixels before it is drawn; the extractor then reads the snapped box.
  function snap(fig) {
    const p = fig.offsetParent, cs = getComputedStyle(fig);
    if (!p || cs.position !== 'absolute') return;
    const r = fig.getBoundingClientRect(), q = p.getBoundingClientRect();
    const x = r.left - q.left - p.clientLeft, y = r.top - q.top - p.clientTop;
    const X = Math.round(x), Y = Math.round(y), w = Math.round(x + r.width) - X, h = Math.round(y + r.height) - Y;
    if (Math.abs(X - x) > 0.01) fig.style.left = `${X}px`;
    if (Math.abs(Y - y) > 0.01) fig.style.top = `${Y}px`;
    if (Math.abs(w - r.width) > 0.01) fig.style.width = `${parseFloat(cs.width) + w - r.width}px`;
    if (Math.abs(h - r.height) > 0.01) fig.style.height = `${parseFloat(cs.height) + h - r.height}px`;
  }

  function draw(fig) {
    snap(fig);
    const spec = colorsOf(JSON.parse(fig.dataset.chart), fig);
    let o = { ...D, ...styleOf(fig), ...spec };
    o = { ...gaps(o), ...o };
    // The chart's key: HTML text and swatches compose writes beside the figure, so they export as native text.
    const legend = fig.dataset.id && fig.parentElement.querySelector(`[data-legend-for="${fig.dataset.id}"]`);
    if (legend) {
      // The key wraps inside its figure, from the plot's left edge: on a narrow template a one-line key ran on under
      // the takeaway panel beside the chart (Madison, Oct 18, 2026 stress test).
      const room = fig.clientWidth - (o.type === 'doughnut' ? 0 : fitPlot(o, spec.plot || {}, null).l);
      if (legend.offsetWidth > room + 0.5) {
        legend.style.maxWidth = `${room}px`;
        legend.style.flexWrap = 'wrap';
        legend.style.rowGap = '6px';
      }
    }
    o.plot = fitPlot(o, spec.plot || {}, legend);
    // Everything the native chart needs, resolved, for the extractor.
    const { plot, ...resolved } = o;
    fig.dataset.resolved = JSON.stringify(resolved);
    const W = fig.clientWidth, H = fig.clientHeight;
    fig.innerHTML = '';
    const svg = el('svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}` }, fig);
    svg.style.display = 'block';
    const P = { x: o.plot.l, y: o.plot.t, w: W - o.plot.l - o.plot.r, h: H - o.plot.t - o.plot.b };
    fig.dataset.plot = JSON.stringify(P);
    if (legend) {  // its left edge on the plot's, its top on the figure's
      legend.style.left = `${fig.offsetLeft + (o.type === 'doughnut' ? 0 : P.x)}px`;
      legend.style.top = `${fig.offsetTop}px`;
    }

    if (o.type === 'doughnut') {
      const vals = o.series[0].values, total = vals.reduce((a, b) => a + b, 0);
      const R = Math.min(P.w, P.h) / 2, r = R * o.hole / 100;
      const cx = P.x + P.w / 2, cy = P.y + P.h / 2;
      let a0 = -Math.PI / 2;  // PowerPoint starts at 12 o'clock and runs clockwise
      vals.forEach((v, i) => {
        const a1 = a0 + v / total * 2 * Math.PI, big = a1 - a0 > Math.PI ? 1 : 0;
        const p = (rad, ang) => `${cx + rad * Math.cos(ang)} ${cy + rad * Math.sin(ang)}`;
        el('path', {
          d: `M${p(R, a0)} A${R} ${R} 0 ${big} 1 ${p(R, a1)} L${p(r, a1)} A${r} ${r} 0 ${big} 0 ${p(r, a0)} Z`,
          fill: (o.colors || [])[i] || o.series[0].color,
        }, svg);
        a0 = a1;
      });
      return;
    }

    const { min, max, step } = o.axis;
    const horiz = o.type === 'bar', stacked = !!o.stacked && (o.type === 'column' || o.type === 'bar');
    const [dy, dx] = shift(o);
    const n = o.categories.length;
    const yOf = v => P.y + P.h - (v - min) / (max - min) * P.h;
    const xOf = v => P.x + (v - min) / (max - min) * P.w;
    if (!horiz) {
      for (let v = min; v <= max + 1e-9; v += step) {
        const y = yOf(v);
        el('line', { x1: P.x, x2: P.x + P.w, y1: y, y2: y, stroke: o.gridColor, 'stroke-width': o.gridWidth }, svg);
        text(svg, fmt(v, o), P.x - o.valueLabelGap + dx, y, 'end', o);
      }
      const cw = P.w / n;
      o.categories.forEach((c, i) => {
        text(svg, c, P.x + cw * (i + 0.5), P.y + P.h + o.categoryLabelGap + o.fontSize * 0.6 + dy, 'middle', o);
      });
    } else {
      // A horizontal bar chart: values along the bottom, categories down the left, the first at the top (PowerPoint:
      // the category axis reversed, the value axis crossing at its maximum so it stays at the bottom).
      for (let v = min; v <= max + 1e-9; v += step) {
        const x = xOf(v);
        el('line', { x1: x, x2: x, y1: P.y, y2: P.y + P.h, stroke: o.gridColor, 'stroke-width': o.gridWidth }, svg);
        text(svg, fmt(v, o), x, P.y + P.h + o.categoryLabelGap + o.fontSize * 0.6 + dy, 'middle', o);
      }
      const ch = P.h / n;
      // Category labels on the left sit a little further out than the plain gap: 0.11 em uncalibrated (bench k08, Oct 18,
      // 2026: 2 px at 18 px), else the brand's own measured lean. Both at once put them 2 to 3 px too far out (range,
      // two templates, Oct 18, 2026).
      const out = o.labelCal && o.labelCal.length ? dx : -0.11 * o.fontSize;
      o.categories.forEach((c, i) => text(svg, c, P.x - o.valueLabelGap + out, P.y + ch * (i + 0.5), 'end', o));
    }

    // Value labels: HTML text over the chart, so they export as native text boxes. chart.js owns their positions.
    const labels = [];
    const lfmt = v => (v < 0 ? '-' : '') + (o.labelFormat || o.axis.format || '{v}').replace('{v}', Math.abs(+(+v).toFixed(6)));
    if (o.type === 'column' || o.type === 'bar') {
      // PowerPoint: per category, k bars of thickness b and a gap of gap% x b, the gap split half before and half
      // after. Stacked: one bar per category, positives stacked up from zero and negatives down, each on its own.
      const band = (horiz ? P.h : P.w) / n;
      const k = stacked ? 1 : o.series.length, b = band / (k + o.gap / 100);
      const pos = new Array(n).fill(0), neg = new Array(n).fill(0);
      o.series.forEach((s, si) => s.values.forEach((v, i) => {
        if (v === null || v === undefined) return;
        const base = stacked ? (v >= 0 ? pos[i] : neg[i]) : 0, top = base + v;
        if (stacked) { if (v >= 0) pos[i] = top; else neg[i] = top; }
        const off = band * i + b * o.gap / 200 + (stacked ? 0 : si * b);
        // One series may color each bar on its own (`colors`, by category), as PowerPoint's data points can.
        const fill = (o.series.length === 1 && (o.colors || [])[i]) || s.color;
        const clamp = t => Math.min(Math.max(t, min), max);
        if (!horiz) {
          const x = P.x + off, y0 = yOf(clamp(base)), y1 = yOf(clamp(top));
          el('rect', { x, y: Math.min(y0, y1), width: b, height: Math.abs(y1 - y0), fill }, svg);
          if (o.labels) labels.push(stacked ? { t: lfmt(v), cx: x + b / 2, cy: (y0 + y1) / 2, inside: true, on: s.on }
                                            : { t: lfmt(v), cx: x + b / 2, cy: v >= 0 ? y1 - o.fontSize * 0.8 - 4 : y1 + o.fontSize * 0.8 + 4 });
        } else {
          const y = P.y + off, x0 = xOf(clamp(base)), x1 = xOf(clamp(top));
          el('rect', { x: Math.min(x0, x1), y, width: Math.abs(x1 - x0), height: b, fill }, svg);
          if (o.labels) labels.push(stacked ? { t: lfmt(v), cx: (x0 + x1) / 2, cy: y + b / 2, inside: true, on: s.on }
                                            : { t: lfmt(v), x: v >= 0 ? x1 + 8 : null, xr: v < 0 ? x1 - 8 : null, cy: y + b / 2 });
        }
      }));
    } else if (o.type === 'line' || o.type === 'area') {
      const cw = P.w / n;
      o.series.forEach(s => {
        const pts = s.values.map((v, i) => [P.x + cw * (i + 0.5), yOf(v)]);
        if (o.type === 'area') {
          const y0 = yOf(Math.max(min, 0));
          const poly = [[pts[0][0], y0], ...pts, [pts[pts.length - 1][0], y0]].map(p => p.join(',')).join(' ');
          el('polygon', { points: poly, fill: s.color, 'fill-opacity': s.opacity === undefined ? 1 : s.opacity }, svg);
        } else {
          el('polyline', { points: pts.map(p => p.join(',')).join(' '), fill: 'none', stroke: s.color, 'stroke-width': o.lineWidth,
                           'stroke-linejoin': 'round', 'stroke-linecap': 'round' }, svg);
        }
        if (o.labels) labels.push({ t: lfmt(s.values[s.values.length - 1]), x: pts[pts.length - 1][0] + 10, cy: pts[pts.length - 1][1] });
      });
      // Lines that end close together printed their labels over each other ("49.6%" on "50.4%", Oct 18, 2026 stress
      // test): spread them a line apart, keeping their middle where it was.
      const ends = labels.slice().sort((a, b) => a.cy - b.cy), gap = Math.round(o.fontSize * 1.25);
      if (ends.length > 1 && ends.some((L, i) => i && L.cy - ends[i - 1].cy < gap)) {
        const was = ends.reduce((a, L) => a + L.cy, 0) / ends.length;
        for (let i = 1; i < ends.length; i++) ends[i].cy = Math.max(ends[i].cy, ends[i - 1].cy + gap);
        const shift = ends.reduce((a, L) => a + L.cy, 0) / ends.length - was;
        ends.forEach(L => { L.cy -= shift; });
      }
    }
    placeLabels(fig, labels, o);
  }

  function placeLabels(fig, labels, o) {
    const fid = fig.dataset.id || 'chart';
    let box = fig.parentElement.querySelector(`[data-labels-for="${fid}"]`);
    if (!labels.length) { if (box) box.remove(); return; }
    if (!box) {
      box = document.createElement('div');
      box.dataset.labelsFor = fid;
      box.dataset.id = `${fid}-labels`;
      box.style.cssText = 'position:absolute;left:0;top:0;width:0;height:0';
      fig.after(box);
    }
    box.innerHTML = '';
    const lh = Math.round(o.fontSize * 1.25 * 0.75) / 0.75;  // a whole point, as PowerPoint draws it
    labels.forEach((L, i) => {
      const p = document.createElement('p');
      const w = Math.ceil(labelWidth(L.t, o)) + 2;
      const left = L.cx !== undefined ? L.cx - w / 2 : L.x !== null && L.x !== undefined ? L.x : L.xr - w;
      p.dataset.id = `${fid}-label-${i + 1}`;
      p.textContent = L.t;
      p.style.cssText = `position:absolute;margin:0;white-space:nowrap;left:${fig.offsetLeft + left}px;` +
        `top:${fig.offsetTop + L.cy - lh / 2}px;width:${w}px;font-size:${o.fontSize}px;line-height:${lh}px;` +
        `font-family:"${o.font}";font-weight:${o.labelWeight || o.fontWeight};text-align:${L.cx !== undefined ? 'center' : L.xr !== null && L.xr !== undefined ? 'right' : 'left'};` +
        `color:${L.inside ? (o.insideLabelColor || L.on || '#ffffff') : (o.valueLabelColor || o.labelColor)};font-kerning:none`;
      box.appendChild(p);
    });
  }

  const run = () => document.querySelectorAll('[data-chart]').forEach(draw);
  if (document.fonts) document.fonts.ready.then(run); else run();
  window.skaldCharts = run;
  window.skaldChartTicks = ticks;
})();
