"""Lint refuses every known-bad feature by name, and passes a slide made of allowed parts.
Neutral, made-up fixtures only.

Run: python3 skill/tests/test_lint.py   (needs Chrome or Edge installed, nothing else)
"""
from __future__ import annotations

import sys
import shutil
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from convey.skald.measure import CHART_JS, measure  # noqa: E402

HEAD = """<!doctype html><html><head><meta charset="utf-8"><style>
* { box-sizing: border-box; margin: 0; padding: 0; }
.slide { position: relative; width: 1280px; height: 720px; overflow: hidden; background: #ffffff;
  color: #222222; font-family: Helvetica; font-size: 18px; line-height: 27px; font-kerning: none; }
.abs { position: absolute; }
</style>{extra}</head><body><section class="slide">{body}</section></body></html>"""

ARROW = """<svg class="abs" style="left:0;top:0" width="1280" height="720"><defs>
<marker id="m" markerUnits="userSpaceOnUse" markerWidth="{w}" markerHeight="{w}" viewBox="0 0 {w} {w}"
 refX="{w}" refY="{h}" orient="auto"><path d="{d}" fill="{fill}"/></marker></defs>
<line data-id="arrow" x1="100" y1="600" x2="400" y2="600" stroke="#444444" stroke-width="2" marker-end="url(#m)"/></svg>"""


def arrow(w=8.0, d=None, fill="#444444"):
    return ARROW.format(w=w, h=w / 2, d=d or f"M0 0 L{w} {w / 2} L0 {w} z", fill=fill)


GOOD = f"""
<h1 class="abs" data-id="title" style="left:64px;top:48px;font-size:40px;line-height:48px;font-weight:700">A plain title</h1>
<div class="abs" data-id="box" style="left:64px;top:140px;width:300px;height:120px;background:#eeeeee;border:1px solid #999999;border-radius:8px;display:flex;align-items:center;justify-content:center">Label</div>
<ul class="abs" data-id="list" style="left:420px;top:140px;width:400px;list-style-type:'•  '"><li>One</li><li>Two</li></ul>
<div class="abs" data-id="tilt" style="left:900px;top:140px;width:200px;height:80px;background:#cccccc;transform:rotate(-8deg)"></div>
<p class="abs" data-id="kpi" style="left:64px;top:300px;font-size:64px;line-height:64px">10,462</p>
<p class="abs" data-id="kpi-label" style="left:64px;top:364px;font-size:18px;line-height:20px">Candidates a night, set tight under it</p>
<div class="abs" data-id="lifted" style="left:900px;top:450px;width:200px;height:100px;border-radius:12px;background:#ffffff;box-shadow:0 12px 24px rgba(0,0,0,0.3)"></div>
<div class="abs" data-id="fade" style="left:900px;top:300px;width:200px;height:100px;background:linear-gradient(135deg, #336699, rgba(0,0,0,0))"></div>
<div class="abs" data-id="glow" style="left:1100px;top:300px;width:120px;height:120px;background:radial-gradient(circle, #6688cc, #222222)"></div>
<p class="abs" data-id="wm" data-overlap style="left:700px;top:400px;width:300px;line-height:40px">A deliberate overlap, marked as one</p>
<p class="abs" data-id="wm2" style="left:700px;top:420px;width:300px;line-height:40px">Its partner, interleaved on purpose</p>
{arrow()}"""

