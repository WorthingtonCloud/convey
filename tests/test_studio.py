"""The review studio's rules, without the page: typed edits write the slide and the storyboard and nothing else,
Undo puts the old words back, the person types only on their turn, notes reach the agent with their target, rounds
snapshot versions and measure what changed, restore brings a version back, and a typed edit survives the agent's
revision (or the round summary says plainly that it didn't). Neutral, made-up fixture only (test_check's deck).

Run: python3 skill/tests/test_studio.py   (Chrome or Edge measures boxes; standard library otherwise)
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from convey import compose  # noqa: E402
from convey.studio import edits as E, log as L, rounds as RD, slidefile as F  # noqa: E402
from test_check import project  # noqa: E402

bad: list[str] = []


def ok(cond, what):
    print(f"{'ok  ' if cond else 'FAIL'}  {what}")
    if not cond:
        bad.append(what)


def refused(fn, what, needle=""):
    try:
        fn()
    except (L.Refused, F.NotEditable) as x:
        ok(needle.lower() in str(x).lower(), f"{what} (refused: {x})")
        return
    ok(False, f"{what} (was not refused)")


def sb(d):
    return json.loads((d / "storyboard.json").read_text())


def slide_file(d, n):
    return next((d / "slides").glob(f"0{n}-*.html"))


def human(d, events, **kw):
    return L.append(d, [{**e, "held": e.get("held", e["type"] in L.HELD)} for e in events], "human", **kw)


def edit(d, file, did, text, seen=None):
    ev = E.prepare(d, file, did, text, seen)
    return human(d, [ev], effect=lambda old, new: E.apply(d, new[0]))


def undo(d, seq):
    def effect(old, new):
        evs = old + new
        for e in new:
            x = evs[e["of"] - 1]
            if x["type"] == "text.edited":
                E.revert(d, x)
    return L.append(d, [{"type": "undo", "of": seq}], "human", effect=effect)


def send(d):
    S, new, first = L.append(d, [{"type": "round.sent"}], "human")
    RD.snapshot_sent(d, L.current(S)["n"])
    return S


def test_slidefile():
    src = ('<html><head><title>Old words</title></head><body><section class="slide" data-slide="S-9">\n'
           '<h1 data-id="headline" data-bind="headline" style="left:1px">Old &amp; tired</h1>\n'
           '<ul data-id="pts" data-bind="content.points"><li class="x">One</li><li>Two</li></ul>\n'
           '<div data-id="group"><p data-id="inner">Inside</p></div><figure data-id="chart" data-chart="{}"></figure>'
           '</section></body></html>')
    ok(F.read(src, "headline") == "Old & tired", "reads a text with entities decoded")
    ok(F.read(src, "pts") == ["One", "Two"], "reads a list item by item")
    ok(F.kind(F.named(src)["group"]) is None and F.kind(F.named(src)["chart"]) is None, "a group and a chart take notes, not typing")
    out = F.write(src, "headline", "New <bold> words")
    ok(out == src.replace("Old &amp; tired", "New &lt;bold&gt; words"), "a write changes the words and not one other byte")
    out = F.write(src, "pts", ["Uno", "Dos"])
    ok(out == src.replace(">One<", ">Uno<").replace(">Two<", ">Dos<"), "a list keeps each item's own tag")
    ok(F.read(F.write(src, "pts", ["A", "B", "C"]), "pts") == ["A", "B", "C"], "a list can grow")
    ok(F.retitle(src, "Old words", "Fresh") .count("<title>Fresh</title>") == 1, "the page title follows the headline")
    refused(lambda: F.write(src, "group", "x"), "typing into a group is refused", "more than words")
    refused(lambda: F.write(src, "nope", "x"), "an unknown object is refused", "no object")


def test_edits_and_turns(d):
    f2 = slide_file(d, 2).name
    S = RD.open_round(d, quiet=True)
    ok(S["turn"] == "human" and (d / "versions/v1/storyboard.json").exists(), "round 1 opens on version 1, the person's turn")
    head = sb(d)["slides"][1]["headline"]
    H, new, seq = edit(d, f2, "headline", "The close fell from 15 days to 4 in the pilot", seen=head)
    ok("in the pilot</h1>" in slide_file(d, 2).read_text(), "a typed edit lands in the slide HTML")
    ok(sb(d)["slides"][1]["headline"].endswith("in the pilot"), "and through data-bind in storyboard.json")
    ok(H["pending"] == [seq] and L.state(d)["edits"] == [], "it waits, held, until Send (the agent can't see it yet)")
    undo(d, seq)
    ok(sb(d)["slides"][1]["headline"] == head and head in slide_file(d, 2).read_text(), "Undo puts the old words back in both")
    refused(lambda: edit(d, f2, "headline", "x", seen="something else"), "an edit on stale words is refused", "changed since")
    H, _, s1 = edit(d, f2, "headline", "Typed once", seen=head)
    H, _, s2 = edit(d, f2, "headline", "Typed twice", seen="Typed once")
    refused(lambda: undo(d, s1), "undoing an older edit under a newer one is refused", "changed again")
    undo(d, s2)
    undo(d, s1)
    ok(sb(d)["slides"][1]["headline"] == head, "two edits undone newest first come all the way back")
    # a number nobody can trace fails check at once
    from convey.check import run
    edit(d, f2, "m2-note", "Saves 40 hours a month", seen=F.read(slide_file(d, 2).read_text(), "m2-note"))
    fails = [p for p in run(d)["results"]["numbers"] if "40" in p]
    ok(bool(fails), "a typed number that traces to no claim fails check")
    undo(d, L.state(d, "human")["pending"][-1])
    ok(not run(d)["results"]["numbers"], "and passes again after Undo")
    refused(lambda: human(d, [{"type": "note.added", "note": {"level": "slide", "slide": "S-2"}}]),
            "a note with no words and no ask is refused", "say what")


def test_round_trip_and_risk7(d):
    """Edit a headline, send a note on the same slide, revise, and the typed edit survives (PLAN risk 7)."""
    f2 = slide_file(d, 2).name
    RD.open_round(d, quiet=True)
    s2 = sb(d)["slides"][1]
    typed = "The close fell from 15 days to 4 in the pilot"
    edit(d, f2, "headline", typed, seen=s2["headline"])
    cav = F.named(slide_file(d, 2).read_text()).get("caveat")
    ok(cav is not None, "the KPI slide has its caveat")
    human(d, [{"type": "note.added", "note": {"level": "object", "slide": "S-2", "file": f2,
                                              "target": {"id": "caveat", "box": [0.05, 0.8, 0.5, 0.85], "text": s2["caveat"]},
                                              "mark": {"type": "click", "x": 0.1, "y": 0.82}, "comment": "Shorter", "ask": "smaller"}},
              {"type": "note.added", "note": {"level": "deck", "comment": "Use the same date format everywhere"}}])
    S = send(d)
    ok(S["turn"] == "agent", "after Send it's the agent's turn")
    refused(lambda: edit(d, f2, "caveat", "x", seen=None), "typing on the agent's turn is refused", "agent's turn")
    A = L.state(d)
    ok(A["notes"]["n-0001"]["target"]["id"] == "caveat" and A["notes"]["n-0001"]["status"] == "sent",
       "the note reaches the agent with its target")
    ok([x["new"] for x in A["edits"]] == [typed], "and so does the typed edit")
    refused(lambda: RD.open_round(d, quiet=True), "a new round waits until every note is answered", "answer every note")
    # the agent revises: the caveat, in the slide and the storyboard together, and nothing else
    f = slide_file(d, 2)
    short = "Finance team only."
    f.write_text(f.read_text().replace(s2["caveat"], short))
    doc = sb(d)
    doc["slides"][1]["caveat"] = short
    (d / "storyboard.json").write_text(json.dumps(doc, indent=1))
    RD.resolve(d, "n-0001", "Cut the caveat to three words.")
    RD.resolve(d, "n-0002", "Dates were already one format; nothing to change.", wontdo=True, files=[])
    S = RD.open_round(d, quiet=True)
    s = L.current(S)["summary"]
    ok(s["edits"] and all(e["kept"] for e in s["edits"]), "the next round says the typed headline was kept")
    ok(typed in slide_file(d, 2).read_text() and sb(d)["slides"][1]["headline"] == typed, "and it really is still there")
    n1 = next(n for n in s["notes"] if n["id"] == "n-0001")
    ok(n1["verdict"] == "changed", f"the caveat note measured changed ({n1['detail']})")
    ok(not s["beyond"], f"nothing changed beyond what was asked ({s['beyond']})")
    ok((d / "versions/v2/slides").exists(), "round 2 snapshots version 2")
    return typed


def test_overwrite_is_reported(d, typed):
    """An agent that overwrites the person's edit, or changes something nobody asked about, is named in the summary."""
    f2 = slide_file(d, 2).name
    edit(d, f2, "m1-label", "Close time", seen=F.read(slide_file(d, 2).read_text(), "m1-label"))
    human(d, [{"type": "note.added", "note": {"level": "slide", "slide": "S-3", "comment": "Tighter"}}])
    send(d)
    f = slide_file(d, 2)
    f.write_text(f.read_text().replace(">Close time<", ">Monthly close<").replace(typed, "The close fell from 15 days to 4"))
    doc = sb(d)
    doc["slides"][1]["content"]["items"][0]["label"] = "Monthly close"
    doc["slides"][1]["headline"] = "The close fell from 15 days to 4"
    (d / "storyboard.json").write_text(json.dumps(doc, indent=1))
    RD.resolve(d, "n-0003", "Tightened.")
    s = L.current(RD.open_round(d, quiet=True))["summary"]
    lost = [e for e in s["edits"] if not e["kept"]]
    ok(lost and lost[0]["id"] == "m1-label", "an overwritten typed edit is reported as changed by the agent")
    ok(any(c["id"] == "headline" for c in s["beyond"]), "a change nobody asked for is listed beyond what was asked")
    n3 = next(n for n in s["notes"] if n["id"] == "n-0003")
    ok(n3["verdict"] == "unchanged", "a slide note whose slide never changed measures unchanged")
    # a deck-wide note answered with the files it changed: those changes were asked for
    human(d, [{"type": "note.added", "note": {"level": "deck", "comment": "Label the first metric everywhere"}}])
    send(d)
    f = slide_file(d, 2)
    f.write_text(f.read_text().replace(">Monthly close<", ">Monthly close time<"))
    doc = sb(d)
    doc["slides"][1]["content"]["items"][0]["label"] = "Monthly close time"
    (d / "storyboard.json").write_text(json.dumps(doc, indent=1))
    RD.resolve(d, "n-0004", "Relabeled it.", files=[f"slides/{f.name}", "storyboard.json"])
    s = L.current(RD.open_round(d, quiet=True))["summary"]
    ok(not s["beyond"], f"a deck note's named files count as asked ({s['beyond']})")


