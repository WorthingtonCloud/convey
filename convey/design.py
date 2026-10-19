"""Design lint: the free, code-only checks of `reference/design/` that a slide can fail while converting perfectly.

  contrast   text against what is really drawn under it (the template's layout picture, a photo, a panel),
             below the accessibility minimum: 4.5:1, or 3:1 for large text (24 px, or 18.67 px bold)
  small      text too small for a live room: under 18 px, or under 16 px for a label or a source
  crowded    more words on a slide than its mode carries (live 60, read-ahead 120), labels and sources aside
  color      colored type (signal, data, muted) straight on the template's own background, which may be a
             picture or a fade the slide can't see; there it takes ink or body
  rhythm     the same variant three slides in a row

Text in one of the template's own placeholders (data-ph) keeps the template's size and color: the company chose
them, so only contrast applies to it. Contrast is measured on pixels, not tokens: the slide is drawn with its words hidden and each line of text is
graded against the background's worst tenth under it (Berlin's ground token says black; its master draws an orange
fade). Run by `convey lint` on the page measure already loaded.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DESIGN_JS = (Path(__file__).parent / "design.js").read_text()

# Accessibility minimums (the published web standard's AA level): large text is 18 pt, or 14 pt bold.
CONTRAST, CONTRAST_LARGE = 4.5, 3.0
LEGIBLE = CONTRAST
LARGE_PX, LARGE_BOLD_PX = 24.0, 18.66
# Type scale (reference/design/type-scale.md): 18 px for anything the audience must read; 16 px only for labels
# and sources. Read-ahead decks are read close up, so they may go one step smaller.
FLOOR = {"live": (18.0, 16.0), "read-ahead": (16.0, 14.0)}
# A live slide carries one takeaway and the speaker carries the words (communication/audience.md).
WORDS = {"live": 60, "read-ahead": 120}
# Text that names or credits rather than tells: may sit at the label size.
LABEL_KEYS = {"source", "kicker", "eyebrow", "label", "tag", "verdict", "when", "who", "meta", "low", "high",
              "legend", "axis", "caption", "unit", "credit", "date", "number", "footer"}
LABEL_WORDS = 4  # a tag, a unit, a date: short enough to be a label wherever it sits
QUIET = {"ink", "body", "title-color", "body-color"}


def design_page(page) -> dict:
    """On a slide measure_page just loaded: its texts, then the same slide with the words hidden, sampled."""
    info = page.evaluate(DESIGN_JS + ";window.conveyDesign.collect()")
    if not info or "error" in info:
        return info or {"error": "no slide"}
    shot = page.send("Page.captureScreenshot", format="png")["data"]
    got = page.evaluate(f"window.conveyDesign.sample('data:image/png;base64,{shot}', "
                        f"{json.dumps([{'rects': t['rects'], 'color': t['color']} for t in info['texts']])})")
    for t, g in zip(info["texts"], got):
        t["bg"] = g
    return info


def _is_label(t: dict) -> bool:
    if t["words"] <= LABEL_WORDS:
        return True
    key = (t.get("bind") or "").split(".")[-1]
    words = set(re.split(r"[-_ ]+", f'{key} {t.get("id", "")} {t.get("cls", "")}'.lower()))
    return bool(words & LABEL_KEYS)


def _role(color, tokens: dict) -> str | None:
    """Which brand color this is (within 2 levels per channel), else None."""
    for name, c in tokens.items():
        if c and all(abs(a - b) <= 2 for a, b in zip(color[:3], c[:3])):
            return name
    return None


def _quote(s: str, n: int = 40) -> str:
    return f'"{s[:n]}…"' if len(s) > n else f'"{s}"'


def slide_problems(info: dict, mode: str = "live") -> list[str]:
    """Every design problem on one slide, one line each, naming the element."""
    if not info or "error" in info:
        return []
    out, seen = [], set()
    floor_text, floor_label = FLOOR.get(mode, FLOOR["live"])
    tokens = info.get("tokens") or {}
    for t in info["texts"]:
        size, bold = t["size"], t["weight"] >= 700
        bg = t.get("bg")
        if bg:
            need = CONTRAST_LARGE if size >= LARGE_PX or (bold and size >= LARGE_BOLD_PX) else CONTRAST
            if bg["contrast"] < need - 0.05 and ("contrast", t["id"]) not in seen:
                seen.add(("contrast", t["id"]))
                over = "a fill the slide painted" if t["painted"] else "the template's background"
                out.append(f'{t["id"]}: {_quote(t["text"])} in {bg["fg"]} on {over} ({bg["at"]} at its worst, '
                           f'{bg["median"]} typical) is {bg["contrast"]:.1f}:1; {size:g} px text needs {need:g}:1')
        if t.get("ph"):  # the template's own placeholder: its size and color are the company's call
            continue
        floor = floor_label if _is_label(t) else floor_text
        if size < floor - 0.05 and ("small", t["id"]) not in seen:
            seen.add(("small", t["id"]))
            what = "a label or source" if floor == floor_label else "text the room must read"
            out.append(f'{t["id"]}: {_quote(t["text"])} is {size:g} px; {what} on a {mode} slide needs {floor:g} px')
        if not t["painted"] and ("color", t["id"]) not in seen:
            role = _role(t["color"], tokens)
            if role not in QUIET and (role or t["color"][3] >= 1):
                seen.add(("color", t["id"]))
                named = f"the brand's {role}" if role else f'{t.get("bg", {}).get("fg", "a color")}, not a brand color'
                out.append(f'{t["id"]}: {_quote(t["text"])} is {named} straight on the template\'s background; '
                           f'color type goes only on a fill the slide paints (a panel, a band), else ink or body')
    words = sum(t["words"] for t in info["texts"] if not _is_label(t))  # sources and labels aren't read aloud
    if words > WORDS.get(mode, WORDS["live"]):
        out.append(f'slide: {words} words; a {mode} slide carries about {WORDS.get(mode, WORDS["live"])}: move detail '
                   f'to the speaker notes, split the slide, or pick a lighter variant')
    return out


def rhythm_problems(infos: list[dict]) -> dict[int, str]:
    """The same variant three slides in a row (deck-rhythm.md), keyed by the slide index of the third and on."""
    out, prev, n = {}, None, 0
    for i, inf in enumerate(infos):
        key = (inf["pattern"], inf.get("variant") or "default") if inf and inf.get("pattern") else None
        n = n + 1 if key and key == prev else (1 if key else 0)
        prev = key
        if n >= 3:
            out[i] = (f'slide: {key[0]} / {key[1]}, {n} slides in a row (slides {i - n + 2} to {i + 1}); '
                      f'vary the shape (reference/design/deck-rhythm.md)')
    return out


def deck_mode(files, slide_id=None) -> dict:
    """Each slide's mode: its storyboard `density`, else the brief's mode ('read-ahead' stays, anything denser than
    a talk counts as read-ahead, 'live' or no brief is live)."""
    proj = Path(files[0]).resolve().parent.parent
    mode = "live"
    try:
        m = json.loads((proj / "brief.json").read_text()).get("mode")
        mode = "live" if m in (None, "live") else "read-ahead"
    except (OSError, ValueError):
        pass
    per = {}
    try:
        for s in json.loads((proj / "storyboard.json").read_text()).get("slides", []):
            if s.get("density") in FLOOR:
                per[s["id"]] = s["density"]
    except (OSError, ValueError):
        pass
    return {"default": mode, **per}


GROUND_JS = """async (src, zone, body) => {
  const img = new Image(); img.src = src; await img.decode();
  const c = document.createElement('canvas'); c.width = 1280; c.height = 720;
  const g = c.getContext('2d', {willReadFrequently: true}); g.drawImage(img, 0, 0, 1280, 720);
  const px = g.getImageData(0, 0, 1280, 720).data;
  const lum = v => { const f = x => { x /= 255; return x <= 0.04045 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(v[0]) + 0.7152 * f(v[1]) + 0.0722 * f(v[2]); };
  const lb = lum(body), out = [];
  for (let y = Math.round(zone.y0); y < zone.y1; y += 4) for (let x = Math.round(zone.x0); x < zone.x1; x += 4) {
    const i = (y * 1280 + x) * 4, l = lum([px[i], px[i + 1], px[i + 2]]);
    out.push((Math.max(l, lb) + 0.05) / (Math.min(l, lb) + 0.05));
  }
  if (!out.length) return null;
  const ch = [[], [], []];
  for (let y = Math.round(zone.y0); y < zone.y1; y += 4) for (let x = Math.round(zone.x0); x < zone.x1; x += 4) {
    const i = (y * 1280 + x) * 4; ch[0].push(px[i]); ch[1].push(px[i + 1]); ch[2].push(px[i + 2]);
  }
  const med = ch.map(v => { v.sort((a, b) => a - b); return v[Math.floor(v.length / 2)]; });
  out.sort((a, b) => a - b);
  return {contrast: out[Math.floor(out.length * 0.1)],
          median: '#' + med.map(v => v.toString(16).padStart(2, '0')).join('').toUpperCase()};
}"""


def ground_contrast(picture: Path, body: str, zone: dict) -> float | None:
    """How the template's body color reads on what its layout picture draws in the content zone: the contrast at the
    background's worst tenth (the same measure lint grades text by). Berlin's orange fade: about 3:1."""
    got = ground_sample(picture, body, zone)
    return got["contrast"] if got else None


def ground_sample(picture: Path, body: str, zone: dict) -> dict | None:
    """The same measure, with the picture's typical color there (each channel's median): the ground to suggest when
    a template declares black over a gradient or a picture (Berlin #B84923, Madison #2D3A32)."""
    import base64
    from .skald.measure import slide_page
    rgb = [int(body[i:i + 2], 16) for i in (1, 3, 5)]
    mime = "image/svg+xml" if str(picture).endswith(".svg") else "image/png"
    src = f"data:{mime};base64," + base64.b64encode(Path(picture).read_bytes()).decode()
    with slide_page() as page:
        page.goto("about:blank")
        return page.evaluate(f"({GROUND_JS})({json.dumps(src)}, {json.dumps(zone)}, {json.dumps(rgb)})")
