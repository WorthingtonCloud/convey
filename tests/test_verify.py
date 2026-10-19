"""The export report grades honestly. Neutral, made-up slides only.

  report      `convey export` writes report.html + report.json, one verdict per slide
  powerpoint  where PowerPoint is installed, plain slides come back green or yellow, never "not tested"
  untested    with PowerPoint pretended away, every slide says "not tested", none says green
  missing     a word taken out of the .pptx is caught by the file check alone (red, the word named)
  nbsp        a no-break space reaches PowerPoint as one (it was turned into a plain space)
  pdftext     the standard-library PDF reader finds every word of the browser's PDF where the slide put it
  look        `convey look` writes one 1280 x 720 picture per slide and sheet.png; a second look lists only the
              pictures that changed
  grade       a spot is red, a 3 px shift is yellow, a clean slide is green

Run: python3 skill/tests/test_verify.py   (needs Chrome or Edge; PowerPoint is optional)
"""
from __future__ import annotations

import base64
import io
import json
import re
import sys
import tempfile
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from convey import cli, powerpoint, verify  # noqa: E402
from convey.pdftext import page_chars  # noqa: E402
from convey.skald.measure import measure_page, slide_page  # noqa: E402

HEAD = """<!doctype html><html><head><meta charset="utf-8"><title>{t}</title><style>
body{{margin:0}} .slide{{position:relative;width:1280px;height:720px;background:#fff;overflow:hidden;
font-family:Arial;font-kerning:none;color:#222}} .abs{{position:absolute;margin:0}}
</style></head><body><div class="slide">"""
SLIDES = {
    "01-plain.html": HEAD.format(t="Plain") + """
<h1 class="abs" style="left:64px;top:56px;width:1000px;font-size:44px;line-height:56px;font-weight:700">Quarterly garden&nbsp;plan</h1>
<p class="abs" style="left:64px;top:140px;width:700px;font-size:22px;line-height:32px">Three beds get tomatoes, two get beans,
and the shady corner stays for herbs.</p>
<div class="abs" style="left:64px;top:300px;width:320px;height:160px;background:#2f6f5e;border-radius:12px"></div>
<p class="abs" style="left:420px;top:330px;width:400px;font-size:15px;line-height:20px;letter-spacing:0.12em;
text-transform:uppercase;font-weight:700">Watering schedule</p>
</div></body></html>""",
    "02-list.html": HEAD.format(t="List") + """
<ul class="abs" style="left:64px;top:80px;width:800px;font-size:24px;line-height:36px;padding-left:28px;list-style-type:'•  '">
<li>Water early in the morning</li><li>Mulch after the first heat</li><li>Pick beans every second day</li></ul>
</div></body></html>""",
}
FAILS: list[str] = []


def ok(cond, what):
    print(("pass  " if cond else "FAIL  ") + what)
    if not cond:
        FAILS.append(what)


