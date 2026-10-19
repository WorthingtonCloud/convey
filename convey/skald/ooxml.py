"""Write a .pptx with nothing but Python's standard library.

A .pptx is a zip of XML parts tied together by relationship files. This module holds the
blank-deck skeleton (theme, master, one blank layout), the shape-tree XML helpers the emitter
uses, the chart part, and the tiny spreadsheet each chart carries so PowerPoint's
"Edit Data" works. Nothing here knows about HTML or any brand.
"""
from __future__ import annotations

import hashlib
import io
import posixpath
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
}
for _k, _v in NS.items():
    ET.register_namespace(_k, _v)

REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
CT_PML = "application/vnd.openxmlformats-officedocument.presentationml"
CT_DML = "application/vnd.openxmlformats-officedocument.drawingml"
CHART_URI = NS["c"]
ZIP_TIME = (1980, 1, 1, 0, 0, 0)  # fixed, so the same slides always make the same file


def q(tag: str) -> str:
    """'a:off' -> '{namespace}off'."""
    prefix, local = tag.split(":")
    return f"{{{NS[prefix]}}}{local}"


def sub(parent: ET.Element, tag: str, **attrs) -> ET.Element:
    """Append a child. Attribute names may carry a prefix (r_embed -> r:embed)."""
    el = ET.SubElement(parent, q(tag))
    for k, v in attrs.items():
        el.set(q(k.replace("_", ":", 1)) if k.startswith("r_") else k, str(v))
    return el


def el(tag: str, **attrs) -> ET.Element:
    e = ET.Element(q(tag))
    for k, v in attrs.items():
        e.set(k, str(v))
    return e


def xml_bytes(root: ET.Element) -> bytes:
    return b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + ET.tostring(root, encoding="utf-8")


def _rels(rels: list[tuple[str, str, str]]) -> bytes:
    root = ET.Element(f"{{{PKG_REL}}}Relationships")
    for rid, typ, target in rels:
        r = ET.SubElement(root, f"{{{PKG_REL}}}Relationship")
        r.set("Id", rid)
        r.set("Type", f"{REL}/{typ}" if "://" not in typ else typ)
        r.set("Target", target)
    return b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + ET.tostring(root, encoding="utf-8")


def _zip(parts: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in parts.items():
            zi = zipfile.ZipInfo(name, ZIP_TIME)
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, data)
    return buf.getvalue()


# ---------------------------------------------------------------- shape tree

class Shape:
    """One drawn object: its XML element plus the frame the emitter reads back
    (connectors glue to a shape's id and edges)."""

    def __init__(self, element: ET.Element, shape_id: int, nv: ET.Element, xfrm: ET.Element):
        self.element, self.shape_id, self._nv, self._xfrm = element, shape_id, nv, xfrm

    @property
    def name(self):
        return self._nv.get("name")

    @name.setter
    def name(self, v):
        self._nv.set("name", v)

    def _pos(self, i):
        node = self._xfrm.find(q("a:off") if i < 2 else q("a:ext"))
        return int(node.get(("x", "y", "cx", "cy")[i]))

    def _set(self, i, v):
        node = self._xfrm.find(q("a:off") if i < 2 else q("a:ext"))
        node.set(("x", "y", "cx", "cy")[i], str(int(v)))

    left = property(lambda s: s._pos(0), lambda s, v: s._set(0, v))
    top = property(lambda s: s._pos(1), lambda s, v: s._set(1, v))
    width = property(lambda s: s._pos(2))
    height = property(lambda s: s._pos(3))

    def rotate(self, degrees: float):
        """Clockwise degrees, stored as 60000ths of a degree in 0..360."""
        rot = int(round(degrees * 60000)) % (360 * 60000)
        if rot:
            self._xfrm.set("rot", str(rot))
        elif "rot" in self._xfrm.attrib:
            del self._xfrm.attrib["rot"]

    @property
    def spPr(self):
        return self.element.find(q("p:spPr"))


def _frame(parent, tag, x, y, w, h):
    xfrm = sub(parent, tag)
    sub(xfrm, "a:off", x=int(x), y=int(y))
    sub(xfrm, "a:ext", cx=int(w), cy=int(h))
    return xfrm


