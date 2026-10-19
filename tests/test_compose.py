"""convey compose fits a pattern's skeleton to the storyboard's content. Standard library only.

  wires   the diagram's arrows follow its steps: 7 steps get 6 arrows (chained s1→s2 … s6→s7), 2 steps get 1;
          before Oct 16, 2026 compose kept the skeleton's 3 arrows whatever the count
  slots   a layout with 3 numbered finding slots takes exactly 3 items; 6 (or 2) items go on the title-only layout,
          on the skeleton's grid, wrapped into rows of 3: before Oct 18, 2026 items 4-6 landed on the layout's
          own "01 02 03" and rules (a real 21-slide deck)
  variants a slide's variant picks patterns/<p>/<v>.html and its data-role (title-only, full-bleed) puts it on the
          template's title-only layout with no placeholder filling; data-class, data-when, data-index, data-icon-bind, emphasis, a chart
          variant's look over the storyboard's data, a photo variant with no photo refused (Oct 18, 2026)
  caveat  a caveat with no slot of its own takes a row the variant's body ends above (Oct 18, 2026)
  restyle the same deck on another brand shares the plan files by link, and carries the slides' design edits (a CSS
          rule, an inline style, a chart's look, an added callout, a removed element) where the new brand's compose
          drew the same thing; where it drew something else the new brand's value stays and is listed (Oct 18, 2026:
          the stress test redid every hand fix on two more templates)
  guarded a second compose refuses to wipe hand edits (--keep-edits carries them, --overwrite drops them); a note
          when the brand has no layout pictures and PowerPoint is installed; steps/row's tag only where a step has one
  named   a big number, options, a timeline and a chart with its takeaway go on the template's layouts made for them
          (bound by name, also for a brand ingested before that), each text in its numbered placeholder; a count
          that misses the slots, or a caveat with no slot, goes on the title-only layout instead (Oct 18, 2026)

Run: python3 skill/tests/test_compose.py
"""
from __future__ import annotations

import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL))
import json  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402

from convey.compose import Tree, compose, fit_items, fit_wires, item_slots, plain_layout, wrap_items  # noqa: E402

fails = 0


def ok(cond: bool, what: str):
    global fails
    print(("ok    " if cond else "FAIL  ") + what)
    fails += 0 if cond else 1


def wires_for(n: int) -> list[tuple[str, str]]:
    root = Tree((SKILL / "patterns" / "diagram" / "skeleton.html").read_text()).root
    slide = {"content": {"steps": [{"label": f"Part {i}", "note": "a line"} for i in range(1, n + 1)]}}
    fit_items(root, slide)
    fit_wires(root)
    return [(w.get("data-from"), w.get("data-to")) for w in root.walk() if w.get("data-from")]


def main() -> int:
    for n in (7, 4, 2):
        w = wires_for(n)
        want = [(f"s{i}", f"s{i + 1}") for i in range(1, n)]
        ok(w == want, f"{n} steps get {n - 1} chained arrows ({len(w)}: {w[:2]}{' …' if len(w) > 2 else ''})")
    root = Tree((SKILL / "patterns" / "diagram" / "skeleton.html").read_text()).root
    fit_items(root, {"content": {"steps": [{"label": str(i), "note": ""} for i in range(7)]}})
    fit_wires(root)
    ids = [w.get("data-id") for w in root.walk() if w.get("data-from")]
    ok(len(set(ids)) == len(ids), f"every added arrow has its own data-id ({ids})")
    summary = {"name": "Executive summary", "placeholders": [{"type": "title", "name": "Title 1"}] + [
        {"type": "body", "name": f"Finding {i}{d}"} for i in (1, 2, 3) for d in ("", " detail")]}
    layouts = {"Executive summary": summary, "Title only": {"name": "Title only", "placeholders": [{"type": "title", "name": "Title 1"}]},
               "Blank": {"name": "Blank", "placeholders": []}}
    ok(item_slots(summary) == 3, f"a layout with Finding 1..3 has 3 item slots ({item_slots(summary)})")
    ok(item_slots(layouts["Title only"]) == 0, "a title-only layout has no item slots")
    ok(plain_layout(layouts)["name"] == "Title only", "the plain fallback is the title-only layout")
    root = Tree((SKILL / "patterns" / "executive-summary" / "skeleton.html").read_text()).root
    slide = {"content": {"items": [{"head": f"Point {i}", "text": "a line"} for i in range(6)]}}
    fit_items(root, slide)
    wrap_items(root, slide)
    cols = [n for n in root.walk() if (n.get("style") or "").find("flex:0 0") >= 0]
    ok(len(cols) == 6 and "/ 3)" in cols[0].get("style"), f"6 items wrap into rows of 3 ({len(cols)} items marked)")
    ok("flex-wrap:wrap" in (cols[0].parent.get("style") or ""), "their row is set to wrap")
    variants()
    named()
    restyled()
    guarded()
    print(f"compose test: {fails} failure(s)")
    return 1 if fails else 0


