"""Which fonts are installed, under which names, and which program can see them.

PowerPoint names a font by its legacy family (name ID 1: "Acme Sans SemiBold") plus a bold flag.
CSS names it by its typographic family (name ID 16: "Acme Sans") plus a numeric weight. This module
reads every installed font file's name and OS/2 tables (standard library only) so the two can be
translated, and records whether Chrome can see the font too (fonts bundled inside Office are
visible to Office only).
"""
from __future__ import annotations

import os
import struct
from pathlib import Path

HOME = Path.home()
DIRS = [  # (folder, visible to the browser?)
    (HOME / "Library/Fonts", True),
    (Path("/Library/Fonts"), True),
    (Path("/System/Library/Fonts"), True),
    (Path("/System/Library/Fonts/Supplemental"), True),
    (Path("/Applications/Microsoft PowerPoint.app/Contents/Resources/DFonts"), False),
    (Path("/usr/share/fonts"), True),
    (HOME / ".fonts", True),
]
EXTS = {".ttf", ".otf", ".ttc", ".otc"}


def _names(data: bytes, off: int) -> dict:
    """One font inside a file: {'id1','id2','id4','id16','id17','weight','italic'}."""
    _, num = struct.unpack_from(">IH", data, off)
    tables = {}
    for i in range(num):
        tag, _, toff, tlen = struct.unpack_from(">4sIII", data, off + 12 + 16 * i)
        tables[tag] = (toff, tlen)
    out = {"weight": 400, "italic": False}
    if b"name" in tables:
        toff, _ = tables[b"name"]
        _, count, soff = struct.unpack_from(">HHH", data, toff)
        best = {}
        for i in range(count):
            pid, eid, lid, nid, ln, so = struct.unpack_from(">HHHHHH", data, toff + 6 + 12 * i)
            if nid not in (1, 2, 4, 16, 17):
                continue
            raw = data[toff + soff + so: toff + soff + so + ln]
            if pid == 3 and lid in (0x409, 0):  # Windows, US English: UTF-16
                rank, text = 0, raw.decode("utf-16-be", "replace")
            elif pid == 1 and lid == 0:  # Mac Roman
                rank, text = 1, raw.decode("mac_roman", "replace")
            elif pid == 0:
                rank, text = 2, raw.decode("utf-16-be", "replace")
            else:
                continue
            if nid not in best or rank < best[nid][0]:
                best[nid] = (rank, text)
        out.update({f"id{k}": v[1] for k, v in best.items()})
    if b"OS/2" in tables:
        toff, tlen = tables[b"OS/2"]
        if tlen >= 64:
            out["weight"] = struct.unpack_from(">H", data, toff + 4)[0]
            out["italic"] = bool(struct.unpack_from(">H", data, toff + 62)[0] & 1)
    return out


def read_font(path: Path) -> list[dict]:
    try:
        data = path.read_bytes()
    except OSError:
        return []
    try:
        if data[:4] == b"ttcf":
            n = struct.unpack_from(">I", data, 8)[0]
            offs = struct.unpack_from(f">{n}I", data, 12)
        else:
            offs = (0,)
        out = []
        for o in offs:
            f = _names(data, o)
            if "id1" in f:
                f["file"] = str(path)
                out.append(f)
        return out
    except (struct.error, IndexError):
        return []


_CACHE: list[dict] | None = None


def installed() -> list[dict]:
    """Every installed face: legacy family, subfamily, typographic family, weight, italic,
    file, and whether the browser can see it."""
    global _CACHE
    if _CACHE is None:
        seen, out = set(), []
        for d, browser in DIRS:
            if not d.is_dir():
                continue
            for root, _, files in os.walk(d):
                for fn in files:
                    p = Path(root) / fn
                    if p.suffix.lower() in EXTS:
                        for f in read_font(p):
                            key = (f.get("id1"), f.get("id2"), f["weight"], f["italic"])
                            f["browser"] = browser
                            if key in seen:
                                # the same face in a browser-visible folder wins
                                if browser:
                                    for g in out:
                                        if (g.get("id1"), g.get("id2"), g["weight"], g["italic"]) == key:
                                            g["browser"] = True
                                continue
                            seen.add(key)
                            out.append(f)
        _CACHE = out
    return _CACHE


def family_of(f: dict) -> str:
    return f.get("id16") or f.get("id1")


def lookup(name: str) -> dict | None:
    """A PowerPoint font name (legacy family, e.g. 'Acme Sans SemiBold') -> its upright regular face."""
    faces = [f for f in installed() if f.get("id1", "").lower() == name.lower() and not f["italic"]]
    if not faces:
        faces = [f for f in installed() if family_of(f).lower() == name.lower() and not f["italic"]]
    if not faces:
        return None
    faces.sort(key=lambda f: (f.get("id2", "").lower() not in ("regular", "roman", "book", "normal"), abs(f["weight"] - 400)))
    return faces[0]


def face_map(family: str) -> dict:
    """CSS family -> {weight: [PowerPoint face name, bold]} for every installed upright weight,
    the shape Skald's emitter reads."""
    faces = [f for f in installed() if family_of(f).lower() == family.lower() and not f["italic"]]
    out = {}
    for f in sorted(faces, key=lambda f: f["weight"]):
        sub = f.get("id2", "Regular").lower()
        bold = "bold" in sub and f.get("id1") != family_of(f) + " Bold"
        w = str(f["weight"])
        if w not in out or (not bold and out[w][1]):
            out[w] = [f["id1"], bool(bold)]
    return out


def visible_to_browser(family: str) -> bool:
    return any(f["browser"] for f in installed() if family_of(f).lower() == family.lower())
