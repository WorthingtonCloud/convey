"""convey check catches planted errors and passes a clean deck. Neutral, made-up fixture only.

A small deck project (a team moving its monthly reporting) is written to a temp folder, taken
through intake and compose, and then broken one way at a time:
  invented    a number on a slide that no claim states
  no source   an observed claim with its source removed
  script      a derived number the ledger states differently from what its script computes
  slide       a number typed into a composed slide's HTML
  binding     a slide text edited so it no longer equals its storyboard field
  month       two slide texts run together: a note ending "September" beside an invented "30 hours" read as the date
              "September 30", so the invented number passed (and "September" beside "10,462" left a false "462")
  exempt      `not_claims: ["0"]` must not blank the 0 inside an invented "40" (it read as a cited 4)
  words       a source that spells a number ("Three analysts") backs a claim of 3 (the clean fixture), and not of 4
  emphasis    a headline word wrapped in <span class="hit"> before a comma reads "never," not "never ," (Oct 18, 2026)
  terse       the headline chain prints the first time, not again until it changes, and always with -v
The clean project must pass every check; each broken one must fail the check it targets.

Run: python3 skill/tests/test_check.py   (needs Chrome or Edge only for nothing; standard library)
"""
from __future__ import annotations

import copy
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from convey import check, compose, intake  # noqa: E402

CSV = "metric,before,after\nMonthly close (days),15,4\nSpreadsheets in circulation,11,1\nAnalysts served,90,90\n"
NOTES = "Pilot notes\n\nThe pilot ran in the finance team only, from Mar 3, 2026 to Apr 30, 2026.\nThree analysts ran it.\n"
SCRIPT = '''import csv, json
rows = {r["metric"]: r for r in csv.DictReader(open("sources/close-times.csv"))}
b, a = float(rows["Monthly close (days)"]["before"]), float(rows["Monthly close (days)"]["after"])
print(json.dumps({"D-1": [round((a - b) / b * 100, 4), a - b]}))
'''
BRIEF = {"schema": "convey.brief/1", "title": "Moving monthly reporting", "audience": {"who": "Finance leads"},
         "purpose": "decide", "mode": "decision", "outcome": "Approve moving the other teams", "brand": "neutral"}
EVIDENCE = {"schema": "convey.evidence/1", "claims": [
    {"id": "E-1", "kind": "observed", "statement": "The monthly close took 15 days before the move.",
     "numbers": [{"value": 15, "unit": "days"}], "source": {"file": "sources/close-times.csv", "locator": "B2"},
     "confidence": {"level": "high", "reason": "From the team's own log"}},
    {"id": "E-2", "kind": "observed", "statement": "It took 4 days after the move.",
     "numbers": [{"value": 4, "unit": "days"}], "source": {"file": "sources/close-times.csv", "locator": "C2"},
     "confidence": {"level": "high", "reason": "From the team's own log"}},
    {"id": "E-3", "kind": "observed", "statement": "Spreadsheets in circulation fell from 11 to 1.",
     "numbers": [{"value": 11}, {"value": 1}], "source": {"file": "sources/close-times.csv", "locator": "row 3"},
     "confidence": {"level": "high", "reason": "Counted"}},
    {"id": "E-4", "kind": "observed", "statement": "The pilot covered the finance team only.",
     "source": {"file": "sources/notes.md", "locator": "line 3", "quote": "in the finance team only"},
     "confidence": {"level": "high", "reason": "Stated in the notes"}},
    {"id": "E-5", "kind": "observed", "statement": "3 analysts ran the pilot.", "numbers": [{"value": 3}],
     "source": {"file": "sources/notes.md", "locator": "line 4"}, "confidence": {"level": "high", "reason": "Stated in the notes"}},
    {"id": "D-1", "kind": "derived", "statement": "The close was 73% shorter: 11 days less.",
     "numbers": [{"value": -73.3, "unit": "%"}, {"value": -11, "unit": "days"}], "inputs": ["E-1", "E-2"],
     "method": "(after - before) / before", "script": "analysis/d1.py",
     "confidence": {"level": "high", "reason": "Arithmetic on two observed values"}}],
    "gaps": [{"id": "G-1", "text": "Other teams' close may not shorten as much.", "could_reverse": True}]}
