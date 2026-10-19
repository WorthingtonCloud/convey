// Compare two pictures of one slide (the browser's and PowerPoint's), inside the installed Chrome.
// Called by verify.py as conveyPixelDiff(a, b, opts) with two PNG data URLs, both drawn by the same
// PDF engine at the same size. The same rules as the private test bench:
//  - a pixel differs only if nothing within 2 device px in the other picture is close (forgives
//    edge smoothing and nothing else), both ways;
//  - hairline edges up to 2 device px thick are dropped (text one pixel off; the text check grades it);
//  - "spots": 16x16 cells with >= 24 differing pixels, joined with their neighbors. A spot inside a
//    text box is that text sitting a little off and is left to the text check.
// Returns percentages, spots, the elements that differ most, and a difference map (PNG data URL).
async function conveyPixelDiff(aUrl, bUrl, opts) {
  const R = 2, T = 48, CELL = 16, MIN_CELL = 24;
  const scale = opts.scale;
  const load = async (u) => createImageBitmap(await (await fetch(u)).blob());
  const [ia, ib] = await Promise.all([load(aUrl), load(bUrl)]);
  const W = Math.min(ia.width, ib.width), H = Math.min(ia.height, ib.height);
  const pixels = (img) => {
    const c = new OffscreenCanvas(W, H), g = c.getContext("2d", {willReadFrequently: true});
    g.drawImage(img, 0, 0);
    return g.getImageData(0, 0, W, H).data;
  };
  const A = pixels(ia), B = pixels(ib), N = W * H;
  const far = (P, p, Q, q) => Math.max(Math.abs(P[p] - Q[q]), Math.abs(P[p + 1] - Q[q + 1]), Math.abs(P[p + 2] - Q[q + 2]));
  const best = (P, Q, x, y) => {  // the closest pixel of Q within R of (x, y), compared with P's pixel there
    let b = 999;
    const p = (y * W + x) * 4;
    for (let dy = -R; dy <= R; dy++) {
      const yy = y + dy;
      if (yy < 0 || yy >= H) continue;
      for (let dx = -R; dx <= R; dx++) {
        const xx = x + dx;
        if (xx < 0 || xx >= W) continue;
        const d = far(P, p, Q, (yy * W + xx) * 4);
        if (d < b) { b = d; if (b <= T) return b; }
      }
    }
    return b;
  };
  const mask = new Uint8Array(N);
  let raw = 0;
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const i = y * W + x;
      if (far(A, i * 4, B, i * 4) <= T) continue;  // same pixel: close both ways
      if (best(A, B, x, y) > T || best(B, A, x, y) > T) { mask[i] = 1; raw++; }
    }
  }
  // Drop hairlines: keep a pixel only if its 8 neighbors differ too.
  const m = new Uint8Array(N);
  let kept = 0;
  for (let y = 1; y < H - 1; y++) {
    for (let x = 1; x < W - 1; x++) {
      const i = y * W + x;
      if (!mask[i]) continue;
      if (mask[i - 1] && mask[i + 1] && mask[i - W] && mask[i + W] &&
          mask[i - W - 1] && mask[i - W + 1] && mask[i + W - 1] && mask[i + W + 1]) { m[i] = 1; kept++; }
    }
  }
  // Spots.
  const hh = Math.floor(H / CELL), ww = Math.floor(W / CELL);
  const cells = new Uint8Array(hh * ww);
  for (let y = 0; y < hh * CELL; y++) {
    for (let x = 0; x < ww * CELL; x++) if (m[y * W + x]) cells[Math.floor(y / CELL) * ww + Math.floor(x / CELL)]++;
  }
  for (let c = 0; c < cells.length; c++) cells[c] = cells[c] >= MIN_CELL ? 1 : 0;
  const seen = new Uint8Array(hh * ww), spots = [], k = CELL / scale;
  for (let cy = 0; cy < hh; cy++) {
    for (let cx = 0; cx < ww; cx++) {
      if (!cells[cy * ww + cx] || seen[cy * ww + cx]) continue;
      const stack = [[cy, cx]], box = [cy, cx, cy, cx];
      seen[cy * ww + cx] = 1;
      while (stack.length) {
        const [y, x] = stack.pop();
        box[0] = Math.min(box[0], y); box[1] = Math.min(box[1], x); box[2] = Math.max(box[2], y); box[3] = Math.max(box[3], x);
        for (const [ny, nx] of [[y + 1, x], [y - 1, x], [y, x + 1], [y, x - 1]]) {
          if (ny >= 0 && ny < hh && nx >= 0 && nx < ww && cells[ny * ww + nx] && !seen[ny * ww + nx]) {
            seen[ny * ww + nx] = 1;
            stack.push([ny, nx]);
          }
        }
      }
      spots.push({x: Math.round(box[1] * k), y: Math.round(box[0] * k),
                  w: Math.round((box[3] - box[1] + 1) * k), h: Math.round((box[2] - box[0] + 1) * k)});
    }
  }
  const inText = (sp) => opts.textBoxes.some(([a, b, c, d]) => sp.x >= a && sp.y >= b && sp.x + sp.w <= c && sp.y + sp.h <= d);
  const textSpots = spots.filter(inText).length, other = spots.filter((sp) => !inText(sp));
  // Which elements carry the difference: each differing pixel belongs to the smallest element over it (a label on
  // a card is the label's), and a pixel under no element is the template's own background. Ranked by their share of
  // the slide's difference, so a big culprit outranks a small element with a few changed pixels.
  const owner = new Int16Array(N).fill(-1);
  const els = opts.elements.map((e, i) => ({e, i, area: e.w * e.h})).sort((a, b) => b.area - a.area);
  for (const {e, i} of els) {
    const x0 = Math.max(Math.floor(e.x * scale), 0), y0 = Math.max(Math.floor(e.y * scale), 0);
    const x1 = Math.min(Math.floor((e.x + e.w) * scale), W), y1 = Math.min(Math.floor((e.y + e.h) * scale), H);
    for (let y = y0; y < y1; y++) owner.fill(i, y * W + x0, y * W + Math.max(x1, x0));
  }
  const count = new Map();
  for (let i = 0; i < N; i++) if (m[i]) count.set(owner[i], (count.get(owner[i]) || 0) + 1);
  const total = [...count.values()].reduce((a, b) => a + b, 0) || 1;
  const worst = [...count.entries()]
    .map(([i, n]) => ({id: i < 0 ? "the template's background" : opts.elements[i].id, pct: Math.round(n / total * 1000) / 10}))
    .filter((w) => w.pct >= 5);
  worst.sort((a, b) => b.pct - a.pct);
  // The difference map: the browser's slide dimmed, differences red, spots outlined in yellow.
  const out = new OffscreenCanvas(W, H), g = out.getContext("2d");
  const img = g.createImageData(W, H), D = img.data;
  for (let i = 0; i < N; i++) {
    const o = i * 4, v = (A[o] + A[o + 1] + A[o + 2]) / 3 * 0.35;
    D[o] = D[o + 1] = D[o + 2] = v; D[o + 3] = 255;
    if (mask[i]) { D[o] = 150; D[o + 1] = 30; D[o + 2] = 30; }
    if (m[i]) { D[o] = 255; D[o + 1] = 40; D[o + 2] = 40; }
  }
  g.putImageData(img, 0, 0);
  g.strokeStyle = "rgb(255,210,60)";
  g.lineWidth = 3 * scale / 2;
  for (const sp of other) g.strokeRect(sp.x * scale - 3, sp.y * scale - 3, sp.w * scale + 6, sp.h * scale + 6);
  const small = new OffscreenCanvas(Math.round(W / scale), Math.round(H / scale));
  small.getContext("2d").drawImage(out, 0, 0, small.width, small.height);
  const blob = await small.convertToBlob({type: "image/png"});
  const map = await new Promise((res) => { const r = new FileReader(); r.onload = () => res(r.result); r.readAsDataURL(blob); });
  const pct = (n) => Math.round(n / N * 100 * 1000) / 1000;
  return {diff_raw_pct: pct(raw), diff_pct: pct(kept), spots: other, text_spots: textSpots,
          worst_elements: worst.slice(0, 6), map, size: [W, H]};
}