def variants():
    d = Path(tempfile.mkdtemp())
    brand = d / "brand"
    (brand / "assets").mkdir(parents=True)
    (brand / "tokens.css").write_text(":root { --brand-ground: #111111; }\n")
    (brand / "brand.json").write_text(json.dumps({"fonts": {}, "bindings": {"scorecard": "Findings"}, "layouts": [
        {"name": "Title Only", "placeholders": [{"type": "title", "idx": 0, "name": "Title 1"}]},
        {"name": "Blank", "type": "blank", "placeholders": []},
        {"name": "Findings", "placeholders": [{"type": "title", "idx": 0, "name": "Title 1"}, {"type": "body", "idx": 1, "name": "Finding 1",
                                               "geometry": {"x": 0, "y": 0, "w": 100, "h": 40}}]}]}))
    (d / "brief.json").write_text(json.dumps({"autonomy": "just-build"}))
    (d / "photo.jpg").write_bytes(b"\xff\xd8\xff")
    rows = [{"head": f"Claim {i}", "verdict": "Pass" if i == 2 else "Fail", "status": "pass" if i == 2 else "fail", "text": "x"} for i in range(12)]
    slides = [
        {"id": "S-1", "pattern": "scorecard", "variant": "ledger", "headline": "Most failed, never once", "emphasis": ["never"],
         "claim_ids": [], "content": {"items": rows}},
        {"id": "S-2", "pattern": "photo-led", "variant": "wash-left", "headline": "A photo", "claim_ids": [],
         "content": {"image": "photo.jpg", "focus": "30% 40%"}},
        {"id": "S-3", "pattern": "steps", "variant": "two-rows", "headline": "Steps", "claim_ids": [],
         "content": {"steps": [{"label": f"S{i}", "note": "n"} for i in range(3)]}},
        {"id": "S-4", "pattern": "options", "variant": "cards-on-baseline", "headline": "Options", "claim_ids": [],
         "content": {"items": [{"head": "A", "icon": "cart"}, {"head": "B"}]}},
        {"id": "S-5", "pattern": "chart", "variant": "keyed-labeled", "headline": "Chart", "claim_ids": [],
         "content": {"chart": {"type": "column", "categories": ["x"], "series": [{"name": "a", "values": [1]}, {"name": "b", "values": [2]}],
                               "axis": {"min": 0, "max": 2, "step": 1, "format": "{v}"}}}},
        # The story's chart type wins over the variant's, and a slot the design has no place for is named (Oct 18, 2026)
        {"id": "S-6", "pattern": "chart", "variant": "keyed-labeled", "headline": "Bars", "claim_ids": [],
         "content": {"chart": {"type": "bar", "categories": ["x"], "series": [{"name": "a", "values": [1]}],
                               "axis": {"min": 0, "max": 2, "step": 1, "format": "{v}"}}, "turn": "nowhere to go"}}]
    (d / "storyboard.json").write_text(json.dumps({"slides": slides}))
    import io
    from contextlib import redirect_stderr
    err = io.StringIO()
    with redirect_stderr(err):
        out = {f.name.split("-")[2]: f.read_text() for f in compose(d, brand)}
    bars = json.loads(re.search(r"data-chart='([^']+)'", out["6"]).group(1))
    ok(bars["type"] == "bar", f"the storyboard's chart type wins over the variant's ({bars['type']})")
    ok("S-6" in err.getvalue() and "content.turn has no place" in err.getvalue() and "S-5" not in err.getvalue(),
       f"compose names a slot the design drops, and only that ({err.getvalue().strip()[:80]}…)")
    sc = out["1"]
    ok('data-layout="Title Only"' in sc and "data-ph" not in sc,
       "a title-only variant lands on the title-only layout, though the pattern is bound to another, and fills no placeholder")
    ok(sc.count('class="row is-fail"') == 11 and sc.count('class="row is-pass"') == 1, "data-class marks each row by its status")
    ok(sc.count('data-icon="check-circle"') == 1 and sc.count('data-icon="cross-circle"') == 11 and "dash-circle" not in sc,
       "data-when keeps one icon per row, the one its status names")
    ok('content.items.11.head' in sc and 'content.items.11.status=fail' in sc and 'content.items.1.status=fail' in sc,
       "items past ten renumber every path (items.1 doesn't catch items.10)")
    ok('<span class="hit">never</span>' in sc, "the emphasis word is wrapped in the headline")
    ph = out["2"]
    ok('data-layout="Title Only"' in ph and 'src="photo.jpg"' in ph and "object-position:30% 40%" in ph and (d / "slides" / "photo.jpg").exists(),
       "a full-bleed variant lands on the title-only layout too (its headline stays the slide's title); its photo "
       "is copied in and cropped at the slide's focus")
    st = out["3"]
    ok(st.count("data-not-claim") == 3 and ">3</p>" in st and 'data-id="row-2"' not in st,
       "steps are numbered by compose (never claims), and the second row goes when there are three steps")
    op = out["4"]
    ok('data-icon="cart"' in op and "data-icon-bind" not in op and 'data-id="baseline"' not in op,
       "an option's icon comes from the skill's set by name; a missing icon and an empty baseline are dropped")
    ch = out["5"]
    spec = json.loads(re.search(r"data-chart='([^']+)'", ch).group(1))
    ok(spec.get("labels") is True and spec["categories"] == ["x"] and spec["series"][1]["values"] == [2],
       "a chart variant keeps its look (value labels) over the storyboard's data")
    ok(ch.count("data-legend-for") == 1 and "font-size:16px" in ch, "compose writes one key, at the variant's type size")
    slides[1]["content"].pop("image")
    (d / "storyboard.json").write_text(json.dumps({"slides": slides}))
    try:
        compose(d, brand)
        ok(False, "a photo variant with no photo is refused")
    except SystemExit as e:
        ok("draws a photo" in str(e), f"a photo variant with no photo is refused ({str(e)[:60]}…)")
    shutil.rmtree(d)
    # Dead skeleton CSS goes (the token diet, Oct 18, 2026): a rule only for classes no element carries.
    from convey.compose import drop_dead_css
    doc = ('<html><head><style>\n* { margin: 0; }\n.used { color: red; }\n.gone, .also-gone p { top: 0; }\n'
           '.used .gone { left: 0; }\n@media print { .gone { top: 1px; } }\nh1 { top: 2px; }\n</style></head>'
           '<body><p class="used x">a</p></body></html>')
    lean = drop_dead_css(doc)
    ok(".used { color" in lean and "* { margin" in lean and "h1 {" in lean and "@media print" in lean
       and ".gone, .also-gone" not in lean and ".used .gone" not in lean,
       "compose drops style rules no element can match, and keeps the rest")


