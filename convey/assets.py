"""The picture vocabulary: concept icons and diagram parts an agent drops into a slide.

    convey assets find growth                     which icons stand for a word
    convey assets show growth --size 64 --id g1   an icon as inline SVG, ready to paste
    convey assets part step n=2 left=100 top=200  a diagram part as slide HTML
    convey assets gallery -o gallery.html         every icon and part [--brand N for its colors]

Every icon and part is drawn for this skill (never copied or traced from an icon library) and uses
only the rulebook's primitives, so it exports as native, editable PowerPoint shapes. Color comes
from `currentColor` (set `color` on the icon or a parent) or var(--brand-*), so it follows any brand.
Icons are drawn for 32 px and up; lint refuses a smaller one.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent / "assets"
MIN_SIZE = 32


def catalog() -> dict:
    return json.loads((HERE / "catalog.json").read_text())


def find(word: str) -> list[dict]:
    """Icons whose id or concepts match the word (exact concept first, then partial)."""
    w = word.strip().lower()
    icons = catalog()["icons"]
    exact = [i for i in icons if w == i["id"] or w in i["concepts"]]
    part = [i for i in icons if i not in exact and (w in i["id"] or any(w in c for c in i["concepts"]))]
    return exact + part


def _f(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".")


def _e(s) -> str:
    return html.escape(str(s))


def svg(icon_id: str, size: float = 64, data_id: str | None = None, cls: str | None = None,
        style: str | None = None) -> str:
    """The icon as inline SVG, sized and named. Its `data-id` names it as one group in PowerPoint."""
    entry = next((i for i in catalog()["icons"] if i["id"] == icon_id), None)
    if entry is None:
        raise KeyError(f"no icon {icon_id!r} (try `convey assets find`)")
    if size < MIN_SIZE:
        raise ValueError(f"icons are drawn for {MIN_SIZE}px and up, not {size:g}px")
    text = (HERE / entry["file"]).read_text().strip()
    attrs = f'width="{size:g}" height="{size:g}" data-icon="{_e(icon_id)}" data-id="{_e(data_id or "icon-" + icon_id)}"'
    if cls:
        attrs += f' class="{_e(cls)}"'
    if style:
        attrs += f' style="{_e(style)}"'
    text = text.replace(' xmlns="http://www.w3.org/2000/svg"', "", 1)
    return text.replace("<svg ", f"<svg {attrs} ", 1)


# ---------- diagram parts ----------
# Each returns absolutely positioned slide HTML (the slide's `.abs { position: absolute }` class).
# Lines take `color` (any CSS color; default the brand's muted ink) and `width` in px.

def _head(mid: str, width: float) -> tuple[str, float]:
    """An arrowhead in PowerPoint's medium size: 3 x the line width, counting no less than 2.667 px."""
    n = 3 * max(width, 8 / 3)
    return (f'<defs><marker id="{mid}" markerUnits="userSpaceOnUse" markerWidth="{_f(n)}" markerHeight="{_f(n)}" '
            f'viewBox="0 0 {_f(n)} {_f(n)}" refX="{_f(n)}" refY="{_f(n / 2)}" orient="auto-start-reverse">'
            f'<path d="M0 0 L{_f(n)} {_f(n / 2)} L0 {_f(n)} z" fill="currentColor"/></marker></defs>'), n


def _line_svg(data_id: str, shape: str, xs: list[float], ys: list[float], color: str, width: float,
              head: bool, both: bool) -> str:
    pad = 12
    x0, y0 = min(xs) - pad, min(ys) - pad
    w, h = max(xs) - x0 + pad, max(ys) - y0 + pad
    mid = f"head-{data_id}"
    defs, _ = _head(mid, width) if head else ("", 0)
    marks = (f' marker-end="url(#{mid})"' if head else "") + (f' marker-start="url(#{mid})"' if head and both else "")
    shape = shape.replace("/>", f' stroke="currentColor" stroke-width="{_f(width)}" fill="none" stroke-linecap="butt" '
                                f'stroke-linejoin="round"{marks}/>', 1)
    if not head:
        shape = shape.replace('stroke-linecap="butt"', 'stroke-linecap="round"', 1)
    return (f'<svg class="abs" data-id="{_e(data_id)}" style="left:{_f(x0)}px;top:{_f(y0)}px;color:{color};overflow:visible" '
            f'width="{_f(w)}" height="{_f(h)}" viewBox="{_f(x0)} {_f(y0)} {_f(w)} {_f(h)}">{defs}{shape}</svg>')


