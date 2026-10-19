"""Fit where PowerPoint sets a line of text inside an exact line height, for one font.

With exact line spacing, PowerPoint puts each line a little lower in its line box than a browser
does. The gap depends on the font, its size and the line height:

    drop = k_lh * line_height + k_fs * font_size + c        (CSS px)

This draws a few calibration slides (21 sizes x 10 line heights), measures them in Chrome, exports
them with no correction, has PowerPoint save them as PDF, reads every line's baseline from both
PDFs (pdftext.py) and fits the three numbers by least squares. The emitter then raises text by
the predicted drop. Needs PowerPoint for Mac.
"""
from __future__ import annotations

import html
import tempfile
from pathlib import Path

from . import pdftext, powerpoint
from .skald.emit import Emitter
from .skald.lines import whole_pt
from .skald.measure import measure_page, slide_page

SIZES = [11, 12, 13, 14, 15, 16, 18, 20, 22, 24, 26, 28, 32, 36, 40, 44, 48, 56, 64, 80, 96]
# Dense around 1.0 to 1.3, where headlines live and where PowerPoint's placement bends most (Oct 18, 2026).
RATIOS = [0.9, 1.0, 1.05, 1.1, 1.125, 1.15, 1.2, 1.25, 1.3, 1.4, 1.5, 1.6, 1.75, 2.0]
# Display type for big-number and statement slides: 120 to 300 px, set tight (Oct 18, 2026).
BIG_SIZES = [120, 144, 180, 240, 300]
BIG_RATIOS = [0.9, 1.0, 1.1, 1.2]