# feature -> (slide body, extra <head> content, words the refusal must contain)
BAD = {
    "two gradients": ('<div class="abs" data-id="bad" style="left:0;top:0;width:200px;height:200px;background:linear-gradient(red,blue),linear-gradient(green,white)"></div>', "", "only one linear or radial"),
    "radial off centre": ('<div class="abs" data-id="bad" style="left:0;top:0;width:300px;height:200px;background:radial-gradient(circle at 30% 20%, red, blue)"></div>', "", "only centred"),
    "radial ellipse": ('<div class="abs" data-id="bad" style="left:0;top:0;width:300px;height:200px;background:radial-gradient(red, blue)"></div>', "", "only as a circle"),
    "gradient text": ('<p class="abs" data-id="bad" style="left:0;top:0;background:linear-gradient(red,blue);-webkit-background-clip:text;background-clip:text;color:transparent">Shiny</p>', "", "gradient text"),
    "background image": ('<div class="abs" data-id="bad" style="left:0;top:0;width:200px;height:200px;background-image:url(x.png)"></div>', "", "background image"),
    "two shadows": ('<div class="abs" data-id="bad" style="left:0;top:0;width:200px;height:200px;background:#eee;box-shadow:0 4px 8px #000, 0 1px 2px #000"></div>', "", "only one shadow"),
    "inset shadow": ('<div class="abs" data-id="bad" style="left:0;top:0;width:200px;height:200px;background:#eee;box-shadow:inset 0 4px 8px #000"></div>', "", "inset"),
    "shadow spread": ('<div class="abs" data-id="bad" style="left:0;top:0;width:200px;height:200px;background:#eee;box-shadow:0 4px 8px 6px #000"></div>', "", "spread"),
    "shadow on bare text": ('<p class="abs" data-id="bad" style="left:0;top:0;box-shadow:0 4px 8px #000">Text</p>', "", "no fill or border"),
    "text shadow": ('<p class="abs" data-id="bad" style="left:0;top:0;text-shadow:0 0 4px #000">Glow</p>', "", "text-shadow"),
    "filter": ('<div class="abs" data-id="bad" style="left:0;top:0;width:200px;height:200px;background:#eee;filter:blur(2px)"></div>', "", "filter"),
    "clip path": ('<div class="abs" data-id="bad" style="left:0;top:0;width:200px;height:200px;background:#eee;clip-path:circle(40%)"></div>', "", "clip-path"),
    "pseudo element": ('<p class="abs deco" data-id="bad" style="left:0;top:0">Text</p>', "<style>.deco::before{content:'>'}</style>", "::before"),
    "canvas": ('<canvas class="abs" data-id="bad" width="100" height="100"></canvas>', "", "<canvas>"),
    "svg text": ('<svg class="abs" width="300" height="100"><text data-id="bad" x="10" y="50">Hi</text></svg>', "", "SVG <text>"),
    "dashed border": ('<div class="abs" data-id="bad" style="left:0;top:0;width:200px;height:200px;border:2px dashed #000"></div>', "", "dashed border"),
    "mixed radii": ('<div class="abs" data-id="bad" style="left:0;top:0;width:200px;height:200px;background:#eee;border-radius:4px 20px"></div>', "", "different radii"),
    "scale transform": ('<div class="abs" data-id="bad" style="left:0;top:0;width:200px;height:200px;background:#eee;transform:scale(1.2)"></div>', "", "only rotation"),
    "rotated parent": ('<div class="abs" data-id="bad" style="left:0;top:0;width:200px;height:200px;transform:rotate(5deg)"><p style="font-size:18px;line-height:27px">Child</p><p style="font-size:18px;line-height:27px">Child</p></div>', "", "rotation on an element with children"),
    "line-height normal": ('<p class="abs" data-id="bad" style="left:0;top:0;line-height:normal">Text</p>', "", "line-height normal"),
    "kerning on": ('<p class="abs" data-id="bad" style="left:0;top:0;font-kerning:normal">Text</p>', "", "font-kerning"),
    "overflow": ('<p class="abs" data-id="bad" style="left:0;top:0;width:40px">Unbreakableword</p>', "", "overflows"),
    "disc bullets": ('<ul class="abs" data-id="list" style="left:40px;top:0;width:300px"><li data-id="bad">Dot</li></ul>', "", "disc"),
    "arrow size": (arrow(w=6.0).replace('data-id="arrow"', 'data-id="bad"'), "", "not a PowerPoint size"),
    "arrow shape": (arrow(d="M0 0 L8 4 L0 8 L2 4 z").replace('data-id="arrow"', 'data-id="bad"'), "", "one filled triangle"),
    "arrow color": (arrow(fill="#ff0000").replace('data-id="arrow"', 'data-id="bad"'), "", "color differs"),
    "chart without chart.js": ('<figure class="abs" data-id="bad" data-chart=\'{"type":"column","categories":["a"],"series":[{"name":"s","values":[1],"color":"#336699"}],"axis":{"min":0,"max":2,"step":1}}\' style="left:0;top:0;width:400px;height:300px"></figure>', "", "not drawn"),
    "text over text": ('<p class="abs" data-id="bad" style="left:0;top:0;width:140px">A label long enough to wrap onto three lines</p>'
                       '<p class="abs" data-id="note" style="left:0;top:30px;width:300px">The note that sat under it</p>', "", "overlaps note"),
    "chart label too wide": ('<figure class="abs" data-id="bad" data-chart=\'{"type":"column","categories":["Sensor readout","Calibrate and subtract","Find candidates","Upload cutouts","Intake queue","Cross-match","Score","Fan-out","Push delivery"],"series":[{"name":"s","values":[1,2,1,1,1,1,1,1,1],"color":"#336699"}],"axis":{"min":0,"max":2,"step":1}}\' style="left:0;top:0;width:560px;height:300px;font-size:12px;font-family:Helvetica"></figure>', '<script src="chart.js"></script>', "wider than its"),
    "text box over text box": ('<p class="abs" data-id="bad" style="left:0;top:0;width:150px;line-height:40px">Two lines of a list placed on</p>'
                               '<p class="abs" data-id="other" style="left:0;top:20px;width:150px;line-height:40px">another list, its lines between</p>', "", "text box overlaps"),
    "chart value label cut": ('<figure class="abs" data-id="bad" data-chart=\'{"type":"column","categories":["a","b"],"series":[{"name":"s","values":[-900,900],"color":"#336699"}],"axis":{"min":-1000,"max":1000,"step":500,"format":"${v}K"},"fontSize":16,"plot":{"l":20}}\' style="left:100px;top:100px;width:600px;height:400px"></figure>', "<script src=\"chart.js\"></script>", "value label"),
    # Collisions only looking caught in the stress test (Oct 18, 2026): a callout on a chart's year labels, a takeaway run
    # out of its panel, a legend drawn under the panel beside it.
    "text on axis labels": ('<figure class="abs" data-id="fig" data-chart=\'{"type":"column","categories":["2005","2015","2025"],"series":[{"name":"s","values":[1,2,1],"color":"#336699"}],"axis":{"min":0,"max":2,"step":1},"fontSize":16}\' style="left:100px;top:100px;width:600px;height:400px"></figure>'
                            '<p class="abs" data-id="bad" style="left:300px;top:478px;width:300px">A callout on the years</p>', '<script src="chart.js"></script>', "axis labels"),
    "text past its panel": ('<div class="abs" data-id="panel" style="left:0;top:0;width:200px;height:60px;background:#eeeeee"><p data-id="bad">Three lines of words that will never fit inside this short panel</p></div>', "", "bottom edge of the panel"),
    "text under a box": ('<p class="abs" data-id="bad" style="left:0;top:0;width:400px">A legend that runs on to the right</p>'
                         '<div class="abs" data-id="cover" style="left:150px;top:0;width:200px;height:80px;background:#dddddd"></div>', "", "drawn under cover"),
    "icon under 32px": ('<svg class="abs" data-icon="dot" data-id="bad" width="24" height="24" viewBox="0 0 48 48" fill="none" stroke="#222222" stroke-width="3"><circle cx="24" cy="24" r="18"/></svg>', "", "32px and up"),
}