def named():
    from convey.brand import _bind
    g = {"x": 0, "y": 0, "w": 100, "h": 40}

    def lay(name, typ, *slots):
        return {"name": name, "type": typ, "placeholders": [{"type": "title", "idx": 0, "name": "Title 1"}] + [
            {"type": "body", "idx": 10 + i, "name": n, "geometry": g, "style": {"upper": True} if "date" in n else {}}
            for i, n in enumerate(slots)]}
    layouts = [lay("Title Only", "titleOnly"),
               lay("Big number", "obj", "Number", "Number label", "Number context", "Comparison"),
               lay("Options", "obj", *[f"Option {i}{d}" for i in (1, 2, 3) for d in ("", " detail")]),
               lay("Timeline", "obj", *[f"Milestone {i}{d}" for i in range(1, 6) for d in (" date", "", " note")]),
               lay("Chart", "obj"), lay("Chart and explanation", "obj", "Explanation")]
    layouts[4]["placeholders"].append({"type": "chart", "idx": 30, "name": "Chart", "geometry": g})
    layouts[5]["placeholders"].append({"type": "chart", "idx": 30, "name": "Chart", "geometry": g})
    flags = []
    b = _bind(layouts, flags)
    ok(b["giant-number"]["layout"] == "Big number" and b["options"]["layout"] == "Options" and b["timeline"]["layout"] == "Timeline"
       and b["chart-explained"]["layout"] == "Chart and explanation", "ingest binds the four by the layouts' names")
    ok(b["comparison"]["layout"] != "Options" and b["kpi-row"]["layout"] != "Big number" and b["chart"]["layout"] == "Chart",
       "a layout made for one of them is never another pattern's near match")
    b2 = _bind([l for l in layouts if l["name"] in ("Title Only", "Chart")], [])
    ok(not any(k in b2 for k in ("giant-number", "options", "timeline", "chart-explained")),
       "without such layouts they are not bound at all (no type match, no fallback)")
    d = Path(tempfile.mkdtemp())
    brand = d / "brand"
    (brand / "assets").mkdir(parents=True)
    (brand / "tokens.css").write_text(":root { --brand-ground: #111111; }\n")
    # Bound before Oct 18, 2026: no binding for the four, so compose finds their layouts by the same rule.
    (brand / "brand.json").write_text(json.dumps({"fonts": {}, "bindings": {"chart": {"layout": "Chart", "how": "x"}},
                                                  "layouts": layouts}))
    (d / "brief.json").write_text(json.dumps({"autonomy": "just-build"}))
    chart = {"type": "column", "categories": ["x"], "series": [{"name": "a", "values": [1]}], "axis": {"min": 0, "max": 2, "step": 1, "format": "{v}"}}
    opt = [{"head": f"O{i}", "text": "t"} for i in range(4)]
    ms = [{"when": f"20{i}0", "label": f"M{i}", "note": "n"} for i in range(5)]
    big = {"value": "79%", "label": "of it", "evidence": "against that", "turn": "but", "source": "src"}
    slides = [
        {"id": "S-1", "pattern": "giant-number", "headline": "Big", "content": big},
        {"id": "S-2", "pattern": "giant-number", "headline": "Big", "content": big, "caveat": "Rounded."},
        {"id": "S-3", "pattern": "options", "headline": "Three", "content": {"items": opt[:3]}},
        {"id": "S-4", "pattern": "options", "headline": "Four", "content": {"items": opt}},
        {"id": "S-5", "pattern": "timeline", "headline": "Five", "content": {"milestones": ms}},
        {"id": "S-6", "pattern": "timeline", "headline": "Four", "content": {"milestones": ms[:4]}},
        {"id": "S-7", "pattern": "chart", "headline": "Said", "content": {"chart": chart, "takeaway": "Look here."}},
        {"id": "S-8", "pattern": "chart", "headline": "Plain", "content": {"chart": chart}}]
    for s in slides:
        s["claim_ids"] = []
    (d / "storyboard.json").write_text(json.dumps({"slides": slides}))
    out = {f.name.split("-")[2]: f.read_text() for f in compose(d, brand)}
    on = lambda k, name: f'data-layout="{name}"' in out[k]
    phs = lambda k: len(re.findall(r'data-ph="\d+"', out[k]))
    ok(on("1", "Big number") and phs("1") == 4, f"a big number fills its layout's four slots ({phs('1')})")
    ok(on("2", "Title Only") and phs("2") == 0 and "Rounded." in out["2"],
       "with a caveat the big-number layout has no slot for, it keeps its own grid on the title-only layout")
    ok(on("3", "Options") and phs("3") == 6 and 'class="opt' not in out["3"], "three options fill the options layout's six slots")
    ok(on("4", "Title Only") and phs("4") == 0 and 'class="opt lead"' in out["4"],
       "four options miss its three slots: title-only layout, the skeleton's columns and accent kept")
    ok(on("5", "Timeline") and phs("5") == 15 and "data-deco" not in out["5"] and "uppercase" in out["5"],
       "five milestones fill the timeline's fifteen slots; the layout draws the ticks; dates keep its capitals")
    ok(on("6", "Title Only") and phs("6") == 0 and out["6"].count("data-deco") == 4,
       "four milestones miss its five: title-only layout, the skeleton's own ticks kept")
    ok(on("7", "Chart and explanation") and phs("7") == 1, "a chart with a takeaway goes on the chart-and-explanation layout")
    ok(on("8", "Chart") and "content.takeaway" not in out["8"], "a chart without one stays on the chart layout")
    shutil.rmtree(d)


