"""The export report: does PowerPoint draw each slide the way the browser does?

`convey export` calls this after writing the .pptx. Where PowerPoint is installed it saves the deck
as PDF; the browser's slide is printed to PDF too, and macOS's own PDF engine draws and reads both,
so smoothing is the same on each side; the text is read from the PDFs themselves (pdftext.py). Then,
per slide:

  1. Text survival: every word the browser shows is in the .pptx (read from the file itself; needs
     no PowerPoint, so it runs everywhere).
  2. Text placement: each word's position, the line breaks, the drawn size and the font, element by
     element, the browser's PDF against PowerPoint's.
  3. Pixels: a tolerant difference, and "spots", small clusters of difference outside text boxes
     (a missing bullet, a moved shape), which a whole-slide percentage would miss.

Grades: green, yellow or red, each with its cause; "blocked" when lint refused the slide; "not
tested" when PowerPoint isn't here. Never "passed" without a comparison. The thresholds are the ones
the test bench uses. Writes report.html (+ report.json and pictures in report/) beside the deck.
Standard library only; the pixel work runs in the installed Chrome (pixeldiff.js).
"""
from __future__ import annotations

import base64
import html
import json
import re
import shutil
import statistics
import tempfile
import time
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

from . import powerpoint
from .pdftext import page_chars
from .skald.measure import Browser

SCALE = 2  # both sides are drawn at 2560 x 1440
W, H = 1280, 720
PIXELDIFF_JS = (Path(__file__).parent / "pixeldiff.js").read_text()
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


# ---------- what the .pptx holds ----------

def pptx_slides(pptx) -> list[str]:
    """The slide parts in deck order."""
    with zipfile.ZipFile(pptx) as z:
        names = [n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)]
    return sorted(names, key=lambda n: int(re.findall(r"\d+", n)[0]))


def pptx_text(pptx) -> list[str]:
    """Per slide, its words as PowerPoint holds them: runs joined within a paragraph, paragraphs on
    their own lines (the way PowerPoint's own text frame reads)."""
    out = []
    with zipfile.ZipFile(pptx) as z:
        for n in pptx_slides(pptx):
            root = ET.fromstring(z.read(n))
            paras = []
            for p in root.iter(A + "p"):
                parts = []
                for node in p:
                    if node.tag == A + "r":
                        t = node.find(A + "t")
                        parts.append(t.text or "" if t is not None else "")
                    elif node.tag == A + "br":
                        parts.append(" ")
                    elif node.tag == A + "fld":
                        t = node.find(A + "t")
                        parts.append(t.text or "" if t is not None else "")
                paras.append("".join(parts))
            out.append("\n".join(paras))
    return out


def object_counts(pptx) -> list[dict]:
    """What each slide is made of, straight from the XML."""
    out = []
    with zipfile.ZipFile(pptx) as z:
        for n in pptx_slides(pptx):
            x = z.read(n).decode("utf-8")
            out.append({
                "shapes": len(re.findall(r"<p:sp>", x)),
                "text_boxes": len(re.findall(r"<p:sp>(?:(?!</p:sp>).)*?<a:t>", x, re.S)),
                "connectors": len(re.findall(r"<p:cxnSp>", x)),
                "groups": len(re.findall(r"<p:grpSp>", x)),
                "pictures": len(re.findall(r"<p:pic>", x)),
                "charts": len(re.findall(r"<c:chart\b", x)),  # not the namespace too: one chart counted 2 (Oct 18, 2026)
            })
    return out


def chart_text(scene) -> list[str]:
    """Labels PowerPoint draws from a native chart's data: categories and axis values."""
    out = []
    for e in scene["elements"]:
        if e["kind"] != "chart":
            continue
        sp = e["spec"]
        out += [str(c) for c in sp["categories"]]
        ax = sp.get("axis")
        if ax:
            v = ax["min"]
            while v <= ax["max"] + 1e-9:
                # PowerPoint's number format puts the minus before the whole format: "-$100K", never "$-100K".
                out.append(("-" if v < 0 else "") + ax.get("format", "{v}").replace("{v}", f"{abs(v):g}"))
                v += ax["step"]
    return out