class ShapeTree:
    """The slide's spTree or a group's grpSp. Ids are shared across the whole slide."""

    def __init__(self, element: ET.Element, slide: "Slide"):
        self.element, self.slide = element, slide

    def _nv(self, sp, nvtag, cnvtag, name, **cnv_attrs):
        nv = sub(sp, nvtag)
        sid = self.slide.next_id()
        cnv = sub(nv, "p:cNvPr", id=sid, name=name)
        for k, v in cnv_attrs.items():
            cnv.set(k, v)
        return nv, cnv, sid

    def add_shape(self, prst: str, x, y, w, h, adj: float | None = None) -> Shape:
        sp = sub(self.element, "p:sp")
        nv, cnv, sid = self._nv(sp, "p:nvSpPr", "p:cNvSpPr", "")
        sub(nv, "p:cNvSpPr")
        sub(nv, "p:nvPr")
        spPr = sub(sp, "p:spPr")
        xfrm = _frame(spPr, "a:xfrm", x, y, w, h)
        geom = sub(spPr, "a:prstGeom", prst=prst)
        av = sub(geom, "a:avLst")
        if adj is not None:
            sub(av, "a:gd", name="adj", fmla=f"val {int(adj * 100000)}")
        return Shape(sp, sid, cnv, xfrm)

    def add_placeholder(self, ph_type: str, idx: int | None, x=None, y=None, w=None, h=None, name="") -> Shape:
        """A shape that fills one of the layout's placeholders. With a frame it sits there; without
        one it inherits the layout's position (footers, slide numbers)."""
        sp = sub(self.element, "p:sp")
        nv, cnv, sid = self._nv(sp, "p:nvSpPr", "p:cNvSpPr", name)
        sub(sub(nv, "p:cNvSpPr"), "a:spLocks", noGrp="1")
        ph = sub(sub(nv, "p:nvPr"), "p:ph", type=ph_type)
        if idx:
            ph.set("idx", str(idx))
        spPr = sub(sp, "p:spPr")
        xfrm = _frame(spPr, "a:xfrm", x, y, w, h) if x is not None else el("a:xfrm")
        return Shape(sp, sid, cnv, xfrm)

    def add_textbox(self, x, y, w, h) -> Shape:
        sp = sub(self.element, "p:sp")
        nv, cnv, sid = self._nv(sp, "p:nvSpPr", "p:cNvSpPr", "")
        sub(nv, "p:cNvSpPr", txBox="1")
        sub(nv, "p:nvPr")
        spPr = sub(sp, "p:spPr")
        xfrm = _frame(spPr, "a:xfrm", x, y, w, h)
        sub(sub(spPr, "a:prstGeom", prst="rect"), "a:avLst")
        sub(spPr, "a:noFill")
        return Shape(sp, sid, cnv, xfrm)

    def add_connector(self, x1, y1, x2, y2) -> Shape:
        """A straight connector from (x1, y1) to (x2, y2): a frame plus flips."""
        sp = sub(self.element, "p:cxnSp")
        nv, cnv, sid = self._nv(sp, "p:nvCxnSpPr", "p:cNvCxnSpPr", "")
        sub(nv, "p:cNvCxnSpPr")
        sub(nv, "p:nvPr")
        spPr = sub(sp, "p:spPr")
        xfrm = _frame(spPr, "a:xfrm", min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
        if x2 < x1:
            xfrm.set("flipH", "1")
        if y2 < y1:
            xfrm.set("flipV", "1")
        sub(sub(spPr, "a:prstGeom", prst="line"), "a:avLst")
        return Shape(sp, sid, cnv, xfrm)

    def add_group(self, name: str) -> "Group":
        g = sub(self.element, "p:grpSp")
        nv, cnv, sid = self._nv(g, "p:nvGrpSpPr", "p:cNvGrpSpPr", name)
        sub(nv, "p:cNvGrpSpPr")
        sub(nv, "p:nvPr")
        sub(g, "p:grpSpPr")
        grp = Group(g, self.slide)
        grp.shape_id = sid
        self.slide.groups.append(grp)
        return grp

    def add_picture(self, path, x, y, w, h, crop=(0, 0, 0, 0), geom: str = "rect", adj: float | None = None) -> Shape:
        rid = self.slide.add_image(Path(path))
        pic = sub(self.element, "p:pic")
        nv, cnv, sid = self._nv(pic, "p:nvPicPr", "p:cNvPicPr", "", descr=Path(path).name)
        sub(sub(nv, "p:cNvPicPr"), "a:picLocks", noChangeAspect="1")
        sub(nv, "p:nvPr")
        bf = sub(pic, "p:blipFill")
        sub(bf, "a:blip", r_embed=rid)
        sr = sub(bf, "a:srcRect")
        if any(crop):
            for side, v in zip("ltrb", crop):
                if v:
                    sr.set(side, str(int(round(v * 100000))))
        sub(sub(bf, "a:stretch"), "a:fillRect")
        spPr = sub(pic, "p:spPr")
        xfrm = _frame(spPr, "a:xfrm", x, y, w, h)
        # The picture's own outline: a rounded or circular frame crops the photo the way CSS border-radius does.
        av = sub(sub(spPr, "a:prstGeom", prst=geom), "a:avLst")
        if geom == "roundRect" and adj is not None:
            sub(av, "a:gd", name="adj", fmla=f"val {int(round(adj * 100000))}")
        return Shape(pic, sid, cnv, xfrm)

    def add_chart(self, chart_xml: bytes, workbook: bytes, x, y, w, h) -> Shape:
        rid = self.slide.add_chart(chart_xml, workbook)
        gf = sub(self.element, "p:graphicFrame")
        nv, cnv, sid = self._nv(gf, "p:nvGraphicFramePr", "p:cNvGraphicFramePr", "")
        sub(sub(nv, "p:cNvGraphicFramePr"), "a:graphicFrameLocks", noGrp="1")
        sub(nv, "p:nvPr")
        xfrm = _frame(gf, "p:xfrm", x, y, w, h)
        gd = sub(sub(gf, "a:graphic"), "a:graphicData", uri=CHART_URI)
        sub(gd, "c:chart", r_id=rid)
        return Shape(gf, sid, cnv, xfrm)


class Group(ShapeTree):
    def fit(self):
        """A group's frame is the box around its children, with child space equal to slide
        space (so nothing inside moves or scales)."""
        boxes = []
        for ch in self.element:
            if ch.tag == q("p:grpSp"):
                x = ch.find(q("p:grpSpPr")).find(q("a:xfrm"))
            elif ch.tag == q("p:graphicFrame"):
                x = ch.find(q("p:xfrm"))
            else:
                sp = ch.find(q("p:spPr"))
                x = sp.find(q("a:xfrm")) if sp is not None else None
            if x is None:
                continue
            o, e = x.find(q("a:off")), x.find(q("a:ext"))
            bx, by = int(o.get("x")), int(o.get("y"))
            boxes.append((bx, by, bx + int(e.get("cx")), by + int(e.get("cy"))))
        x0, y0 = (min(b[0] for b in boxes), min(b[1] for b in boxes)) if boxes else (0, 0)
        x1, y1 = (max(b[2] for b in boxes), max(b[3] for b in boxes)) if boxes else (0, 0)
        gpr = self.element.find(q("p:grpSpPr"))
        for old in list(gpr):
            gpr.remove(old)
        xfrm = sub(gpr, "a:xfrm")
        sub(xfrm, "a:off", x=x0, y=y0)
        sub(xfrm, "a:ext", cx=x1 - x0, cy=y1 - y0)
        sub(xfrm, "a:chOff", x=x0, y=y0)
        sub(xfrm, "a:chExt", cx=x1 - x0, cy=y1 - y0)


class Slide:
    def __init__(self, deck: "Deck", number: int, layout: str = "../slideLayouts/slideLayout1.xml"):
        self.deck, self.number = deck, number
        self.root = el("p:sld")
        self.cSld = sub(self.root, "p:cSld")
        tree = sub(self.cSld, "p:spTree")
        nv = sub(tree, "p:nvGrpSpPr")
        sub(nv, "p:cNvPr", id=1, name="")
        sub(nv, "p:cNvGrpSpPr")
        sub(nv, "p:nvPr")
        sub(tree, "p:grpSpPr")
        self.shapes = ShapeTree(tree, self)
        self.groups: list[Group] = []
        self.rels: list[tuple[str, str, str]] = [("rId1", "slideLayout", layout)]
        self._ids = 1
        self.notes: str | None = None  # speaker notes, written as the slide's notes page

    def next_id(self) -> int:
        self._ids += 1
        return self._ids

    def _rid(self, typ, target) -> str:
        for rid, t, tg in self.rels:
            if t == typ and tg == target:
                return rid
        rid = f"rId{len(self.rels) + 1}"
        self.rels.append((rid, typ, target))
        return rid

    def background(self, hex6: str):
        bg = el("p:bg")
        bgPr = sub(bg, "p:bgPr")
        sub(sub(bgPr, "a:solidFill"), "a:srgbClr", val=hex6)
        sub(bgPr, "a:effectLst")
        self.cSld.insert(0, bg)

    def add_image(self, path: Path) -> str:
        return self._rid("image", "../media/" + self.deck.media(path))

    def add_chart(self, chart_xml: bytes, workbook: bytes) -> str:
        return self._rid("chart", "../charts/" + self.deck.chart(chart_xml, workbook))

    def xml(self) -> bytes:
        for g in reversed(self.groups):  # inner groups first, so outer frames see final sizes
            g.fit()
        sub(sub(self.root, "p:clrMapOvr"), "a:masterClrMapping")
        return xml_bytes(self.root)


IMAGE_TYPES = {b"\x89PNG": ("png", "image/png"), b"\xff\xd8\xff": ("jpeg", "image/jpeg"),
               b"GIF8": ("gif", "image/gif"), b"BM": ("bmp", "image/bmp")}


def image_type(data: bytes) -> tuple[str, str]:
    for magic, t in IMAGE_TYPES.items():
        if data.startswith(magic):
            return t
    raise ValueError("unsupported image format (use PNG, JPEG, GIF or BMP)")


class Deck:
    """A blank presentation: add_slide(), then save(path)."""

    def __init__(self, width_emu: int, height_emu: int):
        self.width, self.height = width_emu, height_emu
        self.slides: list[Slide] = []
        self._media: dict[str, tuple[str, bytes]] = {}  # sha1 -> (name, bytes)
        self._charts: list[tuple[bytes, bytes]] = []

    def add_slide(self) -> Slide:
        s = Slide(self, len(self.slides) + 1)
        self.slides.append(s)
        return s

    def media(self, path: Path) -> str:
        data = path.read_bytes()
        h = hashlib.sha1(data).hexdigest()
        if h not in self._media:
            ext, _ = image_type(data)
            self._media[h] = (f"image{len(self._media) + 1}.{ext}", data)
        return self._media[h][0]

    def chart(self, chart_xml: bytes, workbook: bytes) -> str:
        self._charts.append((chart_xml, workbook))
        return f"chart{len(self._charts)}.xml"

    def save(self, path):
        Path(path).write_bytes(self.to_bytes())

    def to_bytes(self) -> bytes:
        parts: dict[str, bytes] = {}
        over: dict[str, str] = {}
        n = len(self.slides)

        over["/ppt/presentation.xml"] = f"{CT_PML}.presentation.main+xml"
        parts["_rels/.rels"] = _rels([("rId1", "officeDocument", "ppt/presentation.xml")])
        pres_rels = [("rId1", "slideMaster", "slideMasters/slideMaster1.xml"),
                     ("rId2", "theme", "theme/theme1.xml")]
        pres_rels += [(f"rId{i + 3}", "slide", f"slides/slide{i + 1}.xml") for i in range(n)]
        made = add_notes(self.slides, parts, lambda part, typ: over.__setitem__("/" + part, typ), None, THEME)
        if made:
            pres_rels.append(("rIdNotes", "notesMaster", made[len("ppt/"):]))
        parts["ppt/_rels/presentation.xml.rels"] = _rels(pres_rels)
        parts["ppt/presentation.xml"] = _presentation(n, self.width, self.height, notes_master=bool(made))

        parts["ppt/theme/theme1.xml"] = THEME
        over["/ppt/theme/theme1.xml"] = "application/vnd.openxmlformats-officedocument.theme+xml"
        parts["ppt/slideMasters/slideMaster1.xml"] = MASTER
        parts["ppt/slideMasters/_rels/slideMaster1.xml.rels"] = _rels(
            [("rId1", "slideLayout", "../slideLayouts/slideLayout1.xml"), ("rId2", "theme", "../theme/theme1.xml")])
        over["/ppt/slideMasters/slideMaster1.xml"] = f"{CT_PML}.slideMaster+xml"
        parts["ppt/slideLayouts/slideLayout1.xml"] = LAYOUT
        parts["ppt/slideLayouts/_rels/slideLayout1.xml.rels"] = _rels(
            [("rId1", "slideMaster", "../slideMasters/slideMaster1.xml")])
        over["/ppt/slideLayouts/slideLayout1.xml"] = f"{CT_PML}.slideLayout+xml"

        for s in self.slides:
            parts[f"ppt/slides/slide{s.number}.xml"] = s.xml()
            parts[f"ppt/slides/_rels/slide{s.number}.xml.rels"] = _rels(s.rels)
            over[f"/ppt/slides/slide{s.number}.xml"] = f"{CT_PML}.slide+xml"
        for name, data in self._media.values():
            parts[f"ppt/media/{name}"] = data
        for i, (cx, wb) in enumerate(self._charts, 1):
            parts[f"ppt/charts/chart{i}.xml"] = cx
            parts[f"ppt/charts/_rels/chart{i}.xml.rels"] = _rels(
                [("rId1", "package", f"../embeddings/Sheet{i}.xlsx")])
            parts[f"ppt/embeddings/Sheet{i}.xlsx"] = wb
            over[f"/ppt/charts/chart{i}.xml"] = f"{CT_DML}.chart+xml"

        types = ET.Element(f"{{{CT}}}Types")
        defaults = {"rels": "application/vnd.openxmlformats-package.relationships+xml", "xml": "application/xml",
                    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
        for name, _ in self._media.values():
            ext = name.rsplit(".", 1)[1]
            defaults[ext] = next(ct for e, ct in IMAGE_TYPES.values() if e == ext)
        for ext, ct in defaults.items():
            d = ET.SubElement(types, f"{{{CT}}}Default")
            d.set("Extension", ext)
            d.set("ContentType", ct)
        for part, ct in over.items():
            o = ET.SubElement(types, f"{{{CT}}}Override")
            o.set("PartName", part)
            o.set("ContentType", ct)
        out = {"[Content_Types].xml": xml_bytes(types)}
        out.update(parts)
        return _zip(out)


def notes_master_xml() -> bytes:
    """A plain notes master: the slide picture above, the notes below, the theme's body font."""
    return (f'{_HEAD}<p:notesMaster {_PR}><p:cSld><p:bg><p:bgRef idx="1001"><a:schemeClr val="bg1"/></p:bgRef></p:bg>'
            '<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>'
            '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Slide Image Placeholder 1"/><p:cNvSpPr><a:spLocks noGrp="1" noRot="1" '
            'noChangeAspect="1"/></p:cNvSpPr><p:nvPr><p:ph type="sldImg" idx="2"/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm>'
            '<a:off x="685800" y="1143000"/><a:ext cx="5486400" cy="3086100"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/>'
            '</a:prstGeom><a:noFill/><a:ln w="12700"><a:solidFill><a:prstClr val="black"/></a:solidFill></a:ln></p:spPr></p:sp>'
            '<p:sp><p:nvSpPr><p:cNvPr id="3" name="Notes Placeholder 2"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
            '<p:nvPr><p:ph type="body" sz="quarter" idx="3"/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x="685800" '
            'y="4400550"/><a:ext cx="5486400" cy="3600450"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
            '<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:endParaRPr lang="en-US"/></a:p></p:txBody></p:sp></p:spTree></p:cSld>'
            '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" '
            'accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
            '<p:notesStyle><a:lvl1pPr marL="0" algn="l" defTabSz="914400" rtl="0" eaLnBrk="1" latinLnBrk="0" hangingPunct="1">'
            '<a:defRPr sz="1200" kern="1200"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill><a:latin typeface="+mn-lt"/>'
            '<a:ea typeface="+mn-ea"/><a:cs typeface="+mn-cs"/></a:defRPr></a:lvl1pPr></p:notesStyle></p:notesMaster>').encode()


def notes_slide_xml(text: str) -> bytes:
    """One slide's notes page: a paragraph per line of the notes."""
    from xml.sax.saxutils import escape
    paras = "".join(f'<a:p><a:r><a:rPr lang="en-US" dirty="0"/><a:t>{escape(line)}</a:t></a:r></a:p>' if line.strip()
                    else '<a:p><a:endParaRPr lang="en-US"/></a:p>' for line in text.split("\n"))
    return (f'{_HEAD}<p:notes {_PR}><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/>'
            '</p:nvGrpSpPr><p:grpSpPr/><p:sp><p:nvSpPr><p:cNvPr id="2" name="Slide Image Placeholder 1"/><p:cNvSpPr>'
            '<a:spLocks noGrp="1" noRot="1" noChangeAspect="1"/></p:cNvSpPr><p:nvPr><p:ph type="sldImg" idx="2"/></p:nvPr>'
            '</p:nvSpPr><p:spPr/></p:sp><p:sp><p:nvSpPr><p:cNvPr id="3" name="Notes Placeholder 2"/><p:cNvSpPr>'
            '<a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr><p:ph type="body" idx="3"/></p:nvPr></p:nvSpPr><p:spPr/>'
            f'<p:txBody><a:bodyPr/><a:lstStyle/>{paras}</p:txBody></p:sp></p:spTree></p:cSld>'
            '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:notes>').encode()


def add_notes(slides, parts: dict, override, master_part: str | None, theme_bytes: bytes) -> str | None:
    """Notes pages for every slide that has notes. Uses the deck's own notes master when it has one (a company
    template usually does), else writes a plain one with its own copy of the theme. Returns the new master's part
    name when it wrote one (the caller lists it in presentation.xml), else None."""
    noted = [s for s in slides if s.notes]
    if not noted:
        return None
    made = None
    if not master_part:
        made = master_part = "ppt/notesMasters/notesMaster1.xml"
        parts[master_part] = notes_master_xml()
        parts["ppt/theme/convey-notes-theme.xml"] = theme_bytes
        parts["ppt/notesMasters/_rels/notesMaster1.xml.rels"] = _rels([("rId1", "theme", "../theme/convey-notes-theme.xml")])
        override(master_part, f"{CT_PML}.notesMaster+xml")
        override("ppt/theme/convey-notes-theme.xml", "application/vnd.openxmlformats-officedocument.theme+xml")
    for s in noted:
        part = f"ppt/notesSlides/convey-notes{s.number}.xml"
        parts[part] = notes_slide_xml(s.notes)
        parts[f"ppt/notesSlides/_rels/convey-notes{s.number}.xml.rels"] = _rels(
            [("rId1", "notesMaster", "../" + master_part[len("ppt/"):]), ("rId2", "slide", f"../slides/slide{s.number}.xml")])
        override(part, f"{CT_PML}.notesSlide+xml")
        s._rid("notesSlide", f"../notesSlides/convey-notes{s.number}.xml")
    return made


def _presentation(n, w, h, notes_master: bool = False) -> bytes:
    root = el("p:presentation")
    sub(sub(root, "p:sldMasterIdLst"), "p:sldMasterId", id=2147483648, r_id="rId1")
    if notes_master:
        sub(sub(root, "p:notesMasterIdLst"), "p:notesMasterId", r_id="rIdNotes")
    if n:
        lst = sub(root, "p:sldIdLst")
        for i in range(n):
            sub(lst, "p:sldId", id=256 + i, r_id=f"rId{i + 3}")
    sub(root, "p:sldSz", cx=w, cy=h)
    sub(root, "p:notesSz", cx=6858000, cy=9144000)
    return xml_bytes(root)


# ---------------------------------------------------------------- skeleton parts
# Written for this module. Every slide object sets its own fonts, colors and spacing, so the
# skeleton only needs to be valid and neutral: no shadows, no kerning, plain defaults.

_A = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
_PR = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
       'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
       'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"')
_HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'


def _fill(c):
    return f'<a:solidFill><a:schemeClr val="{c}"/></a:solidFill>'


_SOLID3 = _fill("phClr") * 3
_LINES = "".join(f'<a:ln w="{w}"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>' for w in (9525, 12700, 19050))
_COLORS = [("dk1", "000000"), ("lt1", "FFFFFF"), ("dk2", "44546A"), ("lt2", "E7E6E6"), ("accent1", "4472C4"),
           ("accent2", "ED7D31"), ("accent3", "A5A5A5"), ("accent4", "FFC000"), ("accent5", "5B9BD5"),
           ("accent6", "70AD47"), ("hlink", "0563C1"), ("folHlink", "954F72")]

THEME = (_HEAD + f'<a:theme {_A} name="Plain"><a:themeElements><a:clrScheme name="Plain">'
         + "".join(f'<a:{k}><a:srgbClr val="{v}"/></a:{k}>' for k, v in _COLORS)
         + '</a:clrScheme><a:fontScheme name="Plain">'
         + ''.join(f'<a:{k}Font><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:{k}Font>'
                   for k in ("major", "minor"))
         + f'</a:fontScheme><a:fmtScheme name="Plain"><a:fillStyleLst>{_SOLID3}</a:fillStyleLst>'
         f'<a:lnStyleLst>{_LINES}</a:lnStyleLst>'
         '<a:effectStyleLst>' + '<a:effectStyle><a:effectLst/></a:effectStyle>' * 3 + '</a:effectStyleLst>'
         f'<a:bgFillStyleLst>{_SOLID3}</a:bgFillStyleLst></a:fmtScheme></a:themeElements>'
         '<a:objectDefaults/><a:extraClrSchemeLst/></a:theme>').encode()

_TREE = ('<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
         '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/>'
         '<a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree>')
_LVL1 = ('<a:lvl1pPr marL="0" algn="l" rtl="0" eaLnBrk="1" latinLnBrk="0" hangingPunct="1">'
         '<a:defRPr sz="1800"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill>'
         '<a:latin typeface="+mn-lt"/><a:ea typeface="+mn-ea"/><a:cs typeface="+mn-cs"/></a:defRPr></a:lvl1pPr>')

MASTER = (_HEAD + f'<p:sldMaster {_PR}><p:cSld><p:bg><p:bgRef idx="1001"><a:schemeClr val="bg1"/></p:bgRef></p:bg>'
          f'{_TREE}</p:cSld>'
          '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" '
          'accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
          '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
          f'<p:txStyles><p:titleStyle>{_LVL1}</p:titleStyle><p:bodyStyle>{_LVL1}</p:bodyStyle>'
          f'<p:otherStyle>{_LVL1}</p:otherStyle></p:txStyles></p:sldMaster>').encode()

LAYOUT = (_HEAD + f'<p:sldLayout {_PR} type="blank" preserve="1"><p:cSld name="Blank">{_TREE}</p:cSld>'
          '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>').encode()


# ---------------------------------------------------------------- chart workbook

def _col(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def workbook(categories: list, series: list[tuple[str, list]]) -> bytes:
    """The chart's data as a one-sheet .xlsx: categories down column A, one column per series."""
    S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

    def esc(t):
        return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def cell(ref, v):
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return f'<c r="{ref}"><v>{v}</v></c>'
        return f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{esc(v)}</t></is></c>'

    rows = ['<row r="1">' + "".join(cell(f"{_col(j + 1)}1", name) for j, (name, _) in enumerate(series)) + "</row>"]
    for i, cat in enumerate(categories):
        r = i + 2
        cells = cell(f"A{r}", cat) + "".join(
            cell(f"{_col(j + 1)}{r}", vals[i]) for j, (_, vals) in enumerate(series) if i < len(vals) and vals[i] is not None)
        rows.append(f'<row r="{r}">{cells}</row>')
    sheet = f'{_HEAD}<worksheet xmlns="{S}"><sheetData>{"".join(rows)}</sheetData></worksheet>'
    book = (f'{_HEAD}<workbook xmlns="{S}" xmlns:r="{REL}"><sheets>'
            '<sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>')
    ss = "application/vnd.openxmlformats-officedocument.spreadsheetml"
    types = (f'{_HEAD}<Types xmlns="{CT}"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="xml" ContentType="application/xml"/>'
             f'<Override PartName="/xl/workbook.xml" ContentType="{ss}.sheet.main+xml"/>'
             f'<Override PartName="/xl/worksheets/sheet1.xml" ContentType="{ss}.worksheet+xml"/></Types>')
    return _zip({
        "[Content_Types].xml": types.encode(),
        "_rels/.rels": _rels([("rId1", "officeDocument", "xl/workbook.xml")]),
        "xl/workbook.xml": book.encode(),
        "xl/_rels/workbook.xml.rels": _rels([("rId1", "worksheet", "worksheets/sheet1.xml")]),
        "xl/worksheets/sheet1.xml": sheet.encode(),
    })


# ---------------------------------------------------------------- onto a company template

TEMPLATE_TYPES = ("presentationml.template.main+xml", "presentationml.slideshow.main+xml",
                  "presentationml.presentation.macroEnabled.main+xml")


class TemplateDeck(Deck):
    """A deck built on a company template (.potx, .pptx or .thmx): its theme, masters and layouts
    are kept as they are, any sample slides are dropped, and new slides are written onto the
    template's own layouts."""

    def __init__(self, template):
        z = zipfile.ZipFile(template)
        parts = {n: z.read(n) for n in z.namelist() if not n.endswith("/")}
        # An Office theme keeps the presentation under theme/ beside a "theme manager": move it to ppt/.
        if "ppt/presentation.xml" not in parts and "theme/presentation.xml" in parts:
            moved = {}
            for n, d in parts.items():
                if n.startswith("theme/theme/themeManager") or n.startswith("theme/theme/_rels/themeManager"):
                    continue
                moved["ppt/" + n[len("theme/"):] if n.startswith("theme/") else n] = d
            parts = moved
            parts["[Content_Types].xml"] = parts["[Content_Types].xml"].replace(b'PartName="/theme/', b'PartName="/ppt/')
        parts["_rels/.rels"] = _rels([("rId1", "officeDocument", "ppt/presentation.xml")])
        for k in [n for n in parts if n.startswith("docProps/") or n.startswith("themeVariants/")]:
            del parts[k]
        self.parts = parts
        pres = ET.fromstring(parts["ppt/presentation.xml"])
        sz = pres.find(q("p:sldSz"))
        super().__init__(int(sz.get("cx")), int(sz.get("cy")))
        # Drop sample slides (and their notes), keep everything else.
        rels = self._read_rels("ppt/presentation.xml")
        for rid, (typ, target) in list(rels.items()):
            if typ.endswith("/slide"):
                part = posixpath.normpath(posixpath.join("ppt", target))
                for k in (part, posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")):
                    parts.pop(k, None)
                del rels[rid]
        for k in [n for n in parts if n.startswith("ppt/notesSlides/")]:
            del parts[k]
        lst = pres.find(q("p:sldIdLst"))
        if lst is not None:
            pres.remove(lst)
        self._pres, self._pres_rels = pres, rels
        self.layouts = self._layouts()
        self.theme_fonts = self._theme_fonts()

    def _read_rels(self, part: str) -> dict:
        d, f = posixpath.split(part)
        data = self.parts.get(posixpath.join(d, "_rels", f + ".rels"))
        out = {}
        if data:
            for r in ET.fromstring(data):
                out[r.get("Id")] = (r.get("Type"), r.get("Target"))
        return out

    def _layouts(self) -> dict[str, str]:
        """Layout name -> part name, in the masters' own order."""
        out = {}
        for rid in [e.get(q("r:id")) for e in self._pres.find(q("p:sldMasterIdLst"))]:
            mpart = posixpath.normpath(posixpath.join("ppt", self._pres_rels[rid][1]))
            m = ET.fromstring(self.parts[mpart])
            mrels = self._read_rels(mpart)
            for e in m.find(q("p:sldLayoutIdLst")):
                lpart = posixpath.normpath(posixpath.join(posixpath.dirname(mpart), mrels[e.get(q("r:id"))][1]))
                lay = ET.fromstring(self.parts[lpart])
                name = lay.find(q("p:cSld")).get("name", lpart)
                out.setdefault(name, lpart)
        return out

    def _theme_fonts(self) -> dict:
        for n in self.parts:
            if n.startswith("ppt/theme/theme") and n.endswith(".xml"):
                th = ET.fromstring(self.parts[n])
                fs = th.find(f"{q('a:themeElements')}/{q('a:fontScheme')}")
                if fs is not None:
                    get = lambda k: (fs.find(f"{q('a:' + k)}/{q('a:latin')}").get("typeface")
                                     if fs.find(f"{q('a:' + k)}/{q('a:latin')}") is not None else None)
                    return {"major": get("majorFont"), "minor": get("minorFont")}
        return {}

    def layout_info(self, name: str) -> list[dict]:
        """The layout's placeholders: [{type, idx}]."""
        lay = ET.fromstring(self.parts[self.layouts[name]])
        out = []
        for ph in lay.iter(q("p:ph")):
            out.append({"type": ph.get("type", "body"), "idx": int(ph.get("idx", 0)), "sz": ph.get("sz")})
        return out

    def add_slide(self, layout: str | None = None) -> Slide:
        name = layout if layout in self.layouts else next(iter(self.layouts))
        target = "../slideLayouts/" + posixpath.basename(self.layouts[name])
        s = Slide(self, len(self.slides) + 1, target)
        s.layout_name = name
        self.slides.append(s)
        return s

    def media(self, path: Path) -> str:
        data = path.read_bytes()
        h = hashlib.sha1(data).hexdigest()
        if h not in self._media:
            ext, _ = image_type(data)
            self._media[h] = (f"convey-image{len(self._media) + 1}.{ext}", data)
        return self._media[h][0]

    def chart(self, chart_xml: bytes, workbook: bytes) -> str:
        self._charts.append((chart_xml, workbook))
        return f"convey-chart{len(self._charts)}.xml"

    def to_bytes(self) -> bytes:
        parts = dict(self.parts)
        ct = ET.fromstring(parts["[Content_Types].xml"])
        for o in ct.findall(f"{{{CT}}}Override"):
            if o.get("PartName") == "/ppt/presentation.xml":
                o.set("ContentType", f"{CT_PML}.presentation.main+xml")
            elif o.get("PartName").lstrip("/") not in parts:
                ct.remove(o)
        have = {d.get("Extension").lower() for d in ct.findall(f"{{{CT}}}Default")}

        def override(part, typ):
            o = ET.SubElement(ct, f"{{{CT}}}Override")
            o.set("PartName", "/" + part)
            o.set("ContentType", typ)

        def default(ext, typ):
            if ext.lower() not in have:
                d = ET.Element(f"{{{CT}}}Default")
                d.set("Extension", ext)
                d.set("ContentType", typ)
                ct.insert(0, d)
                have.add(ext.lower())

        rels = dict(self._pres_rels)
        n0 = 1 + max([int(r[3:]) for r in rels if r[3:].isdigit()] or [0])
        # Speaker notes: on the template's own notes master when it has one.
        nm = next((posixpath.normpath(posixpath.join("ppt", tg)) for typ, tg in rels.values() if typ.endswith("/notesMaster")), None)
        theme = next((parts[k] for k in sorted(parts) if k.startswith("ppt/theme/theme") and k.endswith(".xml")), b"")
        made = add_notes(self.slides, parts, override, nm, theme)
        if made:
            rels["rIdConveyNotes"] = (REL + "/notesMaster", made[len("ppt/"):])
            pres = self._pres
            if pres.find(q("p:notesMasterIdLst")) is None:
                at = list(pres).index(pres.find(q("p:sldMasterIdLst"))) + 1
                lst_nm = el("p:notesMasterIdLst")
                sub(lst_nm, "p:notesMasterId", r_id="rIdConveyNotes")
                pres.insert(at, lst_nm)
        lst = el("p:sldIdLst")
        for i, s in enumerate(self.slides):
            rid = f"rId{n0 + i}"
            rels[rid] = (REL + "/slide", f"slides/slide{s.number}.xml")
            sub(lst, "p:sldId", id=256 + i, r_id=rid)
            parts[f"ppt/slides/slide{s.number}.xml"] = s.xml()
            parts[f"ppt/slides/_rels/slide{s.number}.xml.rels"] = _rels(s.rels)
            override(f"ppt/slides/slide{s.number}.xml", f"{CT_PML}.slide+xml")
        pres = self._pres
        anchor = max((list(pres).index(pres.find(q(t))) for t in ("p:sldMasterIdLst", "p:notesMasterIdLst", "p:handoutMasterIdLst")
                      if pres.find(q(t)) is not None), default=0)
        if self.slides:
            pres.insert(anchor + 1, lst)
        parts["ppt/presentation.xml"] = xml_bytes(pres)
        parts["ppt/_rels/presentation.xml.rels"] = _rels([(rid, typ, tg) for rid, (typ, tg) in rels.items()])
        for name, data in self._media.values():
            parts[f"ppt/media/{name}"] = data
            ext = name.rsplit(".", 1)[1]
            default(ext, next(c for e, c in IMAGE_TYPES.values() if e == ext))
        for i, (cx, wb) in enumerate(self._charts, 1):
            parts[f"ppt/charts/convey-chart{i}.xml"] = cx
            parts[f"ppt/charts/_rels/convey-chart{i}.xml.rels"] = _rels(
                [("rId1", "package", f"../embeddings/convey-sheet{i}.xlsx")])
            parts[f"ppt/embeddings/convey-sheet{i}.xlsx"] = wb
            override(f"ppt/charts/convey-chart{i}.xml", f"{CT_DML}.chart+xml")
        default("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        default("rels", "application/vnd.openxmlformats-package.relationships+xml")
        default("xml", "application/xml")
        out = {"[Content_Types].xml": xml_bytes(ct)}
        out.update({k: v for k, v in parts.items() if k != "[Content_Types].xml"})
        return _zip(out)