STORY = {"schema": "convey.storyboard/1", "governing_message": "The pilot cut the close from 15 days to 4; move the other teams.",
         "arc": "decision", "ask": "Approve moving the other teams", "approved": {"by": "test", "at": "Jan 1, 2026"},
         "slides": [
             {"id": "S-1", "pattern": "cover", "headline": "One source of numbers, a shorter close",
              "audience_question": "What is this?", "claim_ids": [],
              "content": {"subtitle": "Asking to move the other teams", "meta": "Finance pilot review · May 4, 2026"}},
             {"id": "S-2", "pattern": "kpi-row", "headline": "The close fell from 15 days to 4",
              "audience_question": "What changed?", "claim_ids": ["E-1", "E-2", "E-3", "D-1"],
              "content": {"items": [
                  {"value": "4 days", "label": "Monthly close", "note": "Down from 15 days"},
                  {"value": "73%", "label": "Shorter close", "note": "11 days less each month"},
                  {"value": "1", "label": "Spreadsheet in use", "note": "Down from 11"}]},
              "caveat": "Finance team only; other teams may differ."},
             {"id": "S-3", "pattern": "key-finding", "headline": "The finance pilot is the only evidence so far",
              "audience_question": "How sure are we?", "claim_ids": ["E-4"],
              "content": {"evidence": "The pilot covered the finance team only.", "source": "Pilot notes."}}]}
TOKENS = """:root { --brand-ground: #ffffff; --brand-ink: #111111; --brand-raised: #eeeeee; --brand-body: #333333;
 --brand-muted: #666666; --brand-rule: #cccccc; --brand-signal: #cc3300; --brand-data-1: #336699; --brand-data-2: #669933;
 --brand-font-heading: Helvetica; --brand-weight-heading: 700; --brand-font-body: Helvetica; --brand-weight-body: 400;
 --brand-title-tracking: 0em; --brand-margin-left: 64px; --brand-margin-top: 48px; --brand-margin-footer-top: 676px;
 --brand-content-width: 1152px; --brand-headline-size: 36px; --brand-headline-line: 44px; --brand-statement-size: 48px;
 --brand-statement-line: 56px; --brand-text-size: 20px; --brand-text-line: 28px; --brand-small-size: 14px;
 --brand-small-line: 20px; --brand-display-size: 80px; --brand-display-line: 88px; }"""


def project(root: Path) -> Path:
    d = root / "deck"
    (d / "analysis").mkdir(parents=True)
    raw = root / "raw"
    raw.mkdir()
    (raw / "close-times.csv").write_text(CSV)
    (raw / "notes.md").write_text(NOTES)
    intake.intake([str(raw / "close-times.csv"), str(raw / "notes.md")], d)
    (d / "analysis" / "d1.py").write_text(SCRIPT)
    (d / "brief.json").write_text(json.dumps(BRIEF))
    (d / "evidence.json").write_text(json.dumps(EVIDENCE))
    (d / "storyboard.json").write_text(json.dumps(STORY))
    brand = root / "brand"
    brand.mkdir()
    (brand / "tokens.css").write_text(TOKENS)
    (brand / "brand.json").write_text(json.dumps({"name": "neutral", "fonts": {}, "layouts": [], "bindings": {}}))
    compose.compose(d, brand)
    return d


def failing(d: Path) -> set[str]:
    return {k for k, v in check.run(d)["results"].items() if v}


def edit(d: Path, name: str, fn):
    doc = json.loads((d / f"{name}.json").read_text())
    fn(doc)
    (d / f"{name}.json").write_text(json.dumps(doc))