# ---------- where words sit in a PDF ----------

class PageText:
    """One PDF page's drawn characters, searchable by word."""

    def __init__(self, chars):
        self.text, self.at = "", []  # lower-cased letters, and which character each came from
        self.chars = chars
        for i, c in enumerate(chars):
            for ch in unicodedata.normalize("NFKC", c[1]).lower():
                self.text += ch
                self.at.append(i)
        self.used = [False] * len(chars)

    def find(self, word: str, near: dict, cap: float = 200):
        """The unused run of characters spelling `word` closest to `near` (x, y top-left), as a box
        with its font; claims those characters. None if nothing within `cap` px."""
        key = unicodedata.normalize("NFKC", word).lower()
        if not key:
            return None
        best, bd, start = None, 1e9, self.text.find(key)
        while start >= 0:
            idx = sorted(set(self.at[start:start + len(key)]))
            if not any(self.used[i] for i in idx):
                cs = [self.chars[i] for i in idx]
                box = {"x": min(c[2] for c in cs), "y": min(c[3] for c in cs)}
                box["w"] = max(c[2] + c[4] for c in cs) - box["x"]
                box["h"] = max(c[3] + c[5] for c in cs) - box["y"]
                d = abs(box["x"] - near["x"]) + abs(box["y"] - near["y"])
                # A whole word (a break before and after) beats the same letters inside a longer word.
                pos = [self.at[start], self.at[start + len(key) - 1]]
                whole = ((pos[0] == 0 or self.chars[pos[0] - 1][0] != self.chars[pos[0]][0] - 1) and
                         (pos[1] == len(self.chars) - 1 or self.chars[pos[1] + 1][0] != self.chars[pos[1]][0] + 1))
                d += 0 if whole else 50
                if d < bd:
                    best, bd = (idx, box, Counter(c[6] for c in cs).most_common(1)[0][0]), d
            start = self.text.find(key, start + 1)
        if best is None or bd > cap:
            return None
        for i in best[0]:
            self.used[i] = True
        return {**best[1], "t": word, "font": best[2]}


def norm_font(name: str) -> str:
    name = name.split("+")[-1]
    name = re.sub(r"[-\s]", "", name)
    return re.sub(r"Regular$", "", name).lower()


def lines_of(words, tol=4):
    """A line number for each word, grouping by vertical position."""
    idx, last_y, n = [], None, -1
    for w in words:
        if last_y is None or abs(w["y"] - last_y) > tol:
            n += 1
            last_y = w["y"]
        idx.append(n)
    return idx


def _split_pair(w: dict, bpage: PageText, cpage: PageText):
    """A word the browser broke at a hyphen or dash ("go-" / "live."): find each piece in both PDFs, the first on the
    word's line and the rest on the next (`next`, from extract.js). Before Oct 18, 2026 the whole word was looked for
    and never found, so a correct break read as a word PowerPoint drew differently."""
    cuts = [i + 1 for i, ch in enumerate(w["t"][:-1]) if ch in "-\u2010\u2011\u2013\u2014"]
    for c in reversed(cuts):
        a, b = w["t"][:c], w["t"][c:]
        ra, rb = bpage.find(a, w), bpage.find(b, w["next"])
        ga = cpage.find(a, ra) if ra else None
        gb = cpage.find(b, rb) if rb else None
        if ra and rb and ga and gb:
            return [(ra, ga), (rb, gb)]
    return None


