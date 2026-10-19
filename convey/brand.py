"""Brand Profile: read a company template and record how its decks look.

    convey brand ingest template.potx --name acme      -> ~/.convey/brands/acme/

Reads the template's XML directly (standard library only): theme colors and fonts, masters,
layouts, placeholders, footers, pictures. Every value records where it came from. What a template
only shows on ordinary slides (colors and fonts typed onto text, repeated pictures) is collected
as "inferred" and never used until the person confirms it. Anything ambiguous becomes a flag in
flags.md. Writes brand.json, tokens.css (the only CSS slides use for brand values), assets/, the
untouched template, and brand-sheet.html for the person to check.
"""
from __future__ import annotations

import hashlib
import html
import json
import posixpath
import re
import shutil
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

from .skald.lines import author_pt as whole_pt  # authoring: ties round down
from . import fonts

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PR = "{http://schemas.openxmlformats.org/package/2006/relationships}"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
EMU = 9525  # per CSS px
SLOTS = ["dk1", "lt1", "dk2", "lt2", "accent1", "accent2", "accent3", "accent4", "accent5", "accent6", "hlink", "folHlink"]
HOME = Path.home() / ".convey" / "brands"

# Patterns and the layout each prefers: (name keywords, layout types), in order of preference.
# A match on any of the first PRIMARY keywords is certain; later keywords are near matches and get flagged.
PRIMARY = {"cover": 2}
PATTERNS = {
    "cover": (["cover", "title slide"], ["title"]),
    "closing": (["closing", "close", "end", "thank"], ["title"]),
    "section": (["section"], ["secHead"]),
    "executive-summary": (["executive summary", "summary"], ["obj", "tx"]),
    "key-finding": (["key finding", "finding", "statement", "quote"], ["titleOnly"]),
    "kpi-row": (["kpi", "big number", "number"], ["titleOnly"]),
    "comparison": (["comparison", "compare", "options", "two content"], ["twoTxTwoObj", "twoObj"]),
    "chart": (["chart"], ["chart", "titleOnly"]),
    "diagram": (["diagram", "process"], ["titleOnly"]),
}
# Patterns a template only serves with a layout made for them: bound by the layout's name alone, never by type or as
# a fallback (a near match would put a timeline on any "Title and Content"). Without one, the pattern's slides go on
# the title-only layout, as before. "chart-explained" is the chart pattern with a takeaway beside it (Oct 18, 2026).
NAMED = {
    "giant-number": ["big number", "giant number", "hero number"],
    "options": ["options"],
    "timeline": ["timeline", "roadmap", "milestones"],
    "chart-explained": ["chart and explanation", "chart with explanation", "chart and takeaway"],
}


# ---------------------------------------------------------------- package

class Package:
    """An Office zip: parts by name, relationships resolved to part names."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.z = zipfile.ZipFile(self.path)
        self.names = set(self.z.namelist())

    def xml(self, part: str) -> ET.Element:
        return ET.fromstring(self.z.read(part))

    def bytes(self, part: str) -> bytes:
        return self.z.read(part)

    def rels(self, part: str) -> dict[str, tuple[str, str]]:
        """rId -> (type suffix, target part name)."""
        d, f = posixpath.split(part)
        rp = posixpath.join(d, "_rels", f + ".rels")
        out = {}
        if rp not in self.names:
            return out
        for r in ET.fromstring(self.z.read(rp)):
            t = r.get("Target")
            if r.get("TargetMode") == "External":
                continue
            target = posixpath.normpath(posixpath.join(d, t)) if not t.startswith("/") else t.lstrip("/")
            out[r.get("Id")] = (r.get("Type").rsplit("/", 1)[-1], target)
        return out

    def main(self) -> str:
        """The presentation part. In an Office theme (.thmx) the package's main part is a theme
        manager and the presentation sits beside it, so fall back to finding it by name."""
        for _, (typ, target) in self.rels("").items():
            if typ == "officeDocument" and target.endswith("presentation.xml"):
                return target
        found = sorted(n for n in self.names if n.endswith("/presentation.xml"))
        if found:
            return found[0]
        raise ValueError(f"{self.path.name} has no presentation part (is it a .pptx, .potx or .thmx?)")

    def rel_of(self, part: str, typ: str) -> list[str]:
        return [t for ty, t in self.rels(part).values() if ty == typ]

    def ordered(self, part: str, root: ET.Element, list_tag: str, typ: str) -> list[str]:
        """Targets in the order the part's id list gives (PowerPoint's order), not the .rels file's."""
        rels = self.rels(part)
        lst = root.find(list_tag)
        out = [rels[e.get(R + "id")][1] for e in lst if e.get(R + "id") in rels] if lst is not None else []
        return out + [t for t in self.rel_of(part, typ) if t not in out]


# ---------------------------------------------------------------- helpers

def px(v) -> float:
    return round(int(v) / EMU, 3)


def _hex(c: str) -> str:
    return "#" + c.upper()


def mix(a: str, b: str, t: float) -> str:
    """t of color a over b."""
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * t + y * (1 - t)):02X}" for x, y in zip(ca, cb))