def arrow(x1: float, y1: float, x2: float, y2: float, color: str = "var(--brand-muted)", width: float = 2,
          head: bool = True, both: bool = False, from_id: str | None = None, to_id: str | None = None,
          data_id: str = "arrow") -> str:
    """A straight arrow in slide px. With from_id/to_id it becomes a connector glued to those boxes."""
    glue = (f' data-from="{_e(from_id)}"' if from_id else "") + (f' data-to="{_e(to_id)}"' if to_id else "")
    shape = f'<line data-id="{_e(data_id)}-line"{glue} x1="{_f(x1)}" y1="{_f(y1)}" x2="{_f(x2)}" y2="{_f(y2)}"/>'
    return _line_svg(data_id, shape, [x1, x2], [y1, y2], color, width, head, both)


def elbow(points, color: str = "var(--brand-muted)", width: float = 2, head: bool = True,
          data_id: str = "elbow") -> str:
    """A right-angled connector through the points [x1, y1, x2, y2, ...], arrowhead at the end."""
    pts = [float(v) for v in points]
    xs, ys = pts[0::2], pts[1::2]
    d = "M" + " L".join(f"{_f(x)} {_f(y)}" for x, y in zip(xs, ys))
    return _line_svg(data_id, f'<path data-id="{_e(data_id)}-line" d="{d}"/>', xs, ys, color, width, head, False)


def curve(x1: float, y1: float, x2: float, y2: float, bend: float = 0.3, color: str = "var(--brand-muted)",
          width: float = 2, head: bool = True, data_id: str = "curve") -> str:
    """A curved arrow; `bend` pushes the middle sideways by that share of the length (negative bends the other way)."""
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    dx, dy = x2 - x1, y2 - y1
    cx, cy = mx - dy * bend, my + dx * bend
    d = f"M{_f(x1)} {_f(y1)} Q{_f(cx)} {_f(cy)} {_f(x2)} {_f(y2)}"
    return _line_svg(data_id, f'<path data-id="{_e(data_id)}-line" d="{d}"/>', [x1, x2, cx], [y1, y2, cy],
                     color, width, head, False)


def _turn(pts, side: str, left: float, top: float, length: float, depth: float):
    """Points drawn for a brace opening right ('left' side), turned to face `side`."""
    out = []
    for x, y in pts:
        if side == "left":
            px, py = x, y
        elif side == "right":
            px, py = depth - x, y
        elif side == "top":
            px, py = y, x
        else:  # bottom
            px, py = y, depth - x
        out.append((left + px, top + py))
    return out


def brace(left: float, top: float, length: float, side: str = "left", depth: float = 20,
          color: str = "var(--brand-muted)", width: float = 2, data_id: str = "brace") -> str:
    """A curly brace grouping items. side=left draws '{' (opens right); right, top and bottom likewise.
    (left, top) is the brace's own corner; length runs down (left/right) or across (top/bottom)."""
    q = min(depth / 2, length / 4)
    m = depth / 2
    L = length
    raw = [(depth, 0), (m, 0), (m, q), (m, L / 2 - q), (m, L / 2), (0, L / 2), (m, L / 2), (m, L / 2 + q),
           (m, L - q), (m, L), (depth, L)]
    p = _turn(raw, side, left, top, L, depth)
    d = (f"M{_f(p[0][0])} {_f(p[0][1])} Q{_f(p[1][0])} {_f(p[1][1])} {_f(p[2][0])} {_f(p[2][1])} "
         f"L{_f(p[3][0])} {_f(p[3][1])} Q{_f(p[4][0])} {_f(p[4][1])} {_f(p[5][0])} {_f(p[5][1])} "
         f"Q{_f(p[6][0])} {_f(p[6][1])} {_f(p[7][0])} {_f(p[7][1])} L{_f(p[8][0])} {_f(p[8][1])} "
         f"Q{_f(p[9][0])} {_f(p[9][1])} {_f(p[10][0])} {_f(p[10][1])}")
    xs, ys = [x for x, _ in p], [y for _, y in p]
    return _line_svg(data_id, f'<path data-id="{_e(data_id)}-line" d="{d}"/>', xs, ys, color, width, False, False)


def bracket(left: float, top: float, length: float, side: str = "left", depth: float = 12,
            color: str = "var(--brand-muted)", width: float = 2, data_id: str = "bracket") -> str:
    """A square bracket: '[' for side=left (opens right); right, top and bottom likewise."""
    p = _turn([(depth, 0), (0, 0), (0, length), (depth, length)], side, left, top, length, depth)
    d = "M" + " L".join(f"{_f(x)} {_f(y)}" for x, y in p)
    xs, ys = [x for x, _ in p], [y for _, y in p]
    return _line_svg(data_id, f'<path data-id="{_e(data_id)}-line" d="{d}"/>', xs, ys, color, width, False, False)