def compare_text(sc, bpage: PageText, cpage: PageText) -> dict:
    """Per text element: how far its words moved, whether its lines broke the same way, its drawn
    size and its font."""
    shifts, line_mismatch, font_bad, size_bad, unmeasured, per_el = [], [], [], [], [], []
    unmatched = 0
    for e in sc["elements"]:
        t = e.get("text")
        if not t or not t["words"]:
            continue
        # PowerPoint's PDF keeps no semi-transparent or turned text as text: the pixels still cover it.
        if (any(r.get("color") and r["color"]["a"] < 1 for r in t["runs"] if not r.get("br"))
                or e.get("opacity", 1) < 1 or e.get("rot")):
            unmeasured.append(e["id"])
            continue
        markers = [p["bullet"]["words"][0] for p in t.get("paras", [])
                   if p.get("bullet") and p["bullet"]["words"][0]["y"] is not None]
        pairs = []
        for w in markers + t["words"]:
            got2 = _split_pair(w, bpage, cpage) if w.get("next") else None  # broken at a hyphen or dash: two pieces
            if got2:
                pairs += got2
                continue
            ref = bpage.find(w["t"], w)
            got = cpage.find(w["t"], ref) if ref else None
            if ref is None or got is None:
                unmatched += 1
                continue
            pairs.append((ref, got))
        if not pairs:
            continue
        dx = [m["x"] - w["x"] for w, m in pairs]
        dy = [(m["y"] + m["h"] / 2) - (w["y"] + w["h"] / 2) for w, m in pairs]
        bl, cl = lines_of([w for w, _ in pairs]), lines_of([m for _, m in pairs])
        shift = max(max(map(abs, dx)), max(map(abs, dy)))
        shifts.append(shift)
        if bl != cl:
            line_mismatch.append(e["id"])
        ratios = [m["w"] / w["w"] for w, m in pairs if w["w"] > 24]
        ratio = statistics.median(ratios) if ratios else 1.0
        if abs(ratio - 1) > 0.02:
            size_bad.append(f'{e["id"]}: drawn {ratio * 100:.1f}% of the browser\'s width')
        runs = [r for r in t["runs"] if not r.get("br")]
        for _, m in pairs:
            if m["font"] and not norm_font(m["font"]).startswith(norm_font(runs[0]["font"])):
                font_bad.append(f'{e["id"]}: "{m["t"]}" in {m["font"]}, not {runs[0]["font"]}')
        per_el.append({"id": e["id"], "dx": round(statistics.mean(dx), 2), "dy": round(statistics.mean(dy), 2),
                       "max_shift": round(shift, 2), "lines_browser": max(bl) + 1, "lines_ppt": max(cl) + 1,
                       "lines_ok": bl == cl, "size_ratio": round(ratio, 4)})
    # Chart labels are drawn by PowerPoint from the chart's data: measure them by position.
    for e in sc["elements"]:
        if e["kind"] != "chart":
            continue
        pairs = []
        for w in _chart_words(bpage, e):
            m = cpage.find(w["t"], w)
            if m:
                pairs.append((w, m))
        if pairs:
            dx = [m["x"] - w["x"] for w, m in pairs]
            dy = [(m["y"] + m["h"] / 2) - (w["y"] + w["h"] / 2) for w, m in pairs]
            sh = max(max(map(abs, dx)), max(map(abs, dy)))
            shifts.append(sh)
            per_el.append({"id": e["id"] + " labels", "dx": round(statistics.mean(dx), 2),
                           "dy": round(statistics.mean(dy), 2), "max_shift": round(sh, 2),
                           "lines_browser": 1, "lines_ppt": 1, "lines_ok": True, "size_ratio": 1.0})
    return {"text_elements": per_el, "max_text_shift": round(max(shifts), 2) if shifts else 0,
            "line_mismatch": line_mismatch, "font_bad": font_bad[:10], "size_bad": size_bad[:10],
            "words_unmatched": unmatched, "text_unmeasured": unmeasured}


def _chart_words(page: PageText, e) -> list[dict]:
    """The browser PDF's unclaimed words inside a chart's area, split where the engine split them."""
    words, cur, last = [], None, None
    for i, c in enumerate(page.chars):
        if page.used[i] or not (e["x"] - 60 <= c[2] <= e["x"] + e["w"] and e["y"] <= c[3] <= e["y"] + e["h"] + 20):
            if cur:
                words.append(cur)
            cur, last = None, None
            continue
        gap = last is not None and (c[0] != last[0] + 1 or abs(c[3] - last[3]) > 2)
        if cur and gap:
            words.append(cur)
            cur = None
        if cur is None:
            cur = {"t": "", "x": c[2], "y": c[3], "x1": c[2] + c[4], "y1": c[3] + c[5]}
        cur["t"] += c[1]
        cur["x"], cur["y"] = min(cur["x"], c[2]), min(cur["y"], c[3])
        cur["x1"], cur["y1"] = max(cur["x1"], c[2] + c[4]), max(cur["y1"], c[3] + c[5])
        last = c
    if cur:
        words.append(cur)
    out = []
    for w in words:
        m = page.find(w["t"], w, cap=2)
        if m:
            out.append(m)
    return out


