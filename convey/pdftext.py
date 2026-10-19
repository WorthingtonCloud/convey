"""Where text sits on each page of a PDF, with the standard library only.

Enough of PDF for the two producers Convey compares: Chrome's print-to-PDF and PowerPoint's
"save as PDF". Reads the page tree, inflates each page's content streams, and follows the
graphics and text matrices to every text-showing operator. Returns where each run starts
(its baseline origin), in CSS px from the page's top-left, scaled to a given page width.
It does not decode glyphs: callers locate text by position.
"""
from __future__ import annotations

import re
import zlib

_OBJ = re.compile(rb"(\d+)\s+(\d+)\s+obj\b(.*?)\bendobj", re.S)
_REF = rb"(\d+)\s+\d+\s+R"


def _objects(data: bytes) -> dict[int, bytes]:
    return {int(m.group(1)): m.group(3) for m in _OBJ.finditer(data)}


def _stream(body: bytes) -> bytes:
    m = re.search(rb"stream\r?\n", body)
    if not m:
        return b""
    raw = body[m.end(): body.rfind(b"endstream")]
    head = body[: m.start()]
    if b"/FlateDecode" in head:
        try:
            return zlib.decompress(raw)
        except zlib.error:
            return zlib.decompressobj().decompress(raw)
    return raw


_MB = re.compile(rb"/MediaBox\s*\[\s*([-\d.\s]+)\]")


def _pages(objs: dict[int, bytes]) -> list[tuple[bytes, bytes]]:
    """[(page dictionary, MediaBox numbers)] in page order; the box may be inherited."""
    root = next((b for b in objs.values() if re.search(rb"/Type\s*/Pages\b", b) and b"/Parent" not in b), None)
    out = []

    def walk(body, box):
        m = _MB.search(body.split(b"stream")[0])
        box = m.group(1) if m else box
        if re.search(rb"/Type\s*/Page\b", body):
            out.append((body, box))
            return
        kids = re.search(rb"/Kids\s*\[(.*?)\]", body, re.S)
        for ref in re.findall(_REF, kids.group(1)) if kids else []:
            walk(objs[int(ref)], box)

    if root is not None:
        walk(root, b"0 0 612 792")
    return out


_TOK = re.compile(rb"""\s*(?:
    (?P<num>[-+]?(?:\d+\.?\d*|\.\d+))
  | (?P<name>/[^\s/\[\]()<>{}%]+)
  | (?P<str>\()
  | (?P<hex><[0-9A-Fa-f\s]*>)
  | (?P<dict><<|>>)
  | (?P<arr>[\[\]])
  | (?P<op>[A-Za-z'"*]+[A-Za-z0-9*]*)
  | (?P<other>.)
)""", re.X | re.S)


def _mul(m, n):
    a, b, c, d, e, f = m
    A, B, C, D, E, F = n
    return (a * A + b * C, a * B + b * D, c * A + d * C, c * B + d * D, e * A + f * C + E, e * B + f * D + F)


def _runs(content: bytes):
    """Yield (x, y, size) in PDF user space for each text-showing operator."""
    ctm = (1, 0, 0, 1, 0, 0)
    stack = []
    tm = tlm = (1, 0, 0, 1, 0, 0)
    size, lead = 0.0, 0.0
    ops = []
    depth = 0  # inside an array or dictionary: operands, not operators
    pos, n = 0, len(content)
    while pos < n:
        m = _TOK.match(content, pos)
        if not m:
            break
        pos = m.end()
        k = m.lastgroup
        v = m.group(k)
        if k == "str":  # a literal string: balanced parentheses, backslash escapes
            level = 1
            while pos < n and level:
                ch = content[pos]
                if ch == 0x5C:
                    pos += 1
                elif ch == 0x28:
                    level += 1
                elif ch == 0x29:
                    level -= 1
                pos += 1
        if k == "num":
            if depth == 0:
                ops.append(float(v))
            continue
        if k in ("arr", "dict"):
            depth += 1 if v in (b"[", b"<<") else -1
            if depth == 0 and v == b"]":
                ops.append("array")
            continue
        if k in ("name", "str", "hex"):
            if k == "str" and v == b"(":
                v = b"()"
            if depth == 0:
                ops.append(v)
            continue
        if k != "op" or depth:
            continue
        if v == b"q":
            stack.append(ctm)
        elif v == b"Q":
            ctm = stack.pop() if stack else ctm
        elif v == b"cm" and len(ops) >= 6:
            ctm = _mul(tuple(ops[-6:]), ctm)
        elif v == b"BT":
            tm = tlm = (1, 0, 0, 1, 0, 0)
        elif v == b"Tf" and ops:
            size = ops[-1] if isinstance(ops[-1], float) else size
        elif v == b"TL" and ops:
            lead = ops[-1]
        elif v == b"Tm" and len(ops) >= 6:
            tm = tlm = tuple(ops[-6:])
        elif v in (b"Td", b"TD") and len(ops) >= 2:
            tx, ty = ops[-2], ops[-1]
            if v == b"TD":
                lead = -ty
            tm = tlm = _mul((1, 0, 0, 1, tx, ty), tlm)
        elif v in (b"T*", b"'", b'"'):
            tm = tlm = _mul((1, 0, 0, 1, 0, -lead), tlm)
        if v in (b"Tj", b"TJ", b"'", b'"'):
            full = _mul(tm, ctm)
            scale = (full[2] ** 2 + full[3] ** 2) ** 0.5
            yield full[4], full[5], size * scale
        ops = []


