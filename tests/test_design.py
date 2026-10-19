"""Design lint refuses each planted design problem by element, and passes a slide that keeps the rules.
Neutral, made-up fixtures only.

  contrast  measured on what is drawn: a layout picture that is orange while the ground token says near-black,
            and white type on a light fill the slide painted; large type passes at 3:1
  small     a sentence under 18 px, a source under 16 px (a 16 px source and a read-ahead deck's 16 px pass)
  crowded   80 words on a live slide (the same slide passes in a read-ahead deck)
  color     signal and muted type straight on the template's background (on a panel, or in the template's own
            placeholder, they pass)
  rhythm    the same variant, and the same default, three slides in a row
  stacked   values inside a stacked bar read on their segment (the brand's on-color, else white or black)
  brand     the colors the Brand Profile derives (type on each fill, small signal text, muted) all read at 4.5:1,
            and the background measure turns the content plate on for an orange ground, off for a dark one

Run: python3 skill/tests/test_design.py   (needs Chrome or Edge installed, nothing else)
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from convey.design import deck_mode, design_page, rhythm_problems, slide_problems  # noqa: E402
from convey.skald.measure import measure_page, slide_page  # noqa: E402

HEAD = """<!doctype html><html><head><meta charset="utf-8"><style>
:root { --brand-ground: #101010; --brand-ink: #FFFFFF; --brand-body: #E6E6E6; --brand-muted: #8A8A8A;
  --brand-raised: #2A2A2A; --brand-signal: #FF5A1F; --brand-data-1: #A1D68B; }
* { box-sizing: border-box; margin: 0; padding: 0; }
.slide { position: relative; width: 1280px; height: 720px; overflow: hidden; background: var(--brand-ground);
  color: var(--brand-body); font-family: Helvetica; font-size: 20px; line-height: 28px; font-kerning: none;
  isolation: isolate; }
.abs { position: absolute; }
.panel { position: absolute; padding: 16px; }
</style></head><body><section class="slide"{attrs}>{underlay}{body}</section></body></html>"""

# The template's layout picture: orange, though the brand's ground token says near-black (a master's fade, the way
# a real template's background can differ from its ground color).
ORANGE = ('<img data-underlay alt="" style="position:absolute;left:0;top:0;width:1280px;height:720px;z-index:-1" '
          'src="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%221280%22 height=%22720%22%3E'
          '%3Crect width=%221280%22 height=%22720%22 fill=%22%23E0601A%22/%3E%3C/svg%3E">')
DARK = ORANGE.replace("E0601A", "101010")

HEADLINE = ('<h1 class="abs" data-id="headline" data-bind="headline" style="left:64px;top:48px;width:1100px;'
            'font-size:40px;line-height:48px;color:var(--brand-ink)">{}</h1>')
WORDS = ("Every option goes on one calendar with doing nothing included and each month of delay gets a price "
         "before anyone compares the totals ")


def p(id_, text, top, size=20, line=28, color="var(--brand-body)", extra="", left=64, width=900):
    return (f'<p class="abs" data-id="{id_}"{extra} style="left:{left}px;top:{top}px;width:{width}px;'
            f'font-size:{size}px;line-height:{line}px;color:{color}">{text}</p>')


GOOD = (HEADLINE.format("A slide that keeps every design rule")
        + p("lede", "One sentence in the body color, at a size the back row can read.", 160)
        + '<div class="panel" data-id="panel" style="left:64px;top:240px;width:500px;height:120px;background:var(--brand-raised)">'
        + '<p data-id="tag" style="font-size:24px;line-height:32px;color:var(--brand-signal)">Signal on a panel</p></div>'
        + p("meta", "The template's own small gray line", 400, 13, 16, "var(--brand-muted)", ' data-ph="53"')
        + p("source", "Source: an annual survey of made-up things, 2025.", 640, 16, 20, extra=' data-bind="content.source"'))

# name -> (slide attrs, underlay, body, element id that must be refused, words the refusal must contain)
BAD = {
    "contrast on the layout picture": ("", ORANGE, HEADLINE.format("Headline") .replace("var(--brand-ink)", "#101010")
                                       + p("bad", "Body-colored text over the template's orange background.", 300),
                                       "bad", "template's background"),
    "contrast on a painted fill": ("", DARK, '<div class="panel" style="left:64px;top:200px;width:600px;height:120px;'
                                   'background:var(--brand-data-1)"><p data-id="bad" style="color:#FFFFFF">'
                                   'White words on a light green panel.</p></div>', "bad", "a fill the slide painted"),
    "contrast, not large enough": ("", DARK, '<div class="panel" style="left:64px;top:200px;width:800px;height:200px;'
                                   'background:#E0601A"><p data-id="big" style="font-size:30px;line-height:36px;'
                                   'font-weight:700;color:#FFFFFF">Large bold white passes at 3:1</p><p data-id="bad" '
                                   'style="color:#FFFFFF">The same white at 20 px does not</p></div>', "bad", "needs 4.5:1"),
    "small sentence": ("", DARK, p("bad", "A sentence the audience must read, set at seventeen pixels.", 200, 17, 24),
                       "bad", "needs 18 px"),
    "small source": ("", DARK, p("bad", "Source: an annual survey of made-up things, 2025.", 640, 15, 20,
                                 extra=' data-bind="content.source"'), "bad", "needs 16 px"),
    "crowded": ("", DARK, p("lede", WORDS * 4, 120, 18, 24, width=1150), "slide", "words"),
    "signal on the template": ("", DARK, p("bad", "An orange emphasis line straight on the background.", 300,
                                           24, 32, "var(--brand-signal)"), "bad", "brand's signal"),
    "muted on the template": ("", DARK, p("bad", "A quiet gray line straight on the background, no panel.", 300,
                                          20, 28, "var(--brand-muted)"), "bad", "brand's muted"),
}


def write(d: Path, name: str, attrs: str, underlay: str, body: str):
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.html").write_text(HEAD.replace("{attrs}", attrs).replace("{underlay}", underlay).replace("{body}", body))


def lint(slides: Path) -> dict:
    """{slide stem: [problems]} the way `convey lint` gathers them."""
    files = sorted(slides.glob("*.html"))
    with slide_page() as page:
        infos = []
        for f in files:
            measure_page(page, f)
            infos.append(design_page(page))
    modes, rhythm = deck_mode(files), rhythm_problems(infos)
    return {f.stem: slide_problems(inf, modes.get(inf.get("slideId") or "", modes["default"]))
            + ([rhythm[i]] if i in rhythm else []) for i, (f, inf) in enumerate(zip(files, infos))}


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="convey-design-"))
    live, ahead = root / "live", root / "read-ahead"
    (live / "brief.json").parent.mkdir(parents=True)
    (live / "brief.json").write_text(json.dumps({"mode": "live"}))
    ahead.mkdir()
    (ahead / "brief.json").write_text(json.dumps({"mode": "read-ahead"}))
    write(live / "slides", "00-good", "", DARK, GOOD)
    write(live / "slides", "01-good-no-picture", "", "", GOOD)
    for i, (name, (attrs, under, body, _, _)) in enumerate(BAD.items(), 2):
        write(live / "slides", f"{i:02d}-bad", attrs, under, body)
    # Rhythm: three of one variant in a row, then three of one pattern's default; a pair is fine.
    n = len(BAD) + 2
    for k, attrs in enumerate([' data-pattern="quote" data-variant="panel"'] * 3 + [' data-pattern="chart"'] * 3
                              + [' data-pattern="steps" data-variant="row"'] * 2):
        write(live / "slides", f"{n + k:02d}-rhythm", attrs, DARK, HEADLINE.format(f"Rhythm slide {k + 1}"))
    # The read-ahead deck: the crowded slide and a 16 px sentence pass there.
    write(ahead / "slides", "00-crowded", "", DARK, BAD["crowded"][2])
    write(ahead / "slides", "01-sixteen", "", DARK, p("lede", "A sentence set at sixteen pixels for reading close up.", 200, 16, 24))

    got, fails = lint(live / "slides"), []
    for stem in ("00-good", "01-good-no-picture"):
        if got[stem]:
            fails.append(f"good slide {stem} refused: {got[stem]}")
    for i, (name, (_, _, _, el, want)) in enumerate(BAD.items(), 2):
        errs = got[f"{i:02d}-bad"]
        if not any(e.startswith(f"{el}:") and want in e for e in errs):
            fails.append(f"{name}: expected {el!r} refused with {want!r}, got {errs}")
        if name == "contrast, not large enough" and any(e.startswith("big:") for e in errs):
            fails.append(f"large bold text at 3.6:1 was refused: {errs}")
    rh = {k: [e for e in v if "in a row" in e] for k, v in got.items() if k.endswith("rhythm")}
    want = {f"{n + 2:02d}-rhythm", f"{n + 5:02d}-rhythm"}
    if {k for k, v in rh.items() if v} != want:
        fails.append(f"rhythm: expected {sorted(want)} refused, got {sorted(k for k, v in rh.items() if v)}")
    ra = lint(ahead / "slides")
    if any(ra.values()):
        fails.append(f"read-ahead deck refused what it may carry: {ra}")
    fails += brand_colors(root)
    fails += stacked_labels(root)
    for f in fails:
        print("FAIL", f)
    print(f"design test: {len(BAD)} planted problems + rhythm + 2 good slides + a read-ahead deck, {len(fails)} failures")
    return 1 if fails else 0


def stacked_labels(root: Path) -> list[str]:
    """Values inside a stacked bar take the brand's on-color for their segment's fill, else white or black by
    contrast: they were always white, 3.1:1 on a mid teal (Oct 19, 2026)."""
    import shutil
    d = root / "stacked" / "slides"
    d.mkdir(parents=True)
    shutil.copy(Path(__file__).resolve().parent.parent / "convey" / "skald" / "chart.js", d / "chart.js")
    head = HEAD.replace("--brand-data-1: #A1D68B; }", "--brand-data-1: #1CA0A0; --brand-on-data-1: #101010; "
                        "--brand-data-7: #1CA0A0; }")
    spec = ('{"type": "bar", "stacked": true, "categories": ["One", "Two"], "series": [{"name": "A", "values": '
            '[17, 12], "color": "var(--brand-data-%s)"}], "axis": {"min": 0, "max": 18, "step": 6, "format": "{v}"}, '
            '"fontSize": 16, "labels": true}')
    for n, tone in (("00-own-on-color", "1"), ("01-no-on-color", "7")):
        fig = ('<figure data-id="chart" data-chart=\'' + spec % tone + '\' style="position:absolute;left:64px;top:160px;'
               'width:800px;height:400px;margin:0;font-family:Helvetica;color:var(--brand-body)"></figure>'
               '<script src="chart.js"></script>')
        (d / f"{n}.html").write_text(head.replace("{attrs}", "").replace("{underlay}", DARK).replace("{body}", fig))
    got = lint(d)
    return [f"stacked labels, {k}: {v}" for k, v in got.items() if any("chart-label" in e for e in v)] + \
        ([] if len(got) == 2 else [f"stacked labels: {len(got)} slides linted, not 2"])


def brand_colors(root: Path) -> list[str]:
    """What the Brand Profile derives so variants read on any template: a type color per fill, a signal for small
    text, a derived muted that reads on ground and raised, and the measure that turns the content plate on."""
    from convey.brand import contrast, legible_muted, on_fill, signal_text
    from convey.design import ground_contrast, ground_sample
    fails = []
    light = {"ground": "#FFFFFF", "ink": "#101012", "raised": "#F3F3F4", "signal": "#E5432F", "data-1": "#1CA0A0",
             "data-2": "#2B2B6E"}
    dark = {"ground": "#000000", "ink": "#FFFFFF", "raised": "#383838", "signal": "#F09415"}
    for c in (light, dark):
        for k, v in on_fill(c).items():
            if contrast(v, c[k]) < 4.5:
                fails.append(f"on-{k} {v} on {c[k]} reads {contrast(v, c[k]):.1f}:1")
        st = signal_text(c)
        if any(contrast(st, c[k]) < 4.5 for k in ("ground", "raised")):
            fails.append(f"signal-text {st} doesn't read on ground and raised")
        m = legible_muted(c)
        if any(contrast(m, c[k]) < 4.5 for k in ("ground", "raised")):
            fails.append(f"derived muted {m} doesn't read on ground and raised")
    from convey.brand import field_color, plate_tone
    # A fade-backed template (Berlin-like): neither ground nor white reads on the signal, its charcoal does;
    # the plate steps off the raised color so panels show on it (26); full-bleed fields paint the raised color (27).
    fade = {"ground": "#B84923", "ink": "#FFFFFF", "body": "#FFFFFF", "raised": "#262626", "signal": "#F09415"}
    if on_fill(fade)["signal"] != "#262626":
        fails.append(f"on-signal on a fade template: {on_fill(fade)['signal']}, wanted the raised #262626")
    pt = plate_tone(fade)
    if contrast(pt, fade["raised"]) < 1.2 or contrast(fade["body"], pt) < 4.5:
        fails.append(f"plate tone {pt}: {contrast(pt, fade['raised']):.2f}:1 off raised, body {contrast(fade['body'], pt):.1f}:1")
    grad = {"colors": fade, "master": {"background": {"fill": "gradFill"}}}
    flat = {"colors": dict(fade, ground="#101010"), "master": {"background": {"fill": "solidFill"}}}
    if field_color(grad) != "#262626" or field_color(flat) != "#101010":
        fails.append(f"field color: fade {field_color(grad)} (want raised), flat {field_color(flat)} (want ground)")
    if on_fill(light)["data-2"] != "#FFFFFF":
        fails.append("a dark fill on a light brand should keep the ground color (white) for its type")
    zone = {"x0": 64, "x1": 1216, "y0": 220, "y1": 600}
    for fill, want in (("E0601A", True), ("101010", False)):
        svg = root / f"ground-{fill}.svg"
        svg.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720"><rect width="1280" height="720" fill="#{fill}"/></svg>')
        r = ground_contrast(svg, "#FFFFFF", zone)
        if r is None or (r < 4.5) != want:
            fails.append(f"ground #{fill}: measured {r}, plate should be {'on' if want else 'off'}")
        got = ground_sample(svg, "#FFFFFF", zone)
        if not got or got["median"] != f"#{fill}":
            fails.append(f"ground #{fill}: the measured color to suggest is {got and got['median']}")
    return fails


def test_design():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