# ---------- grading ----------

def grade(res: dict) -> tuple[str, list[str]]:
    """The bench's thresholds, with each cause in plain words."""
    reasons = []
    if res["text_missing"]:
        reasons.append(("red", f'{len(res["text_missing"])} word(s) missing from the PowerPoint file: '
                               + ", ".join(res["text_missing"][:8])))
    if not res.get("compared"):
        level = "red" if reasons else "not tested"
        if res.get("errors"):
            return "blocked", [f"lint refused: {x}" for x in res["errors"][:6]] + [r[1] for r in reasons]
        return level, [r[1] for r in reasons] + [res["not_tested"]]
    if res["words_unmatched"]:
        reasons.append(("red", f'{res["words_unmatched"]} word(s) PowerPoint drew differently (split, moved far, or missing)'))
    if any("overflows" in w for w in res["warnings"]):
        reasons.append(("red", "text overflows its box in the HTML"))
    if res["line_mismatch"]:
        reasons.append(("red", f'lines break differently in {", ".join(res["line_mismatch"])}'))
    if res["font_bad"]:
        reasons.append(("red", "PowerPoint used another font: " + res["font_bad"][0]))
    if res["size_bad"]:
        reasons.append(("red", "text drawn at another size: " + res["size_bad"][0]))
    sh = res["max_text_shift"]
    where = max(res["text_elements"], key=lambda e: e["max_shift"])["id"] if res["text_elements"] else ""
    if sh > 4:
        reasons.append(("red", f"text sits up to {sh} px off ({where})"))
    elif sh > 2:
        reasons.append(("yellow", f"text sits up to {sh} px off ({where})"))
    most = ", ".join(f'{w["id"]} {w["pct"]:g}%' for w in res.get("worst_elements", [])[:3])
    most = f" (most of it in {most})" if most else ""
    if res["spots"]:
        reasons.append(("red", f'{len(res["spots"])} spot(s) look different, outlined on the difference map{most}'))
    if res["diff_pct"] > 0.5:
        reasons.append(("red", f'{res["diff_pct"]}% of the slide\'s pixels differ{most}'))
    elif res["diff_pct"] > 0.05:
        reasons.append(("yellow", f'{res["diff_pct"]}% of the slide\'s pixels differ{most}'))
    if res["warnings"]:
        reasons.append(("yellow", f'{len(res["warnings"])} conversion note(s): ' + res["warnings"][0]))
    level = "red" if any(r[0] == "red" for r in reasons) else "yellow" if reasons else "green"
    if res.get("errors"):
        return "blocked", [f"lint refused: {x}" for x in res["errors"][:6]] + [r[1] for r in reasons]
    return level, [r[1] for r in reasons]


# ---------- the whole check ----------