def restyled():
    from convey.restyle import merge, restyle
    d = Path(tempfile.mkdtemp())
    for name, ground in (("a", "#111111"), ("b", "#EEEEEE")):
        brand = d / name
        (brand / "assets").mkdir(parents=True)
        (brand / "tokens.css").write_text(f":root {{ --brand-ground: {ground}; }}\n")
        (brand / "brand.json").write_text(json.dumps({"fonts": {}, "bindings": {}, "layouts": [
            {"name": "Title Only", "placeholders": [{"type": "title", "idx": 0, "name": "Title 1"}]}]}))
    src = d / "deck"
    (src / "sources").mkdir(parents=True)
    (src / "brief.json").write_text(json.dumps({"autonomy": "just-build", "brand": "../a"}))
    (src / "evidence.json").write_text("{}")
    chart = {"type": "line", "categories": ["x", "y"], "series": [{"name": "a", "values": [1, 2]}],
             "axis": {"min": 0, "max": 2, "step": 1, "format": "{v}"}}
    rows = [{"head": f"Claim {i}", "status": "fail"} for i in range(3)]
    (src / "storyboard.json").write_text(json.dumps({"slides": [
        {"id": "S-1", "pattern": "scorecard", "variant": "tally", "headline": "Most failed", "claim_ids": [],
         "caveat": "One held.", "content": {"tally": {"value": "2 of 3", "label": "failed"}, "items": rows}},
        {"id": "S-2", "pattern": "chart", "variant": "keyed-labeled", "headline": "A line", "claim_ids": [],
         "content": {"chart": chart}}]}))
    compose(src, d / "a", quiet=True)
    ok(len(list((src / "slides" / ".composed").glob("*.html"))) == 2, "compose keeps what it wrote in slides/.composed/")
    f1, f2 = sorted((src / "slides").glob("*.html"))
    t = f1.read_text()
    # A caveat the variant has no slot for gets a row of its own: --caveat-row lifts the body's --bottom above it
    # (a fixed offset drew it over six variants' panels).
    ok(re.search(r'data-slide="S-1"[^>]*style="--caveat-row:40px"', t) and "top:624px" in t,
       "a caveat with no slot reserves a row (--caveat-row) at the bottom of the body zone")
    t = t.replace(".tv { font-size: 104px;", ".tv { font-size: 96px;")  # a CSS rule edit
    t = t.replace('data-bind="caveat" style="position:absolute;', 'data-bind="caveat" style="position:absolute;color:var(--brand-ink);')
    f1.write_text(t)
    t = f2.read_text()
    t = t.replace('"labels": true', '"labels": false')  # a chart look edit
    t = t.replace("</section>", '<p class="abs" data-id="callout" style="left:780px;top:470px">2025: even.</p></section>')
    f2.write_text(t)
    import io
    from contextlib import redirect_stderr
    with redirect_stderr(io.StringIO()):
        r = restyle(src, str(d / "b"), d / "deck-b", d / "a", d / "b")
    new = d / "deck-b"
    ok((new / "storyboard.json").is_symlink() and (new / "sources").is_symlink() and not (new / "brief.json").is_symlink()
       and json.loads((new / "brief.json").read_text())["brand"] == "../b",
       "restyle links the plan files back to the source deck and writes its own brief, naming the new brand")
    n1, n2 = sorted((new / "slides").glob("*.html"))
    a, b = n1.read_text(), n2.read_text()
    ok("--brand-ground: #EEEEEE" in (new / "slides" / "tokens.css").read_text() and ".tv { font-size: 96px" in a
       and "color:var(--brand-ink)" in a, "a CSS rule edit and an inline style edit carry to the new brand")
    spec = json.loads(re.search(r"data-chart='([^']+)'", b).group(1))
    ok(spec.get("labels") is False and spec["type"] == "line" and 'data-id="callout"' in b and "2025: even." in b,
       "a chart's look edit and a hand-added callout carry; the story's data stays the story's")
    ok(r["carried"] == 4 and not r["left"], f"restyle counts the edits it carried ({r['carried']}, left {r['left']})")
    try:
        restyle(src, str(d / "b"), new, d / "a", d / "b")
        ok(False, "a second restyle into a deck with slides is refused")
    except SystemExit as e:
        ok("--overwrite" in str(e), "a second restyle into a deck with slides is refused without --overwrite")
    # Where the new brand drew something else, its value stays and the edit is listed.
    base = Tree('<section><p data-id="t" style="left:72px;top:40px">x</p><i data-id="gone"></i></section>').root
    mine = Tree('<section><p data-id="t" style="left:60px;top:40px">x</p></section>').root
    theirs = Tree('<section><p data-id="t" style="left:274px;top:40px">x</p><i data-id="gone"></i></section>').root
    n, left = merge(base, mine, theirs, "S-9")
    ok("left:274px" in theirs.html() and 'data-id="gone"' not in theirs.html() and n == 1 and len(left) == 1
       and "left" in left[0], f"a position the new template set itself stays, and is listed; a removed element goes ({left})")
    shutil.rmtree(d)
    # Highlights take the signal color: the data colors belong to the options and charts.
    for f, cls in (("comparison/verdict-panels.html", ".is-pick"), ("kpi-row/tiles.html", ".is-lead")):
        css = (SKILL / "patterns" / f).read_text()
        ok(f"{cls} {{ background: var(--brand-signal); }}" in css and
           re.sub(r"\.is-pass[^}]*}", "", css).count("data-1") == 0, f"{f} highlights in the signal color")
    css = (SKILL / "patterns" / "comparison" / "verdict-panels.html").read_text()
    ok(".is-pass { background: var(--brand-data-1); }" in css and "var(--brand-on-data-1)" in css,
       "verdict-panels paints a side that held up (status pass) in the data color, with its on-color type")
    # A variant's display headline marked data-fit-lines keeps to that many lines: set smaller, never reworded.
    from convey.compose import fit_lines, text_lines
    long = "Everyone said the old system was finished, so a team tested every claim behind it"
    t = Tree('<h1 data-bind="headline" data-fit-lines="3" style="width:660px;font-size:80px;line-height:84px">x</h1>').root
    fit_lines(t, {"headline": long})
    h1 = next(n for n in t.walk() if n.tag == "h1")
    size = float(re.search(r"font-size:([\d.]+)px", h1.get("style")).group(1))
    ok(size < 80 and text_lines(long, size, 660) <= 3 and "line-height:" in h1.get("style"),
       f"a long photo-slide headline is set smaller to keep to three lines ({size:g} px)")
    # On a title layout the plate goes only behind the texts off the layout's band, kept clear of it.
    from convey.compose import band_plate
    sec = Tree('<section><h1 data-bind="headline" style="left:70px;top:290px;width:850px;height:140px">T</h1>'
               '<p data-ph="1" data-bind="content.subtitle" style="left:70px;top:461px;width:850px;height:117px">S</p>'
               '</section>').root
    lay = {"show_master_shapes": False, "drawn": [{"color": "#000000", "geometry": {"x": 0, "y": 272, "w": 940, "h": 174}},
                                                  {"geometry": {"x": 0, "y": 446, "w": 940, "h": 29}}]}
    box = band_plate(sec, lay, {"margins": {"footer_top": 623}})
    ok(box and "top:449px" in box and "height:141px" in box and "left:46px" in box,
       f"a title layout's plate sits behind the subtitle only, under the band ({box})")