def drop_word(pptx: Path, word: str, out: Path):
    with zipfile.ZipFile(pptx) as z, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as w:
        for n in z.namelist():
            data = z.read(n)
            if re.match(r"ppt/slides/slide1\.xml$", n):
                data = data.replace(word.encode(), b"")
            w.writestr(n, data)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="convey-verify-test-"))
    slides = tmp / "slides"
    slides.mkdir()
    for name, html in SLIDES.items():
        (slides / name).write_text(html)
    deck = tmp / "build" / "deck.pptx"
    deck.parent.mkdir()

    # report
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(["export", str(slides), "-o", str(deck)])
    rep = json.loads((deck.parent / "report.json").read_text())
    ok(code == 0 and (deck.parent / "report.html").exists() and len(rep["slides"]) == 2, "report: written, one verdict per slide")
    ok("vs " in buf.getvalue(), "report: export prints the summary line")

    # powerpoint
    if powerpoint.available():
        verdicts = [s["verdict"] for s in rep["slides"]]
        ok(rep["tested"] and all(v in ("green", "yellow") for v in verdicts), f"powerpoint: plain slides graded {verdicts}")
        ok(all((deck.parent / "report" / f"{i:02d}-diff.png").exists() for i in (1, 2)), "powerpoint: pictures beside the report")
    else:
        print("skip  powerpoint: not installed here")

    # untested, and pdftext, from the browser's own PDFs
    scenes, pdfs = [], []
    with slide_page() as page:
        for i, f in enumerate(sorted(slides.glob("*.html"))):
            sc = measure_page(page, f)
            sc["allText"] = page.evaluate("document.querySelector('.slide').innerText")
            pdfs.append(tmp / f"b{i}.pdf")
            page.pdf(pdfs[-1])
            scenes.append(sc)
    real = powerpoint.available
    powerpoint.available = lambda: False
    try:
        r2 = verify.verify_export(scenes, pdfs, deck, tmp / "untested" / "report.html")
    finally:
        powerpoint.available = real
    ok(not r2["tested"] and all(s["verdict"] == "not tested" for s in r2["slides"]), "untested: every slide 'not tested'")
    ok(all("not tested" in " ".join(s["reasons"]) for s in r2["slides"]), "untested: the reason says so")
    ok("not tested" in (tmp / "untested" / "report.html").read_text(), "untested: the page says so")

    # missing
    broken = tmp / "broken.pptx"
    drop_word(deck, "tomatoes", broken)
    r3 = verify.compare(scenes, pdfs, broken, None)
    ok(r3[0]["verdict"] == "red" and "tomatoes," in r3[0]["text_missing"], "missing: a dropped word is red and named")
    ok(r3[1]["verdict"] == "not tested", "missing: the untouched slide stays 'not tested'")

    # nbsp
    runs = [r["text"] for e in scenes[0]["elements"] if e.get("text") for r in e["text"]["runs"]]
    ok(any("garden\u00a0plan" in t for t in runs), "nbsp: the scene keeps the no-break space")
    ok("garden\u00a0plan" in verify.pptx_text(deck)[0], "nbsp: the .pptx keeps it")

    # pdftext
    found, total, worst = 0, 0, 0.0
    for sc, pdf in zip(scenes, pdfs):
        pt = verify.PageText(page_chars(pdf)[0])
        for e in sc["elements"]:
            for w in (e.get("text") or {}).get("words", []):
                total += 1
                m = pt.find(w["t"], w)
                if m:
                    found += 1
                    worst = max(worst, abs(m["x"] - w["x"]))
    ok(total and found == total and worst < 1.5, f"pdftext: {found}/{total} words found, worst x {worst:.2f} px")

    # look
    import struct
    with redirect_stdout(io.StringIO()):
        cli.main(["look", str(slides), "-o", str(tmp / "look")])
    pics = sorted(p for p in (tmp / "look").glob("*.png") if p.name != "sheet.png")
    sizes = [struct.unpack(">II", p.read_bytes()[16:24]) for p in pics]
    ok(len(pics) == 2 and all(sz == (1280, 720) for sz in sizes), f"look: {len(pics)} pictures, {sizes}")
    ok((tmp / "look" / "sheet.png").exists(), "look: sheet.png holds every slide, small")
    (tmp / "look" / "99-renamed-slide.png").write_bytes(pics[0].read_bytes())  # a picture from an older look
    buf = io.StringIO()
    with redirect_stdout(buf):
        cli.main(["look", str(slides), "-o", str(tmp / "look")])
    ok(not (tmp / "look" / "99-renamed-slide.png").exists()
       and len([p for p in (tmp / "look").glob("*.png") if p.name != "sheet.png"]) == 2,
       "look: a second look replaces its own old pictures (none left from a renamed slide)")
    ok("0 changed" in buf.getvalue() and pics[0].name not in buf.getvalue(),
       f"look: an unchanged slide's picture isn't listed again ({buf.getvalue().splitlines()[0][:60]})")
    first = sorted(slides.glob("*.html"))[0]
    keep = first.read_text()
    first.write_text(keep.replace("</div></body>", '<div style="position:absolute;left:4px;top:4px;width:20px;'
                                                   'height:20px;background:#E5432F"></div></div></body>', 1))
    buf = io.StringIO()
    with redirect_stdout(buf):
        cli.main(["look", str(slides), "-o", str(tmp / "look")])
    first.write_text(keep)
    ok("1 changed" in buf.getvalue() and f"{first.stem}.png" in buf.getvalue(),
       "look: a changed slide's picture is listed to open")

    # grade
    base = {"text_missing": [], "compared": True, "words_unmatched": 0, "warnings": [], "line_mismatch": [],
            "font_bad": [], "size_bad": [], "max_text_shift": 0.5, "text_elements": [], "spots": [],
            "worst_elements": [], "diff_pct": 0.0}
    ok(verify.grade(base)[0] == "green", "grade: clean is green")
    ok(verify.grade({**base, "max_text_shift": 3.0, "text_elements": [{"id": "p-1", "max_shift": 3.0}]})[0] == "yellow",
       "grade: 3 px is yellow")
    ok(verify.grade({**base, "spots": [{"x": 1, "y": 1, "w": 8, "h": 8}]})[0] == "red", "grade: a spot is red")
    v, why = verify.grade({**base, "diff_pct": 0.07, "worst_elements": [{"id": "headline", "pct": 97.1}]})
    ok(v == "yellow" and "most of it in headline" in " ".join(why), f"grade: a pixel-only yellow names its element ({why})")

    # which element carries the difference: the smallest one over each changed pixel, else the background
    import zlib

    def png(w, h, dark):
        rows = b"".join(b"\0" + bytes(0 if dark(x, y) else 255 for x in range(w) for _ in range(3)) for y in range(h))
        chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
        raw = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + \
            chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")
        return "data:image/png;base64," + base64.b64encode(raw).decode()
    a = png(200, 100, lambda x, y: False)
    b = png(200, 100, lambda x, y: (145 <= x < 165 and 45 <= y < 65) or (5 <= x < 13 and 5 <= y < 13))
    from convey.skald.measure import slide_page as _page
    with _page() as br:
        br.goto("about:blank")
        br.evaluate(verify.PIXELDIFF_JS + "; true")
        px = br.evaluate(f"conveyPixelDiff({json.dumps(a)}, {json.dumps(b)}, " + json.dumps(
            {"scale": 1, "textBoxes": [], "elements": [{"id": "card", "x": 0, "y": 30, "w": 200, "h": 70},
                                                      {"id": "label", "x": 140, "y": 40, "w": 30, "h": 30}]}) + ")")
    ids = [w["id"] for w in px["worst_elements"]]
    ok(ids[:2] == ["label", "the template's background"],
       f"pixels: the change is the small label's, not the card under it; one outside every element is the background ({px['worst_elements']})")
    print(f"{len(FAILS)} failure(s)")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