def contrast(a: str, b: str) -> float:
    """The accessibility contrast ratio of two #RRGGBB colors (1 to 21)."""
    def lum(c):
        v = [int(c[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        v = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in v]
        return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]
    x, y = lum(a), lum(b)
    return (max(x, y) + 0.05) / (min(x, y) + 0.05)


DERIVED_MUTED = "derived: ink over ground, legible on ground and raised"
LEGIBLE = 4.5  # the accessibility minimum for text under 24 px (design lint grades the same)
FILLS = ("signal", "data-1", "data-2", "data-3", "data-4", "data-5")


def on_fill(c: dict) -> dict:
    """The type color for each fill a variant paints: the ground color where it is legible (the template's own
    look), else ink, else the raised or body color (Berlin's charcoal reads 6.5:1 on its orange signal, where ground
    and white read 2.3:1), else whichever reads best (design lint then names the slide)."""
    out = {}
    for k in FILLS:
        if k in c:
            tries = [c[x] for x in ("ground", "ink", "raised", "body") if c.get(x)]
            out[k] = next((t for t in tries if contrast(t, c[k]) >= LEGIBLE), max(tries, key=lambda t: contrast(t, c[k])))
    return out


def plate_tone(c: dict) -> str:
    """The content plate's color: the raised color a step away from the body type, so the raised panels a variant
    draws still show on the plate (Berlin's panels vanished into a plate of their own color)."""
    toward = "#000000" if contrast(c["body"], "#000000") > contrast(c["body"], "#FFFFFF") else "#FFFFFF"
    t = 0.0
    while t < 0.6 and contrast(mix(toward, c["raised"], t), c["raised"]) < 1.2:
        t = round(t + 0.04, 2)
    return mix(toward, c["raised"], t)


def field_color(b: dict) -> str:
    """The flat color a full-bleed variant paints over the whole slide: the ground, unless the template draws a
    gradient or picture there (a flat swatch of it looks unlike the template) or the signal can't read on it; then the
    raised color where body and signal both read on it (Berlin's statement slides)."""
    c = b["colors"]
    bg = ((b.get("master") or {}).get("background") or {})
    busy = (bg.get("fill") or bg.get("kind")) in ("gradFill", "blipFill", "pattFill")
    reads = lambda x: contrast(c["body"], x) >= LEGIBLE and contrast(c.get("signal", c["ink"]), x) >= 3  # noqa: E731
    if (busy or not reads(c["ground"])) and c.get("raised") and reads(c["raised"]):
        return c["raised"]
    return c["ground"]


def signal_text(c: dict) -> str:
    """The signal color for text under 24 px: the signal nudged toward ink until it reads at 4.5:1 on ground and
    raised (a mid-tone red read 4.0:1 on white and 4.2:1 on a dark panel). Same hue family, a shade apart."""
    t = 0.0
    while t < 1:
        v = mix(c["ink"], c["signal"], t)
        if all(contrast(v, c[k]) >= LEGIBLE for k in ("ground", "raised") if k in c):
            return v
        t = round(t + 0.02, 2)
    return c["ink"]


def legible_muted(c: dict, t: float = 0.6) -> str:
    """A derived muted: t of ink over ground, raised until it reads at 4.5:1 on both ground and raised (Berlin's
    derived #999999 measured 4.1:1 on its raised panels, Oct 18, 2026)."""
    while t < 1:
        m = mix(c["ink"], c["ground"], t)
        if all(contrast(m, c[k]) >= LEGIBLE for k in ("ground", "raised") if k in c):
            return m
        t = round(t + 0.02, 2)
    return c["ink"]


class Resolver:
    """Turns DrawingML color elements into #RRGGBB through the theme and the master's color map."""

    def __init__(self, scheme: dict[str, str], clr_map: dict[str, str]):
        self.scheme, self.map = scheme, clr_map

    def color(self, parent) -> tuple[str | None, str]:
        """(hex, provenance) for the first color under a fill element, or (None, why)."""
        if parent is None:
            return None, "none"
        for c in parent.iter():
            tag = c.tag.split("}")[1]
            if tag == "srgbClr":
                return _hex(c.get("val")), "srgbClr"
            if tag == "sysClr":
                return _hex(c.get("lastClr", "000000")), f"sysClr {c.get('val')}"
            if tag == "schemeClr":
                v = c.get("val")
                slot = self.map.get(v, v)
                if slot in self.scheme:
                    mods = [m.tag.split("}")[1] for m in c]
                    return self.scheme[slot], f"schemeClr {v}→{slot}" + (f" (+{','.join(mods)} ignored)" if mods else "")
                return None, f"schemeClr {v} (unknown)"
            if tag == "prstClr":
                return None, f"prstClr {c.get('val')}"
        return None, "none"


def _fill_kind(sppr) -> str:
    if sppr is None:
        return "none"
    for k in ("solidFill", "gradFill", "blipFill", "pattFill", "grpFill", "noFill"):
        if sppr.find(A + k) is not None:
            return k
    return "none"


def _ph(sp):
    nv = next((c for c in sp if c.tag.endswith("Pr") and c.tag.startswith(P + "nv")), None)
    if nv is None:
        return None, ""
    cnv = nv.find(P + "cNvPr")
    ph = nv.find(P + "nvPr/" + P + "ph")
    return ph, cnv.get("name", "") if cnv is not None else ""


def _xfrm(sp):
    sppr = sp.find(P + "spPr")
    if sppr is None:
        sppr = sp.find(P + "grpSpPr")
    x = sppr.find(A + "xfrm") if sppr is not None else None
    if x is None:
        x = sp.find(P + "xfrm")
    if x is None or x.find(A + "off") is None:
        return None
    o, e = x.find(A + "off"), x.find(A + "ext")
    g = {"x": px(o.get("x")), "y": px(o.get("y")), "w": px(e.get("cx")), "h": px(e.get("cy"))}
    if x.get("rot") and int(x.get("rot")) % 21600000:
        g["rot"] = int(x.get("rot")) / 60000  # degrees; the box above is the shape before it turns about its center
    return g


def _lvl_style(lvl, res: Resolver, theme_fonts: dict) -> dict:
    """A paragraph level's declared look: size, line, tracking, bold, font, color."""
    out = {}
    if lvl is None:
        return out
    ls = lvl.find(A + "lnSpc")
    d = lvl.find(A + "defRPr")
    if d is not None:
        if d.get("sz"):
            out["size"] = round(int(d.get("sz")) / 100 / 0.75, 2)
        if d.get("b") is not None:
            out["bold"] = d.get("b") in ("1", "true")
        if d.get("spc") is not None:
            out["tracking_pt"] = int(d.get("spc")) / 100
        if d.get("cap") == "all":
            out["upper"] = True
        lat = d.find(A + "latin")
        if lat is not None:
            tf = lat.get("typeface")
            out["font"] = theme_fonts.get(tf, tf)
        fill = d.find(A + "solidFill")
        if fill is not None:
            c, how = res.color(fill)
            if c:
                out["color"] = c
    if ls is not None:
        pts, pct = ls.find(A + "spcPts"), ls.find(A + "spcPct")
        if pts is not None:
            out["line"] = round(int(pts.get("val")) / 100 / 0.75, 2)
        elif pct is not None:
            out["line_multiple"] = int(pct.get("val")) / 100000
    if lvl.get("algn"):
        out["align"] = lvl.get("algn")
    return out


# ---------------------------------------------------------------- reading

def read(path: Path) -> dict:
    """Everything declared in the template, with provenance. No guessing here."""
    pkg = Package(path)
    pres_part = pkg.main()
    pres = pkg.xml(pres_part)
    sz = pres.find(P + "sldSz")
    size = {"width": px(sz.get("cx")), "height": px(sz.get("cy"))} if sz is not None else {"width": 1280.0, "height": 720.0}

    masters = []
    for mpart in pkg.ordered(pres_part, pres, P + "sldMasterIdLst", "slideMaster"):
        m = pkg.xml(mpart)
        tpart = pkg.rel_of(mpart, "theme")[0]
        th = pkg.xml(tpart)
        te = th.find(A + "themeElements")
        scheme, scheme_from = {}, {}
        for slot in SLOTS:
            el = te.find(f"{A}clrScheme/{A}{slot}")
            if el is None:
                continue
            c = el[0]
            v = c.get("val") if c.tag == A + "srgbClr" else c.get("lastClr", "000000")
            scheme[slot] = _hex(v)
            scheme_from[slot] = f"{posixpath.basename(tpart)} clrScheme/{slot}"
        bsl = te.find(f"{A}fmtScheme/{A}bgFillStyleLst")
        bg_styles = [ch.tag.split("}")[1] for ch in bsl] if bsl is not None else []
        tf = {}
        for k, key in (("majorFont", "+mj-lt"), ("minorFont", "+mn-lt")):
            lat = te.find(f"{A}fontScheme/{A}{k}/{A}latin")
            tf[key] = lat.get("typeface") if lat is not None else ""
        custom = {}
        for cc in th.iter(A + "custClr"):
            c = cc[0] if len(cc) else None
            if c is not None and c.get("val"):
                custom[cc.get("name", f"custom{len(custom) + 1}")] = _hex(c.get("val"))
        cm = m.find(P + "clrMap")
        clr_map = dict(cm.attrib) if cm is not None else {}
        res = Resolver(scheme, clr_map)

        def bg_of(root):
            bg = root.find(f"{P}cSld/{P}bg")
            if bg is None:
                return None
            bgpr = bg.find(P + "bgPr")
            if bgpr is not None:
                kind = _fill_kind(bgpr)
                c, how = res.color(bgpr.find(A + "solidFill")) if kind == "solidFill" else (None, kind)
                return {"kind": kind, "color": c, "from": how}
            ref = bg.find(P + "bgRef")
            if ref is not None:  # a theme background style (idx 1001 = the first), drawn in the referenced color
                c, how = res.color(ref)
                i = int(ref.get("idx", "0")) - 1001
                fill = bg_styles[i] if 0 <= i < len(bg_styles) else "solidFill"
                return {"kind": f"bgRef {ref.get('idx')}", "fill": fill, "color": c, "from": how}
            return None

        def shapes_of(root, part):
            """Placeholders and drawn shapes on a master or layout."""
            phs, drawn = [], []
            tree = root.find(f"{P}cSld/{P}spTree")
            rels = pkg.rels(part)

            def walk(node, depth=0):
                for sp in node:
                    tag = sp.tag.split("}")[1]
                    if tag not in ("sp", "pic", "grpSp", "cxnSp", "graphicFrame"):
                        continue
                    ph, name = _ph(sp)
                    geo = _xfrm(sp)
                    if ph is not None:
                        lst = sp.find(f"{P}txBody/{A}lstStyle/{A}lvl1pPr")
                        phs.append({"type": ph.get("type", "body"), "idx": int(ph.get("idx", 0)), "name": name,
                                    "geometry": geo, "style": _lvl_style(lst, res, tf),
                                    "prompt": "".join(t.text or "" for t in sp.iter(A + "t")) or None})
                        continue
                    item = {"kind": tag, "name": name, "geometry": geo}
                    sppr = sp.find(P + "spPr")
                    if tag == "sp":
                        g = sppr.find(A + "prstGeom") if sppr is not None else None
                        item["shape"] = g.get("prst") if g is not None else ("custom" if sppr is not None and sppr.find(A + "custGeom") is not None else None)
                        item["fill"] = _fill_kind(sppr)
                        if item["fill"] == "solidFill":
                            item["color"] = res.color(sppr.find(A + "solidFill"))[0]
                        txt = "".join(t.text or "" for t in sp.iter(A + "t"))
                        if txt:
                            item["text"] = txt[:80]
                    if tag == "pic":
                        blip = sp.find(f"{P}blipFill/{A}blip")
                        rid = blip.get(R + "embed") if blip is not None else None
                        if rid in rels:
                            item["image"] = rels[rid][1]
                        svg = [e for e in sp.iter() if e.tag.endswith("}svgBlip")]
                        if svg and svg[0].get(R + "embed") in rels:
                            item["svg"] = rels[svg[0].get(R + "embed")][1]
                    if tag == "grpSp":
                        walk(sp, depth + 1)
                        item["kind"] = "group"
                    drawn.append(item)

            if tree is not None:
                walk(tree)
            return phs, drawn

        ts = m.find(P + "txStyles")
        styles = {}
        if ts is not None:
            for k in ("titleStyle", "bodyStyle", "otherStyle"):
                el = ts.find(P + k)
                if el is not None:
                    styles[k] = [_lvl_style(el.find(f"{A}lvl{n}pPr"), res, tf) for n in (1, 2, 3)]
        mphs, mdrawn = shapes_of(m, mpart)
        layouts = []
        for lpart in pkg.ordered(mpart, m, P + "sldLayoutIdLst", "slideLayout"):
            lay = pkg.xml(lpart)
            phs, drawn = shapes_of(lay, lpart)
            for ph in phs:  # geometry and look come from the master when the layout doesn't say
                if ph["geometry"] is None:
                    mp = next((q for q in mphs if q["type"] == ph["type"] or
                               (ph["type"] in ("ctrTitle",) and q["type"] == "title") or
                               (ph["type"] in ("subTitle", "obj") and q["type"] == "body")), None)
                    if mp:
                        ph["geometry"] = mp["geometry"]
                        ph["geometry_from"] = "master"
            cs = lay.find(P + "cSld")
            layouts.append({"name": cs.get("name", posixpath.basename(lpart)) if cs is not None else posixpath.basename(lpart),
                            "type": lay.get("type", "cust"), "part": lpart,
                            "show_master_shapes": lay.get("showMasterSp", "1") not in ("0", "false"),
                            "background": bg_of(lay), "placeholders": phs, "drawn": drawn})
        masters.append({"part": mpart, "theme": tpart, "scheme": scheme, "scheme_from": scheme_from,
                        "theme_fonts": {"heading": tf["+mj-lt"], "body": tf["+mn-lt"]}, "custom_colors": custom,
                        "color_map": clr_map, "background": bg_of(m), "text_styles": styles,
                        "placeholders": mphs, "drawn": mdrawn, "layouts": layouts})

    slides = []
    for spart in pkg.ordered(pres_part, pres, P + "sldIdLst", "slide"):
        s = pkg.xml(spart)
        runs = []
        for rpr in s.iter(A + "rPr"):
            f = rpr.find(A + "solidFill")
            c = f.find(A + "srgbClr") if f is not None else None
            lat = rpr.find(A + "latin")
            runs.append({"color": _hex(c.get("val")) if c is not None else None,
                         "font": lat.get("typeface") if lat is not None else None})
        pics = []
        rels = pkg.rels(spart)
        for blip in s.iter(A + "blip"):
            rid = blip.get(R + "embed")
            if rid in rels:
                pics.append(hashlib.sha1(pkg.bytes(rels[rid][1])).hexdigest())
        slides.append({"part": spart, "runs": runs, "pictures": pics})
    return {"file": Path(path).name, "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "size": size, "masters": masters, "slides": slides, "_pkg": pkg}


# ---------------------------------------------------------------- deciding

def _font(name: str, role: str, flags: list) -> dict:
    f = fonts.lookup(name) if name else None
    if not f:
        flags.append((f"font-missing-{role}", f"The {role} font \"{name}\" is not installed here. Slides will fall back to another "
                      "font in the browser and in PowerPoint; install it or choose a replacement."))
        return {"powerpoint": name, "css": name, "weight": 400, "installed": False, "browser": False, "faces": {}}
    fam = fonts.family_of(f)
    out = {"powerpoint": name, "css": fam, "weight": f["weight"], "installed": True,
           "browser": fonts.visible_to_browser(fam), "faces": fonts.face_map(fam), "file": f["file"]}
    if not out["browser"]:
        flags.append((f"font-browser-{role}", f"The {role} font \"{name}\" is installed for Office only, so the browser can't "
                      "show it: the studio would draw slides in a substitute and measure the wrong widths. "
                      "Install the font system-wide (or pick a replacement) before designing."))
    return out


def bind_named(layouts: list[dict]) -> dict:
    """The NAMED patterns' layouts: the first layout whose name holds one of the pattern's words, in word order."""
    out = {}
    for pat, words in NAMED.items():
        for w in words:
            hit = next((l for l in layouts if w in l["name"].lower()), None)
            if hit:
                out[pat] = {"layout": hit["name"], "how": f'name contains "{w}"'}
                break
    return out


def _bind(layouts: list[dict], flags: list) -> dict:
    named = bind_named(layouts)
    # A layout made for a named pattern is never another pattern's near match ("Options" is not a comparison).
    claimed = {v["layout"] for v in named.values()}
    free = [l for l in layouts if l["name"] not in claimed]
    out = {}
    for pat, (words, types) in PATTERNS.items():
        hit, how = None, None
        for i, w in enumerate(words):
            hit = next((l for l in free if w in l["name"].lower()), None)
            if hit:
                how = f'name contains "{w}"' + ("" if i < PRIMARY.get(pat, 1) else " (a near match)")
                break
        if not hit:
            for t in types:
                hit = next((l for l in free if l["type"] == t), None)
                if hit:
                    how = f"layout type {t}"
                    break
        if not hit:
            hit = next((l for l in free if l["type"] in ("titleOnly", "obj")), free[0] if free else None)
            how = "fallback"
        if hit is None:
            continue
        out[pat] = {"layout": hit["name"], "how": how}
        if not how.startswith("name") or "near" in how:
            flags.append((f"binding-{pat}", f'Pattern "{pat}" uses layout "{hit["name"]}" ({how}). Confirm, or name the layout to use.'))
    out.update(named)
    return out


def _footer_top(m: dict, foot: list, H: float) -> float:
    """Where the footer zone starts: footer placeholders in the bottom half, else shapes the master
    draws in its bottom 15% (a footer drawn as plain shapes), else 40 px from the bottom. A footer turned on its
    side (a vertical strip in a side band) bounds nothing below: Madison's sat at y 384 before it turns, and the
    body zone came out half the slide (Oct 18, 2026)."""
    ys = [p["geometry"]["y"] for p in foot if p["geometry"] and p["geometry"]["y"] > H / 2
          and round(p["geometry"].get("rot", 0)) % 180 == 0]
    if not ys:
        ys = [d["geometry"]["y"] for d in m["drawn"] if d.get("geometry") and d["geometry"]["y"] > H * 0.85]
    return min(ys, default=H - 40)


def _line(style: dict, fallback: float) -> float:
    if "line" in style:
        return style["line"]
    if "line_multiple" in style and "size" in style:
        return round(style["size"] * 1.2 * style["line_multiple"], 2)
    return fallback


def decide(raw: dict, name: str) -> tuple[dict, list]:
    """Declared values -> brand.json, plus flags for everything that needed a choice."""
    flags: list[tuple[str, str]] = []
    if not raw["masters"]:
        raise ValueError("the template has no slide master")
    if len(raw["masters"]) > 1:
        flags.append(("masters", f"The template has {len(raw['masters'])} masters; Convey uses the first. Say if another is the house one."))
    m = raw["masters"][0]
    S, W, H = m["scheme"], raw["size"]["width"], raw["size"]["height"]
    if abs(W / H - 16 / 9) > 0.01:
        flags.append(("size", f"Slides are {W:g} x {H:g} px, not 16:9. The pattern skeletons are drawn for 1280 x 720."))
    cmap = m["color_map"]
    role = lambda r: S.get(cmap.get(r, r))
    named = {k.lower(): v for k, v in m["custom_colors"].items()}

    colors, prov = {}, {}

    def put(key, value, how):
        colors[key], prov[key] = value, how

    for key, slot_role in (("ground", "bg1"), ("ink", "tx1"), ("raised", "bg2"), ("body", "tx2")):
        if key in named:
            put(key, named[key], f"custom color \"{key.title()}\"")
        else:
            put(key, role(slot_role), f"theme {slot_role} → {cmap.get(slot_role, slot_role)}")
    if "body" not in named:  # body text color: the master's body style if it says, else the main text color
        bs = (m["text_styles"].get("bodyStyle") or [{}])[0]
        if bs.get("color"):
            put("body", bs["color"], "master body text style, level 1")
        else:
            put("body", colors["ink"], "same as ink (the master names no body text color)")
    if "raised" not in named:
        flags.append(("raised", f"\"Raised\" (card and panel fill) is theme bg2 {colors['raised']}. Confirm, or name a color."))
    for key, t in (("muted", 0.6), ("rule", 0.22)):
        if key in named:
            put(key, named[key], f"custom color \"{key.title()}\"")
        elif key == "muted":
            put(key, legible_muted(colors, t), DERIVED_MUTED)
        else:
            put(key, mix(colors["ink"], colors["ground"], t), f"derived: {int(t * 100)}% ink over ground")
            flags.append((key, f"\"{key.title()}\" {colors[key]} is derived ({int(t * 100)}% ink over ground); the template doesn't name one."))
    if "signal" in named:
        put("signal", named["signal"], "custom color \"Signal\"")
        sig_slot = next((s for s in SLOTS[4:10] if S.get(s) == named["signal"]), None)
    else:
        put("signal", S.get("accent1"), "theme accent1 (guess)")
        sig_slot = "accent1"
        flags.append(("signal", f"The emphasis color is a guess: accent1 {S.get('accent1')}. Confirm, or name the color "
                      "that means \"this is the thing\"."))
    data = [S[s] for s in SLOTS[4:10] if s in S and s != sig_slot]
    for i, c in enumerate(data, 1):
        put(f"data-{i}", c, "theme accents in order" + (f", minus the emphasis color ({sig_slot})" if sig_slot else ""))

    heading = _font(m["theme_fonts"]["heading"], "heading", flags)
    body = _font(m["theme_fonts"]["body"], "body", flags)
    for css in dict.fromkeys(f["css"] for f in (heading, body) if f["installed"]):
        flags.append(("calibrate-" + css, f"\"{css}\" has no line-spacing calibration yet: run `convey brand calibrate` "
                      "(needs PowerPoint). Until then text may sit up to a few px off in PowerPoint."))

    ts = m["text_styles"]
    t1 = (ts.get("titleStyle") or [{}])[0]
    b1 = (ts.get("bodyStyle") or [{}])[0]
    title_ph = next((p for p in m["placeholders"] if p["type"] in ("title", "ctrTitle")), None)
    foot = [p for p in m["placeholders"] if p["type"] in ("dt", "ftr", "sldNum")]
    tg = title_ph["geometry"] if title_ph and title_ph["geometry"] else None
    if tg is None:
        flags.append(("margins", "The master has no title placeholder, so margins are a default (64 px)."))
    t_size = t1.get("size", 40.0)
    b_size = b1.get("size", 20.0)
    typ = {
        "title": {"size": t_size, "line": _line(t1, round(t_size * 1.1, 2)),
                  "tracking_em": round(t1.get("tracking_pt", 0) / (t_size * 0.75), 4),
                  "font": "heading", "color": t1.get("color", colors["ink"])},
        "body": {"size": b_size, "line": _line(b1, round(b_size * 1.5, 2)),
                 "tracking_em": round(b1.get("tracking_pt", 0) / (b_size * 0.75), 4),
                 "font": "body", "color": b1.get("color", colors["body"])},
    }
    margins = {"left": tg["x"] if tg else 64.0, "right": round(W - (tg["x"] + tg["w"]), 3) if tg else 64.0,
               "top": tg["y"] if tg else 48.0,
               "footer_top": _footer_top(m, foot, H)}

    layouts = m["layouts"]
    bindings = _bind(layouts, flags)
    bg = m["background"] or {}
    fill = bg.get("fill") or bg.get("kind")
    plain = {"gradFill": "a gradient", "blipFill": "a picture", "pattFill": "a pattern"}
    if fill in plain:
        base = f" built on {bg['color']} ({bg.get('from')})" if bg.get("color") else ""
        flags.append(("background", f"PowerPoint draws the master background as {plain[fill]}{base}, not the flat "
                      f"\"ground\" {colors['ground']}. Text and cards sit on that, so judge every color against the layout "
                      "pictures (`convey brand render`), not the swatches. Confirm, or set the ground slides should assume "
                      "(background=#RRGGBB)."))
    elif bg.get("color") and bg["color"] != colors["ground"]:
        flags.append(("background", f"The master background is {bg['color']} ({bg.get('from')}), but \"ground\" is "
                      f"{colors['ground']}. Confirm, or set the ground (background=#RRGGBB)."))
    pics = [d for d in m["drawn"] if d.get("image")]
    for l in layouts:
        pics += [dict(d, layout=l["name"]) for d in l["drawn"] if d.get("image")]
    if pics:
        distinct = len({d["image"] for d in pics})
        flags.append(("pictures", f"The template places {distinct} distinct picture(s) on its master or layouts, "
                      f"{len(pics)} times in all (logos, textures). They are saved in assets/; say which one is the logo, or \"none\"."))

    inferred = []
    slides = raw["slides"]
    if slides:
        n = len(slides)
        cc, fc, pc = Counter(), Counter(), Counter()
        for s in slides:
            cc.update({r["color"] for r in s["runs"] if r["color"]})
            fc.update({r["font"] for r in s["runs"] if r["font"]})
            pc.update(set(s["pictures"]))
        for c, k in cc.most_common(8):
            inferred.append({"what": "text color", "value": c, "seen": f"{k} of {n} slides", "confirmed": False})
        for f, k in fc.most_common(4):
            inferred.append({"what": "font typed on text", "value": f, "seen": f"{k} of {n} slides", "confirmed": False})
        for h, k in pc.most_common(3):
            if k >= max(2, n // 2):
                inferred.append({"what": "repeated picture (logo?)", "value": h[:12], "seen": f"{k} of {n} slides", "confirmed": False})
        if inferred:
            flags.append(("inferred", f"{len(inferred)} value(s) were seen on the deck's slides but not declared in its theme "
                          "(see \"inferred\" in brand.json). None is used until you confirm it."))

    brand = {
        "name": name, "made": date.today().isoformat(),
        "source": {"file": raw["file"], "sha256": raw["sha256"]},
        "slide": raw["size"],
        "colors": colors, "colors_from": prov,
        "theme": {"slots": S, "slots_from": m["scheme_from"], "custom": m["custom_colors"], "color_map": cmap},
        "fonts": {"heading": heading, "body": body},
        "type": typ, "margins": margins,
        "master": {"background": m["background"], "placeholders": m["placeholders"], "drawn": m["drawn"],
                   "text_styles": ts},
        "layouts": [{k: v for k, v in l.items() if k != "part"} for l in layouts],
        "footer": {k: any(p["type"] == k for p in m["placeholders"]) for k in ("dt", "ftr", "sldNum")},
        "bindings": bindings,
        "inferred": inferred,
        "vertical": {},
        "flags": [{"id": i, "text": t, "settled": False} for i, t in flags],
    }
    return brand, flags


# ---------------------------------------------------------------- writing

def pattern_scale(b: dict) -> dict:
    t, body = b["type"]["title"]["size"], b["type"]["body"]["size"]
    head = (b.get("scale") or {}).get("headline-size") or min(max(t, 32), 44)  # the person's size, when settled
    text = min(max(body, 16), 22)
    small = max(16, round(text * 0.72))  # labels and sources: 16 px is the smallest a room reads (design/type-scale.md)
    # Line heights on whole points, which PowerPoint draws as written (skald/lines.py).
    return {"headline-size": head, "headline-line": whole_pt(head * 1.15),
            "statement-size": round(head * 1.3), "statement-line": whole_pt(round(head * 1.3) * 1.12),
            "text-size": text, "text-line": whole_pt(text * 1.45),
            "small-size": small, "small-line": whole_pt(small * 1.4),
            "display-size": 96, "display-line": whole_pt(100)}


def tokens_css(b: dict) -> str:
    c, t, m, f = b["colors"], b["type"], b["margins"], b["fonts"]
    lines = [f"/* {b['name']}: generated by `convey brand ingest` from {b['source']['file']} on {b['made']}.",
             "   Edit brand.json and re-run, never this file. Slides use only these variables. */", ":root {"]
    for k, v in c.items():
        lines.append(f"  --brand-{k}: {v};")
    lines.append("  /* Type on each fill a variant paints: ground where it reads at 4.5:1, else ink. */")
    for k, v in on_fill(c).items():
        lines.append(f"  --brand-on-{k}: {v};")
    if "signal" in c and "ground" in c and "ink" in c:
        on = on_fill(c)["signal"]
        other = c["ink"] if on == c["ground"] else c["ground"]
        hit = other if contrast(other, c["signal"]) >= 3 else on  # display type needs 3:1
        lines.append("  /* Emphasis words in display type on a signal field: the other type color where it reads at 3:1. */")
        lines.append(f"  --brand-on-signal-hit: {hit};")
    if "signal" in c:
        lines.append("  /* The signal for text under 24 px: nudged toward ink until it reads at 4.5:1 on ground and raised. */")
        lines.append(f"  --brand-signal-text: {signal_text(c)};")
    if "ground" in c and "body" in c:
        lines.append("  /* The flat color a full-bleed slide paints: ground, or raised where the template draws a fade or a picture. */")
        lines.append(f"  --brand-field: {field_color(b)};")
    for role in ("heading", "body"):
        lines.append(f'  --brand-font-{role}: "{f[role]["css"]}";')
        lines.append(f"  --brand-weight-{role}: {f[role]['weight']};")
    for k in ("title", "body"):
        lines.append(f"  --brand-{k}-size: {t[k]['size']:g}px;")
        lines.append(f"  --brand-{k}-line: {whole_pt(t[k]['line']):g}px;")
        lines.append(f"  --brand-{k}-tracking: {t[k]['tracking_em']:g}em;")
        lines.append(f"  --brand-{k}-color: {t[k]['color']};")
    for k, v in m.items():
        if k == "set" or k.startswith("title_"):  # the person widened the margins: a mark, and the title's own box
            continue
        lines.append(f"  --brand-margin-{k.replace('_', '-')}: {v:g}px;")
    lines.append(f"  --brand-content-width: {b['slide']['width'] - m['left'] - m['right']:g}px;")
    if "title_left" in m or "title_right" in m:
        tl, tr = m.get("title_left", m["left"]), m.get("title_right", m["right"])
        lines.append("  /* The headline keeps the template's title box; the margins above widen the body only. */")
        lines.append(f"  --brand-title-left: {tl:g}px;")
        lines.append(f"  --brand-title-width: {b['slide']['width'] - tl - tr:g}px;")
    lines.append("  /* The pattern scale: derived from the template's title and body sizes, held to ranges that keep")
    lines.append("     a one-sentence headline and a dense slide readable in any brand. */")
    for k, v in pattern_scale(b).items():
        lines.append(f"  --brand-{k}: {v:g}px;")
    cal = (b.get("vertical") or {}).get(f["body"]["css"]) or {}
    if cal.get("chart"):
        lines.append("  /* Where PowerPoint sets chart axis labels in the body font, vs chart.js: size dy dx (convey brand calibrate). */")
        lines.append('  --brand-chart-labels: "' + ", ".join(f"{s:g} {dy:g} {dx:g}" for s, dy, dx in cal["chart"]) + '";')
    lines.append("}")
    return "\n".join(lines) + "\n"


def flags_md(b: dict) -> str:
    out = [f"# {b['name']}: what needs your call", "",
           f"From `{b['source']['file']}` on {b['made']}. Once the person decides, settle each one with "
           "`convey brand settle <brand> <id>` (confirm as it stands) or `<id>=<value>` (a color, a layout's name, "
           "or for pictures a file in assets/ or `none`). Settled values survive a re-ingest.", ""]
    # Agent to-dos (a font to calibrate) are not the person's calls: they clear themselves (Oct 18, 2026 stress test).
    todo = [fl for fl in b["flags"] if fl["id"].startswith("calibrate-")]
    calls = [fl for fl in b["flags"] if fl not in todo]
    if not calls:
        out.append("Nothing. Every value came straight from the template.")
    for fl in calls:
        out.append(f"- [{'x' if fl['settled'] else ' '}] **{fl['id']}**: {fl['text']}")
    if todo:
        out += ["", "## For the agent, not the person", "",
                "These clear themselves when you run `convey brand calibrate` after the person approves the profile; "
                "don't settle them."]
        out += [f"- **{fl['id']}**: {fl['text']}" for fl in todo]
    if not b.get("plate"):
        out += ["", "Background under small text: not measured yet. `convey brand render` (needs PowerPoint) measures it "
                "and adds a `plate` flag here if the background can't carry small text."]
    idle = unfilled_layouts(b)
    if idle:
        out += ["", "Layouts no pattern fills yet: " + ", ".join(f'"{n}"' for n in idle) + ". Slides of those kinds go "
                "on the title-only layout, keeping its title, logo and footer. Tell the person; `brand settle "
                "binding-<pattern>=<layout>` points a pattern that fills placeholders (" + ", ".join([*PATTERNS, *NAMED]) +
                ") at any layout; compose fills it only when the layout's placeholder names match the pattern's."]
    return "\n".join(out) + "\n"


def unfilled_layouts(b: dict) -> list[str]:
    """The template's own layouts that no pattern lands on, besides the plain ones (title only, blank, title and
    content) that variants and fallbacks use."""
    used = {v["layout"] for v in b.get("bindings", {}).values()}
    plain = ("titleOnly", "blank")
    return [l["name"] for l in b.get("layouts", []) if l["name"] not in used and l.get("type") not in plain
            and l["name"].lower() != "title and content"]


def save_assets(raw: dict, b: dict, out: Path):
    pkg = raw["_pkg"]
    (out / "assets").mkdir(exist_ok=True)
    seen = {}
    m = b["master"]
    groups = [("master", m["drawn"])] + [(f"layout-{i + 1:02d}", l["drawn"]) for i, l in enumerate(b["layouts"])]
    for where, drawn in groups:
        for d in drawn:
            for key in ("image", "svg"):
                part = d.get(key)
                if not part or part not in pkg.names:
                    continue
                data = pkg.bytes(part)
                h = hashlib.sha1(data).hexdigest()[:10]
                if h not in seen:
                    fn = f"{h}{posixpath.splitext(part)[1].lower()}"
                    (out / "assets" / fn).write_bytes(data)
                    seen[h] = f"assets/{fn}"
                d[key] = seen[h]


def sheet_html(b: dict) -> str:
    """The brand sheet: swatches, type, layouts drawn from their geometry, bindings, flags."""
    e = html.escape
    W, H = b["slide"]["width"], b["slide"]["height"]
    sw = "".join(f'<div class="sw"><i style="background:{v}"></i><b>{e(k)}</b><code>{v}</code>'
                 f'<small>{e(b["colors_from"][k])}</small></div>' for k, v in b["colors"].items())
    slots = "".join(f'<div class="sw"><i style="background:{v}"></i><b>{k}</b><code>{v}</code></div>'
                    for k, v in b["theme"]["slots"].items())

    def frame(drawn, phs, bg, scale=0.25, label=""):
        out = [f'<svg viewBox="0 0 {W} {H}" width="{W * scale:g}" height="{H * scale:g}"><rect width="{W}" height="{H}" fill="{bg}"/>']
        for d in drawn:
            g = d.get("geometry")
            if not g:
                continue
            if d.get("image"):
                out.append(f'<image href="{e(d["image"])}" x="{g["x"]}" y="{g["y"]}" width="{g["w"]}" height="{g["h"]}" preserveAspectRatio="none"/>')
            else:
                fill = d.get("color") or "none"
                out.append(f'<rect x="{g["x"]}" y="{g["y"]}" width="{max(g["w"], 1)}" height="{max(g["h"], 1)}" fill="{fill}" '
                           f'stroke="{b["colors"]["muted"]}" stroke-width="1" stroke-dasharray="{"" if fill != "none" else "4 4"}"/>')
        for p in phs:
            g = p.get("geometry")
            if not g:
                continue
            out.append(f'<rect x="{g["x"]}" y="{g["y"]}" width="{g["w"]}" height="{g["h"]}" fill="none" stroke="#3B82F6" stroke-width="3"/>'
                       f'<text x="{g["x"] + 8}" y="{g["y"] + 30}" font-size="26" fill="#3B82F6">{e(p["type"])} {p["idx"]}</text>')
        out.append("</svg>")
        return "".join(out)

    ground = b["colors"]["ground"]
    lays = []
    for l in b["layouts"]:
        drawn = (b["master"]["drawn"] if l["show_master_shapes"] else []) + l["drawn"]
        bg = (l.get("background") or {}).get("color") or ground
        uses = [p for p, v in b["bindings"].items() if v["layout"] == l["name"]]
        pic = (f'<div class="pic"><img src="{e(l["picture"])}" alt="">{frame([], l["placeholders"], "none")}</div>'
               if l.get("picture") else frame(drawn, l["placeholders"], bg))
        lays.append(f'<figure>{pic}<figcaption><b>{e(l["name"])}</b> '
                    f'<span>{e(l["type"])}</span>{"".join(f"<em>{e(u)}</em>" for u in uses)}</figcaption></figure>')
    f = b["fonts"]
    fonts_html = "".join(
        f'<div class="font"><div style="font-family:\'{e(v["css"])}\';font-weight:{v["weight"]};font-size:40px">Aa Bb 0123</div>'
        f'<b>{role}</b>: {e(v["powerpoint"])} <small>(CSS "{e(v["css"])}" {v["weight"]}; installed: {v["installed"]}; '
        f'browser can see it: {v["browser"]}; calibrated: {bool(b["vertical"].get(v["css"]))})</small></div>'
        for role, v in f.items())
    binds = "".join(f'<tr><td>{e(p)}</td><td>{e(v["layout"])}</td><td>{e(v["how"])}</td></tr>' for p, v in b["bindings"].items())
    # The person's calls apart from the agent's to-dos, as flags.md splits them (the sheet counted a
    # calibrate to-do as one of the person's open calls).
    todo = [fl for fl in b["flags"] if fl["id"].startswith("calibrate-")]
    calls = [fl for fl in b["flags"] if fl not in todo]
    flags = "".join(f'<li class="{"ok" if fl["settled"] else ""}"><b>{e(fl["id"])}</b> {e(fl["text"])}</li>' for fl in calls) or "<li>None.</li>"
    todo_html = (f'<h2>For the agent, not the person ({len(todo)})</h2><p class="sub">These clear themselves when the agent '
                 'runs <code>convey brand calibrate</code>.</p><ul>' + "".join(
                     f'<li><b>{e(fl["id"])}</b> {e(fl["text"])}</li>' for fl in todo) + "</ul>") if todo else ""
    inferred = "".join(f'<li>{e(i["what"])}: <code>{e(i["value"])}</code> ({e(i["seen"])})</li>' for i in b["inferred"])
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(b["name"])} brand sheet</title><style>
:root {{ --bg:#fafafa; --fg:#18181b; --mute:#71717a; --line:#e4e4e7; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#18181b; --fg:#f4f4f5; --mute:#a1a1aa; --line:#3f3f46; }} }}
body {{ margin:0; padding:32px 16px; background:var(--bg); color:var(--fg); font:15px/1.5 -apple-system,system-ui,sans-serif; }}
main {{ max-width:1200px; margin:0 auto; }} h1 {{ margin:0 0 4px; }} h2 {{ margin:40px 0 12px; font-size:18px; }}
.sub {{ color:var(--mute); }} .grid {{ display:flex; flex-wrap:wrap; gap:12px; }}
.sw {{ width:170px; display:flex; flex-direction:column; font-size:13px; }} .sw i {{ height:56px; border:1px solid var(--line); border-radius:6px; margin-bottom:4px; }}
.sw small {{ color:var(--mute); }} figure {{ margin:0; }} figure svg {{ border:1px solid var(--line); border-radius:4px; display:block; max-width:100%; height:auto; }}
figcaption {{ font-size:13px; margin-top:4px; }}
.pic {{ position:relative; width:320px; }} .pic img {{ width:320px; display:block; border:1px solid var(--line); border-radius:4px; }}
.pic svg {{ position:absolute; left:0; top:0; border:none !important; }} figcaption span {{ color:var(--mute); margin-left:6px; }}
figcaption em {{ font-style:normal; background:#3B82F6; color:#fff; border-radius:4px; padding:0 6px; margin-left:6px; font-size:12px; }}
table {{ border-collapse:collapse; }} td {{ border-bottom:1px solid var(--line); padding:6px 16px 6px 0; }}
.font {{ margin-bottom:16px; }} li {{ margin-bottom:6px; }} li.ok {{ color:var(--mute); text-decoration:line-through; }}
</style></head><body><main>
<h1>{e(b["name"])}</h1><div class="sub">Brand Profile from {e(b["source"]["file"])} · {e(b["made"])} · {W:g} × {H:g} px · {len(b["layouts"])} layouts</div>
<h2>Flags: what needs your call ({sum(not x["settled"] for x in calls)} open)</h2><ul>{flags}</ul>{todo_html}
<h2>Brand colors (what slides use)</h2><div class="grid">{sw}</div>
<h2>Theme slots (as declared)</h2><div class="grid">{slots}</div>
<h2>Type</h2>{fonts_html}
<p class="sub">Title {b["type"]["title"]["size"]:g}/{b["type"]["title"]["line"]:g} px · body {b["type"]["body"]["size"]:g}/{b["type"]["body"]["line"]:g} px · margins L {b["margins"]["left"]:g} R {b["margins"]["right"]:g} top {b["margins"]["top"]:g} · footer from y {b["margins"]["footer_top"]:g}</p>
<h2>Patterns → layouts</h2><table>{binds}</table>
<h2>Layouts ({"as PowerPoint draws them" if any(l.get("picture") for l in b["layouts"]) else "drawn from the template's geometry; run `convey brand render` for real pictures"}; blue = placeholders)</h2><div class="grid">{"".join(lays)}</div>
{f"<h2>Inferred from slides (not used until confirmed)</h2><ul>{inferred}</ul>" if inferred else ""}
</main></body></html>"""


def ingest(template, name: str, out: Path | None = None) -> Path:
    out = Path(out) if out else HOME / name
    out.mkdir(parents=True, exist_ok=True)
    raw = read(Path(template))
    brand, _ = decide(raw, name)
    old = out / "brand.json"
    if old.exists():  # keep the person's settlements and the calibration
        prev = json.loads(old.read_text())
        settled = {f["id"]: f for f in prev.get("flags", []) if f.get("settled")}
        for f in brand["flags"]:
            if f["id"] in settled:
                f["settled"] = True
        brand["vertical"] = prev.get("vertical", {})
        pics = {l["name"]: l.get("picture") for l in prev.get("layouts", [])}
        for l in brand["layouts"]:
            if pics.get(l["name"]) and (out / pics[l["name"]]).exists():
                l["picture"] = pics[l["name"]]
        for f in brand["fonts"].values():
            if brand["vertical"].get(f["css"]):
                brand["flags"] = [x for x in brand["flags"] if x["id"] != "calibrate-" + f["css"]]
        # the person's settled values outlive a re-read of the template
        for f in prev.get("flags", []):
            if f.get("settled") and "value" in f and any(x["id"] == f["id"] for x in brand["flags"]):
                settle(brand, f["id"], f["value"])
        if "logo" in prev:
            brand["logo"] = prev["logo"]
    save_assets(raw, brand, out)
    shutil.copy(template, out / ("template" + Path(template).suffix.lower()))
    write(brand, out)
    return out


COLOR_FLAGS = ("raised", "muted", "rule", "signal")
ANYTIME = ("background", "ground", "headline-size", "plate-color", "margin-left", "margin-right")
NARROW = 0.7  # a content area under 70% of the slide's width (896 of 1280 px) is flagged


def settle(brand: dict, flag_id: str, value: str | None = None) -> str:
    """Settle one flag: confirm it as it stands (no value) or set its value. Returns what changed.
    Color flags take a hex color, binding-<pattern> a layout name, pictures "none" or a file in assets/."""
    if flag_id == "plate" and value and re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        flag_id = "plate-color"  # plate=on|off turns it on or off; plate=#RRGGBB is its color
    flag = next((f for f in brand["flags"] if f["id"] == flag_id), None)
    if flag is None and flag_id.startswith("binding-"):
        # The person may point any pattern compose fills by placeholder at any layout, flag or no flag (Oct 18, 2026).
        pat = flag_id[len("binding-"):]
        if pat not in PATTERNS and pat not in NAMED:
            raise ValueError(f'"{pat}" has no design for a company layout yet: its variants draw on the title-only '
                             f'layout. Patterns that can go on any layout: {", ".join([*PATTERNS, *NAMED])}')
        flag = {"id": flag_id, "text": f'Pattern "{pat}": the person chose its layout.', "settled": False}
        brand["flags"].append(flag)
    if flag is None and (flag_id in ANYTIME or flag_id in brand.get("colors", {})):
        # Any brand color, the ground and the headline size can be set with no flag open: a derived color the template
        # never named (Madison's muted) had no way to be corrected (Oct 18, 2026).
        flag = {"id": flag_id, "text": f'"{flag_id}": set by the person.', "settled": False}
        brand["flags"].append(flag)
    if flag is None:
        ids = ", ".join(f["id"] for f in brand["flags"]) or "none"
        raise ValueError(f'no flag "{flag_id}" (open flags: {ids})')
    said = "confirmed as it stands"
    if value is not None and value != "":
        if flag_id == "ground":
            flag_id = "background"
        if flag_id == "plate-color":
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                raise ValueError(f'plate-color needs a color like #1A1A1A, not "{value}"')
            brand["colors"]["plate"] = value.upper()
            brand["colors_from"]["plate"] = "set by the person"
            said = f"plate color = {value.upper()}"
        elif flag_id in COLOR_FLAGS or (flag_id in brand.get("colors", {}) and flag_id != "ground"):
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                raise ValueError(f'{flag_id} needs a color like #383838, not "{value}"')
            brand["colors"][flag_id] = value.upper()
            brand["colors_from"][flag_id] = "set by the person"
            said = f"{flag_id} = {value.upper()}"
        elif flag_id == "background":
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                raise ValueError(f'background needs a color like #9D360E, not "{value}"')
            brand["colors"]["ground"] = value.upper()
            brand["colors_from"]["ground"] = "set by the person"
            said = f"ground = {value.upper()}"
        elif flag_id.startswith("binding-"):
            pat = flag_id[len("binding-"):]
            names = [l["name"] for l in brand["layouts"]]
            hit = next((n for n in names if n.lower() == value.lower()), None)
            if hit is None:
                raise ValueError(f'no layout "{value}"; the layouts are: {", ".join(names)}')
            brand["bindings"][pat] = {"layout": hit, "how": "set by the person"}
            said = f'pattern {pat} uses layout "{hit}"'
        elif flag_id in ("margin-left", "margin-right"):
            W = brand["slide"]["width"]
            if not re.fullmatch(r"\d+(\.\d+)?", value) or not 0 <= float(value) <= W / 3:
                raise ValueError(f'{flag_id} takes a distance in px from 0 to {W / 3:g}, not "{value}"')
            side = flag_id[len("margin-"):]
            # The headline keeps the template's title position (Madison draws a mark left of its title); only the body
            # widens.
            brand["margins"].setdefault(f"title_{side}", brand["margins"][side])
            brand["margins"][side] = float(value)
            brand["margins"]["set"] = True
            brand["flags"] = [f for f in brand["flags"] if f["id"] != "narrow" or f.get("settled")]
            said = f"{flag_id} {float(value):g} px (content width {W - brand['margins']['left'] - brand['margins']['right']:g} px)"
        elif flag_id == "headline-size":
            if not re.fullmatch(r"\d{2}(\.\d+)?", value) or not 24 <= float(value) <= 60:
                raise ValueError(f'headline-size takes a size in px from 24 to 60, not "{value}"')
            brand.setdefault("scale", {})["headline-size"] = float(value)
            said = f"headline size {float(value):g} px (compose then keeps it, fitted or not)"
        elif flag_id == "plate":
            if value.lower() not in ("on", "off"):
                raise ValueError('plate takes on or off')
            value = value.lower()
            brand.setdefault("plate", {}).update({"on": value == "on", "how": f"set by the person ({value})"})
            said = f"plate {value}"
        elif flag_id == "pictures":
            if value.lower() == "none":
                brand["logo"] = None
                said = "no logo"
            else:
                brand["logo"] = value if value.startswith("assets/") else "assets/" + value
                said = f"logo = {brand['logo']}"
        else:
            raise ValueError(f'"{flag_id}" takes no value: settle it with just its name')
        flag["value"] = value
    flag["settled"] = True
    return said


def plate_check(d: Path, b: dict) -> dict | None:
    """Can the template's own background carry small text? Measured on the title-only layout's picture, under the
    content zone, against the body color. Below 4.5:1 (Berlin's orange fade measured about 3:1) the content sits on
    a plate in the raised color: compose draws one under each non-full-bleed slide's content. A person's call on
    the flag (plate=on or off) wins over the measure."""
    from .compose import plain_layout
    from .design import LEGIBLE as _L, ground_sample
    lay = plain_layout({l["name"]: l for l in b["layouts"]})
    pic = d / lay["picture"] if lay and lay.get("picture") else None
    if not pic or not pic.exists():
        return None
    sc, m = pattern_scale(b), b["margins"]
    zone = {"x0": m["left"], "x1": b["slide"]["width"] - m["right"],
            "y0": m["top"] + 2 * sc["headline-line"] + 40, "y1": m["footer_top"] - 24}
    got = ground_sample(pic, b["colors"]["body"], zone)
    if got is None:
        return None
    r = got["contrast"]
    bgf = next((f for f in b["flags"] if f["id"] == "background"), None)
    if bgf and not bgf.get("settled") and got["median"].upper() != b["colors"]["ground"].upper():
        # The rendered background's typical color under the content, offered as the ground (a test agent
        # wrote a PNG decoder to find Berlin's #B84923 and Madison's #2D3A32).
        bgf["text"] = re.sub(r" Measured: .*$", "", bgf["text"]) + (
            f" Measured: the layout picture's typical color under the content is {got['median']}; "
            f"`brand settle {b['name']} background={got['median']}` uses it.")
    flag = next((f for f in b["flags"] if f["id"] == "plate"), None)
    settled = flag.get("value") if flag and flag.get("settled") and flag.get("value") in ("on", "off") else None
    on = settled == "on" if settled else r < _L
    b["plate"] = {"contrast": round(r, 2), "median": got["median"], "on": on,
                  "how": f"set by the person ({settled})" if settled else "measured"}
    if r < _L and not flag:
        b["flags"].append({"id": "plate", "settled": False, "text": (
            f"The template's background under the content measures {r:.1f}:1 against its body color; small text needs "
            f"4.5:1. Slides put their content on a panel in the raised color ({b['colors'].get('raised')}). Settle "
            "plate=off to keep the bare background (lint will then refuse small text there).")})
    return b["plate"]


def write(brand: dict, out: Path):
    c, src = brand["colors"], brand.get("colors_from", {})
    if str(src.get("muted", "")).startswith("derived") and not any(
            f["id"] == "muted" and f.get("value") for f in brand.get("flags", [])):
        c["muted"], src["muted"] = legible_muted(c), DERIVED_MUTED  # follows a settled raised or ground
    plate = (brand.get("plate") or {}).get("on")
    if str(src.get("rule", "")).startswith("derived") and "ink" in c and "ground" in c:
        # Every derived color follows the ground it was derived from: a rule left derived from Madison's declared black
        # read 1.02:1 on its real ground. On a plate, the rule is drawn on the plate's raised color.
        on = "raised" if plate and c.get("raised") else "ground"
        c["rule"], src["rule"] = mix(c["ink"], c[on], 0.22), f"derived: 22% ink over {on}"
    if plate and c.get("raised") and c.get("body") and (src.get("plate") or "derived").startswith("derived"):
        c["plate"], src["plate"] = plate_tone(c), "derived: raised, a step from the body type, so panels show on it"
    elif not plate and str(src.get("plate", "")).startswith("derived"):
        c.pop("plate", None)
        src.pop("plate", None)
    flags = brand.setdefault("flags", [])
    m, W = brand.get("margins") or {}, (brand.get("slide") or {}).get("width", 1280)
    width = W - m.get("left", 0) - m.get("right", 0)
    if m and width < NARROW * W and not m.get("set") and not any(f["id"] == "narrow" for f in flags):
        # Madison's title indent set a 274 px left margin, so every design had 836 px, and nothing said so.
        flags.append({"id": "narrow", "settled": False, "text": (
            f"The content area is {width:g} px wide (left margin {m.get('left', 0):g} px, right {m.get('right', 0):g} px, from "
            f"the title placeholder). The designs are drawn for about 1,000 to 1,150 px, so four cards or a long chart "
            f"crowd. Confirm, or widen it: margin-left=N and margin-right=N (px).")})
    for f in flags:  # a derived color's flag text follows its value
        if f["id"] == "rule" and str(src.get("rule", "")).startswith("derived"):
            f["text"] = re.sub(r"#[0-9A-Fa-f]{6} is derived \([^)]*\)", f"{c['rule']} is derived ({src['rule'][9:]})", f["text"])
    same = plate and c.get("plate") and c.get("plate", "").upper() == str(c.get("raised", "")).upper()
    old = next((f for f in flags if f["id"] == "plate-raised"), None)
    if same and not old:
        flags.append({"id": "plate-raised", "settled": False, "text": (
            f"The content plate and the raised panels are the same color ({c['plate']}), so every card and tile on a "
            "plate vanishes into it. Settle plate-color=#RRGGBB a step lighter or darker, or confirm.")})
    elif old and not same and not old.get("settled"):
        flags.remove(old)
    (out / "brand.json").write_text(json.dumps(brand, indent=1, ensure_ascii=False))
    (out / "tokens.css").write_text(tokens_css(brand))
    (out / "flags.md").write_text(flags_md(brand))
    (out / "brand-sheet.html").write_text(sheet_html(brand))


def faces_for(brand: dict) -> dict:
    """The emitter's face map (fonts.json shape) for a brand, with its calibration."""
    out = {}
    for f in brand["fonts"].values():
        if f["faces"]:
            out[f["css"]] = f["faces"]
    if brand.get("vertical"):
        out["_vertical"] = brand["vertical"]
    return out


def render_layouts(d: Path, b: dict) -> list[str]:
    """Picture every layout as PowerPoint draws it (an empty slide on each), into assets/layouts/.
    The pictures go on the brand sheet and under slides in the browser (data-underlay)."""
    import re as _re
    import tempfile
    from . import powerpoint
    from .skald.ooxml import TemplateDeck
    tpl = next(iter(sorted(d.glob("template.*"))))
    deck = TemplateDeck(tpl)
    names = [l["name"] for l in b["layouts"]]
    for n in names:
        deck.add_slide(n)
    work = Path(tempfile.mkdtemp(prefix="convey-layouts-"))
    deck.save(work / "layouts.pptx")
    pdf = powerpoint.render_pdf(work / "layouts.pptx", work / "layouts.pdf")
    pages = powerpoint.pdf_to_png(pdf, work / "png")
    out = d / "assets" / "layouts"
    out.mkdir(parents=True, exist_ok=True)
    files = []
    for i, (n, page) in enumerate(zip(names, pages), 1):
        fn = f"{i:02d}-{_re.sub(r'[^a-z0-9]+', '-', n.lower()).strip('-')}.png"
        shutil.copy(page, out / fn)
        b["layouts"][i - 1]["picture"] = f"assets/layouts/{fn}"
        files.append(fn)
    return files