def test_versions(d):
    v1 = json.loads((d / "versions/v1/storyboard.json").read_text())
    RD.restore(d, "v1")
    ok(sb(d) == v1, "convey restore v1 brings version 1's storyboard back")
    ok(slide_file(d, 2).read_text() == (d / "versions/v1/slides" / slide_file(d, 2).name).read_text(), "and its slides")
    ok(any(p.name.startswith("before-restore-") for p in (d / "versions").iterdir()), "what was there is kept")
    refused(lambda: RD.restore(d, "v9"), "an unknown version is refused", "no version")
    try:
        compose.compose(d, d.parent / "brand")
        ok(False, "compose refused a deck in review")
    except SystemExit as x:
        ok("in review" in str(x), "compose refuses a deck in review (it would wipe typed edits)")


def main() -> int:
    test_slidefile()
    with tempfile.TemporaryDirectory() as t:
        base = project(Path(t))
        d1 = Path(t) / "turns"
        shutil.copytree(base, d1)
        test_edits_and_turns(d1)
        d2 = Path(t) / "deck2"
        shutil.copytree(base, d2)
        typed = test_round_trip_and_risk7(d2)
        test_overwrite_is_reported(d2, typed)
        test_versions(d2)
    print(f"studio test: {len(bad)} failure(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