def page_runs(path, width_px: float = 1280) -> list[list[tuple[float, float, float]]]:
    """Per page, [(x_px, baseline_y_px, size_px)] in reading order of the content stream."""
    data = open(path, "rb").read()
    objs = _objects(data)
    out = []
    for page, box in _pages(objs):
        x0, y0, x1, y1 = (float(t) for t in box.split())
        k = width_px / (x1 - x0)
        cont = re.search(rb"/Contents\s*(\[.*?\]|\d+\s+\d+\s+R)", page, re.S)
        content = b""
        for ref in re.findall(_REF, cont.group(1)) if cont else []:
            content += _stream(objs[int(ref)]) + b"\n"
        out.append([((x - x0) * k, (y1 - y) * k, s * k) for x, y, s in _runs(content)])
    return out


# ---------- every character, decoded ----------
# The export report needs each character's text, place, advance, size and font, on PDFs from Chrome
# (Type0 fonts, Identity-H, a ToUnicode map) and PowerPoint for Mac (TrueType fonts, MacRoman).

_NAMES = {"bullet": "•", "endash": "–", "emdash": "—", "quoteleft": "‘", "quoteright": "’", "quotedblleft": "“",
          "quotedblright": "”", "ellipsis": "…", "periodcentered": "·", "arrowright": "→", "arrowleft": "←",
          "minus": "−", "multiply": "×", "degree": "°", "space": " ", "nbspace": " "}
_ESC = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12}


def _literal(raw: bytes) -> bytes:
    """A PDF literal string's bytes (without its outer parentheses)."""
    out, i, n = bytearray(), 0, len(raw)
    while i < n:
        c = raw[i]
        if c != 0x5C:
            out.append(c)
            i += 1
            continue
        i += 1
        if i >= n:
            break
        c = raw[i]
        if c in _ESC:
            out.append(_ESC[c])
            i += 1
        elif 0x30 <= c <= 0x37:
            j = i
            while j < n and j - i < 3 and 0x30 <= raw[j] <= 0x37:
                j += 1
            out.append(int(raw[i:j], 8) & 0xFF)
            i = j
        elif c in (0x0A, 0x0D):  # a line continuation
            i += 1 + (c == 0x0D and i + 1 < n and raw[i + 1] == 0x0A)
        else:
            out.append(c)
            i += 1
    return bytes(out)


def _deref(objs, v: bytes) -> bytes:
    m = re.fullmatch(rb"\s*(\d+)\s+\d+\s+R\s*", v)
    return objs.get(int(m.group(1)), b"") if m else v


def _dict_entry(body: bytes, key: bytes) -> bytes | None:
    """The raw value of /key in a dictionary: a reference, a name, a number, or a balanced << >> / [ ]."""
    m = re.search(rb"/" + key + rb"(?![A-Za-z0-9])\s*", body)
    if not m:
        return None
    i = m.end()
    if body[i:i + 2] == b"<<" or body[i:i + 1] == b"[":
        opener, closer = (b"<<", b">>") if body[i:i + 2] == b"<<" else (b"[", b"]")
        depth, j = 0, i
        while j < len(body):
            if body.startswith(opener, j):
                depth += 1
                j += len(opener)
            elif body.startswith(closer, j):
                depth -= 1
                j += len(closer)
                if depth == 0:
                    return body[i:j]
            else:
                j += 1
        return body[i:]
    r = re.match(rb"\d+\s+\d+\s+R|/[^\s/\[\]()<>]+|[-+\d.]+", body[i:])
    return r.group(0) if r else None


