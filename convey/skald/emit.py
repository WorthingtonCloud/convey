"""Scene graph -> native PowerPoint objects.

Reads only the scene (see extract.js). Never looks at the HTML.
1 CSS px = 9525 EMU = 0.75 pt, so a 1280x720 slide is exactly PowerPoint's 16:9 size.
Writes the file with Python's standard library only (ooxml.py).
"""
from __future__ import annotations

from .lines import whole_pt
import math
from urllib.parse import unquote, urlparse

from . import svgpath
from .ooxml import Deck, TemplateDeck, el, q, sub, workbook, xml_bytes

EMU_PER_PX = 9525
PT_PER_PX = 0.75


def emu(v: float) -> int:
    return int(round(v * EMU_PER_PX))


def centipoints(pt: float) -> int:
    """Points -> the hundredths of a point PowerPoint stores (via whole EMUs, 12700 per point)."""
    return int(pt * 12700) // 127


ALIGN = {"left": "l", "center": "ctr", "right": "r", "justify": "just"}


def _solid(parent, hex6, alpha=None):
    f = sub(parent, "a:solidFill")
    c = sub(f, "a:srgbClr", val=hex6.lstrip("#").upper())
    if alpha is not None and alpha < 0.999:
        sub(c, "a:alpha", val=int(round(alpha * 100000)))
    return f


# PowerPoint's blur radius for a CSS blur B: 1.5 x B. Bench d04 (Oct 18, 2026), PowerPoint 16.114's PDF against
# the browser's, mean pixel error by scale: 0.75 -> 1.14 levels, 1.0 -> 0.90, 1.25 -> 0.64, 1.5 -> 0.50, 2.0 -> 0.82.
SHADOW_BLUR = 1.5


def _position(pos, w, h, dw, dh):
    """CSS object-position as fractions (0 = the photo's left/top edge shows, 1 = its right/bottom): "30% 50%",
    keywords, or px offsets measured against the cut-off part. Missing or unreadable: centered."""
    if not pos:
        return 0.5, 0.5
    kw = {"left": "0%", "top": "0%", "center": "50%", "right": "100%", "bottom": "100%"}
    parts = [kw.get(p, p) for p in pos.split()]
    if len(parts) == 1:
        parts.append("50%")
    out = []
    for p, box, drawn in zip(parts[:2], (w, h), (dw, dh)):
        if p.endswith("%"):
            out.append(float(p[:-1]) / 100)
        elif p.endswith("px") and drawn - box > 0.5:
            out.append(min(max(-float(p[:-2]) / (drawn - box), 0), 1))
        else:
            out.append(0.5)
    return out[0], out[1]


def _shadow(parent, sh: dict, opacity: float = 1.0):
    """A CSS box-shadow as PowerPoint's soft outer shadow: the offset as a distance and direction (0 = right,
    clockwise, as y runs down), the blur scaled to PowerPoint's own blur radius."""
    import math
    eff = sub(parent, "a:effectLst")
    dist = math.hypot(sh["x"], sh["y"])
    o = sub(eff, "a:outerShdw", blurRad=emu(sh["blur"] * SHADOW_BLUR), dist=emu(dist),
            dir=int(round((math.degrees(math.atan2(sh["y"], sh["x"])) % 360) * 60000)) if dist else 0,
            algn="ctr", rotWithShape="0")
    c = sub(o, "a:srgbClr", val=sh["color"]["hex"].upper())
    a = sh["color"].get("a", 1) * opacity
    if a < 0.999:
        sub(c, "a:alpha", val=int(round(a * 100000)))
    return o