def main() -> int:
    d = Path(tempfile.mkdtemp(prefix="convey-lint-"))
    (d / "00-good.html").write_text(HEAD.replace("{extra}", "").replace("{body}", GOOD))
    (d / "chart.js").write_bytes(CHART_JS.read_bytes())  # for the slides that draw a chart
    names = {}
    for i, (name, (body, extra, _)) in enumerate(BAD.items(), 1):
        f = d / f"{i:02d}-bad.html"
        f.write_text(HEAD.replace("{extra}", extra).replace("{body}", body))
        names[f.stem] = name
    # A word the browser breaks at its hyphen still makes a second line (counted as one, the export turned wrapping off
    # and PowerPoint ran "go-live." past its box, Oct 18, 2026).
    (d / "98-hyphen.html").write_text(HEAD.replace("{extra}", "").replace("{body}", "".join(
        f'<p class="abs" data-id="split-{w}" style="left:0;top:{(w - 150) * 10}px;width:{w}px;font-size:18px;line-height:27px">'
        'Then check it after go-live.</p>' for w in range(150, 216, 3))))
    scenes = {sc["card"]: sc for sc in measure([d])}
    fails = []
    hy = [e["text"] for e in scenes["98-hyphen"]["elements"] if (e.get("id") or "").startswith("split") and e.get("text")]
    split = [t for t in hy if any(w.get("next") for w in t.get("words", []))]
    if not split or any(t.get("lines", 0) < 2 for t in split):
        fails.append(f"a word broken at its hyphen didn't count its second line ({len(split)} split, lines "
                     f"{[t.get('lines') for t in split]})")
    if scenes["00-good"]["errors"]:
        fails.append(f"good slide refused: {scenes['00-good']['errors']}")
    for stem, name in names.items():
        want = BAD[name][2]
        errs = scenes[stem]["errors"]
        if not any(want in e and e.startswith("bad") for e in errs):
            fails.append(f"{name}: expected a refusal of element 'bad' containing {want!r}, got {errs}")
    # Text laid on what the slide's layout draws itself (its numbers and rules), known from the Brand Profile.
    from convey.cli import layout_clashes
    brand = {"bindings": {"executive-summary": "Summary"}, "layouts": [{"name": "Summary", "drawn": [
        {"name": "Finding 1 number", "text": "01", "geometry": {"x": 64, "y": 276, "w": 60, "h": 16}},
        {"name": "Finding 1 rule", "geometry": {"x": 64, "y": 256, "w": 368, "h": 1}}]}]}
    word = lambda y: {"text": {"paras": [{"words": [{"x": 64, "y": y, "w": 200, "h": 22}]}]}}
    on = {"pattern": "executive-summary", "elements": [{"id": "item", **word(270)}]}
    clear = {"pattern": "executive-summary", "elements": [{"id": "item", **word(320)}]}
    plain = {"pattern": "executive-summary", "layout": "Title only", "elements": [{"id": "item", **word(270)}]}
    if not any("Finding 1 number" in e for e in layout_clashes(on, brand)):
        fails.append(f"text on the layout's drawn number passed: {layout_clashes(on, brand)}")
    if layout_clashes(clear, brand) or layout_clashes(plain, brand):
        fails.append("text clear of the layout's marks (or on another layout) was refused")
    # A headline in the template's title area must end inside it (a third line ran out of a title band, Oct 18, 2026),
    # unless the slide paints its own ground over the whole layout; and a full-bleed slide hides the layout's marks.
    brand["layouts"].append({"name": "Title only", "drawn": [], "placeholders": [
        {"type": "title", "geometry": {"x": 64, "y": 80, "w": 1000, "h": 112}}]})
    lines = lambda n: {"text": {"paras": [{"words": [{"x": 64, "y": 80 + 50 * i, "w": 300, "h": 50} for i in range(n)]}]}}
    ground = {"id": "field", "kind": "box", "x": 0, "y": 0, "w": 1280, "h": 720, "fill": {"hex": "000000", "a": 1}}
    three = {"layout": "Title only", "elements": [{"id": "headline", "bind": "headline", **lines(3)}]}
    two = {"layout": "Title only", "elements": [{"id": "headline", "bind": "headline", **lines(2)}]}
    bled = {"layout": "Title only", "elements": [ground, {"id": "headline", "bind": "headline", **lines(4)}]}
    if not any("title area" in e for e in layout_clashes(three, brand)):
        fails.append(f"a three-line headline past the title area passed: {layout_clashes(three, brand)}")
    if layout_clashes(two, brand) or layout_clashes(bled, brand):
        fails.append(f"a headline inside the title area, or on a full-bleed slide, was refused: "
                     f"{layout_clashes(two, brand) + layout_clashes(bled, brand)}")
    if layout_clashes({**on, "elements": [ground] + on["elements"]}, brand):
        fails.append("text on a full-bleed slide was refused for a layout mark its ground hides")
    # Terse (the token diet, Oct 18, 2026): a passing slide is listed only with -v; a refused one always.
    import io
    from contextlib import redirect_stdout
    from convey import cli
    for verbose in (False, True):
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.main(["lint", str(d / "00-good.html"), str(d / "01-bad.html"), "--no-design"] + (["-v"] if verbose else []))
        listed = "00-good.html" in buf.getvalue()
        if listed != verbose or "REFUSED  01-bad.html" not in buf.getvalue():
            fails.append(f"lint {'-v ' if verbose else ''}output: {buf.getvalue()[:200]!r}")
    # Characters the slide's font lacks: the browser borrows a font, PowerPoint picks another (Oct 18, 2026 stress test).
    glyphs = d.parent / (d.name + "-glyphs")
    glyphs.mkdir()
    (glyphs / "01-jp.html").write_text(HEAD.replace("{extra}", "").replace("{body}", '<div class="abs" data-id="box" '
        'style="left:0;top:0;width:600px;height:80px"><p class="abs" data-id="jp" style="left:0;top:0;width:600px">'
        'Plain words and 日本語 too</p></div>'))
    (glyphs / "02-latin.html").write_text(HEAD.replace("{extra}", "").replace("{body}", GOOD))
    buf = io.StringIO()
    with redirect_stdout(buf):
        cli.main(["lint", str(glyphs), "--no-design"])
    said = buf.getvalue()
    if "jp: has characters Helvetica doesn't have" not in said or "box:" in said or "02-latin" in said:
        fails.append(f"missing characters: {said[:300]!r}")
    shutil.rmtree(glyphs)
    # A deck's stale copy of chart.js is replaced when its folder is linted (compose writes it only once).
    from convey.skald.measure import slide_files
    (d / "chart.js").write_text("// an old copy\n")
    slide_files([d])
    if (d / "chart.js").read_bytes() != CHART_JS.read_bytes():
        fails.append("a stale chart.js beside the slides was not refreshed")
    for f in fails:
        print("FAIL", f)
    print(f"lint test: {len(BAD)} refusals + 1 good slide, {len(fails)} failures")
    return 1 if fails else 0


def test_lint():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