def step(n, left: float, top: float, size: float = 48, filled: bool = True, color: str = "var(--brand-ink)",
         data_id: str | None = None) -> str:
    """A numbered step marker: a disc with its number (any short label) centered in it."""
    fs = round(size * 0.46)
    face = (f"background:{color};color:var(--brand-ground)" if filled
            else f"border:2px solid {color};color:{color}")
    return (f'<div class="abs" data-id="{_e(data_id or f"step-{n}")}" style="left:{_f(left)}px;top:{_f(top)}px;'
            f'width:{_f(size)}px;height:{_f(size)}px;border-radius:50%;{face};display:flex;align-items:center;'
            f'justify-content:center;font-family:var(--brand-font-heading);font-weight:var(--brand-weight-heading);'
            f'font-size:{fs}px;line-height:{fs + 4}px">{_e(n)}</div>')


def callout(text: str, left: float, top: float, width: float = 320, height: float = 96, side: str = "bottom",
            at: float = 0.2, fill: str = "var(--brand-raised)", ink: str = "var(--brand-ink)",
            data_id: str = "callout") -> str:
    """A note box with a pointer. `side` is the edge the pointer leaves from; `at` is where along that
    edge (0 to 1). Text sits inside the box; lint refuses text that doesn't fit."""
    t = 16  # pointer depth and half-width
    w, h = width, height
    if side in ("bottom", "top"):
        x = w * at
        x = min(max(x, t + 8), w - t - 8)
        tri = ([(x - t, h - 1), (x + t, h - 1), (x, h + t)] if side == "bottom"
               else [(x - t, 1), (x + t, 1), (x, -t)])
    else:
        y = h * at
        y = min(max(y, t + 8), h - t - 8)
        tri = ([(w - 1, y - t), (w - 1, y + t), (w + t, y)] if side == "right"
               else [(1, y - t), (1, y + t), (-t, y)])
    pts = " ".join(f"{_f(px)},{_f(py)}" for px, py in tri)
    return (f'<div data-group data-id="{_e(data_id)}" class="abs" style="left:{_f(left)}px;top:{_f(top)}px;width:{_f(w)}px;height:{_f(h)}px">\n'
            f'  <svg class="abs" data-id="{_e(data_id)}-pointer" style="left:0;top:0;overflow:visible" width="{_f(w)}" height="{_f(h)}">'
            f'<polygon points="{pts}" fill="{fill}"/></svg>\n'
            f'  <div class="abs" data-id="{_e(data_id)}-box" style="left:0;top:0;width:{_f(w)}px;height:{_f(h)}px;background:{fill};'
            f'border-radius:6px;padding:16px 20px;color:{ink};font-size:var(--brand-text-size);line-height:var(--brand-text-line)">'
            f'{_e(text)}</div>\n</div>')


def chevrons(labels, left: float, top: float, width: float = 1152, height: float = 72, gap: float = 6,
             fill: str = "var(--brand-raised)", ink: str = "var(--brand-ink)", data_id: str = "process") -> str:
    """A row of process steps as chevrons, one per label, filling `width`."""
    labels = [str(x) for x in (labels.split("|") if isinstance(labels, str) else labels)]
    n = len(labels)
    tip = height / 3
    each = (width - gap * (n - 1) + tip * (n - 1)) / n
    out = [f'<div data-group data-id="{_e(data_id)}" class="abs" style="left:{_f(left)}px;top:{_f(top)}px;'
           f'width:{_f(width)}px;height:{_f(height)}px">']
    for i, lab in enumerate(labels):
        x0 = i * (each + gap - tip)
        notch = tip if i else 0
        end = tip if i < n - 1 else 0
        pts = [(x0, 0), (x0 + each - end, 0), (x0 + each, height / 2), (x0 + each - end, height),
               (x0, height), (x0 + notch, height / 2)]
        poly = " ".join(f"{_f(x)},{_f(y)}" for x, y in pts)
        out.append(f'  <svg class="abs" data-id="{_e(data_id)}-{i + 1}" style="left:0;top:0;overflow:visible" '
                   f'width="{_f(width)}" height="{_f(height)}"><polygon points="{poly}" fill="{fill}"/></svg>')
        tl, tr = x0 + notch + 12, x0 + each - end - 4
        out.append(f'  <div class="abs" data-id="{_e(data_id)}-{i + 1}-label" style="left:{_f(tl)}px;top:0;'
                   f'width:{_f(tr - tl)}px;height:{_f(height)}px;display:flex;align-items:center;justify-content:center;'
                   f'text-align:center;color:{ink};font-family:var(--brand-font-heading);font-weight:var(--brand-weight-heading);'
                   f'font-size:var(--brand-text-size);line-height:var(--brand-text-line)">{_e(lab)}</div>')
    return "\n".join(out) + "\n</div>"


