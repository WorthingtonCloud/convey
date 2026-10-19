"""Brand Profile: settling flags, keeping the person's values across a re-ingest, and a full-page look.

Uses PowerPoint's own Berlin theme when it is installed (skips otherwise; the skill ships no template):
  settle      confirm a flag, set a color, set a layout by name (any case), say there is no logo
  refuse      a bad color, an unknown layout, an unknown flag, a value on a confirm-only flag
  re-ingest   every settled value survives reading the template again
  look        `convey look --full` pictures the whole brand sheet, not one slide's worth
  anywhere    `ingest --out DIR` writes outside the home folder, and every command takes the folder
  background  a theme background style that is a gradient (Berlin) is flagged, and settling it sets the ground
  compose     a title placeholder takes the master's line spacing (Berlin: 90%, so two lines fit its 113 px box)
  calibrate   the calibration's leftover error is explained in the report's terms (good fit vs poor fit)
  anytime     any brand color, the headline size, the plate color and the margins settle with no flag open; a new
              ground re-derives the rule; the sheet splits the agent's to-dos; a narrow content area is flagged
  footer      a footer turned on its side in a side band bounds nothing below (Madison's put the footer at y 384)

Run: python3 skill/tests/test_brand.py   (needs Chrome or Edge for the look; standard library)
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
CONVEY = [sys.executable, str(SKILL / "bin" / "convey")]
BERLIN = Path("/Applications/Microsoft PowerPoint.app/Contents/Resources/Office Themes/Berlin.thmx")
fails = 0


def run(*args) -> subprocess.CompletedProcess:
    return subprocess.run(CONVEY + [str(a) for a in args], capture_output=True, text=True)


def ok(cond: bool, what: str):
    global fails
    print(("ok    " if cond else "FAIL  ") + what)
    fails += 0 if cond else 1


def main() -> int:
    sys.path.insert(0, str(SKILL))
    from convey.cli import calibration_verdict
    ok("good fit" in calibration_verdict({"typical_residual": 0.4, "max_residual": 3.978}),
       "calibrate: a 4 px worst line with a 0.4 px typical one reads as a good fit")
    ok("poor fit" in calibration_verdict({"typical_residual": 1.6, "max_residual": 5.0}),
       "calibrate: a 1.6 px typical miss reads as a poor fit, with what to do")
    if not BERLIN.exists():
        print("brand test: skipped (no PowerPoint Berlin theme on this machine)")
        return 0
    tmp = Path(tempfile.mkdtemp(prefix="convey-brand-test-"))
    d = tmp / "brands" / "berlin"
    r = run("brand", "ingest", BERLIN, "--name", "berlin", "--out", d)
    ok(r.returncode == 0 and (d / "brand.json").exists(), "ingest --out writes the profile where it was told")

    flags0 = {f["id"]: f for f in json.loads((d / "brand.json").read_text())["flags"]}
    ok("background" in flags0 and "gradient" in flags0["background"]["text"],
       "Berlin's gradient background (a theme background style) is flagged, not passed off as flat black")
    r = run("brand", "settle", d, "raised=#383838", "binding-key-finding=title only", "pictures=none", "signal")
    ok(r.returncode == 0, "settle: a color, a layout (any case), no logo, a plain confirm")
    b = json.loads((d / "brand.json").read_text())
    flags = {f["id"]: f for f in b["flags"]}
    ok(b["colors"]["raised"] == "#383838" and b["colors_from"]["raised"] == "set by the person", "the color is set")
    ok(b["bindings"]["key-finding"]["layout"] == "Title Only", "the layout is set by its real name")
    ok(b.get("logo", "missing") is None, "no logo is recorded as none")
    ok(all(flags[i]["settled"] for i in ("raised", "binding-key-finding", "pictures", "signal")), "all four settled")
    ok("--brand-raised: #383838" in (d / "tokens.css").read_text(), "tokens.css carries the new color")
    ok("[x] **raised**" in (d / "flags.md").read_text(), "flags.md ticks a settled flag")

    from convey.compose import _style_css
    b = json.loads((d / "brand.json").read_text())
    ph = next(p for l in b["layouts"] if l["name"] == "Title Only" for p in l["placeholders"] if p["type"] == "title")
    css = _style_css(ph, b)
    ok("line-height:52px" in css and 2 * 52 <= ph["geometry"]["h"],
       f"compose: Berlin's title takes the master's 90% spacing, two lines fit ({css.split('line-height:')[1][:5]})")
    r = run("brand", "settle", d, "background=#9d360e")
    b = json.loads((d / "brand.json").read_text())
    ok(r.returncode == 0 and b["colors"]["ground"] == "#9D360E", "settling the background sets the ground slides assume")
    from convey.brand import mix
    tok = (d / "tokens.css").read_text()
    ok(b["colors"]["rule"] == mix(b["colors"]["ink"], "#9D360E", 0.22) and f"--brand-rule: {b['colors']['rule']}" in tok,
       f"a new ground re-derives the rule too, not only muted ({b['colors']['rule']})")
    r = run("brand", "settle", d, "muted=#B3B3B3", "headline-size=36", "plate=#151515")
    b = json.loads((d / "brand.json").read_text())
    tok = (d / "tokens.css").read_text()
    ok(r.returncode == 0 and b["colors"]["muted"] == "#B3B3B3" and "--brand-headline-size: 36px" in tok
       and b["colors"]["plate"] == "#151515" and "--brand-plate: #151515" in tok,
       "settle takes any brand color with no flag open, a headline size, and a plate color")
    r = run("brand", "settle", d, "headline-size=99")
    ok(r.returncode == 2 and "24 to 60" in r.stderr, "and refuses a headline size out of range")
    sheet = (d / "brand-sheet.html").read_text()
    ok("For the agent, not the person" in sheet and "calibrate-Trebuchet MS" in sheet.split("For the agent")[1],
       "the brand sheet lists the agent's calibrate to-do apart from the person's calls")
    r = run("brand", "settle", d, "margin-left=300", "margin-right=120")
    b = json.loads((d / "brand.json").read_text())
    ok(r.returncode == 0 and "--brand-content-width: 860px" in (d / "tokens.css").read_text()
       and not any(f["id"] == "narrow" for f in b["flags"]), "settle sets the margins; set by the person, no narrow flag")
    from convey.brand import write
    b["margins"].pop("set")
    write(b, d)
    ok(any(f["id"] == "narrow" and "860 px" in f["text"] for f in json.loads((d / "brand.json").read_text())["flags"]),
       "a template's narrow content area (under 70% of the slide) is flagged")
    for bad, why in (("raised=red", "a bad color"), ("binding-chart=Nope", "an unknown layout"),
                     ("nosuch", "an unknown flag"), ("signal=#000000x", "a bad emphasis color")):
        r = run("brand", "settle", d, bad)
        ok(r.returncode == 2 and "error:" in r.stderr, f"refuses {why}")
    r = run("brand", "settle", d, "binding-timeline=title only")
    b = json.loads((d / "brand.json").read_text())
    ok(r.returncode == 0 and b["bindings"]["timeline"]["layout"] == "Title Only",
       "settle points a pattern bound by name (timeline) at a layout, flag or no flag")
    r = run("brand", "settle", d, "binding-matrix=title only")
    ok(r.returncode == 2 and "no design for a company layout" in r.stderr, "and refuses one with no layout design (matrix)")
    r = run("brand", "settle", d, "calibrate-Trebuchet MS=yes")
    ok(r.returncode == 2 and "takes no value" in r.stderr, "refuses a value on a confirm-only flag")

    r = run("brand", "ingest", BERLIN, "--name", "berlin", "--out", d)
    b = json.loads((d / "brand.json").read_text())
    ok(r.returncode == 0 and b["colors"]["raised"] == "#383838", "re-ingest keeps the person's color")
    ok(b["bindings"]["key-finding"]["layout"] == "Title Only", "re-ingest keeps the person's layout")
    ok(b.get("logo", "missing") is None, "re-ingest keeps no-logo")

    r = run("look", "--full", d / "brand-sheet.html", "-o", tmp / "look")
    png = tmp / "look" / "brand-sheet.png"
    h = int.from_bytes(png.read_bytes()[20:24], "big") if png.exists() else 0
    ok(r.returncode == 0 and h > 1000, f"look --full pictures the whole brand sheet ({h} px tall)")

    from convey.brand import _footer_top
    m = {"drawn": []}
    side = {"type": "ftr", "geometry": {"x": -235, "y": 384, "w": 618, "h": 19, "rot": 270}}
    flat = {"type": "ftr", "geometry": {"x": 400, "y": 660, "w": 480, "h": 20}}
    ok(_footer_top(m, [side], 720) == 680 and _footer_top(m, [side, flat], 720) == 660,
       "a sideways footer sets no footer line; a flat one does")

    print(f"brand test: {fails} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