def cards(family: str, weight: int, folder: Path) -> list[tuple[Path, list[dict]]]:
    """Write the calibration slides; return each file with the blocks on it. About 200 one-line
    boxes, each at a slightly different fractional position, so PowerPoint's coarse placement
    grid averages out instead of biasing the fit."""
    combos = [(fs, ratio) for fs in SIZES for ratio in RATIOS] + [(fs, ratio) for fs in BIG_SIZES for ratio in BIG_RATIOS]
    out, n, i = [], 0, 0
    while i < len(combos):
        n += 1
        blocks, rows, x, y, row_h = [], [], 24.0, 16.0, 0.0
        while i < len(combos):
            fs, ratio = combos[i]
            lh = whole_pt(fs * ratio)  # a line height PowerPoint draws as written (skald/lines.py)
            w = round(fs * 2.4) + 12
            if x + w > 1256:
                x, y, row_h = 24.0, y + row_h + 10, 0.0
            if y + lh > 704:
                break
            fx, fy = x + (i * 0.37) % 1, y + (i * 0.61) % 1  # spread over sub-pixel positions
            blocks.append({"x": fx, "y": fy, "fs": fs, "lh": lh, "w": w, "r": ratio})
            rows.append(f'<p class="abs" data-id="cal-{i}" style="left:{fx:.2f}px;top:{fy:.2f}px;width:{w}px;'
                        f'font-size:{fs}px;line-height:{lh}px">Hxg</p>')
            x += w + 8
            row_h = max(row_h, lh)
            i += 1
        f = folder / f"cal-{n}.html"
        f.write_text(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Calibration {n}</title><style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
.slide {{ position: relative; width: 1280px; height: 720px; overflow: hidden; background: #ffffff; color: #000000;
  font-family: "{html.escape(family)}"; font-weight: {weight}; font-kerning: none; }}
.abs {{ position: absolute; white-space: nowrap; }}
</style></head><body><section class="slide">
{chr(10).join(rows)}
</section></body></html>""")
        out.append((f, blocks))
    return out


def _first_baseline(runs, b, size_tol=0.1):
    """The baseline of the run that starts this block: its column, its size, inside its own line box
    (a baseline can't sit above the box's top or more than half a font size below its bottom)."""
    hits = [(x, y) for x, y, s in runs
            if b["x"] - 1 <= x <= b["x"] + b["w"] - 4 and b["y"] <= y <= b["y"] + b["lh"] + 0.5 * b["fs"]
            and abs(s - b["fs"]) <= max(size_tol * b["fs"], 0.5)]
    return min(hits)[1] if hits else None


def solve3(rows):
    """Least squares for y = a*u + b*v + c, rows of (u, v, y). Plain normal equations."""
    S = [[0.0] * 4 for _ in range(3)]
    for u, v, y in rows:
        x = (u, v, 1.0)
        for i in range(3):
            for j in range(3):
                S[i][j] += x[i] * x[j]
            S[i][3] += x[i] * y
    for i in range(3):  # Gauss-Jordan
        p = max(range(i, 3), key=lambda r: abs(S[r][i]))
        S[i], S[p] = S[p], S[i]
        for r in range(3):
            if r != i:
                f = S[r][i] / S[i][i]
                S[r] = [a - f * b for a, b in zip(S[r], S[i])]
    return [S[i][3] / S[i][i] for i in range(3)]


def calibrate(family: str, faces: dict, weight: int = 400, work: Path | None = None) -> dict:
    """{'lh', 'fs', 'c', 'samples', 'max_residual', 'note'} for one CSS font family."""
    if not powerpoint.available():
        raise RuntimeError("calibration needs PowerPoint for Mac; without it the font keeps no correction "
                           "and the brand sheet says verification is weaker")
    work = Path(work or tempfile.mkdtemp(prefix="convey-cal-"))
    work.mkdir(parents=True, exist_ok=True)
    slides = cards(family, weight, work)
    scenes, chrome_runs = [], []
    with slide_page() as page:
        for f, _ in slides:
            scenes.append(measure_page(page, f))
            pdf = work / f"{f.stem}-chrome.pdf"
            page.pdf(pdf)
            chrome_runs.append(pdftext.page_runs(pdf)[0])
    for sc in scenes:
        if sc.get("errors"):
            raise RuntimeError(f"calibration slide failed lint: {sc['errors'][:3]}")
    deck = work / "calibration.pptx"
    Emitter(faces={family: faces[family]} if family in faces else {}).deck(scenes).save(deck)
    ppt_pdf = powerpoint.render_pdf(deck, work / "calibration-powerpoint.pdf")
    ppt_runs = pdftext.page_runs(ppt_pdf)
    rows, missing, by_ratio = [], 0, {}
    for (f, blocks), cr, pr in zip(slides, chrome_runs, ppt_runs):
        for b in blocks:
            ya, yb = _first_baseline(cr, b), _first_baseline(pr, b)
            if ya is None or yb is None:
                missing += 1
                continue
            rows.append((b["lh"], b["fs"], yb - ya))
            by_ratio.setdefault(b["r"], []).append((b["fs"], yb - ya))
    if len(rows) < 12:
        raise RuntimeError(f"only {len(rows)} of {sum(len(b) for _, b in slides)} calibration lines were found in both PDFs")
    k_lh, k_fs, c = solve3(rows)
    # The measured table: one straight line in font size per line-height ratio. A single plane in (line height, size)
    # can't follow PowerPoint, whose placement bends with the ratio (48/54 px headlines: 2.8 px low on the plane).
    # Measured points, not a fitted line: at some ratios the drop swings between neighbouring sizes (ratio 1.2:
    # +1.9, -1.6, +2.4, -1.2 px at 36, 44, 48, 64 px; 144 px at 1.2 sits 8 px off its neighbours, and a slide at
    # exactly that size confirms it), and display sizes (to 300 px) bend away from any one line. Near 1.2 the exact
    # spacing crosses the font's own line height, where PowerPoint changes how it places the line. Every point is kept.
    table = []
    for r, pts in sorted(by_ratio.items()):
        sizes = sorted({p[0] for p in pts})
        mean = [(fs, sum(d for f, d in pts if f == fs) / sum(1 for f, _ in pts if f == fs)) for fs in sizes]
        table.append({"r": r, "pts": [[fs, round(d, 3)] for fs, d in mean]})
    from .skald.emit import predict_drop
    model = {"lh": k_lh, "fs": k_fs, "c": c, "table": table}
    res = [abs(predict_drop(model, u, v) - y) for u, v, y in rows]
    return {"lh": round(k_lh, 4), "fs": round(k_fs, 4), "c": round(c, 4), "table": table, "samples": len(rows),
            "missing": missing, "max_residual": round(max(res), 3),
            "typical_residual": round(sorted(res)[len(res) // 2], 3),
            "note": f"PowerPoint line position minus Chrome's, px; fit over {len(rows)} calibration lines "
                    f"(convey brand calibrate)"}


# ---------- width ----------

# Every size from 11 to 32 px (PowerPoint's rounding error jumps between neighbouring sizes), then the display steps.
WIDTH_SIZES = list(range(11, 33)) + [36, 40, 44, 48, 56, 64, 72, 80, 96, 120, 144]
SAMPLE = ("Most of the money goes to running what already exists, and 79% of a large budget, about $83 billion, "
          "never sees a build. Five ways to get software: buy, build, compose, extend or defer. ")


def width_cards(family: str, weight: int, folder: Path) -> list[tuple[Path, list[dict]]]:
    """One line of ordinary text per size, about 1,000 px long, each on its own row: no wrapping, no kerning."""
    out, n, i = [], 0, 0
    while i < len(WIDTH_SIZES):
        n += 1
        rows, blocks, y = [], [], 12.0
        while i < len(WIDTH_SIZES):
            fs = WIDTH_SIZES[i]
            lh = whole_pt(fs * 1.25)
            if y + lh > 708:
                break
            k = max(12, min(len(SAMPLE) * 2, int(1000 / (fs * 0.52))))
            text = (SAMPLE * 4)[:k].rstrip()
            x = 24 + (i * 0.37) % 1
            blocks.append({"fs": fs, "y": y, "lh": lh, "x": x, "text": text})
            rows.append(f'<p class="abs" data-id="w-{i}" style="left:{x:.2f}px;top:{y:.2f}px;width:1240px;'
                        f'font-size:{fs}px;line-height:{lh}px">{html.escape(text)}</p>')
            y += lh + 6
            i += 1
        f = folder / f"width-{n}.html"
        f.write_text(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Width {n}</title><style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
.slide {{ position: relative; width: 1280px; height: 720px; overflow: hidden; background: #ffffff; color: #000000;
  font-family: "{html.escape(family)}"; font-weight: {weight}; font-kerning: none; }}
.abs {{ position: absolute; white-space: nowrap; }}
</style></head><body><section class="slide">
{chr(10).join(rows)}
</section></body></html>""")
        out.append((f, blocks))
    return out