class _Font:
    def __init__(self, objs, body: bytes):
        self.name = (re.search(rb"/BaseFont\s*/([^\s/\[\]<>]+)", body) or [b"", b""])[1].decode("latin-1").split("+")[-1]
        self.two = b"/Type0" in body
        self.uni: dict[int, str] = {}
        self.widths: dict[int, float] = {}
        self.dw = 1000.0
        desc = body
        if self.two:
            d = _dict_entry(body, b"DescendantFonts") or b""
            ref = re.search(_REF, d)
            desc = objs.get(int(ref.group(1)), b"") if ref else b""
            dw = _dict_entry(desc, b"DW")
            self.dw = float(dw) if dw and re.fullmatch(rb"[-+\d.]+", dw) else 1000.0
            w = _deref(objs, _dict_entry(desc, b"W") or b"[]")
            toks = re.findall(rb"\[|\]|[-+\d.]+", w[1:-1] if w.startswith(b"[") else w)
            i = 0
            while i < len(toks):
                first = int(float(toks[i]))
                if i + 1 < len(toks) and toks[i + 1] == b"[":
                    j, c = i + 2, first
                    while j < len(toks) and toks[j] != b"]":
                        self.widths[c] = float(toks[j])
                        c += 1
                        j += 1
                    i = j + 1
                elif i + 2 < len(toks):
                    for c in range(first, int(float(toks[i + 1])) + 1):
                        self.widths[c] = float(toks[i + 2])
                    i += 3
                else:
                    break
        else:
            fc = _dict_entry(body, b"FirstChar")
            ws = _deref(objs, _dict_entry(body, b"Widths") or b"[]")
            first = int(float(fc)) if fc else 0
            for k, v in enumerate(re.findall(rb"[-+\d.]+", ws)):
                self.widths[first + k] = float(v)
            enc = _deref(objs, _dict_entry(body, b"Encoding") or b"")
            codec = "cp1252" if b"WinAnsi" in enc else "mac_roman" if b"MacRoman" in enc else "latin-1"
            for c in range(256):
                self.uni[c] = bytes([c]).decode(codec, "replace")
            diffs = _dict_entry(enc, b"Differences") if enc.startswith(b"<<") else None
            code = 0
            for t in re.findall(rb"\d+|/[^\s/\[\]]+", diffs or b""):
                if t[:1] == b"/":
                    nm = t[1:].decode("latin-1")
                    u = _NAMES.get(nm) or (chr(int(nm[3:7], 16)) if re.fullmatch(r"uni[0-9A-Fa-f]{4}", nm) else
                                           nm if len(nm) == 1 else "?")
                    self.uni[code] = u
                    code += 1
                else:
                    code = int(t)
        fd = _deref(objs, _dict_entry(desc, b"FontDescriptor") or _dict_entry(body, b"FontDescriptor") or b"")
        asc, dsc = _dict_entry(fd, b"Ascent"), _dict_entry(fd, b"Descent")
        self.ascent = float(asc) if asc else 800.0
        self.descent = -abs(float(dsc)) if dsc else -200.0
        tu = _dict_entry(body, b"ToUnicode")
        if tu:
            self._cmap(_stream(_deref(objs, tu)))

    def _cmap(self, data: bytes):
        def hexs(h):
            b = bytes.fromhex(h.decode())
            return b.decode("utf-16-be", "replace") if len(b) >= 2 else chr(b[0]) if b else ""
        for block in re.findall(rb"beginbfchar(.*?)endbfchar", data, re.S):
            for a, b in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]*)>", block):
                self.uni[int(a, 16)] = hexs(b)
        for block in re.findall(rb"beginbfrange(.*?)endbfrange", data, re.S):
            for a, b, rest in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(<[0-9A-Fa-f]*>|\[[^\]]*\])", block):
                lo, hi = int(a, 16), int(b, 16)
                if rest.startswith(b"["):
                    for k, h in enumerate(re.findall(rb"<([0-9A-Fa-f]*)>", rest)):
                        self.uni[lo + k] = hexs(h)
                else:
                    start = bytes.fromhex(rest[1:-1].decode())
                    for k in range(hi - lo + 1):
                        v = int.from_bytes(start, "big") + k
                        self.uni[lo + k] = v.to_bytes(len(start), "big").decode("utf-16-be", "replace") \
                            if len(start) >= 2 else chr(v)

    def codes(self, s: bytes):
        if self.two:
            return [int.from_bytes(s[i:i + 2], "big") for i in range(0, len(s) - 1, 2)]
        return list(s)


