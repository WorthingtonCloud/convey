"""convey check: hold the brief, the evidence, the story and the slides together.

    convey check DIR [-v]       (a deck project: brief.json, evidence.json, storyboard.json, slides/)

Checks, each PASS or FAIL with every problem named:
  structure    the three files match their schemas; ids are unique; each slide's content fits its pattern
  claims       every claim a slide cites exists; only covers, sections and agendas go without claims
  sources      every observed number appears in its source file at its locator (from `convey intake`)
  derived      every derived claim has a script, its inputs exist, and the script still prints its numbers
  numbers      every number shown on a slide (storyboard text, slide HTML, chart data) traces to a cited claim,
               or is a date, or is marked as not a claim (storyboard `not_claims`, HTML `data-not-claim`)
  bindings     every slide text with data-bind equals its storyboard field
Then prints the headline chain for the person to read, the gaps that could reverse the conclusion,
whether the story is approved, and what code can't check (causal overreach, chart honesty, design). Passing
checks share one line, and the chain, gaps and limits print only when they changed since the project's last
check; `-v` prints everything.
Standard library only.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

from . import intake
from .schema import validate

NO_CLAIMS_OK = {"cover", "closing", "section", "agenda", "photo-led"}

# The typed slots of each pattern's content: required and optional (see patterns/<id>/pattern.md).
SLOTS = {
    "cover": ({"subtitle"}, {"meta", "image", "focus", "credit"}),
    "closing": (set(), {"subtitle", "meta", "kicker", "items", "image", "focus"}),
    "agenda": ({"items"}, set()),
    "section": (set(), {"number", "standfirst", "kicker", "image", "focus"}),
    "executive-summary": ({"items"}, {"answer"}),
    "key-finding": ({"evidence"}, {"source", "kicker", "value", "icon"}),
    "kpi-row": ({"items"}, {"source"}),
    "comparison": ({"left", "right"}, {"criteria", "source"}),
    "chart": ({"chart"}, {"source", "legend", "takeaway", "callout"}),
    "diagram": ({"steps"}, {"source"}),
    "photo-led": ({"image"}, {"kicker", "subtitle", "credit", "focus"}),
    "quote": ({"who"}, {"quote", "context", "source"}),
    "scorecard": ({"items"}, {"tally", "source"}),
    "options": ({"items"}, {"baseline", "source"}),
    "statement": (set(), {"kicker", "proof", "source"}),
    "giant-number": ({"value", "label"}, {"evidence", "turn", "source", "second"}),
    "before-after": ({"before", "after"}, {"source", "change"}),
    "steps": ({"steps"}, {"source"}),
    "timeline": ({"milestones"}, {"source"}),
    "matrix": ({"x", "y", "quadrants"}, {"source"}),
}
# Content keys that hold a file or a crop, never words: no number in them is a figure.
NOT_TEXT = {"chart", "image", "focus", "icon"}

# ---------- numbers ----------

MONTHS = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
DATES = re.compile(
    rf"\b{MONTHS}\.?\s+\d{{1,2}}(?:,\s*\d{{4}})?\b|\b\d{{1,2}}\s+{MONTHS}\.?(?:\s+\d{{4}})?\b|\b{MONTHS}\.?\s+\d{{4}}\b"
    r"|\b\d{4}-\d{2}-\d{2}\b|\b(?:Q[1-4]|H[12]|FY)\s*'?\d{2,4}\b|\b(?:19|20)\d{2}\b")
NUM = re.compile(
    r"(?<![A-Za-z0-9.])(?<![A-Za-z]-)(?P<sign>[−–+-])?\s?(?P<cur>[$€£])?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)"
    r"(?P<suf>\s?(?:%|percent\b|per cent\b|pp\b|k\b|K\b|M\b|B\b|bn\b|thousand\b|million\b|billion\b))?"
    r"(?![A-Za-z0-9])(?!\.\d)")
SCALE = {"k": 1e3, "K": 1e3, "thousand": 1e3, "M": 1e6, "million": 1e6, "B": 1e9, "bn": 1e9, "billion": 1e9}


def numbers_in(text: str) -> list[dict]:
    """Every figure in a text, dates removed: {text, raw, decimals, scale, percent}."""
    clean = DATES.sub(lambda m: " " * len(m.group()), text)
    out = []
    for m in NUM.finditer(clean):
        n = m.group("num").replace(",", "")
        suf = (m.group("suf") or "").strip()
        out.append({"text": m.group().strip(), "raw": float(n), "decimals": len(n.split(".")[1]) if "." in n else 0,
                    "scale": SCALE.get(suf, 1.0), "percent": suf in ("%", "percent", "per cent", "pp")})
    return out


UNITS = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
WORDNUM = re.compile(r"\b(?:(?P<tens>" + "|".join(TENS) + r")(?:-(?P<unit>" + "|".join(UNITS[1:10]) + r"))?|(?P<small>"
                     + "|".join(sorted(UNITS, key=len, reverse=True)) + r"))\b", re.I)


def source_numbers(text: str) -> list[dict]:
    """numbers_in plus small numbers spelled out ("all three cases", "twenty-one"): a source often writes a
    number in words that a slide shows in digits. Slides are never read this way ("one did" is not a figure)."""
    out = numbers_in(text)
    for m in WORDNUM.finditer(text):
        v = UNITS.index(m.group("small").lower()) if m.group("small") else \
            TENS[m.group("tens").lower()] + (UNITS.index(m.group("unit").lower()) if m.group("unit") else 0)
        out.append({"text": m.group(), "raw": float(v), "decimals": 0, "scale": 1.0, "percent": False})
    return out


def matches(shown: dict, value: float, unit: str = "") -> bool:
    """Does a shown figure state this claim value, at the precision it is shown? Signs are not compared
    ("fell 40%" states -40), but scale and percent forms are: 40% = 0.40 = 40 percent."""
    v = abs(value)
    tries = [v]
    # A claim kept in thousands or millions ("340" with unit "$K", as spreadsheets often hold money) states "$340K".
    u = unit.strip().lstrip("$€£").strip()
    if u in SCALE:
        tries.append(v * SCALE[u])
    if shown["percent"] and unit not in ("%", "percent", "pp") and v <= 1:
        tries.append(v * 100)
    if not shown["percent"] and unit in ("%", "percent") and shown["decimals"] > 0:
        tries.append(v / 100)
    for t in tries:
        t = t / shown["scale"]
        if abs(round(t, shown["decimals"]) - shown["raw"]) < 1e-9:
            return True
    return False


def reads_as_year(v: float, unit: str, found: list[dict]) -> bool:
    """A claim number from 1900 to 2099 with no unit is a year (a date, never checked as a figure), unless its source
    writes it as a count, with a thousands comma: "a 2,000-person manufacturer" (Oct 18, 2026 stress test)."""
    if not (v.is_integer() and 1900 <= v <= 2099 and unit in ("", "year")):
        return False
    return not any("," in f["text"] and f["raw"] == v and f["scale"] == 1 for f in found)


def claim_values(c: dict) -> list[tuple[float, str]]:
    vals = [(float(n["value"]), n.get("unit", "")) for n in c.get("numbers", [])]
    for n in numbers_in(c.get("statement", "")):
        vals.append((n["raw"] * n["scale"], "%" if n["percent"] else ""))
    return vals


# ---------- slide HTML ----------

class Slide(HTMLParser):
    """Collects data-bind texts, data-claims, visible text (minus data-not-claim) and chart specs."""

    INLINE = {"span", "b", "strong", "em", "i", "u", "small", "sub", "sup", "a", "code", "abbr", "mark", "s", "q",
              "time", "data", "bdi", "bdo", "kbd", "var", "wbr", "br"}
    VOID = {"br", "img", "meta", "link", "input", "hr", "source", "path", "rect", "circle", "line", "polygon",
            "polyline", "ellipse", "stop"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.binds, self.claims, self.text, self.exempt, self.charts = [], [], set(), [], [], []
        self.slide_id = None
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "section" and "data-slide" in a:
            self.slide_id = a["data-slide"]
        if a.get("data-claims"):
            self.claims |= {c.strip() for c in a["data-claims"].split(",") if c.strip()}
        if "data-chart" in a:
            self.charts.append((a.get("data-bind"), json.loads(a["data-chart"])))
        node = {"tag": tag, "bind": a.get("data-bind"), "buf": [], "items": [],
                "exempt": "data-not-claim" in a, "hidden": tag in ("style", "script") or "data-underlay" in a}
        if tag in self.VOID:
            return
        self.stack.append(node)

    def handle_endtag(self, tag):
        if tag in self.VOID or not self.stack:
            return
        while self.stack:
            node = self.stack.pop()
            text = " ".join("".join(node["buf"]).split())
            if node["bind"]:
                self.binds.append((node["bind"], node["items"] if node["tag"] in ("ul", "ol") else text))
            if self.stack:
                parent = self.stack[-1]
                # a block ends a word ("a</p><p>b" is two); an inline run doesn't ("<span>never</span>," stays "never,")
                pad = "" if node["tag"] in self.INLINE else " "
                parent["buf"].append(pad + "".join(node["buf"]) + pad)
                if node["tag"] == "li":
                    parent["items"].append(text)
            if node["tag"] == tag:
                break

    def handle_data(self, data):
        if not self.stack or any(n["hidden"] for n in self.stack):
            return
        self.stack[-1]["buf"].append(data)
        if any(n["exempt"] for n in self.stack):
            self.exempt.append(data)
            return
        # one text per block: inline runs join their block ("73<b>%</b>"), but two blocks never run together,
        # or a note ending "September" beside a "10,462" would read as the date "September 10"
        block = next((n for n in reversed(self.stack) if n["tag"] not in self.INLINE), self.stack[0])
        if self.text and self.text[-1][0] is block:
            self.text[-1][1].append(data)
        else:
            self.text.append((block, [data]))

    def texts(self) -> list[str]:
        return ["".join(parts) for _, parts in self.text]


def read_slide(path: Path) -> Slide:
    p = Slide()
    p.feed(path.read_text())
    return p


def field(slide: dict, path: str):
    node = slide
    for part in path.split("."):
        if isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        elif isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return node


def strings(node) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for k, v in node.items() if k not in NOT_TEXT for s in strings(v)]
    if isinstance(node, list):
        return [s for v in node for s in strings(v)]
    return []


def chart_values(spec: dict) -> list[float]:
    return [v for s in spec.get("series", []) for v in s.get("values", []) if isinstance(v, (int, float))]


# ---------- the checks ----------

def load(d: Path, name: str):
    p = d / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def run(d: Path) -> dict:
    res = {k: [] for k in ("structure", "claims", "sources", "derived", "numbers", "bindings")}
    notes = []
    brief, ev, sb = load(d, "brief"), load(d, "evidence"), load(d, "storyboard")
    for name, doc in (("brief", brief), ("evidence", ev), ("storyboard", sb)):
        if doc is None and name == "brief":
            res["structure"].append(f"{name}.json is missing")
        elif doc is None:  # a project at the brief or ledger stage: check what exists (Oct 18, 2026)
            notes.append(f"{name}.json not written yet: checked what exists")
        else:
            res["structure"] += [f"{name}.json {p}" for p in validate(doc, name)]
    ev = ev or {"claims": []}
    sb = sb or {"slides": []}
    claims = {}
    for c in ev.get("claims", []):
        if c.get("id") in claims:
            res["structure"].append(f"evidence.json: claim id {c['id']} is used twice")
        claims[c.get("id")] = c
    sids = [s.get("id") for s in sb.get("slides", [])]
    for s in {x for x in sids if sids.count(x) > 1}:
        res["structure"].append(f"storyboard.json: slide id {s} is used twice")

    # claims a slide cites
    for s in sb.get("slides", []):
        for cid in s.get("claim_ids", []):
            if cid not in claims:
                res["claims"].append(f"{s['id']} cites {cid}, which is not in evidence.json")
        if not s.get("claim_ids") and s.get("pattern") not in NO_CLAIMS_OK and s.get("role") not in ("agenda", "divider"):
            res["claims"].append(f"{s['id']} ({s.get('pattern')}) cites no claims; only covers, sections and agendas may")
        req, opt = SLOTS.get(s.get("pattern"), (set(), set()))
        content = s.get("content") or {}
        for k in req - set(content):
            res["structure"].append(f"{s['id']}: {s.get('pattern')} needs content.{k}")
        for k in set(content) - req - opt - {"not_claims"}:
            res["structure"].append(f"{s['id']}: content.{k} is not a {s.get('pattern')} slot")

    # sources and derivations
    for c in claims.values():
        vals = claim_values(c)
        if c["kind"] == "observed":
            src = c.get("source")
            if not src:
                res["sources"].append(f"{c['id']} is observed but names no source file and locator")
            else:
                text = intake.locate(d, src["file"], src["locator"])
                if text is None:
                    res["sources"].append(f"{c['id']}: {src['file']} has nothing at {src['locator']!r} (run `convey intake`?)")
                else:
                    found = source_numbers(text)
                    there = ", ".join(dict.fromkeys(f["text"] for f in found)) or "none"
                    for v, unit in [(float(n["value"]), n.get("unit", "")) for n in c.get("numbers", [])]:
                        if reads_as_year(v, unit, found):
                            res["sources"].append(f"{c['id']}: {v:g} reads as a year, and years are dates, never checked "
                                                  "as figures: leave it out of numbers, or if it's a count (\"2,000 "
                                                  "people\") give it its unit")
                        elif not any(matches(f, v, unit) for f in found):
                            res["sources"].append(f"{c['id']}: {v:g} is not in {src['file']} at {src['locator']} "
                                                  f"(figures there: {there})")
                    if src.get("quote") and " ".join(src["quote"].split()) not in " ".join(text.split()):
                        res["sources"].append(f"{c['id']}: the quote is not in {src['file']} at {src['locator']}")
        for i in c.get("inputs", []):
            if i not in claims:
                res["derived"].append(f"{c['id']} is computed from {i}, which is not in evidence.json")
        if c["kind"] == "derived" and c.get("numbers"):
            if not c.get("script"):
                res["derived"].append(f"{c['id']} is derived but has no script in analysis/: its arithmetic is unchecked")
                continue
            script = d / c["script"]
            if not script.exists():
                res["derived"].append(f"{c['id']}: {c['script']} does not exist")
                continue
            r = subprocess.run([sys.executable, "-I", str(script.resolve())], cwd=d.resolve(), capture_output=True, text=True, timeout=120)
            try:
                got = json.loads(r.stdout)[c["id"]]
            except (ValueError, KeyError, TypeError):
                res["derived"].append(f"{c['id']}: {c['script']} did not print {{\"{c['id']}\": [...]}} "
                                      f"(exit {r.returncode}{': ' + r.stderr.strip().splitlines()[-1] if r.stderr.strip() else ''})")
                continue
            got = [float(x["value"] if isinstance(x, dict) else x) for x in (got if isinstance(got, list) else [got])]
            for n in c["numbers"]:
                v = float(n["value"])
                tol = 0.5 * 10 ** -len(f"{v:g}".split(".")[1]) if "." in f"{v:g}" else 0.5
                if not any(abs(g - v) <= tol for g in got):
                    res["derived"].append(f"{c['id']}: the ledger says {v:g}, but {c['script']} now gives "
                                          f"{', '.join(f'{g:g}' for g in got)}")

    # numbers in the storyboard
    def trace(where: str, text: str, cited: set[str], exempt: list[str]):
        for ex in exempt:  # whole matches only: exempting "0" must not eat the 0 in "450" or "1.0"
            text = re.sub(r"(?<![0-9A-Za-z.,])" + re.escape(ex) + r"(?![0-9A-Za-z]|[.,][0-9])", " ", text)
        for f in numbers_in(text):
            if not any(matches(f, v, u) for cid in cited if cid in claims for v, u in claim_values(claims[cid])):
                res["numbers"].append(f"{where}: {f['text']!r} traces to no cited claim ({', '.join(sorted(cited)) or 'none cited'})")

    by_id = {s.get("id"): s for s in sb.get("slides", [])}
    for s in sb.get("slides", []):
        cited = set(s.get("claim_ids", []))
        exempt = [x["text"] if isinstance(x, dict) else x for x in (s.get("content") or {}).get("not_claims", [])]
        for t in [s.get("headline", ""), s.get("caveat", ""), s.get("notes", "")] + strings({k: v for k, v in (s.get("content") or {}).items()
                                                                             if k != "not_claims"}):
            trace(f"{s['id']} storyboard", t, cited, exempt)
        chart = (s.get("content") or {}).get("chart")
        if isinstance(chart, dict):
            for v in chart_values(chart):
                if not any(abs(abs(v) - abs(cv)) < 1e-9 for cid in cited if cid in claims for cv, _ in claim_values(claims[cid])):
                    res["numbers"].append(f"{s['id']} chart: the value {v:g} traces to no cited claim")

    # the slides themselves
    slides_dir = d / "slides"
    files = sorted(slides_dir.glob("*.html")) if slides_dir.exists() else []
    for f in files:
        p = read_slide(f)
        s = by_id.get(p.slide_id)
        if s is None:
            res["bindings"].append(f"{f.name}: no data-slide, or its id is not in storyboard.json")
            continue
        for cid in p.claims - set(claims):
            res["claims"].append(f"{f.name}: data-claims names {cid}, which is not in evidence.json")
        cited = set(s.get("claim_ids", [])) | p.claims
        exempt = [x["text"] if isinstance(x, dict) else x for x in (s.get("content") or {}).get("not_claims", [])]
        for t in p.texts():
            trace(f.name, t, cited, exempt)
        for bind, spec in p.charts:
            for v in chart_values(spec):
                if not any(abs(abs(v) - abs(cv)) < 1e-9 for cid in cited if cid in claims for cv, _ in claim_values(claims[cid])):
                    res["numbers"].append(f"{f.name} chart: the value {v:g} traces to no cited claim")
            if bind:
                want = field(s, bind)
                if not isinstance(want, dict) or chart_values(want) != chart_values(spec) or \
                        want.get("categories") != spec.get("categories"):
                    res["bindings"].append(f"{f.name}: the chart's data differs from storyboard {s['id']}.{bind}")
                elif want.get("type") and spec.get("type", "column") != want["type"]:
                    res["bindings"].append(f"{f.name}: the chart is drawn as {spec.get('type', 'column')}; storyboard "
                                           f"{s['id']}.{bind} says {want['type']}")
        for bind, got in p.binds:
            want = field(s, bind)
            if bind.endswith("chart"):
                continue
            if isinstance(want, list):
                ok = [" ".join(str(x).split()) for x in want] == got
            else:
                ok = want is not None and " ".join(str(want).split()) == got
            if not ok:
                res["bindings"].append(f"{f.name}: {bind} shows {got!r} but storyboard {s['id']} says {want!r}")

    # what the person reads
    chain = [f"{i}. {s.get('headline', '')}" for i, s in enumerate(sb.get("slides", []), 1)]
    gaps = [g for g in ev.get("gaps", []) if g.get("could_reverse")]
    if sb.get("approved"):
        a = sb["approved"]
        notes.append(f"story approved by {a.get('by', '?')} on {a.get('at', '?')}")
    elif (brief or {}).get("autonomy") == "just-build":
        notes.append("story not approved: the brief says just-build, so every choice must be logged in storyboard.choices")
    else:
        notes.append("story NOT approved yet: compose refuses until the person approves it")
    return {"results": res, "chain": chain, "gaps": gaps, "notes": notes, "slides": len(files),
            "not_supplied": ev.get("not_supplied", [])}


NOT_CHECKED = ("Not checked by code (judgment, for the agent's rubric and the person's review): whether a claim "
               "overstates cause, readiness or money; whether a chart's encoding is honest; design quality.")


def report(d: Path, verbose: bool = False) -> int:
    """Print the checks. Terse by default (Oct 18, 2026, the token diet): passing checks on one line, every problem in
    full, and the headline chain, gaps and not-supplied list only when they differ from what this project's last
    check printed (build/.check-seen); -v prints everything every time."""
    import hashlib
    r = run(d)
    bad = sum(bool(p) for p in r["results"].values())
    passed = [n for n, p in r["results"].items() if not p]
    if verbose:
        for name in r["results"]:
            print(f"{'FAIL' if r['results'][name] else 'PASS'}  {name}")
            for p in r["results"][name]:
                print(f"        {p}")
    else:
        if passed:
            print("PASS  " + ", ".join(passed))
        for name, probs in r["results"].items():
            if probs:
                print(f"FAIL  {name}")
                for p in probs:
                    print(f"        {p}")
    story = [f"\nHeadline chain ({len(r['chain'])} slides; read it alone, it should carry the argument):"] if r["chain"] else []
    story += [f"  {line}" for line in r["chain"]]
    if r["gaps"]:
        story += ["\nGaps that could reverse the conclusion:"] + [f"  {g['id']}: {g['text']}" for g in r["gaps"]]
    if r["not_supplied"]:
        story += ["\nNot supplied, so never on a slide: " + "; ".join(r["not_supplied"])]
    story += ["", NOT_CHECKED]
    digest = hashlib.sha256("\n".join(story).encode()).hexdigest()[:16]
    seen = d / "build" / ".check-seen"
    try:
        same = seen.read_text().strip() == digest
    except OSError:
        same = False
    if verbose or not same:
        print("\n".join(story))
        try:
            seen.parent.mkdir(parents=True, exist_ok=True)
            seen.write_text(digest + "\n")
        except OSError:
            pass
    else:
        print(f"headline chain, gaps and limits: unchanged since the last check ({len(r['chain'])} slides; -v prints them)")
    for n in r["notes"]:
        print(n)
    print(f"{'check FAILED' if bad else 'check passed'}: {bad} of {len(r['results'])} checks failed"
          f"{'' if r['slides'] else ' (no slides yet)'}")
    return 1 if bad else 0