PARTS = {"arrow": arrow, "elbow": elbow, "curve": curve, "brace": brace, "bracket": bracket, "step": step,
         "callout": callout, "chevrons": chevrons}


def part(name: str, **kw) -> str:
    if name not in PARTS:
        raise KeyError(f"no part {name!r}; parts: {', '.join(PARTS)}")
    return PARTS[name](**kw)


# ---------- gallery ----------

NEUTRAL = """:root { --brand-ground: #ffffff; --brand-raised: #eeeeee; --brand-ink: #1a1a1a; --brand-body: #333333;
  --brand-muted: #6b6b6b; --brand-rule: #d0d0d0; --brand-font-body: system-ui; --brand-font-heading: system-ui;
  --brand-weight-heading: 600; --brand-text-size: 18px; --brand-text-line: 26px; }"""

PART_DEMOS = [
    ("arrow", "Straight arrow; glue it to two boxes with from_id / to_id",
     lambda: arrow(20, 60, 300, 60, data_id="g-arrow")),
    ("elbow", "Right-angled connector through a list of points",
     lambda: elbow([20, 30, 160, 30, 160, 100, 300, 100], data_id="g-elbow")),
    ("curve", "Curved arrow; bend sets how far the middle swings",
     lambda: curve(20, 100, 300, 40, 0.25, data_id="g-curve")),
    ("brace", "Curly brace grouping items (left, right, top, bottom)",
     lambda: brace(40, 16, 110, "left", data_id="g-brace-l") + brace(260, 16, 110, "right", data_id="g-brace-r")),
    ("bracket", "Square bracket (left, right, top, bottom)",
     lambda: bracket(40, 16, 110, "left", data_id="g-bracket-l") + bracket(260, 16, 110, "right", data_id="g-bracket-r")),
    ("step", "Numbered step, filled or outlined",
     lambda: step(1, 30, 40, 56) + step(2, 120, 40, 56, filled=False) + step(3, 210, 40, 56)),
    ("callout", "Note box with a pointer on any edge",
     lambda: callout("A short note about one point.", 20, 16, 280, 80, "bottom", 0.25, data_id="g-callout")),
    ("chevrons", "A row of process steps",
     lambda: chevrons(["Plan", "Build", "Ship"], 10, 40, 300, 56, data_id="g-chev")),
]


def gallery(out: Path, tokens: Path | None = None) -> Path:
    """One page with every icon (id and concepts) and every diagram part, in the brand's colors."""
    cat = catalog()
    css = tokens.read_text() if tokens else NEUTRAL
    groups = []
    for g in cat["groups"]:
        cards = [f'<figure><div class="ic">{svg(i["id"], 56)}{svg(i["id"], 32, i["id"] + "-32")}</div>'
                 f'<figcaption><b>{_e(i["id"])}</b><br>{_e(", ".join(i["concepts"]))}</figcaption></figure>'
                 for i in cat["icons"] if i["group"] == g]
        groups.append(f'<h2>{_e(g.title())}</h2><main>{"".join(cards)}</main>')
    parts = "".join(f'<figure><div class="stage">{make()}</div><figcaption><b>{_e(n)}</b><br>{_e(what)}</figcaption></figure>'
                    for n, what, make in PART_DEMOS)
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Icon gallery</title>
<style>{css}
body {{ margin: 0; padding: 32px; background: var(--brand-ground); color: var(--brand-body);
  font: 14px/20px var(--brand-font-body), system-ui, sans-serif; }}
h1 {{ font-size: 24px; line-height: 30px; color: var(--brand-ink); margin: 0 0 6px; }}
h2 {{ font-size: 17px; color: var(--brand-ink); margin: 28px 0 10px; }}
p.note {{ color: var(--brand-muted); margin: 0 0 8px; max-width: 760px; }}
main {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }}
main.parts {{ grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); }}
figure {{ margin: 0; padding: 14px; background: var(--brand-raised); border-radius: 6px; }}
.ic {{ display: flex; align-items: flex-end; gap: 14px; color: var(--brand-ink); }}
.stage {{ position: relative; height: 150px; color: var(--brand-ink); }} .abs {{ position: absolute; }}
figcaption {{ margin-top: 10px; color: var(--brand-muted); font-size: 12px; line-height: 17px; }}
figcaption b {{ color: var(--brand-ink); font-size: 14px; }}
</style></head><body><h1>Icons ({len(cat["icons"])}) and diagram parts ({len(PART_DEMOS)})</h1>
<p class="note">{_e(cat["style"])} Shown at 56 and 32 px. Paste one with <code>convey assets show ID</code>,
or a part with <code>convey assets part NAME key=value…</code>.</p>
{"".join(groups)}<h2>Diagram parts</h2><main class="parts">{parts}</main></body></html>"""
    out.write_text(page)
    return out