def compare(scenes, browser_pdfs, pptx, ppt_pdf=None, work=None, pictures=None, why: str = "") -> list[dict]:
    """Grade every slide. `browser_pdfs`: one PDF per slide from the browser. `ppt_pdf`: PowerPoint's
    PDF of the deck, or None when PowerPoint isn't here or failed (`why`; then only text survival runs).
    `pictures`: a folder for the B/C/D pictures of each slide."""
    text = pptx_text(pptx)
    counts = object_counts(pptx)
    results = []
    for i, sc in enumerate(scenes):
        want = Counter(re.findall(r"\S+", sc.get("allText", "").lower()))
        got = Counter(re.findall(r"\S+", " ".join([text[i] if i < len(text) else ""] + chart_text(sc)).lower()))
        results.append({"id": sc["card"], "warnings": sc.get("warnings", []), "errors": sc.get("errors", []),
                        "text_words": sum(want.values()), "text_missing": sorted((want - got).elements()),
                        "objects": counts[i] if i < len(counts) else {}, "compared": False})
    if ppt_pdf is None:
        for r in results:
            r["not_tested"] = (f"not tested in PowerPoint: {why or 'it is not installed here'}, so nothing was drawn and "
                               "compared (the word check read the file itself)")
            r["verdict"], r["reasons"] = grade(r)
        return results

    work = Path(work or tempfile.mkdtemp(prefix="convey-verify-"))
    pictures = Path(pictures) if pictures else work
    pictures.mkdir(parents=True, exist_ok=True)
    cpages = page_chars(ppt_pdf, W)
    cpngs = powerpoint.pdf_to_png(ppt_pdf, work / "ppt", W * SCALE)
    if len(cpngs) != len(scenes):
        raise RuntimeError(f"PowerPoint drew {len(cpngs)} pages for {len(scenes)} slides")
    br = Browser()
    try:
        br.goto("about:blank")
        br.evaluate(PIXELDIFF_JS + "; true")
        for i, (sc, r) in enumerate(zip(scenes, results)):
            bpdf = Path(browser_pdfs[i])
            bpng = powerpoint.pdf_to_png(bpdf, work / f"b{i + 1}", W * SCALE)[0]
            r.update(compare_text(sc, PageText(page_chars(bpdf, W)[0]), PageText(cpages[i])))
            text_boxes = [(e["x"] - 4, e["y"] - 4, e["x"] + e["w"] + 4, e["y"] + e["h"] + 4)
                          for e in sc["elements"] if e.get("text") and e["text"]["words"]]
            elements = [{"id": e["id"], "x": e["x"], "y": e["y"], "w": e["w"], "h": e["h"]}
                        for e in sc["elements"] if e["kind"] != "group" and "x" in e]
            url = lambda p: "data:image/png;base64," + base64.b64encode(Path(p).read_bytes()).decode()
            px = br.evaluate(f"conveyPixelDiff({json.dumps(url(bpng))}, {json.dumps(url(cpngs[i]))}, "
                             f"{json.dumps({'scale': SCALE, 'textBoxes': text_boxes, 'elements': elements})})")
            stem = f"{i + 1:02d}"
            (pictures / f"{stem}-diff.png").write_bytes(base64.b64decode(px.pop("map").split(",", 1)[1]))
            shutil.copy(bpng, pictures / f"{stem}-browser.png")
            shutil.copy(cpngs[i], pictures / f"{stem}-powerpoint.png")
            r.update({k: v for k, v in px.items() if k != "size"})
            r["compared"] = True
            r["verdict"], r["reasons"] = grade(r)
    finally:
        br.close()
    return results


def verify_export(scenes, browser_pdfs, pptx, out_html, files=None, keep_pdf=None) -> dict:
    """Render the deck in PowerPoint when it's installed, grade every slide, write the report. `keep_pdf`: also keep
    PowerPoint's own PDF of the deck there (the PDF the person hands out is the one the report graded)."""
    out_html = Path(out_html)
    out_html.parent.mkdir(parents=True, exist_ok=True)
    pictures = out_html.with_suffix("")  # report.html -> report/
    if pictures.exists():
        shutil.rmtree(pictures)
    work = Path(tempfile.mkdtemp(prefix="convey-verify-"))
    ppt_pdf, why, version = None, "", ""
    try:
        if powerpoint.available():
            try:
                ppt_pdf = powerpoint.render_pdf(pptx, work / "powerpoint.pdf")
                version = powerpoint.version()
                if keep_pdf:
                    shutil.copy(ppt_pdf, keep_pdf)
            except RuntimeError as e:
                why = "PowerPoint could not draw the deck (" + str(e).splitlines()[0] + ")"
        results = compare(scenes, browser_pdfs, pptx, ppt_pdf, work, pictures, why)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    report = {"deck": str(pptx), "made": time.strftime("%Y-%m-%d %H:%M"), "powerpoint": version,
              "tested": ppt_pdf is not None, "slides": results,
              "files": [str(f) for f in files] if files else None}
    out_html.with_suffix(".json").write_text(json.dumps(report, indent=1))
    out_html.write_text(render_html(report, pictures.name))
    return report


