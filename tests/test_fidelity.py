"""The fidelity fixes the design range needed (Oct 18, 2026), each on a made-up fixture:

- a wrapped line that fills its box gets spare frame width, never enough to pull the next word up;
- a font's measured width table picks the nearest size, and the export writes it as letter spacing;
- a brand color mixed with transparent (color-mix) reads as a color with alpha, in fills, gradients and shadows;
- chart.js moves its axis labels by a brand's measured offsets (--brand-chart-labels), and only then;
- a chart placed on a fractional box (a template's EMU margins) snaps to whole pixels, its key wraps inside the
  figure, and line-end labels that would overprint spread a line apart (Oct 18, 2026 stress test).

Run: python3 skill/tests/test_fidelity.py   (needs Chrome or Edge installed, nothing else)
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from convey.skald.emit import Emitter, _spare_width, predict_advance  # noqa: E402
from convey.skald.measure import CHART_JS, measure, slide_page  # noqa: E402

FAILS = []


def check(ok: bool, what: str):
    print(("ok    " if ok else "FAIL  ") + what)
    if not ok:
        FAILS.append(what)


def words(*rows):
    """A paragraph from rows of (x, width) words, one row per line, 20 px apart."""
    return [{"t": "w", "x": x, "y": 100 + 20 * i, "w": w, "h": 16} for i, row in enumerate(rows) for x, w in row]


# 1. Spare width: line 1 ends exactly at the frame's edge (100..400); the next line starts with a 60 px word.
t = {"lineHeight": 20, "runs": [{"size": 16}], "paras": [{"lineHeight": 20, "words": words(
    [(100, 80), (190, 90), (290, 110)], [(100, 60), (170, 50)])}]}
room = _spare_width(t, 100, 400, "left")
check(0 < room <= 300 * 0.004 + 1e-9, f"a line that fills its box gets spare width ({room:.2f} px, capped at 0.4%)")
# The next word would fit with 4 px more: the room must stay under half of that.
t2 = {"lineHeight": 20, "runs": [{"size": 16}], "paras": [{"lineHeight": 20, "words": words(
    [(100, 80), (190, 90), (290, 50)], [(100, 56), (166, 50)])}]}
room2 = _spare_width(t2, 100, 400, "left")
check(room2 <= 2.0 + 1e-9, f"never enough to pull the next line's first word up ({room2:.2f} px <= 2 px)")
check(_spare_width({"runs": [{"size": 16}], "paras": [{"words": words([(100, 80)])}]}, 100, 400, "left") > 0,
      "one line has nothing to pull up")

# 2. Width table: the nearest measured size counts.
v = {"advance": [[14, -0.019], [16, 0.0315], [18, -0.0233]]}
check(predict_advance(v, 16) == 0.0315 and predict_advance(v, 17.2) == 0.0233 * -1 and predict_advance(None, 16) == 0,
      "a width table gives the nearest size's correction, none without a table")

# 3. color-mix fills, gradients and shadows, through the real extractor; then the export writes the alpha.
HEAD = """<!doctype html><html><head><meta charset="utf-8"><style>
* { box-sizing: border-box; margin: 0; padding: 0; }
:root { --c: #3366aa; --brand-chart-labels: "16 2 -1"; }
.slide { position: relative; width: 1280px; height: 720px; overflow: hidden; background: #101010; color: #ffffff;
  font-family: Helvetica; font-size: 18px; line-height: 24px; font-kerning: none; }
.abs { position: absolute; }
.plain { --brand-chart-labels: ""; }
</style></head><body><section class="slide">BODY</section><script src="chart.js"></script></body></html>"""
BODY = """
<div class="abs" data-id="fill" style="left:40px;top:40px;width:200px;height:100px;background:color-mix(in srgb, var(--c) 50%, transparent)"></div>
<div class="abs" data-id="glow" style="left:300px;top:40px;width:200px;height:200px;border-radius:50%;background:radial-gradient(circle, color-mix(in srgb, var(--c) 40%, transparent) 0%, transparent 70%)"></div>
<div class="abs" data-id="lift" style="left:560px;top:40px;width:200px;height:100px;background:#202020;box-shadow:0px 8px 16px color-mix(in srgb, var(--c) 45%, transparent)"></div>
<figure class="abs" data-id="cal" data-chart='{"type":"column","categories":["North","South"],"series":[{"name":"A","values":[40,80],"color":"#448844"}],"axis":{"min":0,"max":100,"step":50,"format":"{v}%"},"fontSize":16}' style="left:40px;top:300px;width:560px;height:300px;margin:0"></figure>
<figure class="abs plain" data-id="raw" data-chart='{"type":"column","categories":["North","South"],"series":[{"name":"A","values":[40,80],"color":"#448844"}],"axis":{"min":0,"max":100,"step":50,"format":"{v}%"},"fontSize":16}' style="left:680px;top:300px;width:560px;height:300px;margin:0"></figure>
<figure class="abs plain" data-id="keyed" data-chart='{"type":"bar","categories":["A","B"],"series":[{"name":"A","values":[1,2],"color":"#448844"}],"axis":{"min":0,"max":2,"step":1,"format":"{v}"},"fontSize":16}' style="left:900px;top:40px;width:300px;height:200px;margin:0"></figure>
<div data-id="keyed-legend" data-legend-for="keyed" style="position:absolute;display:flex;align-items:center;column-gap:28px"><div style="display:flex;column-gap:10px"><div style="width:14px;height:14px;background:#448844"></div><p style="margin:0;white-space:nowrap;font-size:16px;line-height:20px">Run or paid for by a maker</p></div><div style="display:flex;column-gap:10px"><div style="width:14px;height:14px;background:#884444"></div><p style="margin:0;white-space:nowrap;font-size:16px;line-height:20px">Independent</p></div></div>
<figure class="abs plain" data-id="ends" data-chart='{"type":"line","labels":true,"categories":["a","b"],"series":[{"name":"A","values":[40,49.6],"color":"#448844"},{"name":"B","values":[60,50.4],"color":"#884444"}],"axis":{"min":0,"max":100,"step":50,"format":"{v}%"},"fontSize":16}' style="left:40px;top:40px;width:200px;height:200px;margin:0"></figure>
<figure class="abs plain" data-id="snap" data-chart='{"type":"column","categories":["A"],"series":[{"name":"A","values":[1],"color":"#448844"}],"axis":{"min":0,"max":2,"step":1,"format":"{v}"},"fontSize":16}' style="left:71.425px;top:606.4px;width:1009.33px;height:100.5px;margin:0"></figure>
"""
with tempfile.TemporaryDirectory() as d:
    f = Path(d) / "s.html"
    f.write_text(HEAD.replace("BODY", BODY))
    (Path(d) / "chart.js").write_text(CHART_JS.read_text())
    g = Path(d) / "faded.html"
    g.write_text(HEAD.replace("BODY", '<div class="abs" data-id="dim" style="left:40px;top:40px;width:200px;height:200px;'
                              'border-radius:50%;opacity:0.5;background:radial-gradient(circle, #3366aa 0%, transparent 70%)"></div>'))
    errs = measure([g])[0].get("errors") or []
    check(any("opacity on a gradient" in e for e in errs), f"lint refuses opacity on a gradient ({errs})")
    sc = measure([f])[0]
    check(not sc.get("errors"), f"color-mix passes lint ({sc.get('errors')})")
    el = {e["id"]: e for e in sc["elements"]}
    fill = el["fill"].get("fill") or {}
    check(fill.get("hex") == "3366aa" and abs(fill.get("a", 1) - 0.5) < 0.01, f"a mixed fill keeps its color and alpha ({fill})")
    st = (el["glow"].get("gradient") or {}).get("stops") or []
    check(len(st) == 2 and st[0]["hex"] == "3366aa" and abs(st[0]["a"] - 0.4) < 0.01, "a mixed gradient stop keeps its alpha")
    sh = (el["lift"].get("shadow") or {}).get("color") or {}
    check(sh.get("hex") == "3366aa" and abs(sh.get("a", 1) - 0.45) < 0.01, "a mixed shadow keeps its alpha")
    words = [w for e in sc["elements"] if e.get("text") for p in e["text"].get("paras", []) for w in p.get("words", [])
             if w["t"] in ("maker", "Independent")]
    k = el["keyed"]
    check(len(words) == 2 and max(w["x"] + w["w"] for w in words) <= k["x"] + k["w"] + 0.5,
          f"a chart's key wraps inside its figure, never past it ({[round(w['x'] + w['w']) for w in words]} vs {k['x'] + k['w']})")
    ys = sorted(e["y"] for e in sc["elements"] if str(e.get("id", "")).startswith("ends-label-") and e.get("text"))
    check(len(ys) == 2 and ys[1] - ys[0] >= 16 * 1.2, f"line-end labels close together are spread a line apart ({ys})")
    sn = el["snap"]
    check(all(abs(sn[k] - round(sn[k])) < 0.01 for k in ("x", "y", "w", "h")) and abs(sn["x"] - 71.425) < 1,
          f"a chart on a fractional box snaps to whole pixels ({sn['x']}, {sn['y']}, {sn['w']} x {sn['h']})")
    deck = Emitter().deck([sc])
    out = Path(d) / "s.pptx"
    deck.save(out)
    import zipfile
    xml = zipfile.ZipFile(out).read("ppt/slides/slide1.xml").decode()
    check('<a:srgbClr val="3366AA"><a:alpha val="50000" />' in xml, "the export writes the fill's alpha")

    # 4. chart labels: the calibrated figure's category label sits 2 px lower and its axis label ends 1 px further left of
    # the plot (whose left margin grows by the same 1 px, so PowerPoint finds the room it wants).
    with slide_page() as page:
        page.goto(f.as_uri())
        pos = page.evaluate("""(() => { const at = id => { const f = document.querySelector(`[data-id="${id}"]`);
          const t = [...f.querySelectorAll('text')]; const cat = t.find(x => x.textContent === 'North');
          const top = t.find(x => x.textContent === '100%');
          return [ +cat.getAttribute('y'), +top.getAttribute('x') - JSON.parse(f.dataset.plot).x ]; };
          return [at('cal'), at('raw')]; })()""")
    (cy, cx), (ry, rx) = pos
    check(abs((cy - ry) - 2) < 0.01 and abs((cx - rx) + 1) < 0.01,
          f"chart.js moves axis labels by the brand's measured offsets only where they're set (dy {cy - ry:.2f}, dx {cx - rx:.2f})")

print(f"fidelity test: {len(FAILS)} failure(s)")
sys.exit(1 if FAILS else 0)