def _span(chars, b) -> tuple[float, int] | None:
    """Left edge of the line's last drawn character minus its first, and how many characters lie between them."""
    row = sorted((c for c in chars if b["y"] - 2 <= c[3] <= b["y"] + b["lh"] + 2 and c[1].strip()), key=lambda c: c[2])
    if len(row) < 8:
        return None
    first, last = row[0], row[-1]
    text = b["text"]
    a, z = text.find(first[1]), text.rfind(last[1])
    if a < 0 or z <= a:
        return None
    return last[2] - first[2], z - a


def advance(family: str, faces: dict, weight: int = 400, work: Path | None = None) -> dict:
    """{'advance': [[size, px per character], ...], ...}: what to add after each character so PowerPoint sets a line
    as wide as the browser does. Measured on lines of ordinary text, both drawn to PDF and read by pdftext."""
    if not powerpoint.available():
        raise RuntimeError("width calibration needs PowerPoint for Mac")
    work = Path(work or tempfile.mkdtemp(prefix="convey-width-"))
    work.mkdir(parents=True, exist_ok=True)
    slides = width_cards(family, weight, work)
    scenes, chrome = [], []
    with slide_page() as page:
        for f, _ in slides:
            scenes.append(measure_page(page, f))
            pdf = work / f"{f.stem}-chrome.pdf"
            page.pdf(pdf)
            chrome.append(pdftext.page_chars(pdf)[0])
    deck = work / "width.pptx"
    Emitter(faces={family: faces[family]} if family in faces else {}).deck(scenes).save(deck)
    ppt = pdftext.page_chars(powerpoint.render_pdf(deck, work / "width-powerpoint.pdf"))
    pts, missing = [], 0
    for (f, blocks), cc, pc in zip(slides, chrome, ppt):
        for b in blocks:
            sa, sb = _span(cc, b), _span(pc, b)
            if not sa or not sb or sa[1] != sb[1]:
                missing += 1
                continue
            pts.append([b["fs"], round((sa[0] - sb[0]) / sa[1], 4)])
    if len(pts) < len(WIDTH_SIZES) // 2:
        raise RuntimeError(f"only {len(pts)} of {len(WIDTH_SIZES)} width lines were found in both PDFs")
    return {"advance": pts, "advance_weight": weight, "advance_missing": missing,
            "advance_note": "px to add after each character so PowerPoint's line is as wide as the browser's, by size "
                            "(convey brand calibrate)"}


# ---------- chart labels ----------

CHART_SIZES = [12, 16, 20, 24]
CHART_WORDS = ["Kappa", "Lambda", "Sigma", "Omega", "Theta", "Delta", "Gamma", "Zeta"]