def _resources(objs, body: bytes, inherited: bytes = b"") -> dict:
    res = _dict_entry(body, b"Resources")
    res = _deref(objs, res) if res else inherited
    fonts, forms = {}, {}
    fd = _dict_entry(res, b"Font")
    for nm, ref in re.findall(rb"/([^\s/\[\]<>]+)\s+(\d+)\s+\d+\s+R", _deref(objs, fd) if fd else b""):
        fonts[nm] = int(ref)
    xd = _dict_entry(res, b"XObject")
    for nm, ref in re.findall(rb"/([^\s/\[\]<>]+)\s+(\d+)\s+\d+\s+R", _deref(objs, xd) if xd else b""):
        forms[nm] = int(ref)
    return {"raw": res, "fonts": fonts, "forms": forms}


def _glyphs(objs, content: bytes, res: dict, ctm, fonts_cache: dict, out: list, depth: int = 0):
    """Append (char, x, baseline_y, advance, size, top, bottom, font) in PDF user space, per glyph."""
    stack = []
    tm = tlm = (1, 0, 0, 1, 0, 0)
    font, size, tc, tw, th, lead, rise = None, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0
    ops, depth_arr, arr = [], 0, None
    pos, n = 0, len(content)

    def show(s: bytes):
        nonlocal tm
        if font is None:
            return
        for code in font.codes(s):
            ch = font.uni.get(code, "")
            w0 = font.widths.get(code, font.dw) / 1000.0
            trm = _mul((size * th, 0, 0, size, 0, rise), _mul(tm, ctm))
            adv = (w0 * size + tc + (tw if (not font.two and code == 32) else 0)) * th
            sx = (trm[0] ** 2 + trm[1] ** 2) ** 0.5 / max(size * th, 1e-9) if size else 1
            sy = (trm[2] ** 2 + trm[3] ** 2) ** 0.5
            out.append((ch, trm[4], trm[5], w0 * size * th * sx, sy, trm[5] + font.ascent / 1000 * sy,
                        trm[5] + font.descent / 1000 * sy, font.name))
            tm = _mul((1, 0, 0, 1, adv, 0), tm)

    while pos < n:
        m = _TOK.match(content, pos)
        if not m:
            break
        pos = m.end()
        k = m.lastgroup
        v = m.group(k)
        if k == "str":
            level, start = 1, pos
            while pos < n and level:
                ch = content[pos]
                if ch == 0x5C:
                    pos += 1
                elif ch == 0x28:
                    level += 1
                elif ch == 0x29:
                    level -= 1
                pos += 1
            val = _literal(content[start:pos - 1])
            (arr if arr is not None else ops).append(val)
            continue
        if k == "hex":
            h = re.sub(rb"\s", b"", v[1:-1])
            val = bytes.fromhex((h + b"0" * (len(h) % 2)).decode())
            (arr if arr is not None else ops).append(val)
            continue
        if k == "num":
            (arr if arr is not None else ops).append(float(v))
            continue
        if k == "arr":
            if v == b"[":
                depth_arr += 1
                if depth_arr == 1:
                    arr = []
            else:
                depth_arr -= 1
                if depth_arr == 0:
                    ops.append(arr)
                    arr = None
            continue
        if k == "dict":
            continue
        if k == "name":
            (arr if arr is not None else ops).append(v)
            continue
        if k != "op" or depth_arr:
            continue
        if v == b"BI":  # an inline image: skip its data
            e = content.find(b"EI", content.find(b"ID", pos))
            pos = e + 2 if e > 0 else n
        elif v == b"q":  # the text state is part of the graphics state: q/Q save and restore it too
            stack.append((ctm, font, size, tc, tw, th, lead, rise))
        elif v == b"Q":
            if stack:
                ctm, font, size, tc, tw, th, lead, rise = stack.pop()
        elif v == b"cm" and len(ops) >= 6:
            ctm = _mul(tuple(ops[-6:]), ctm)
        elif v == b"BT":
            tm = tlm = (1, 0, 0, 1, 0, 0)
        elif v == b"Tf" and len(ops) >= 2:
            size = ops[-1]
            ref = res["fonts"].get(ops[-2][1:] if isinstance(ops[-2], bytes) else b"")
            if ref is not None:
                if ref not in fonts_cache:
                    fonts_cache[ref] = _Font(objs, objs.get(ref, b""))
                font = fonts_cache[ref]
        elif v == b"Tc" and ops:
            tc = ops[-1]
        elif v == b"Tw" and ops:
            tw = ops[-1]
        elif v == b"Tz" and ops:
            th = ops[-1] / 100
        elif v == b"TL" and ops:
            lead = ops[-1]
        elif v == b"Ts" and ops:
            rise = ops[-1]
        elif v == b"Tm" and len(ops) >= 6:
            tm = tlm = tuple(ops[-6:])
        elif v in (b"Td", b"TD") and len(ops) >= 2:
            tx, ty = ops[-2], ops[-1]
            if v == b"TD":
                lead = -ty
            tm = tlm = _mul((1, 0, 0, 1, tx, ty), tlm)
        elif v == b"T*":
            tm = tlm = _mul((1, 0, 0, 1, 0, -lead), tlm)
        elif v == b"Tj" and ops and isinstance(ops[-1], bytes):
            show(ops[-1])
        elif v == b"'" and ops:
            tm = tlm = _mul((1, 0, 0, 1, 0, -lead), tlm)
            show(ops[-1])
        elif v == b'"' and len(ops) >= 3:
            tw, tc = ops[-3], ops[-2]
            tm = tlm = _mul((1, 0, 0, 1, 0, -lead), tlm)
            show(ops[-1])
        elif v == b"TJ" and ops and isinstance(ops[-1], list):
            for item in ops[-1]:
                if isinstance(item, bytes):
                    show(item)
                elif isinstance(item, float):
                    tm = _mul((1, 0, 0, 1, -item / 1000 * size * th, 0), tm)
        elif v == b"Do" and ops and depth < 8:
            ref = res["forms"].get(ops[-1][1:] if isinstance(ops[-1], bytes) else b"")
            body = objs.get(ref, b"") if ref is not None else b""
            if b"/Form" in body.split(b"stream")[0]:
                mx = _dict_entry(body.split(b"stream")[0], b"Matrix")
                mat = tuple(float(x) for x in re.findall(rb"[-+\d.]+", mx)) if mx else (1, 0, 0, 1, 0, 0)
                sub_res = _resources(objs, body.split(b"stream")[0], res["raw"])
                _glyphs(objs, _stream(body), sub_res, _mul(mat, ctm), fonts_cache, out, depth + 1)
        ops = []