def main() -> int:
    bad = []
    with tempfile.TemporaryDirectory() as t:
        base = project(Path(t))
        got = failing(base)
        if got:
            bad.append(f"clean fixture fails {sorted(got)}: {check.run(base)['results']}")

        def variant(name, change, target):
            import shutil
            d = Path(t) / name
            shutil.copytree(base, d)
            change(d)
            got = failing(d)
            if target not in got:
                bad.append(f"{name}: check did not fail {target!r} (failed: {sorted(got) or 'nothing'})")
            print(f"{name:10} -> fails {sorted(got)}")

        def invented(d):
            def f(sb):
                sb["slides"][1]["content"]["items"][2]["note"] = "Saves $40,000 a year"
            edit(d, "storyboard", f)

        def no_source(d):
            edit(d, "evidence", lambda ev: ev["claims"][1].pop("source"))

        def script(d):
            def f(ev):
                ev["claims"][5]["numbers"][0]["value"] = -80
            edit(d, "evidence", f)

        def slide_number(d):
            f = next((d / "slides").glob("02-*.html"))
            f.write_text(f.read_text().replace("Down from 11", "Down from 11; 30 hours saved"))

        def binding(d):
            f = next((d / "slides").glob("03-*.html"))
            f.write_text(f.read_text().replace("The finance pilot is the only evidence so far", "The pilot proves it works"))

        variant("invented", invented, "numbers")
        variant("no-source", no_source, "sources")
        variant("script", script, "derived")
        variant("slide", slide_number, "numbers")
        variant("binding", binding, "bindings")

        def exempt(d):
            def f(sb):
                sb["slides"][1]["content"]["not_claims"] = ["0"]
                sb["slides"][1]["content"]["items"][2]["note"] = "Saves 40 hours"
            edit(d, "storyboard", f)

        variant("exempt", exempt, "numbers")

        def month(d):
            f = next((d / "slides").glob("02-*.html"))
            f.write_text(f.read_text().replace("</section>", '<p class="small">Logged since September</p><p class="small">30 hours saved</p></section>'))

        variant("month", month, "numbers")

        def words(d):
            edit(d, "evidence", lambda ev: ev["claims"][4]["numbers"][0].update(value=4))

        variant("words", words, "sources")
        h = Path(t) / "emphasis.html"
        h.write_text('<section class="slide" data-slide="S-1"><h1 data-bind="headline">Inputs <span class="hit">never</span>, '
                     'ever<b>!</b></h1><p data-bind="content.a">One</p><p data-bind="content.b">Two</p></section>')
        binds = check.read_slide(h).binds
        if ("headline", "Inputs never, ever!") not in binds or ("content.a", "One") not in binds:
            bad.append(f"emphasis: an inline run changed the bound text: {binds}")
        print(f"emphasis   -> {binds[-1]}")
        # a claim kept in thousands states "$340K" and "-$390K" (Oct 18, 2026), and not "$350K"
        k = check.numbers_in("$340K, then -$390K, then $350K")
        got = [check.matches(f, v, "$K") for f, v in zip(k, (340, -390, 340))]
        if got != [True, True, False]:
            bad.append(f"thousands: $K claims matched {got}, wanted [True, True, False]")
        print(f"thousands  -> {got}")
        # a count a source writes with a comma ("2,000-person") is a figure, not a year; a bare 2000 is a year
        got = [check.reads_as_year(2000.0, "", check.source_numbers(t_)) for t_ in
               ("a 2,000-person manufacturer", "in 2000 it began", "a 2,000-person maker")] + \
              [check.reads_as_year(2000.0, "people", check.source_numbers("in 2000"))]
        if got != [False, True, False, False]:
            bad.append(f"count: years and counts read {got}, wanted [False, True, False, False]")
        print(f"count      -> {got}")
        # terse output (the token diet, Oct 18, 2026): the chain prints when it changed since the last check, and with -v
        import io
        from contextlib import redirect_stdout

        def said(*a):
            buf = io.StringIO()
            with redirect_stdout(buf):
                check.report(base, *a)
            return buf.getvalue()
        first, again, loud = said(), said(), said(True)
        edit(base, "storyboard", lambda sb: sb["slides"][0].update(headline=sb["slides"][0]["headline"] + " now"))
        changed = said()
        terse = ("Headline chain" in first and "Headline chain" not in again and "unchanged" in again
                 and "Headline chain" in loud and "PASS  structure" in loud and "Headline chain" in changed)
        if not terse:
            bad.append(f"terse: chain first/again/-v/changed = {['Headline chain' in x for x in (first, again, loud, changed)]}")
        print(f"terse      -> {len(first.splitlines())} lines, then {len(again.splitlines())} unchanged")
        # a photo for a slide is a picture, not unreadable evidence (Oct 18, 2026 stress test)
        pic = Path(t) / "cover.png"
        pic.write_bytes(b"\x89PNG\r\n\x1a\n")
        m = intake.intake([str(pic)], Path(t) / "pictures")
        e = m["files"][0]
        if not e.get("picture") or e.get("flag"):
            bad.append(f"picture: intake flagged a photo as unreadable: {e}")
        print(f"picture    -> {'picture, no flag' if e.get('picture') and not e.get('flag') else e}")
        # the story gate: an unapproved story is not composed
        edit(base, "storyboard", lambda sb: sb.update(approved=None))
        try:
            compose.compose(base, Path(t) / "brand")
            bad.append("compose ran on an unapproved story")
        except SystemExit:
            print("gate       -> compose refused an unapproved story")
    for b in bad:
        print("FAIL", b)
    print(f"check test: clean passes, 8 planted errors, {len(bad)} failures")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