def chart_cards(family: str, weight: int, folder: Path) -> tuple[Path, list[dict]]:
    """One slide of small column charts, one per label size, so PowerPoint's own axis labels can be compared with the
    ones chart.js draws. chart.js places them from constants measured on one font; another font sits differently."""
    import json as _json
    import shutil as _shutil
    _shutil.copy(Path(__file__).parent / "skald" / "chart.js", folder / "chart.js")
    figs, blocks = [], []
    for i, fs in enumerate(CHART_SIZES):
        x, y = 24 + (i % 2) * 628, 24 + (i // 2) * 348
        cats = CHART_WORDS[2 * i: 2 * i + 2]
        spec = {"type": "column", "categories": cats, "series": [{"name": "A", "values": [40, 80], "color": "#888888"}],
                "axis": {"min": 0, "max": 100, "step": 50, "format": "{v}%"}, "fontSize": fs}
        figs.append(f"<figure data-id=\"cal-chart-{i}\" data-chart='{_json.dumps(spec)}' style=\"position:absolute;left:{x}px;"
                    f"top:{y}px;width:600px;height:320px;margin:0;color:#000000\"></figure>")
        blocks.append({"fs": fs, "x": x, "y": y, "w": 600, "h": 320, "cats": cats})
    f = folder / "chart-labels.html"
    f.write_text(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Chart labels</title><style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
.slide {{ position: relative; width: 1280px; height: 720px; overflow: hidden; background: #ffffff; color: #000000;
  font-family: "{html.escape(family)}"; font-weight: {weight}; font-kerning: none; }}
figure {{ font-family: "{html.escape(family)}"; font-weight: {weight}; --chart-grid: #cccccc; }}
</style></head><body><section class="slide">
{chr(10).join(figs)}
</section><script src="chart.js"></script></body></html>""")
    return f, blocks


def _word_top(chars, word: str, box: dict) -> float | None:
    """Mean glyph top of a word's characters inside one chart's box."""
    inside = sorted((c for c in chars if box["x"] <= c[2] <= box["x"] + box["w"] and box["y"] <= c[3] <= box["y"] + box["h"] + 40),
                    key=lambda c: (round(c[3]), c[2]))
    text = "".join(c[1] for c in inside)
    k = text.find(word)
    return sum(c[3] for c in inside[k:k + len(word)]) / len(word) if k >= 0 else None


def _top_value_end(chars, box: dict) -> float | None:
    """Right edge of the top value-axis label ("100%"): the topmost characters left of the plot's middle."""
    left = [c for c in chars if box["x"] <= c[2] <= box["x"] + box["w"] / 3 and box["y"] - 20 <= c[3] <= box["y"] + box["h"] / 3]
    if not left:
        return None
    top = min(c[3] for c in left)
    row = [c for c in left if abs(c[3] - top) < 2]
    last = max(row, key=lambda c: c[2])
    return last[2] + last[4]


def chart_labels(family: str, faces: dict, weight: int = 400, work: Path | None = None) -> dict:
    """{'chart': [[size, dy, dx], ...]}: how much lower (dy) PowerPoint sets a chart's bottom-axis labels, and how much
    further right (dx) it ends its left-axis labels, than chart.js does, by label size. Written into the brand's tokens
    as --brand-chart-labels; chart.js moves its labels by them."""
    if not powerpoint.available():
        raise RuntimeError("chart-label calibration needs PowerPoint for Mac")
    work = Path(work or tempfile.mkdtemp(prefix="convey-chart-"))
    work.mkdir(parents=True, exist_ok=True)
    f, blocks = chart_cards(family, weight, work)
    with slide_page() as page:
        scene = measure_page(page, f)
        pdf = work / "chart-labels-chrome.pdf"
        page.pdf(pdf)
    chrome = pdftext.page_chars(pdf)[0]
    deck = work / "chart-labels.pptx"
    Emitter(faces={family: faces[family]} if family in faces else {}).deck([scene]).save(deck)
    ppt = pdftext.page_chars(powerpoint.render_pdf(deck, work / "chart-labels-powerpoint.pdf"))[0]
    out = []
    for b in blocks:
        dys = [p - c for p, c in ((_word_top(ppt, w, b), _word_top(chrome, w, b)) for w in b["cats"]) if p is not None and c is not None]
        ce, pe = _top_value_end(chrome, b), _top_value_end(ppt, b)
        if dys and ce is not None and pe is not None:
            out.append([b["fs"], round(sum(dys) / len(dys), 2), round(pe - ce, 2)])
    if not out:
        raise RuntimeError("no chart labels were found in both PDFs")
    return {"chart": out, "chart_note": "PowerPoint's chart labels minus chart.js's, px: [size, bottom-axis dy, left-axis dx]"}
