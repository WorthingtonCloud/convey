"""A typed edit: the person's new words go into the slide HTML and, through data-bind, into storyboard.json, so the
two stay equal (the one place the studio writes backward, PLAN section 3). Undo puts the old words back in both.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import slidefile as F
from .log import Refused


def _write(p: Path, text: str):
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, p)


def load_storyboard(d: Path) -> dict:
    return json.loads((d / "storyboard.json").read_text())


def save_storyboard(d: Path, sb: dict) -> str:
    text = json.dumps(sb, indent=1, ensure_ascii=False) + "\n"
    _write(d / "storyboard.json", text)
    return text


def slide_of(sb: dict, sid: str) -> dict:
    for s in sb.get("slides", []):
        if s.get("id") == sid:
            return s
    raise Refused(f"storyboard.json has no slide {sid}")


def get_field(slide: dict, path: str):
    node = slide
    for part in path.split("."):
        if isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        elif isinstance(node, dict) and part in node:
            node = node[part]
        else:
            raise Refused(f"storyboard slide {slide.get('id')} has no field {path}: the edit would break the binding")
    return node


def set_field(slide: dict, path: str, value):
    parts = path.split(".")
    parent = get_field(slide, ".".join(parts[:-1])) if len(parts) > 1 else slide
    last = parts[-1]
    if isinstance(parent, list) and last.isdigit() and int(last) < len(parent):
        parent[int(last)] = value
    elif isinstance(parent, dict) and last in parent:
        parent[last] = value
    else:
        raise Refused(f"storyboard slide {slide.get('id')} has no field {path}: the edit would break the binding")


def slide_path(d: Path, file: str) -> Path:
    p = (d / "slides" / file).resolve()
    if p.parent != (d / "slides").resolve() or p.suffix != ".html" or not p.exists():
        raise Refused(f"no slide {file!r} in slides/")
    return p


def prepare(d: Path, file: str, did: str, new, seen) -> dict:
    """The text.edited event for this change, checked against the files as they are now. `seen` is the text the
    page showed: if the file says something else, someone changed it since, and the edit is refused."""
    p = slide_path(d, file)
    src = p.read_text()
    sid = F.slide_id(src)
    if not sid:
        raise Refused(f"{file} has no data-slide")
    el = F.named(src).get(did)
    if el is None:
        raise Refused(f"{file} has no object named {did}")
    if F.kind(el) is None:
        raise Refused(f"{did} holds more than words: leave a note instead")
    old = F.value(src, el)
    if isinstance(new, list):
        new = [" ".join(str(x).split()) for x in new if str(x).strip()]
    else:
        new = " ".join(str(new).split())
    if seen is not None and _norm(seen) != _norm(old):
        raise Refused(f"{did} on {sid} changed since the page loaded it: it now says “{_show(old)}”. Look again, then type")
    if _norm(new) == _norm(old):
        raise Refused("nothing changed")
    bind = el.bind
    if bind:
        get_field(slide_of(load_storyboard(d), sid), bind)  # the binding must exist before anything is written
    return {"type": "text.edited", "held": True, "slide": sid, "file": file, "id": did, "bind": bind,
            "old": old, "new": new}


def _norm(v):
    return [" ".join(str(x).split()) for x in v] if isinstance(v, list) else " ".join(str(v or "").split())


def _show(v):
    return " / ".join(v) if isinstance(v, list) else v


def write(d: Path, e: dict, frm, to):
    """Put `to` where `frm` is, in the slide and its storyboard field. Refused if the slide doesn't show `frm`."""
    p = slide_path(d, e["file"])
    src = p.read_text()
    if _norm(F.read(src, e["id"])) != _norm(frm):
        raise Refused(f"{e['id']} on {e['slide']} changed again since: undo the later edit first")
    out = F.write(src, e["id"], to)
    if e.get("bind") == "headline" and not isinstance(to, list):
        out = F.retitle(out, frm, to)
    sb = None
    if e.get("bind"):
        sb = load_storyboard(d)
        set_field(slide_of(sb, e["slide"]), e["bind"], to)
    _write(p, out)
    if sb is not None:
        save_storyboard(d, sb)


def apply(d: Path, e: dict):
    write(d, e, e["old"], e["new"])


def revert(d: Path, e: dict):
    write(d, e, e["new"], e["old"])
