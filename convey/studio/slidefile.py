"""Read and write the text of named objects (data-id) in a slide's HTML, touching nothing else.

A slide is hand-designed HTML, so an edit must change one object's words and leave every other byte as it was.
The parser records where each data-id element's start tag, inner content and end tag sit in the file; a write
replaces only the inner text. Editable objects are text only (no elements inside), or a list whose items are text
only. Everything else (a chart, a group, a picture) takes notes, not typed edits.
"""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr",
        "path", "rect", "circle", "line", "polygon", "polyline", "ellipse", "stop", "use"}


class Elem:
    __slots__ = ("tag", "attrs", "start", "inner", "inner_end", "end", "children", "direct", "raw")

    def __init__(self, tag, attrs, start, inner, raw):
        self.tag, self.attrs, self.start, self.inner, self.raw = tag, attrs, start, inner, raw
        self.inner_end = self.end = None
        self.children: list[Elem] = []
        self.direct: list[str] = []  # its own text, children's excluded

    @property
    def id(self):
        return self.attrs.get("data-id")

    @property
    def bind(self):
        return self.attrs.get("data-bind")


class _Parser(HTMLParser):
    def __init__(self, src: str):
        super().__init__(convert_charrefs=False)
        self.src = src
        self.lines = [0]
        for m in re.finditer("\n", src):
            self.lines.append(m.end())
        self.stack: list[Elem] = []
        self.all: list[Elem] = []
        self.title: Elem | None = None

    def _off(self):
        line, col = self.getpos()
        return self.lines[line - 1] + col

    def handle_starttag(self, tag, attrs):
        start = self._off()
        raw = self.get_starttag_text() or ""
        e = Elem(tag, dict(attrs), start, start + len(raw), raw)
        if self.stack:
            self.stack[-1].children.append(e)
        self.all.append(e)
        if tag in VOID:
            e.inner_end = e.end = e.inner
            return
        self.stack.append(e)
        if tag == "title" and self.title is None:
            self.title = e

    def handle_startendtag(self, tag, attrs):
        start = self._off()
        raw = self.get_starttag_text() or ""
        e = Elem(tag, dict(attrs), start, start + len(raw), raw)
        e.inner_end = e.end = e.inner
        self.all.append(e)
        if self.stack:
            self.stack[-1].children.append(e)

    def handle_endtag(self, tag):
        if tag in VOID or not any(e.tag == tag for e in self.stack):
            return
        at = self._off()
        close = self.src.find(">", at)
        while self.stack:
            e = self.stack.pop()
            e.inner_end, e.end = at, (close + 1 if close >= 0 else at)
            if e.tag == tag:
                break

    def _text(self, data):
        if self.stack:
            self.stack[-1].direct.append(data)

    handle_data = _text

    def handle_entityref(self, name):
        self._text(f"&{name};")

    def handle_charref(self, name):
        self._text(f"&#{name};")


def parse(src: str) -> tuple[list[Elem], Elem | None]:
    p = _Parser(src)
    p.feed(src)
    p.close()
    for e in p.stack:  # never closed: runs to the end of the file
        e.inner_end = e.end = len(src)
    return p.all, p.title


def clean(text: str) -> str:
    """What a reader sees: entities decoded, whitespace collapsed (the same rule as convey check)."""
    return " ".join(html.unescape(text).split())


def named(src: str) -> dict[str, Elem]:
    out = {}
    for e in parse(src)[0]:
        if e.id and e.id not in out:
            out[e.id] = e
    return out


def kind(e: Elem) -> str | None:
    """'text' (words only), 'list' (items of words only), or None (takes notes, not typed edits)."""
    if e.tag in ("style", "script", "svg", "figure") or "data-chart" in e.attrs:
        return None
    if not e.children:
        return "text" if e.bind or "".join(e.direct).strip() else None  # an emptied container is not a text
    if e.tag in ("ul", "ol") and all(c.tag == "li" and not c.children for c in e.children):
        return "list"
    return None


def value(src: str, e: Elem):
    k = kind(e)
    if k == "text":
        return clean(src[e.inner:e.inner_end])
    if k == "list":
        return [clean(src[c.inner:c.inner_end]) for c in e.children]
    return None


def read(src: str, did: str):
    e = named(src).get(did)
    return None if e is None else value(src, e)


class NotEditable(ValueError):
    pass


def write(src: str, did: str, new) -> str:
    """The slide with object `did` showing `new` (a string, or a list of strings for a list). Only its words change."""
    e = named(src).get(did)
    if e is None:
        raise NotEditable(f"no object named {did!r} on this slide")
    k = kind(e)
    if k is None:
        raise NotEditable(f"{did} holds more than words (a chart, a group or a picture): leave a note instead")
    esc = lambda s: html.escape(" ".join(str(s).split()), quote=False)
    if k == "text":
        if isinstance(new, list):
            raise NotEditable(f"{did} is one text, not a list")
        out = src[:e.inner] + esc(new) + src[e.inner_end:]
    else:
        items = new if isinstance(new, list) else [x for x in str(new).split("\n")]
        items = [x for x in items if str(x).strip()]
        if not items:
            raise NotEditable(f"{did} would be an empty list: leave a note to remove it")
        if len(items) == len(e.children):  # same items: each keeps its own tag and attributes
            out, last = [], e.inner
            for c, t in zip(e.children, items):
                out += [src[last:c.inner], esc(t)]
                last = c.inner_end
            out = src[:e.inner] + "".join(out) + src[last:]
        else:
            tag = e.children[0].raw if e.children else "<li>"
            out = src[:e.inner] + "".join(f"{tag}{esc(t)}</li>" for t in items) + src[e.inner_end:]
    return out


def retitle(src: str, old: str, new: str) -> str:
    """The page's <title> follows the headline when it showed the same words."""
    t = parse(src)[1]
    if t is None or clean(src[t.inner:t.inner_end]) != clean(old):
        return src
    return src[:t.inner] + html.escape(" ".join(new.split()), quote=False) + src[t.inner_end:]


def slide_id(src: str) -> str | None:
    m = re.search(r"<section\b[^>]*\bdata-slide=[\"']([^\"']+)", src)
    return m.group(1) if m else None


def signatures(src: str) -> dict[str, str]:
    """Each named object's own look and words (its start tag and its own text, children's excluded), for telling
    what changed between two versions. A child's change shows on the child, not its parent."""
    out = {}
    for e in parse(src)[0]:
        if e.id and e.id not in out:
            out[e.id] = " ".join(e.raw.split()) + " | " + clean("".join(e.direct))
            if kind(e) == "list":
                out[e.id] += " | " + " / ".join(value(src, e))
    return out


def outside(src: str) -> str:
    """The slide with every named object cut out: what's left changing means a change outside the named objects."""
    spans = sorted((e.start, e.end) for e in parse(src)[0] if e.id)
    out, last = [], 0
    for a, b in spans:
        if a < last:
            continue
        out.append(src[last:a])
        last = b
    out.append(src[last:])
    return " ".join("".join(out).split())