def summary(report) -> str:
    c = Counter(r["verdict"] for r in report["slides"])
    order = ["green", "yellow", "red", "blocked", "not tested"]
    parts = [f"{c[k]} {k}" for k in order if c[k]]
    where = f"PowerPoint {report['powerpoint']}" if report["tested"] else "no PowerPoint (not tested)"
    return f"{len(report['slides'])} slides vs {where}: " + ", ".join(parts)


# ---------- the page ----------

COLORS = {"green": "#2f9e5b", "yellow": "#c9a227", "red": "#d64545", "blocked": "#7a7a8c", "not tested": "#7a7a8c"}


def render_html(report, pics: str) -> str:
    e = html.escape
    cards = []
    for i, r in enumerate(report["slides"]):
        stem = f"{i + 1:02d}"
        reasons = "".join(f"<li>{e(x)}</li>" for x in r["reasons"]) or "<li>Drawn the same in both.</li>"
        o = r.get("objects", {})
        native = (f'{o.get("text_boxes", 0)} text boxes, {o.get("shapes", 0)} shapes, {o.get("connectors", 0)} connectors, '
                  f'{o.get("charts", 0)} charts, {o.get("pictures", 0)} pictures') if o else ""
        meas = ""
        if r.get("compared"):
            meas = (f'<p class="m">Text: worst {r["max_text_shift"]} px off; {r["text_words"]} words, '
                    f'{len(r["text_missing"])} missing. Pixels: {r["diff_pct"]}% differ, {len(r["spots"])} spot(s).</p>')
            imgs = "".join(f'<figure><img loading="lazy" src="{e(pics)}/{stem}-{k}.png" alt="{k}">'
                           f"<figcaption>{label}</figcaption></figure>"
                           for k, label in (("browser", "Browser"), ("powerpoint", "PowerPoint"),
                                            ("diff", "Difference (red; spots outlined)")))
        else:
            imgs = ""
        cards.append(f'''<section class="card"><header><span class="chip" style="background:{COLORS.get(r["verdict"], "#777")}">
{e(r["verdict"])}</span><h2>{stem} · {e(r["id"])}</h2></header><ul>{reasons}</ul>{meas}
<p class="m">In the file: {e(native)}</p><div class="imgs">{imgs}</div></section>''')
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Export report</title><style>
:root{{--bg:#111318;--fg:#e9e9ee;--mut:#9a9aa8;--card:#1a1d24;--line:#2a2e38}}
@media (prefers-color-scheme: light){{:root{{--bg:#f6f6f8;--fg:#16161a;--mut:#5c5c68;--card:#fff;--line:#dcdce4}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,system-ui,sans-serif}}
main{{max-width:1180px;margin:0 auto;padding:24px 16px 64px}} h1{{font-size:24px;margin:0 0 4px}}
.lead{{color:var(--mut);margin:0 0 20px}} .card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin:0 0 16px}}
header{{display:flex;gap:12px;align-items:center}} h2{{font-size:17px;margin:0}}
.chip{{color:#fff;font-weight:600;font-size:13px;padding:2px 10px;border-radius:99px;text-transform:uppercase;letter-spacing:.04em}}
ul{{margin:10px 0 6px;padding-left:20px}} .m{{color:var(--mut);margin:4px 0;font-size:13px}}
.imgs{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px;margin-top:10px}}
figure{{margin:0}} img{{width:100%;display:block;border:1px solid var(--line);border-radius:4px}} figcaption{{color:var(--mut);font-size:12px;margin-top:4px}}
</style></head><body><main><h1>Export report</h1>
<p class="lead">{e(summary(report))}. Made {e(report["made"])}. This checks that PowerPoint draws what the browser drew
(words, placement, fonts, sizes, pixels). It does not judge whether a claim is fair or the design is good: that is
<code>convey check</code> plus the review. Green: the same within the bench's tolerances. Yellow: a small difference
worth a look. Red: a visible difference, named. "Not tested" is never "passed".</p>
{"".join(cards)}</main></body></html>"""