def dense_stops(stops: list[dict], step: float = 10.0) -> list[dict]:
    """The CSS stops plus one every `step`% between them, colored as the browser blends (straight sRGB). PowerPoint
    blends gradients in linear light, so between two far-apart stops its middle comes out brighter (dark to teal,
    halfway: #15595B in the browser, #007A7C in PowerPoint; bench d01, Oct 18, 2026). Over a short step the two
    blends agree to a level or two."""
    out = []
    for a, b in zip(stops, stops[1:]):
        out.append(a)
        span = b["pos"] - a["pos"]
        n = int(span // step)
        for k in range(1, n + 1):
            t = k / (n + 1)
            ca, cb = [int(a["hex"][i:i + 2], 16) for i in (0, 2, 4)], [int(b["hex"][i:i + 2], 16) for i in (0, 2, 4)]
            # premultiplied, as the browser blends a see-through stop: a fade to clear keeps its color
            aa, ab = a.get("a", 1), b.get("a", 1)
            al = aa + (ab - aa) * t
            rgb = [((x * aa) + ((y * ab) - (x * aa)) * t) / al if al > 1e-6 else x + (y - x) * t for x, y in zip(ca, cb)]
            out.append({"hex": "".join(f"{max(0, min(255, round(v))):02x}" for v in rgb), "a": al, "pos": a["pos"] + span * t})
    out.append(stops[-1])
    return out


def _gradient(parent, g: dict, opacity: float = 1.0):
    """A CSS gradient as PowerPoint's own: stops at their % positions with their alpha; linear at the CSS angle
    (CSS 0deg points up and turns clockwise, PowerPoint 0 points right: ang = css - 90), not scaled with the shape,
    as CSS isn't; radial as a path gradient centred on the CSS position."""
    gf = sub(parent, "a:gradFill", rotWithShape="1")
    lst = sub(gf, "a:gsLst")
    for st in dense_stops(g["stops"]):
        c = sub(sub(lst, "a:gs", pos=int(round(min(max(st["pos"], 0), 100) * 1000))), "a:srgbClr", val=st["hex"].upper())
        a = st.get("a", 1) * opacity
        if a < 0.999:
            sub(c, "a:alpha", val=int(round(a * 100000)))
    if g["kind"] == "linear":
        sub(gf, "a:lin", ang=int(round(((g["angle"] - 90) % 360) * 60000)), scaled="0")
    else:
        path = sub(gf, "a:path", path="circle")
        cx, cy = g.get("cx", 50) * 1000, g.get("cy", 50) * 1000
        sub(path, "a:fillToRect", l=int(cx), t=int(cy), r=int(100000 - cx), b=int(100000 - cy))
    return gf


def predict_advance(v: dict, fs: float) -> float:
    """Px to add after every character so PowerPoint sets a line as wide as the browser does, from a font's measured
    width table (`advance`: [[size, px per character], ...]). PowerPoint lays small text out on its own rounded advances:
    Trebuchet MS at 16 px came out 0.6% narrower and another font at 14 px 0.3% wider, 3 px adrift by the end of a source
    line (design range, Oct 18, 2026). Between measured sizes the nearest one counts: the error follows each size's
    rounding, not a curve."""
    pts = v.get("advance") if v else None
    if not pts or fs > 32:  # display sizes: one sample per size is noise next to the drift (bench t04, Oct 18, 2026)
        return 0.0
    return min(pts, key=lambda p: (abs(p[0] - fs), p[0]))[1]


def predict_drop(v: dict, lh: float, fs: float) -> float:
    """How much lower PowerPoint sets a line than the browser (px), from a font's calibration: its measured table
    (one fit per line-height ratio, interpolated between the two nearest ratios) when it has one, else the
    plain three-number fit. The single fit missed by up to 4 px on tight headlines (48/54 px, Oct 18, 2026)."""
    tab = v.get("table")
    if tab:
        r = lh / fs
        # Only ratios measured at this size count: a ratio sampled from 120 px up says nothing about 48 px text.
        covers = [e for e in tab if "pts" not in e or e["pts"][0][0] <= fs <= e["pts"][-1][0]]
        tab = sorted(covers or tab, key=lambda e: e["r"])
        lo = max([e for e in tab if e["r"] <= r] or tab[:1], key=lambda e: e["r"])
        hi = min([e for e in tab if e["r"] >= r] or tab[-1:], key=lambda e: e["r"])

        def at(e):  # the ratio's measured drop at this size: between its two nearest sizes, held past its ends
            if "pts" not in e:
                return e["a"] * fs + e["c"]
            pts = e["pts"]
            if fs <= pts[0][0]:
                return pts[0][1]
            if fs >= pts[-1][0]:
                return pts[-1][1]
            for (f0, d0), (f1, d1) in zip(pts, pts[1:]):
                if f0 <= fs <= f1:
                    return d0 + (d1 - d0) * (fs - f0) / (f1 - f0)
            return pts[-1][1]
        dl, dh = at(lo), at(hi)
        if hi["r"] == lo["r"]:
            return dl
        w = (r - lo["r"]) / (hi["r"] - lo["r"])
        return dl + (dh - dl) * w
    return v["lh"] * lh + v["fs"] * fs + v["c"]


def _spare_width(t: dict, cl: float, cr: float, align: str) -> float:
    """How much to widen (or, below zero, narrow) a wrapped text's frame so PowerPoint keeps the browser's line breaks.

    PowerPoint sets text a hair wider or narrower than the browser, by font and size. Too wide, and a line the
    browser fills to its box's edge loses its last word (Trebuchet MS at 44 px: +0.55 px over a 919 px line, Berlin
    headline, Oct 18, 2026); too narrow, and a next word that just missed the line gets pulled up (a SemiBold sans at
    40 px: "16%" came up a line, Oct 18, 2026). So the frame's edge goes halfway between the two limits the browser's
    breaks set: the widest line's end (no line may outgrow the frame) and the nearest point where a line's next word
    would have ended (none may fit; a hard break sets no limit). Growth is capped at 0.4% of the frame; with no wrap there
    is only the first limit."""
    width = cr - cl
    widest, nearest = None, None
    for p in (t.get("paras") or [t]):
        words = sorted(p.get("words") or [], key=lambda w: (w["y"], w["x"]))
        lh = p.get("lineHeight") or t.get("lineHeight") or 0
        rows: list[list[dict]] = []
        for w in words:
            if rows and abs(w["y"] - rows[-1][0]["y"]) < max(lh / 2, 1):
                rows[-1].append(w)
            else:
                rows.append([w])
        rows = [sorted(r, key=lambda w: w["x"]) for r in rows]
        gaps = sorted(b["x"] - (a["x"] + a["w"]) for r in rows for a, b in zip(r, r[1:]))
        size = max((r.get("size") or 0 for r in t.get("runs", [])), default=0)
        gap = gaps[len(gaps) // 2] if gaps else size * 0.25
        # each limit as an overshoot past the box: below zero is room to spare
        over = (lambda r: r[-1]["x"] + r[-1]["w"] - cr) if align == "left" else (lambda r: r[-1]["x"] + r[-1]["w"] - r[0]["x"] - width)
        for r in rows:
            widest = over(r) if widest is None else max(widest, over(r))
        for a, b in zip(rows, rows[1:]):
            reach = over(a) + gap + b[0]["w"]
            if reach <= 0:  # the next word would have fitted: a hard break (<br>), not a wrap, so it sets no limit
                continue
            nearest = reach if nearest is None else min(nearest, reach)
    room = width * 0.004
    if nearest is None:
        return room
    return min(room, ((widest or 0) + nearest) / 2)


class Emitter:
    """faces: {family: {weight: [face_name, bold]}} maps CSS weights to installed font faces.
    PowerPoint has no numeric weights, only bold on/off, so weights become named faces.
    Without a map, weight >= 600 becomes bold."""

    def __init__(self, faces: dict | None = None, wrap_slack: float = 0.0, arrow_size: str = "med"):
        faces = dict(faces or {})
        # Per-font vertical calibration: with exact line spacing PowerPoint sets a line lower in its
        # line box than a browser does, by dy = lh*k_lh + fs*k_fs + c (px). Measured per font.
        self.vertical = faces.pop("_vertical", {})
        self.faces = faces
        self.wrap_slack = wrap_slack
        self.arrow_size = arrow_size

    # ---------- deck ----------
    def deck(self, scenes: list[dict], template=None, bindings: dict | None = None, numbers: bool = False,
             notes: dict | None = None) -> Deck:
        """Blank deck, or onto a company template: each slide on its layout (the slide's
        data-layout, else the brand's binding for its data-pattern, else the template's blank
        layout); the headline in the layout's title placeholder; numbers=True adds the layout's
        slide-number placeholder."""
        self.template = TemplateDeck(template) if template else None
        self.bindings = bindings or {}
        self.numbers = numbers
        self.theme_fonts = self.template.theme_fonts if self.template else {}
        d = self.template or Deck(emu(scenes[0]["width"]), emu(scenes[0]["height"]))
        for sc in scenes:
            sl = d.add_slide(self._layout_for(sc)) if self.template else d.add_slide()
            self.slide(sl, sc)
            sl.notes = (notes or {}).get(sc.get("slideId")) or None  # speaker notes, by the slide's data-slide id
        return d

    def _layout_for(self, sc) -> str:
        lays = self.template.layouts
        if sc.get("layout") in lays:
            return sc["layout"]
        b = self.bindings.get(sc.get("pattern") or "")
        name = b["layout"] if isinstance(b, dict) else b
        if name in lays:
            return name
        for n in lays:  # the template's blank layout
            if 'type="blank"' in self.template.parts[lays[n]].decode("utf-8", "replace")[:600]:
                return n
        return next(iter(lays))

    def slide(self, slide, scene: dict):
        if scene.get("background") and not self.template:  # on a template, the layout owns the background
            slide.background(scene["background"]["hex"])
        self._title_ph = None
        if self.template:
            phs = self.template.layout_info(slide.layout_name)
            self._title_ph = next((p for p in phs if p["type"] in ("title", "ctrTitle")), None)
            self._layout_phs = phs
        self._used_phs: set[int] = set()
        self._groups: dict[str, object] = {}
        self._group_parent: dict[str, str | None] = {}
        self._slide = slide
        self._by_id: dict[str, object] = {}
        self._connect: list[tuple[object, dict]] = []
        for e in scene["elements"]:
            k = e["kind"]
            if k == "group":
                self._group_parent[e["id"]] = e.get("group")
            elif k == "box":
                self.box(e)
            elif k == "svg":
                self.svg(e)
            elif k == "image":
                self.image(e)
            elif k == "chart":
                self.chart(e)
        for sh, e in self._connect:
            self._attach(sh, e)
        if self.template and self.numbers:
            sn = next((p for p in self._layout_phs if p["type"] == "sldNum"), None)
            if sn:
                sh = slide.shapes.add_placeholder("sldNum", sn["idx"], name="Slide Number")
                body = sub(sh.element, "p:txBody")
                sub(body, "a:bodyPr")
                sub(body, "a:lstStyle")
                f = sub(sub(body, "a:p"), "a:fld", id="{%08X-0000-4000-8000-%012X}" % (slide.number, slide.number), type="slidenum")
                sub(f, "a:t").text = str(slide.number)

    def _container(self, gid):
        """Groups are created lazily, where their first child paints, so paint order holds."""
        if not gid:
            return self._slide.shapes
        if gid not in self._groups:
            parent = self._container(self._group_parent.get(gid))
            self._groups[gid] = parent.add_group(gid)
        return self._groups[gid]

    # ---------- styling helpers ----------
    @staticmethod
    def _fill(sh, c, opacity=1.0):
        if not c:
            sub(sh.spPr, "a:noFill")
            return
        _solid(sh.spPr, c["hex"], c["a"] * opacity)

    @staticmethod
    def _line(sh, c, width_px, opacity=1.0, dash=None, cap=None, join=None):
        ln = sub(sh.spPr, "a:ln")
        if not c or not width_px:
            sub(ln, "a:noFill")
            return
        ln.set("w", str(emu(width_px)))
        if cap:
            ln.set("cap", {"round": "rnd", "square": "sq"}.get(cap, "flat"))
        _solid(ln, c["hex"], c["a"] * opacity)
        if dash:
            parts = [float(x) for x in dash.replace("px", "").replace(",", " ").split()]
            if len(parts) % 2:
                parts *= 2
            cd = sub(ln, "a:custDash")
            for i in range(0, len(parts), 2):
                sub(cd, "a:ds", d=int(round(parts[i] / width_px * 100000)), sp=int(round(parts[i + 1] / width_px * 100000)))
        # Corners where segments meet: the browser's value, said out loud (PowerPoint's default differs).
        if join == "round":
            sub(ln, "a:round")
        elif join == "bevel":
            sub(ln, "a:bevel")
        elif join in ("miter", "miter-clip", "arcs"):
            sub(ln, "a:miter", lim="400000")

    SIZES = {2: "sm", 3: "med", 5: "lg"}

    def _arrow(self, sh, which, marker=None, kind="triangle"):
        """PowerPoint heads come in 2, 3 or 5 x the line width; extract.js measured which."""
        ln = sh.spPr.find(q("a:ln"))
        w = self.SIZES.get(marker.get("widthMult"), self.arrow_size) if marker else self.arrow_size
        n = self.SIZES.get(marker.get("lenMult"), self.arrow_size) if marker else self.arrow_size
        sub(ln, f"a:{which}", type=kind, w=w, len=n)

    def _attach(self, sh, e):
        """Glue a connector's ends to the boxes it joins (data-from / data-to), without moving it.
        Sites on a rectangle: 0 top, 1 left, 2 bottom, 3 right."""
        cnv = sh.element.find(q("p:nvCxnSpPr")).find(q("p:cNvCxnSpPr"))
        a, b, c, d, tx, ty = e["matrix"]
        at = e["attrs"]
        ends = {"stCxn": (e.get("from"), float(at.get("x1", 0)), float(at.get("y1", 0))),
                "endCxn": (e.get("to"), float(at.get("x2", 0)), float(at.get("y2", 0)))}
        for tag, (target, ux, uy) in ends.items():
            if not target:
                continue
            t = self._by_id.get(target) or self._by_id.get(f"{target}-box") or self._by_id.get(f"{target}-shape")
            if t is None:
                continue
            x, y = (a * ux + c * uy + tx) * EMU_PER_PX, (b * ux + d * uy + ty) * EMU_PER_PX
            L, T, W, H = t.left, t.top, t.width, t.height
            sites = [(L + W / 2, T), (L, T + H / 2), (L + W / 2, T + H), (L + W, T + H / 2)]
            idx = min(range(4), key=lambda i: (sites[i][0] - x) ** 2 + (sites[i][1] - y) ** 2)
            sub(cnv, f"a:{tag}", id=t.shape_id, idx=idx)

    def _face(self, run):
        fam = self.faces.get(run["font"])
        w = run["weight"]
        if fam:
            key = str(min(fam, key=lambda k: abs(int(k) - w)))
            face, bold = fam[key]
            return face, bool(bold)
        return run["font"], w >= 600

    # ---------- text ----------
    def _text(self, sh, t, anchor, insets, align=None, wrap=True, text_left=None, shape=False):
        """Write the shape's text body. text_left: the slide x where the text area starts, for list indents."""
        old = sh.element.find(q("p:txBody"))
        if old is not None:
            sh.element.remove(old)
        body = sub(sh.element, "p:txBody")
        bp = sub(body, "a:bodyPr")
        if shape:
            bp.set("rtlCol", "0")
        bp.set("wrap", "square" if wrap else "none")
        bp.set("anchor", anchor)
        for k, v in zip(("lIns", "rIns", "tIns", "bIns"), insets):
            bp.set(k, str(emu(v)))
        if self.template:  # the layout's own text frame settings must not apply
            bp.set("rot", "0")
            bp.set("vert", "horz")
            bp.set("anchorCtr", "0")
        sub(bp, "a:noAutofit")
        sub(body, "a:lstStyle")
        paras = t.get("paras") or [{"runs": t["runs"], "align": t["align"], "lineHeight": t["lineHeight"]}]
        for i, para in enumerate(paras):
            p = sub(body, "a:p")
            pPr = sub(p, "a:pPr", algn=ALIGN.get((align if len(paras) == 1 else None) or para["align"], "l"))
            # PowerPoint draws exact spacing in whole points (skald/lines.py); the file says what it will draw.
            sub(sub(pPr, "a:lnSpc"), "a:spcPts", val=centipoints(whole_pt(para["lineHeight"]) * PT_PER_PX))
            sub(sub(pPr, "a:spcBef"), "a:spcPts", val=centipoints(max(para.get("spaceBefore", 0), 0) * PT_PER_PX if i else 0))
            sub(sub(pPr, "a:spcAft"), "a:spcPts", val=0)
            bu = para.get("bullet")
            if bu and text_left is not None:
                # The text starts at marL; the bullet hangs at marL + indent (negative).
                pPr.set("marL", str(emu(para["left"] - text_left)))
                pPr.set("indent", str(emu(bu["x"] - para["left"])))
                if bu["color"]:
                    sub(sub(pPr, "a:buClr"), "a:srgbClr", val=bu["color"]["hex"])
                face, _ = self._face(bu)
                sub(pPr, "a:buFont", typeface=face)
                if bu["kind"] == "number":
                    an = sub(pPr, "a:buAutoNum", type="arabicPeriod")
                    if i == 0 and bu.get("start", 1) != 1:
                        an.set("startAt", str(bu["start"]))
                else:
                    sub(pPr, "a:buChar", char=bu["char"])
            else:
                if self.template:
                    pPr.set("marL", "0")
                    pPr.set("indent", "0")
                sub(pPr, "a:buNone")
            for r in para["runs"]:
                if r.get("br"):
                    sub(p, "a:br")
                    continue
                run = sub(p, "a:r")
                face, bold = self._face(r)
                rPr = sub(run, "a:rPr", lang="en-US", sz=centipoints(round(r["size"] * PT_PER_PX * 100) / 100),
                          b=int(bold), i=int(bool(r["italic"])))
                if r["underline"]:
                    rPr.set("u", "sng")
                spc = int(round((r["spacing"] + predict_advance(self._width_cal(r), r["size"])) * PT_PER_PX * 100))
                if spc:
                    rPr.set("spc", str(spc))
                if r["upper"]:
                    rPr.set("cap", "all")
                if self.template:
                    # On a template, inherited styles must not leak in: say every default out loud.
                    rPr.set("kern", "0")
                    rPr.attrib.setdefault("spc", "0")
                    rPr.attrib.setdefault("cap", "none")
                    rPr.attrib.setdefault("u", "none")
                    # The theme's own fonts are named through the theme, so changing the template's
                    # fonts in PowerPoint restyles every slide.
                    if face == self.theme_fonts.get("major"):
                        face = "+mj-lt"
                    elif face == self.theme_fonts.get("minor"):
                        face = "+mn-lt"
                if r["color"]:
                    _solid(rPr, r["color"]["hex"], r["color"]["a"])
                sub(rPr, "a:latin", typeface=face)
                sub(run, "a:t").text = r["text"]

    @staticmethod
    def _empty_text(sh):
        """A preset shape always carries a text body, so PowerPoint lets you type into it."""
        body = sub(sh.element, "p:txBody")
        sub(body, "a:bodyPr", rtlCol="0", anchor="ctr")
        sub(body, "a:lstStyle")
        sub(sub(body, "a:p"), "a:pPr", algn="ctr")

    def _cal(self, run: dict, *parts: str) -> dict | None:
        """The run's font calibration that has any of these parts: the fit for its exact weight ("Family@600") when it
        has one, else the family's (fitted at 400)."""
        for key in (f'{run["font"]}@{run.get("weight", 400)}', run["font"]):
            v = self.vertical.get(key)
            if v and any(p in v for p in parts):
                return v
        return None

    def _width_cal(self, run: dict) -> dict | None:
        """The width table measured for this run's exact weight ("Family@600", or the family's own, measured at 400):
        another weight's advances round differently, and borrowing the 400 table moved weight-500 text the wrong way
        (bench t04, Oct 18, 2026)."""
        weight = int(run.get("weight", 400))
        for key in (f'{run["font"]}@{weight}', run["font"]):
            v = self.vertical.get(key)
            if v and v.get("advance") and int(v.get("advance_weight") or (key.split("@")[1] if "@" in key else 400)) == weight:
                return v
        return None

    def _dy(self, t):
        runs = [r for r in t["runs"] if not r.get("br")]
        if not runs:
            return 0.0
        # A fit for this exact weight ("Family@600") beats the family's (fitted at 400), for families whose faces
        # carry different vertical metrics.
        v = self._cal(runs[0], "table", "lh")
        if not v:
            return 0.0
        fs = max(r["size"] for r in runs)
        return predict_drop(v, whole_pt(t["lineHeight"]), fs)

    def _layout_text(self, t, cl, cr, ct, cb):
        """Decide wrapping, alignment and the text's real extent inside a content box.
        One line in the browser = no wrapping in PowerPoint: PowerPoint measures text a
        hair wider, so a box exactly as wide as its text would push the last word down.
        For one line, alignment comes from where the text actually sits (flexbox can
        center text whose CSS says left)."""
        paras = t.get("paras") or [t]
        one = (len(paras) == 1 and t.get("lines", 0) == 1 and not paras[0].get("bullet")
               and not any(r.get("br") for r in t["runs"]))
        align = t["align"]
        left = cl
        if one and t.get("minX") is not None:
            lg, rg = t["minX"] - cl, cr - t["maxX"]
            if lg > 2 and abs(lg - rg) <= 2:
                align = "center"
            elif lg > 2 and rg <= 2:
                align = "right"
            elif align not in ("center", "right") or (lg <= 2 and rg > 2):
                align, left = "left", t["minX"]
        # A list's bullets hang left of its text: the frame starts at the leftmost bullet.
        marks = [p["bullet"]["x"] for p in paras if p.get("bullet")]
        if marks:
            left = min(left, min(marks))
        top = t["textTop"] if t["textTop"] is not None else ct
        bottom = t["textBottom"] if t["textBottom"] is not None else cb
        return one, align, left, top, bottom, self._dy(t)

    # ---------- boxes (HTML elements) ----------
    def box(self, e):
        shapes = self._container(e.get("group"))
        x, y, w, h = e["x"], e["y"], e["w"], e["h"]
        b = e["borders"]
        uniform = all(b) and len({(s["w"], s["color"]["hex"], s["color"]["a"]) for s in b}) == 1
        draws = bool(e["fill"] or any(b))
        t = e.get("text")

        if t:
            pad = t["pad"]
            cl, cr, ct, cb = x + pad["l"], x + w - pad["r"], y + pad["t"], y + h - pad["b"]
            one, align, left, top, bottom, dy = self._layout_text(t, cl, cr, ct, cb)

        if not draws and t:
            # Plain text: the frame covers the measured line boxes, insets zero.
            tx, tw = left, cr - left
            s = self.wrap_slack + _spare_width(t, cl, cr, align) if not one else 0
            if s:
                if align == "center":
                    tx, tw = tx - s / 2, tw + s
                elif align == "right":
                    tx, tw = tx - s, tw + s
                else:
                    tw = tw + s
            ph = None
            if self._title_ph and e.get("bind") == "headline" and not e.get("group"):
                ph, self._title_ph = self._title_ph, None  # one title per slide
            elif self.template and e.get("ph") is not None and not e.get("group"):
                # data-ph="N": the text fills the layout's own placeholder N (each one once).
                ph = next((p for p in self._layout_phs if p["idx"] == e["ph"] and p["type"] not in ("title", "ctrTitle")
                           and p["idx"] not in self._used_phs), None)
            if ph:
                self._used_phs.add(ph["idx"])
                sh = shapes.add_placeholder(ph["type"], ph["idx"], emu(tx), emu(top - dy), emu(tw), emu(bottom - top))
            else:
                sh = shapes.add_textbox(emu(tx), emu(top - dy), emu(tw), emu(bottom - top))
            sh.name = e["id"]
            self._text(sh, t, "t", (0, 0, 0, 0), align, wrap=not one, text_left=tx)
            if e.get("rot"):
                self._rotate(sh, e, top - dy, bottom - top, tx, tw)
            self._by_id[e["id"]] = sh
            return

        inset = b[0]["w"] / 2 if uniform else 0
        gx, gy, gw, gh = x + inset, y + inset, w - 2 * inset, h - 2 * inset
        r = max(e["radius"] - inset, 0)
        if e.get("ellipse"):
            kind = "ellipse"
        elif r > 0:
            kind = "roundRect"
        else:
            kind = "rect"

        # PowerPoint's own text area inside each preset shape (presetShapeDefinitions.xml):
        # a rounded rectangle insets it by 0.29289 x radius, an ellipse by 0.14645 x size.
        adj = min(r / min(gw, gh), 0.5) if kind == "roundRect" else 0
        if kind == "roundRect":
            ix = iy = adj * min(gw, gh) * 0.29289
        elif kind == "ellipse":
            ix, iy = gw * 0.14645, gh * 0.14645
        else:
            ix = iy = 0

        split = False
        if t:
            top_gap, bottom_gap = top - ct, cb - bottom
            centered = top_gap > 1 and abs(top_gap - bottom_gap) < 1
            l = left - gx - ix
            rr = gx + gw - cr - ix
            # dy: PowerPoint sets lines lower than the browser; raise the text by that much.
            if centered:
                anchor, tins, bins = "ctr", top - dy - gy - iy, gy + gh - bottom + dy - iy
            else:
                anchor, tins, bins = "t", top - dy - gy - iy, 0
            split = min(l, rr, tins, bins) < -0.01

        container = shapes
        if split:
            container = shapes.add_group(e["id"])
        sh = container.add_shape(kind, emu(gx), emu(gy), emu(gw), emu(gh), adj if kind == "roundRect" else None)
        sh.name = f"{e['id']}-shape" if split else e["id"]
        if e.get("gradient"):
            _gradient(sh.spPr, e["gradient"], e["opacity"])
        else:
            self._fill(sh, e["fill"], e["opacity"])
        if uniform:
            self._line(sh, b[0]["color"], b[0]["w"], e["opacity"])
        else:
            self._line(sh, None, 0)
        if e.get("shadow"):
            _shadow(sh.spPr, e["shadow"], e["opacity"])

        if t and not split:
            self._text(sh, t, anchor, (l, rr, tins, bins), align, wrap=not one, text_left=gx + ix + l, shape=True)
        else:
            self._empty_text(sh)
            if t:
                tb = container.add_textbox(emu(left), emu(top - dy), emu(cr - left), emu(bottom - top))
                tb.name = f"{e['id']}-text"
                self._text(tb, t, "t", (0, 0, 0, 0), align, wrap=not one, text_left=left)
        if e.get("rot"):
            sh.rotate(e["rot"])
        self._by_id[e["id"]] = sh

        if not uniform:
            sides = [
                (b[0], x, y, w, b[0]["w"] if b[0] else 0),
                (b[1], x + w - (b[1]["w"] if b[1] else 0), y, b[1]["w"] if b[1] else 0, h),
                (b[2], x, y + h - (b[2]["w"] if b[2] else 0), w, b[2]["w"] if b[2] else 0),
                (b[3], x, y, b[3]["w"] if b[3] else 0, h),
            ]
            for i, (side, sx, sy, sw, shh) in enumerate(sides):
                if not side:
                    continue
                bs = shapes.add_shape("rect", emu(sx), emu(sy), emu(sw), emu(shh))
                bs.name = f"{e['id']}-border-{'trbl'[i]}"
                self._fill(bs, side["color"], e["opacity"])
                self._line(bs, None, 0)
                self._empty_text(bs)

    def _rotate(self, sh, e, y, h, x, w):
        """CSS rotates the element about its own center; PowerPoint rotates a frame about the
        frame's center. Move the frame's center to where the CSS rotation puts it, then rotate."""
        th = math.radians(e["rot"])
        ecx, ecy = e["x"] + e["w"] / 2, e["y"] + e["h"] / 2
        ox, oy = x + w / 2 - ecx, y + h / 2 - ecy
        cx, cy = ecx + ox * math.cos(th) - oy * math.sin(th), ecy + ox * math.sin(th) + oy * math.cos(th)
        sh.left, sh.top = emu(cx - w / 2), emu(cy - h / 2)
        sh.rotate(e["rot"])

    # ---------- charts ----------
    def chart(self, e):
        spec, P = e["spec"], e["plot"]
        # chart.js resolves font and colors from the slide's CSS; these are geometry fallbacks.
        o = {"fontSize": 12, "fontWeight": 400, "gridWidth": 1, "gap": 80, "lineWidth": 2.5, "hole": 60, **spec}
        shapes = self._container(e.get("group"))
        cats, series = spec["categories"], [(s_["name"], s_["values"]) for s_ in spec["series"]]
        face, bold = self._face({"font": o["font"], "weight": o["fontWeight"]})
        kind = spec["type"]

        cs = el("c:chartSpace")
        sub(cs, "c:date1904", val=0)
        sub(cs, "c:roundedCorners", val=0)
        ch = sub(cs, "c:chart")
        sub(ch, "c:autoTitleDeleted", val=1)
        pa = sub(ch, "c:plotArea")
        # The plot area exactly where chart.js drew it (fractions of the chart frame).
        ml = sub(sub(pa, "c:layout"), "c:manualLayout")
        for tag, val in (("layoutTarget", "inner"), ("xMode", "edge"), ("yMode", "edge"),
                         ("x", P["x"] / e["w"]), ("y", P["y"] / e["h"]), ("w", P["w"] / e["w"]), ("h", P["h"] / e["h"])):
            sub(ml, f"c:{tag}", val=val)

        stacked = bool(spec.get("stacked")) and kind in ("column", "bar")
        if kind in ("column", "bar"):
            plot = sub(pa, "c:barChart")
            sub(plot, "c:barDir", val="col" if kind == "column" else "bar")
            sub(plot, "c:grouping", val="stacked" if stacked else "clustered")
            sub(plot, "c:varyColors", val=0)
        elif kind == "line":
            plot = sub(pa, "c:lineChart")
            sub(plot, "c:grouping", val="standard")
            sub(plot, "c:varyColors", val=0)
        elif kind == "area":
            plot = sub(pa, "c:areaChart")
            sub(plot, "c:grouping", val="standard")
            sub(plot, "c:varyColors", val=0)
        else:
            plot = sub(pa, "c:doughnutChart")
            sub(plot, "c:varyColors", val=1)

        n = len(cats)
        for j, (s_, (name, vals)) in enumerate(zip(spec["series"], series)):
            ser = sub(plot, "c:ser")
            sub(ser, "c:idx", val=j)
            sub(ser, "c:order", val=j)
            col = chr(66 + j)
            sr = sub(sub(ser, "c:tx"), "c:strRef")
            sub(sr, "c:f").text = f"Sheet1!${col}$1"
            sc = sub(sr, "c:strCache")
            sub(sc, "c:ptCount", val=1)
            sub(sub(sc, "c:pt", idx=0), "c:v").text = str(name)
            if kind == "area":
                sp = sub(ser, "c:spPr")
                _solid(sp, s_["color"], s_.get("opacity"))
                sub(sub(sp, "a:ln"), "a:noFill")
            elif kind in ("column", "bar"):
                sp = sub(ser, "c:spPr")
                _solid(sp, s_["color"])
                sub(sub(sp, "a:ln"), "a:noFill")
                sub(ser, "c:invertIfNegative", val=0)
                if len(series) == 1:  # one series may color each bar (a data point) on its own
                    for i, colr in enumerate(spec.get("colors", [])[:n]):
                        dpt = sub(ser, "c:dPt")
                        sub(dpt, "c:idx", val=i)
                        sub(dpt, "c:invertIfNegative", val=0)
                        sub(dpt, "c:bubble3D", val=0)
                        sp = sub(dpt, "c:spPr")
                        _solid(sp, colr)
                        sub(sub(sp, "a:ln"), "a:noFill")
            elif kind == "line":
                sp = sub(ser, "c:spPr")
                ln = sub(sp, "a:ln", w=emu(o["lineWidth"]), cap="rnd")
                _solid(ln, s_["color"])
                sub(ln, "a:round")
                sub(sub(ser, "c:marker"), "c:symbol", val="none")
            else:
                for i, colr in enumerate(spec.get("colors", [])):
                    dpt = sub(ser, "c:dPt")
                    sub(dpt, "c:idx", val=i)
                    sp = sub(dpt, "c:spPr")
                    _solid(sp, colr)
                    sub(sub(sp, "a:ln"), "a:noFill")
            cr = sub(sub(ser, "c:cat"), "c:strRef")
            sub(cr, "c:f").text = f"Sheet1!$A$2:$A${n + 1}"
            cc = sub(cr, "c:strCache")
            sub(cc, "c:ptCount", val=n)
            for i, cat in enumerate(cats):
                sub(sub(cc, "c:pt", idx=i), "c:v").text = str(cat)
            nr = sub(sub(ser, "c:val"), "c:numRef")
            sub(nr, "c:f").text = f"Sheet1!${col}$2:${col}${n + 1}"
            nc = sub(nr, "c:numCache")
            sub(nc, "c:formatCode").text = "General"
            sub(nc, "c:ptCount", val=n)
            for i, v in enumerate(vals):
                if v is not None:
                    sub(sub(nc, "c:pt", idx=i), "c:v").text = str(v)
            if kind == "line":
                sub(ser, "c:smooth", val=0)

        if kind == "doughnut":
            dl = sub(plot, "c:dLbls")
            for tag in ("showLegendKey", "showVal", "showCatName", "showSerName", "showPercent", "showBubbleSize"):
                sub(dl, f"c:{tag}", val=0)
            sub(dl, "c:showLeaderLines", val=1)
            sub(plot, "c:firstSliceAng", val=0)
            sub(plot, "c:holeSize", val=int(o["hole"]))
        else:
            if kind in ("column", "bar"):
                sub(plot, "c:gapWidth", val=int(o["gap"]))
                sub(plot, "c:overlap", val=100 if stacked else 0)
            elif kind == "line":
                sub(plot, "c:marker", val=1)
            sub(plot, "c:axId", val=1001)
            sub(plot, "c:axId", val=1002)
            ax = spec["axis"]
            pre, _, suf = ax.get("format", "{v}").partition("{v}")
            fmt = (f'"{pre}"' if pre else "") + "General" + (f'"{suf}"' if suf else "")
            for axis in ("cat", "val"):
                a = sub(pa, f"c:{axis}Ax")
                sub(a, "c:axId", val=1001 if axis == "cat" else 1002)
                scl = sub(a, "c:scaling")
                # Horizontal bars read top to bottom: the category axis runs from the top (maxMin).
                sub(scl, "c:orientation", val="maxMin" if (kind == "bar" and axis == "cat") else "minMax")
                if axis == "val":
                    sub(scl, "c:max", val=float(ax["max"]))
                    sub(scl, "c:min", val=float(ax["min"]))
                sub(a, "c:delete", val=0)
                sub(a, "c:axPos", val=("l" if axis == "cat" else "b") if kind == "bar" else ("b" if axis == "cat" else "l"))
                if axis == "val":
                    gl = sub(sub(sub(a, "c:majorGridlines"), "c:spPr"), "a:ln", w=emu(o["gridWidth"]))
                    _solid(gl, o["gridColor"])
                    sub(a, "c:numFmt", formatCode=fmt, sourceLinked=0)
                sub(a, "c:majorTickMark", val="none")
                sub(a, "c:minorTickMark", val="none")
                # Category labels sit below the plot ("low"), as chart.js draws them; "nextTo" puts them on the
                # zero line, over the bars, whenever a value is negative (seen on a real deck, Oct 18, 2026).
                sub(a, "c:tickLblPos", val="low" if axis == "cat" else "nextTo")
                sub(sub(sub(a, "c:spPr"), "a:ln"), "a:noFill")
                sub(a, "c:crossAx", val=1002 if axis == "cat" else 1001)
                # With the categories reversed, the value axis crosses at the last one, so it stays at the bottom.
                sub(a, "c:crosses", val="max" if (kind == "bar" and axis == "val") else "autoZero")
                if axis == "cat":
                    sub(a, "c:auto", val=1)
                    sub(a, "c:lblAlgn", val="ctr")
                    sub(a, "c:lblOffset", val=100)
                    sub(a, "c:noMultiLvlLbl", val=0)
                else:
                    sub(a, "c:crossBetween", val="between")
                    sub(a, "c:majorUnit", val=float(ax["step"]))
        sub(ch, "c:plotVisOnly", val=1)
        sub(ch, "c:dispBlanksAs", val="gap")
        # No chart-area fill or border.
        sp = sub(cs, "c:spPr")
        sub(sp, "a:noFill")
        sub(sub(sp, "a:ln"), "a:noFill")
        tp = sub(cs, "c:txPr")
        sub(tp, "a:bodyPr")
        sub(tp, "a:lstStyle")
        p = sub(tp, "a:p")
        dr = sub(sub(p, "a:pPr"), "a:defRPr", sz=centipoints(o["fontSize"] * PT_PER_PX), b=int(bold))
        _solid(dr, o["labelColor"])
        sub(dr, "a:latin", typeface=face)
        sub(p, "a:endParaRPr", lang="en-US")
        sub(sub(cs, "c:externalData", r_id="rId1"), "c:autoUpdate", val=0)

        gf = shapes.add_chart(xml_bytes(cs), workbook(cats, series), emu(e["x"]), emu(e["y"]), emu(e["w"]), emu(e["h"]))
        gf.name = e["id"]

    # ---------- SVG ----------
    def svg(self, e):
        shapes = self._container(e.get("group"))
        a, b, c, d, tx, ty = e["matrix"]
        at = e["attrs"]
        num = lambda k, dflt=0.0: float(str(at.get(k, dflt)).replace("px", "") or dflt)
        axis = abs(b) < 1e-9 and abs(c) < 1e-9
        scale = (abs(a * d - b * c)) ** 0.5
        sw = e["strokeWidth"] * scale
        tag = e["tag"]

        def P(px_, py_):
            return a * px_ + c * py_ + tx, b * px_ + d * py_ + ty

        if tag == "line":
            x1, y1 = P(num("x1"), num("y1"))
            x2, y2 = P(num("x2"), num("y2"))
            sh = shapes.add_connector(emu(x1), emu(y1), emu(x2), emu(y2))
            sh.name = e["id"]
            self._line(sh, e["stroke"], sw, e["opacity"] * e["strokeOpacity"], e["dash"], e["cap"], e.get("join"))
            if e.get("markerStart"):
                self._arrow(sh, "headEnd", e["markerStart"])
            if e.get("markerEnd"):
                self._arrow(sh, "tailEnd", e["markerEnd"])
            if e.get("from") or e.get("to"):
                self._connect.append((sh, e))
            self._by_id[e["id"]] = sh
            return

        if axis and tag in ("rect", "circle", "ellipse"):
            if tag == "rect":
                x0, y0 = P(num("x"), num("y"))
                w, h = num("width") * a, num("height") * d
                rx = num("rx", 0) * a or num("ry", 0) * d
                kind = "roundRect" if rx > 0 else "rect"
            else:
                cx, cy = P(num("cx"), num("cy"))
                rx_, ry_ = (num("r"), num("r")) if tag == "circle" else (num("rx"), num("ry"))
                w, h = 2 * rx_ * a, 2 * ry_ * d
                x0, y0 = cx - w / 2, cy - h / 2
                kind, rx = "ellipse", 0
            sh = shapes.add_shape(kind, emu(x0), emu(y0), emu(w), emu(h),
                                  min(rx / min(w, h), 0.5) if kind == "roundRect" else None)
            sh.name = e["id"]
            self._fill(sh, e["fill"], e["opacity"] * e["fillOpacity"])
            self._line(sh, e["stroke"], sw, e["opacity"] * e["strokeOpacity"], e["dash"], e["cap"], e.get("join"))
            self._empty_text(sh)
            self._by_id[e["id"]] = sh
            return

        self.freeform(shapes, e, sw)

    def freeform(self, shapes, e, sw):
        at = e["attrs"]
        tag = e["tag"]
        if tag == "path":
            d = at["d"]
        elif tag in ("polyline", "polygon"):
            pts = at["points"].replace(",", " ").split()
            d = "M " + " L ".join(f"{pts[i]} {pts[i + 1]}" for i in range(0, len(pts) - 1, 2))
            d += " Z" if tag == "polygon" else ""
        elif tag == "rect":
            x, y, w, h = (float(at.get(k, 0)) for k in ("x", "y", "width", "height"))
            d = f"M{x} {y} h{w} v{h} h{-w} Z"
        else:  # circle / ellipse under a skew or rotation
            cx, cy = float(at.get("cx", 0)), float(at.get("cy", 0))
            rx = float(at.get("r", at.get("rx", 0)))
            ry = float(at.get("r", at.get("ry", 0)))
            d = f"M{cx - rx} {cy} A{rx} {ry} 0 1 0 {cx + rx} {cy} A{rx} {ry} 0 1 0 {cx - rx} {cy} Z"
        segs = svgpath.parse(d, e["matrix"])
        pts = [p for s in segs for p in s[1:]]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        x0, y0 = min(xs), min(ys)
        w, h = max(max(xs) - x0, 0.01), max(max(ys) - y0, 0.01)

        sh = shapes.add_shape("rect", emu(x0), emu(y0), emu(w), emu(h))
        sh.name = e["id"]
        spPr = sh.spPr
        prst = spPr.find(q("a:prstGeom"))
        cust = el("a:custGeom")
        for tagname in ("a:avLst", "a:gdLst", "a:ahLst", "a:cxnLst"):
            sub(cust, tagname)
        sub(cust, "a:rect", l=0, t=0, r="r", b="b")
        pe = sub(sub(cust, "a:pathLst"), "a:path", w=emu(w), h=emu(h))
        if not e["fill"]:
            pe.set("fill", "none")

        def pt(parent, p):
            sub(parent, "a:pt", x=emu(p[0] - x0), y=emu(p[1] - y0))

        names = {"M": "a:moveTo", "L": "a:lnTo", "C": "a:cubicBezTo", "Q": "a:quadBezTo"}
        for s in segs:
            if s[0] == "Z":
                sub(pe, "a:close")
            else:
                node = sub(pe, names[s[0]])
                for p in s[1:]:
                    pt(node, p)
        i = list(spPr).index(prst)
        spPr.remove(prst)
        spPr.insert(i, cust)
        self._fill(sh, e["fill"], e["opacity"] * e["fillOpacity"])
        self._line(sh, e["stroke"], sw, e["opacity"] * e["strokeOpacity"], e["dash"], e["cap"], e.get("join"))
        if e.get("markerStart"):
            self._arrow(sh, "headEnd", e["markerStart"])
        if e.get("markerEnd"):
            self._arrow(sh, "tailEnd", e["markerEnd"])
        self._empty_text(sh)

    # ---------- images ----------
    def image(self, e):
        shapes = self._container(e.get("group"))
        bx = e.get("box") or {}
        if bx.get("fill") or any(bx.get("borders") or []):
            # The element's own background or border, behind the picture (letterboxing shows it).
            self.box({"id": f"{e['id']}-frame", "kind": "box", "group": e.get("group"), "x": e["x"], "y": e["y"],
                      "w": e["w"], "h": e["h"], "rot": e.get("rot", 0), "opacity": e.get("opacity", 1), **bx})
        src = e["src"]
        path = unquote(urlparse(src).path) if src.startswith("file:") else src
        x, y, w, h = e["x"], e["y"], e["w"], e["h"]
        nw, nh = e["natural"]["w"], e["natural"]["h"]
        fit = e.get("fit", "fill")
        crop = (0, 0, 0, 0)
        if fit == "cover" and nw and nh:
            k = max(w / nw, h / nh)
            tx, ty = (nw - w / k) / nw, (nh - h / k) / nh  # how much of the photo is cut, across and down
            fx, fy = _position(e.get("position"), w, h, nw * k, nh * k)  # object-position: which part shows
            crop = (tx * fx, ty * fy, tx * (1 - fx), ty * (1 - fy))
        elif fit in ("contain", "scale-down") and nw and nh:
            k = min(w / nw, h / nh, 1 if fit == "scale-down" else 1e9)
            dw, dh = nw * k, nh * k
            x, y, w, h = x + (w - dw) / 2, y + (h - dh) / 2, dw, dh
        elif fit == "none" and nw and nh:
            x, y, w, h = x + (w - nw) / 2, y + (h - nh) / 2, nw, nh
        geom, adj = "rect", None
        if fit in ("cover", "fill") and bx.get("ellipse"):
            geom = "ellipse"
        elif fit in ("cover", "fill") and bx.get("radius"):
            geom, adj = "roundRect", min(bx["radius"] / min(w, h), 0.5)
        pic = shapes.add_picture(path, emu(x), emu(y), emu(w), emu(h), crop, geom, adj)
        pic.name = e["id"]
        if bx.get("shadow"):
            _shadow(pic.spPr, bx["shadow"], e.get("opacity", 1))
        if e.get("rot"):
            pic.rotate(e["rot"])
        self._by_id[e["id"]] = pic