def page_chars(path, width_px: float = 1280) -> list[list[list]]:
    """Per page, every drawn character that isn't white space, in drawing order, as
    [index, char, x, top, advance, height, font] in CSS px from the page's top-left at `width_px`
    (top/height span the font's ascent to descent). `index` jumps by 2 where a word break was:
    a space, a line change, or a gap wider than a third of the size."""
    data = open(path, "rb").read()
    objs = _objects(data)
    out = []
    for page, box in _pages(objs):
        x0, y0, x1, y1 = (float(t) for t in box.split())
        k = width_px / (x1 - x0)
        cont = re.search(rb"/Contents\s*(\[.*?\]|\d+\s+\d+\s+R)", page, re.S)
        content = b""
        for ref in re.findall(_REF, cont.group(1)) if cont else []:
            content += _stream(objs[int(ref)]) + b"\n"
        gl: list = []
        _glyphs(objs, content, _resources(objs, page), (1, 0, 0, 1, 0, 0), {}, gl)
        chars, idx, prev = [], 0, None
        for ch, x, base, adv, size, top, bottom, fname in gl:
            for c in ch or "�":
                if c.isspace():
                    prev = None
                    continue
                if prev is None or abs(base - prev[1]) > 0.3 * size or x - prev[0] > 0.34 * size or x < prev[0] - 0.5 * size:
                    idx += 2
                else:
                    idx += 1
                chars.append([idx, c, (x - x0) * k, (y1 - top) * k, adv * k, (top - bottom) * k, fname])
                prev = (x + adv, base)
        out.append(chars)
    return out