def guarded():
    """A second compose refuses to wipe hand edits, or carries them with keep_edits; compose says when the brand has
    no layout pictures though PowerPoint is installed; a step's tag shows only where the step has one (explainer
    build, Oct 19, 2026)."""
    import io
    from contextlib import redirect_stderr
    from convey import powerpoint
    d = Path(tempfile.mkdtemp())
    brand = d / "a"
    (brand / "assets").mkdir(parents=True)
    (brand / "tokens.css").write_text(":root { --brand-ground: #111111; }\n")
    (brand / "brand.json").write_text(json.dumps({"fonts": {}, "bindings": {}, "layouts": [
        {"name": "Title Only", "placeholders": [{"type": "title", "idx": 0, "name": "Title 1"}]}]}))
    deck = d / "deck"
    deck.mkdir()
    (deck / "brief.json").write_text(json.dumps({"autonomy": "just-build", "brand": "../a"}))
    steps = [{"label": "One", "note": "a"}, {"label": "Two", "note": "b", "tag": "You sign off"}, {"label": "Three", "note": "c"}]
    (deck / "storyboard.json").write_text(json.dumps({"slides": [
        {"id": "S-1", "pattern": "steps", "variant": "row", "headline": "Three steps", "claim_ids": [],
         "content": {"steps": steps}}]}))
    real = powerpoint.APP
    try:
        powerpoint.APP = Path(__file__)  # PowerPoint "installed"
        err = io.StringIO()
        with redirect_stderr(err):
            compose(deck, brand)
        ok("no layout pictures" in err.getvalue() and "convey brand render" in err.getvalue(),
           "compose says when the brand has no layout pictures and PowerPoint is installed")
        (brand / "assets" / "layouts").mkdir()
        (brand / "assets" / "layouts" / "01-title-only.png").write_bytes(b"")
        err = io.StringIO()
        with redirect_stderr(err):
            compose(deck, brand)
        ok("no layout pictures" not in err.getvalue(), "with layout pictures, no such note")
    finally:
        powerpoint.APP = real
    f = next((deck / "slides").glob("*.html"))
    t = f.read_text()
    tags = re.findall(r'data-id="g-(\d)"[^>]*>([^<]*)<', t)
    ok(tags == [("2", "You sign off")], f"steps/row shows a tag only on the step that has one ({tags})")
    f.write_text(t.replace(".t { margin-top: 24px;", ".t { margin-top: 30px;"))
    try:
        compose(deck, brand, quiet=True)
        ok(False, "a second compose over hand-edited slides is refused")
    except SystemExit as e:
        ok("--keep-edits" in str(e) and f.name in str(e), "a second compose names the hand-edited slides and refuses")
    compose(deck, brand, quiet=True, keep_edits=True)
    ok(".t { margin-top: 30px;" in f.read_text(), "compose --keep-edits carries the hand edit")
    compose(deck, brand, quiet=True, overwrite=True)
    ok(".t { margin-top: 24px;" in f.read_text(), "compose --overwrite drops it")
    shutil.rmtree(d)


if __name__ == "__main__":
    sys.exit(main())
