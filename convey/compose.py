"""convey compose: a deterministic first draft of every slide, from the storyboard and the brand.

    convey compose DIR [--brand NAME] [--force]

For each storyboard slide, takes its pattern's skeleton (patterns/<id>/skeleton.html, or the slide's
`variant`: patterns/<id>/<variant>.html), fills every data-bind with the slide's content, drops items
the content doesn't have and repeats ones it has more of, and writes DIR/slides/NN-<id>.html with the
brand's tokens.css, the patterns' base.css and chart.js beside it.

A variant names how it uses the template (data-role on its section): "title-only" sits on the template's
title-only layout, its headline in the title placeholder and the layout's logo and footer kept; "full-bleed"
paints its own ground over the whole slide, on the same layout when there is one (so its headline is still
the slide's real title: PowerPoint's outline, and its accessibility check, read it), else the blank layout.
Either way the variant's own grid is the design, so no placeholder filling.
Variants may also carry data-class="PATH" (adds the class is-<value>, such as an item's status "pick"),
data-when="PATH=VALUE" (kept only when the field matches; "!=" for not, no "=" for present), and an
<img data-bind="content.image"> (the file is copied into slides/). A slide's `emphasis` words are wrapped
in the headline as <span class="hit">, which a variant colors only where it painted the fill.

On a brand whose layout for the pattern has its own placeholders, each text goes INTO the layout:
it takes the placeholder's position, size and type style and is marked data-ph, so export writes
it into that placeholder, and the skeleton's own decoration (data-deco, and boxes left empty) is
dropped, because the layout already draws its rules and marks. The layout's picture is shown under
the slide (data-underlay) when `convey brand render` has made one. Slots the layout has no
placeholder for keep the skeleton's grid. A big number, options, a timeline and a chart with its takeaway go on a
layout only when the template has one made for them, found by name (brand.NAMED); otherwise, or when the item count
misses the layout's numbered slots, or a caveat has no slot, the skeleton keeps its grid on the title-only layout,
only its headline in a placeholder. The slide names its layout (data-layout), which export and lint follow.

Refuses to run until the story is approved (storyboard.approved), unless the brief says just-build.
This is a first draft: the agent then designs each slide by editing its HTML; lint and check keep it honest.
"""
from __future__ import annotations

import copy
import html
import json
import re
import shutil
import sys
from html.parser import HTMLParser
from pathlib import Path

from .skald.lines import author_pt as whole_pt  # authoring: ties round down
from . import powerpoint
from .brand import NAMED, _line, bind_named

SKILL = Path(__file__).resolve().parent.parent
SKELETON = {"closing": "cover"}
VOID = {"br", "img", "meta", "link", "input", "hr", "source", "path", "rect", "circle", "line", "polygon",
        "polyline", "ellipse", "stop", "col", "wbr"}


# ---------- a small HTML tree ----------

class Node:
    def __init__(self, tag, attrs=None, parent=None):
        self.tag, self.attrs, self.children, self.parent = tag, list(attrs or []), [], parent

    def get(self, k, d=None):
        return next((v for a, v in self.attrs if a == k), d)

    def set(self, k, v):
        for i, (a, _) in enumerate(self.attrs):
            if a == k:
                self.attrs[i] = (k, v)
                return
        self.attrs.append((k, v))

    def walk(self):
        yield self
        for c in self.children:
            if isinstance(c, Node):
                yield from c.walk()

    def text(self, value: str):
        self.children = [html.escape(value, quote=False)]

    def remove(self):
        self.parent.children.remove(self)

    def html(self) -> str:
        if self.tag == "#root":
            return "".join(c if isinstance(c, str) else c.html() for c in self.children)
        a = "".join(f" {k}" if v is None else f" {k}='{v}'" if '"' in v and "'" not in v and "&" not in v
                    else f' {k}="{html.escape(v)}"' for k, v in self.attrs)
        if self.tag in VOID:
            return f"<{self.tag}{a}>" if self.tag not in ("path", "rect", "circle", "line", "polygon", "polyline",
                                                           "ellipse", "stop") else f"<{self.tag}{a}/>"
        inner = "".join(c if isinstance(c, str) else c.html() for c in self.children)
        return f"<{self.tag}{a}>{inner}</{self.tag}>"


class Tree(HTMLParser):
    RAW = {"script", "style"}

    def __init__(self, text: str):
        super().__init__(convert_charrefs=False)
        self.root = Node("#root")
        self.cur = self.root
        self.feed(text)

    def handle_decl(self, decl):
        self.cur.children.append(f"<!{decl}>")

    def handle_comment(self, data):
        self.cur.children.append(f"<!--{data}-->")

    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs, self.cur)
        self.cur.children.append(n)
        if tag not in VOID:
            self.cur = n

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(Node(tag, attrs, self.cur))

    def handle_endtag(self, tag):
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.children.append(data)

    def handle_entityref(self, name):
        self.cur.children.append(f"&{name};")

    def handle_charref(self, name):
        self.cur.children.append(f"&#{name};")


# ---------- content ----------

def field(slide: dict, path: str):
    node = slide
    for part in path.split("."):
        if isinstance(node, list) and part.isdigit():
            node = node[int(part)] if int(part) < len(node) else None
        elif isinstance(node, dict):
            node = node.get(part)
        else:
            return None
        if node is None:
            return None
    return node


ITEM = re.compile(r"^(?P<list>.+?)\.(?P<i>\d+)(?:\.|$)")


def _item_of(node: Node):
    """(list path, index) when every data-bind inside this node belongs to one item of one list."""
    keys = set()
    for n in node.walk():
        b = n.get("data-bind")
        if b:
            m = ITEM.match(b)
            if not m:
                return None
            keys.add((m.group("list"), int(m.group("i"))))
    return keys.pop() if len(keys) == 1 else None


PATHS = ("data-bind", "data-class", "data-when", "data-index", "data-icon-bind")


def _renumber(node: Node, lst: str, old: int, new: int):
    for n in node.walk():
        for k in PATHS:
            b = n.get(k)
            if b and re.match(rf"{re.escape(lst)}\.{old}(?![0-9])", b):  # items.1 must not catch items.10
                n.set(k, f"{lst}.{new}" + b[len(f"{lst}.{old}"):])
        did = n.get("data-id")
        if did:
            n.set("data-id", re.sub(rf"{old + 1}(?!\d)", str(new + 1), did, count=1) if str(old + 1) in did else f"{did}-{new + 1}")


def fit_items(root: Node, slide: dict):
    """Drop item containers the content doesn't have; repeat the last one for extra items."""
    containers: dict[str, dict[int, Node]] = {}
    for n in list(root.walk()):
        it = _item_of(n)
        if it and (n.parent is None or _item_of(n.parent) != it):
            containers.setdefault(it[0], {})[it[1]] = n
    for lst, nodes in containers.items():
        items = field(slide, lst)
        count = len(items) if isinstance(items, list) else 0
        for i, n in nodes.items():
            if i >= count:
                n.remove()
        top = max(nodes)
        last = nodes[top]
        for i in range(top + 1, count):
            twin = copy.deepcopy(last)
            _renumber(twin, lst, top, i)
            parent = last.parent
            twin.parent = parent
            parent.children.insert(parent.children.index(last) + 1 + (i - top - 1), twin)


def wrap_items(root: Node, slide: dict):
    """More than four items in one row squeeze each into a sliver: wrap them into rows of three (or four from
    seven on), the last row left-aligned. Only items that sit side by side in a flex row are touched."""
    groups: dict[int, list[Node]] = {}
    for n in root.walk():
        it = _item_of(n)
        if it and n.parent is not None and _item_of(n.parent) != it:
            groups.setdefault(id(n.parent), []).append(n)
    for kids in groups.values():
        if len(kids) <= 4:
            continue
        per = 3 if len(kids) <= 6 else 4
        par = kids[0].parent
        par.set("style", ((par.get("style") or "") + ";flex-wrap:wrap;row-gap:28px").lstrip(";"))
        for k in kids:
            k.set("style", ((k.get("style") or "") + f";flex:0 0 calc((100% - {(per - 1) * 32}px) / {per})").lstrip(";"))


ITEM_SLOT = re.compile(r"^(finding|metric|option|milestone) (\d+)$")


# The list a pattern's numbered slots hold, when it isn't content.items.
SLOT_LIST = {"timeline": "milestones"}


def item_slots(lay: dict) -> int:
    """How many numbered item slots a layout has ("Finding 1".."Finding 3" = 3); 0 when it has none."""
    nums = {int(m.group(2)) for p in lay.get("placeholders", []) if (m := ITEM_SLOT.match((p.get("name") or "").lower()))}
    return max(nums) if nums else 0


# The content plate's box, written on the element (the default skeletons don't load base.css): the body zone under a
# two-line headline and above the footer, 24 px wider than the text on each side.
PLATE = ("position:absolute;left:calc(var(--brand-margin-left) - 24px);"
         "top:calc(var(--brand-margin-top) + 2 * var(--brand-headline-line) + 28px);"
         "width:calc(var(--brand-content-width) + 48px);"
         "height:calc(var(--brand-margin-footer-top) - var(--brand-margin-top) - 2 * var(--brand-headline-line) - 40px);"
         "background:var(--brand-plate, var(--brand-raised))")


def band_plate(section: Node, lay: dict, brand: dict) -> str | None:
    """The plate's box on a title or section layout: around the slide's texts that sit off the layout's own filled
    shapes (its title band), 24 px wider and 12 px taller than them, its edges kept off those shapes; None when every
    text sits on the band."""
    shapes = [d["geometry"] for d in (((brand.get("master") or {}).get("drawn") or []) if lay.get("show_master_shapes")
                                      else []) + (lay.get("drawn") or []) if d.get("color") and d.get("geometry")]
    on = lambda r, g: g["x"] <= r[0] + r[2] / 2 <= g["x"] + g["w"] and g["y"] <= r[1] + r[3] / 2 <= g["y"] + g["h"]  # noqa: E731
    rects, loose = [], False
    for n in section.walk():
        if n.get("data-bind") is None:
            continue
        st = decls_of(n.get("style") or "")
        try:
            r = [float(st[k].replace("px", "")) for k in ("left", "top", "width", "height")]
        except (KeyError, ValueError):
            loose = loose or n.get("data-bind") != "headline"  # placed by the skeleton's own CSS: somewhere below
            continue
        if not any(on(r, g) for g in shapes):
            rects.append(r)
    if not rects:
        return None
    x0, y0 = min(r[0] for r in rects) - 24, min(r[1] for r in rects) - 12
    x1, y1 = max(r[0] + r[2] for r in rects) + 24, max(r[1] + r[3] for r in rects) + 12
    if loose:  # a text the skeleton places (a cover's meta line) sits between the band and the footer: reach the footer
        y1 = max(y1, float((brand.get("margins") or {}).get("footer_top") or y1))
    for g in shapes:  # keep clear of the band: above the text block, the plate starts under it; below, ends over it
        if min(x1, g["x"] + g["w"]) > max(x0, g["x"]) and min(y1, g["y"] + g["h"]) > max(y0, g["y"]):
            if g["y"] + g["h"] / 2 < (y0 + y1) / 2:
                y0 = max(y0, g["y"] + g["h"])
            else:
                y1 = min(y1, g["y"])
    return (f"position:absolute;left:{x0:g}px;top:{y0:g}px;width:{x1 - x0:g}px;height:{max(0, y1 - y0):g}px;"
            "background:var(--brand-plate, var(--brand-raised))")


def plain_layout(layouts: dict) -> dict | None:
    """The template's title-only layout: by name, else the one with a title and the fewest other text slots."""
    for name, lay in layouts.items():
        if re.fullmatch(r"title only", name.strip().lower()):
            return lay
    titled = [l for l in layouts.values() if any(p["type"] == "title" for p in l.get("placeholders", []))]
    return min(titled, key=lambda l: sum(p["type"] in ("body", "obj", "pic", "chart") for p in l["placeholders"]), default=None)


def add_legend(section: Node, slide: dict):
    """A chart's key, as HTML (a swatch and a label per entry) that chart.js places over the plot: every series of a
    multi-series chart, or the storyboard's own `content.legend` ([{label, color}]) for a one-series chart whose bars
    take their own colors. Before Oct 18, 2026 compose wrote none, and a four-option chart was unreadable."""
    content = slide.get("content") or {}
    spec = content.get("chart")
    fig = next((n for n in section.walk() if n.tag == "figure" and n.get("data-chart") is not None), None)
    if not isinstance(spec, dict) or fig is None:
        return
    if any(n.get("data-legend-for") == (fig.get("data-id") or "chart") for n in section.walk()):
        return
    if content.get("legend"):
        entries = [(e.get("color", ""), f"content.legend.{i}.label") for i, e in enumerate(content["legend"])]
        labels = [e.get("label", "") for e in content["legend"]]
    elif len(spec.get("series", [])) > 1:
        entries = [(s_.get("color") or f"var(--brand-data-{min(k, 5)})", f"content.chart.series.{k - 1}.name")
                   for k, s_ in enumerate(spec["series"], 1)]
        labels = [s_.get("name", "") for s_ in spec["series"]]
    else:
        return
    try:  # the figure's spec, a variant's look merged in, sets the key's type size
        size = int(json.loads(fig.get("data-chart") or "{}").get("fontSize") or spec.get("fontSize", 16))
    except ValueError:
        size = int(spec.get("fontSize", 16))
    line = spec.get("type") == "line"
    key = "width:24px;height:4px;border-radius:2px" if line else f"width:{size - 2}px;height:{size - 2}px;border-radius:3px"
    fid = fig.get("data-id") or "chart"
    box = Node("div", [("data-id", f"{fid}-legend"), ("data-legend-for", fid),
                       ("style", "position:absolute;display:flex;align-items:center;column-gap:28px")], section)
    for i, ((color, bind), label) in enumerate(zip(entries, labels), 1):
        item = Node("div", [("data-id", f"{fid}-legend-{i}"), ("style", "display:flex;align-items:center;column-gap:10px")], box)
        swatch = Node("div", [("data-id", f"{fid}-legend-{i}-key"), ("style", f"{key};background:{color}")], item)
        txt = Node("p", [("data-id", f"{fid}-legend-{i}-label"), ("data-bind", bind),
                         ("style", f"margin:0;font-size:{size}px;line-height:{round(size * 1.25)}px;white-space:nowrap;"
                                   "color:var(--brand-body)")], item)
        txt.text(label)
        item.children = [swatch, txt]
        box.children.append(item)
    section.children.insert(section.children.index(fig) + 1 if fig in section.children else len(section.children), box)


def fit_wires(root: Node):
    """Connectors that chain numbered boxes (data-from="s1" data-to="s2", ...) follow the boxes fit_items kept:
    a wire to a box that is gone goes, and a chain grows a wire for every box added after its last one."""
    ids = {n.get("data-id") for n in root.walk() if n.get("data-id")}
    num = re.compile(r"^(?P<p>\D*)(?P<i>\d+)$")
    wires = [n for n in root.walk() if n.get("data-from") and n.get("data-to")]
    for w in wires:
        if w.get("data-from") not in ids or w.get("data-to") not in ids:
            w.remove()
    chains: dict[str, Node] = {}
    for w in [w for w in wires if w.parent and w in w.parent.children]:
        a, b = num.match(w.get("data-from")), num.match(w.get("data-to"))
        if a and b and a["p"] == b["p"] and int(b["i"]) == int(a["i"]) + 1:
            last = chains.get(a["p"])
            if last is None or int(num.match(last.get("data-to"))["i"]) < int(b["i"]):
                chains[a["p"]] = w
    for pre, last in chains.items():
        k = int(num.match(last.get("data-to"))["i"])
        while f"{pre}{k + 1}" in ids:
            twin = copy.deepcopy(last)
            twin.set("data-from", f"{pre}{k}")
            twin.set("data-to", f"{pre}{k + 1}")
            wid = last.get("data-id") or "a"
            m = num.match(wid)
            twin.set("data-id", f"{m['p']}{int(m['i']) + 1}" if m else f"{wid}-{k}")
            twin.parent = last.parent
            last.parent.children.insert(last.parent.children.index(last) + 1, twin)
            last, k = twin, k + 1


# The storyboard owns a chart's data; a variant may set how it looks (value labels on, type size, bar gap,
# horizontal bars), and those keys of the skeleton's own spec win.
# What the storyboard owns in a chart; a variant only sets how it looks. The type is the story's too: a variant's
# "column" turned a 21-year line and a set of horizontal bars into columns (Oct 18, 2026 stress test).
CHART_DATA = {"type", "categories", "series", "axis", "stacked", "colors", "labelFormat"}


def fill(root: Node, slide: dict, claim_ids: list[str], images: dict | None = None):
    for n in root.walk():
        b = n.get("data-bind")
        if n.get("data-claims") is not None:
            n.set("data-claims", ",".join(claim_ids))
        if not b:
            continue
        v = field(slide, b)
        if n.tag == "img":
            if v:
                n.set("src", (images or {}).get(str(v), Path(str(v)).name))
                focus = field(slide, "content.focus")
                if focus:
                    n.set("style", re.sub(r";?\s*object-position:[^;]*", "", n.get("style") or "") + f";object-position:{focus}")
            continue
        if b.endswith("chart") and isinstance(v, dict):
            try:
                look = {k: x for k, x in json.loads(n.get("data-chart") or "{}").items() if k not in CHART_DATA}
            except ValueError:
                look = {}
            spec = {**copy.deepcopy(v), **look}
            for k, s in enumerate(spec.get("series", []), 1):
                s.setdefault("color", f"var(--brand-data-{min(k, 5)})")
            n.set("data-chart", json.dumps(spec, ensure_ascii=False))
        elif n.tag in ("ul", "ol"):
            items = v if isinstance(v, list) else []
            n.children = [x for x in n.children if not (isinstance(x, Node) and x.tag == "li")]
            for x in items:
                li = Node("li", [], n)
                li.text(str(x))
                n.children.append(li)
        elif v is not None:
            n.text(str(v))


def _when(slide: dict, test: str) -> bool:
    neg = "!=" in test
    path, _, want = test.partition("!=" if neg else "=")
    got = field(slide, path.strip())
    if not _ and not neg:
        return got not in (None, "", [], False)
    return (str(got) == want.strip()) != neg


def variant_attrs(root: Node, slide: dict):
    """data-when keeps an element only when its test holds; data-class adds is-<value> from a content field;
    data-index="content.steps.3" writes the item's number ("4", or "04" with data-pad="2"), which is never a
    claim; data-icon-bind="content.items.0.icon" puts in the skill's icon of that name (assets/), at the
    placeholder's size, or drops the placeholder when the item names none."""
    from . import assets
    for n in list(root.walk()):
        path = n.get("data-icon-bind")
        if path is None or n.parent is None:
            continue
        name = field(slide, path)
        if not name:
            n.remove()
            continue
        try:
            svg = assets.svg(str(name), float(n.get("width") or 40), data_id=n.get("data-id"), cls=n.get("class"),
                             style=n.get("style"))
        except (KeyError, ValueError) as e:
            raise SystemExit(f"compose refused: {slide['id']}: {path} is {name!r}: {e}")
        icon = next(c for c in Tree(svg).root.children if isinstance(c, Node))
        icon.parent = n.parent
        n.parent.children[n.parent.children.index(n)] = icon
    for n in root.walk():
        path = n.get("data-index")
        if path and re.search(r"\.(\d+)$", path):
            n.text(str(int(re.search(r"\.(\d+)$", path).group(1)) + 1).zfill(int(n.get("data-pad") or 1)))
            n.set("data-not-claim", None)
    for n in list(root.walk()):
        t = n.get("data-when")
        if t is not None and n.parent is not None and not _when(slide, t):
            n.remove()
    for n in root.walk():
        path = n.get("data-class")
        if path:
            v = field(slide, path)
            if v not in (None, "", [], False):
                n.set("class", " ".join(filter(None, [n.get("class"), "is-" + _slug(str(v))])))


def emphasize(root: Node, words: list[str]):
    """Wrap each emphasis word's first appearance in the headline as <span class="hit">."""
    head = next((n for n in root.walk() if n.get("data-bind") == "headline"), None)
    if head is None or not words or len(head.children) != 1 or not isinstance(head.children[0], str):
        return
    text = head.children[0]
    for w in words:
        e = html.escape(w, quote=False)
        m = re.search(rf"(?<![\w>]){re.escape(e)}(?!\w)", text)
        if m:
            text = text[:m.start()] + f'<span class="hit">{e}</span>' + text[m.end():]
    head.children = [text]


def drop_dead_css(doc: str) -> str:
    """Drop the skeleton's style rules that match nothing on the composed slide: rules for the placeholders compose
    replaced with the layout's own (inline) styles, and for parts the slide doesn't use. They can't change the drawing,
    but an agent reads them on every slide, and editing one did nothing (the token diet, Oct 18, 2026). A rule goes
    only when every selector in it names a class no element carries; at-rules and class-free selectors stay."""
    styles = list(re.finditer(r"(<style[^>]*>)(.*?)(</style>)", doc, re.S))
    rest = re.sub(r"<style[^>]*>.*?</style>", "", doc, flags=re.S)
    have = {c for m in re.finditer(r"""class\s*=\s*(["'])(.*?)\1""", rest, re.S) for c in m.group(2).split()}

    def live(selectors: str) -> bool:
        for sel in selectors.split(","):
            names = re.findall(r"\.(-?[_a-zA-Z][\w-]*)", sel)
            if not names or all(n in have for n in names):
                return True
        return False

    def clean(css: str) -> str:
        out, i, n = [], 0, len(css)
        while i < n:
            j = css.find("{", i)
            if j < 0:
                out.append(css[i:])
                break
            depth, k = 1, j + 1
            while k < n and depth:
                depth += {"{": 1, "}": -1}.get(css[k], 0)
                k += 1
            head = css[i:j]
            sel = re.sub(r"/\*.*?\*/", "", head, flags=re.S).strip()
            if sel.startswith("@") or live(sel):
                out.append(css[i:k])
            i = k  # a dropped rule goes with the line break before it
        return "".join(out)

    for m in reversed(styles):
        doc = doc[:m.start(2)] + clean(m.group(2)) + doc[m.end(2):]
    return doc


USED_BY_CODE = {"not_claims", "focus", "legend"}  # read by compose itself (claims, a photo's crop, the chart key)


def dropped_slots(binds: list[str], slide: dict) -> list[str]:
    """The storyboard's content the composed slide uses nowhere: a slot (or an item's field) that no data-bind,
    data-class, data-when, data-index or data-icon-bind of the design names (`binds`, read before fill)."""
    has = lambda path: any(b == path or b.startswith(path + ".") for b in binds)  # noqa: E731
    out = []
    for k, v in (slide.get("content") or {}).items():
        if k in USED_BY_CODE or v in (None, "", []):
            continue
        if not has(f"content.{k}"):
            out.append(f"content.{k}")
        elif isinstance(v, list) and all(isinstance(x, dict) for x in v):
            for sub in dict.fromkeys(f for x in v for f in x):
                if not any(has(f"content.{k}.{j}.{sub}") for j, x in enumerate(v) if x.get(sub) not in (None, "")):
                    if any(x.get(sub) not in (None, "") for x in v):
                        out.append(f"content.{k}[].{sub}")
    return out


def prune(root: Node, slide: dict):
    """Remove bound elements with no content, then arrows whose ends are gone."""
    for n in list(root.walk()):
        b = n.get("data-bind")
        if b and field(slide, b) in (None, "", []):
            if n.parent:
                n.remove()
    ids = {n.get("data-id") for n in root.walk()}
    for n in list(root.walk()):
        if (n.get("data-from") and n.get("data-from") not in ids) or (n.get("data-to") and n.get("data-to") not in ids):
            n.remove()


# ---------- the layout's placeholders ----------

# slot path pattern -> how to find its placeholder: ("type", ...) or ("name", regex with {n} = item number)
MATCH = [
    (r"^headline$", ("type", "title", "ctrTitle")),
    (r"^content\.subtitle$", ("type", "subTitle")),
    (r"^content\.subtitle$", ("name", r"standfirst|subtitle")),
    (r"^content\.meta$", ("name", r"stamp|meta|date|presenter|address")),
    (r"^content\.number$", ("name", r"section number|^number$")),
    (r"^content\.standfirst$", ("name", r"standfirst|subtitle")),
    (r"^caveat$", ("name", r"standfirst")),  # the qualification sits right under the headline when it can
    (r"^content\.items\.(\d+)\.head$", ("name", r"^finding {n}$")),
    (r"^content\.items\.(\d+)\.text$", ("name", r"^finding {n} detail$")),
    (r"^content\.items\.(\d+)\.value$", ("name", r"^metric {n}$")),
    (r"^content\.items\.(\d+)\.label$", ("name", r"^metric {n} label$")),
    (r"^content\.items\.(\d+)\.note$", ("name", r"^metric {n} note$")),
    (r"^content\.evidence$", ("name", r"evidence")),
    (r"^content\.source$", ("name", r"^source")),
    (r"^content\.left\.head$", ("name", r"left heading")),
    (r"^content\.left\.points$", ("name", r"left content")),
    (r"^content\.right\.head$", ("name", r"right heading")),
    (r"^content\.right\.points$", ("name", r"right content")),
    (r"^content\.chart$", ("type", "chart")),
    # The layouts bound by name alone (brand.NAMED), by their placeholders' names: a big number, its label, what it
    # is compared with and a second remark; options and their details; milestones' dates, names and notes; a chart's
    # explanation (Oct 18, 2026).
    (r"^content\.value$", ("name", r"^number$")),
    (r"^content\.label$", ("name", r"^number label$")),
    (r"^content\.evidence$", ("name", r"number context")),
    (r"^content\.turn$", ("name", r"^comparison$")),
    (r"^content\.items\.(\d+)\.head$", ("name", r"^option {n}$")),
    (r"^content\.items\.(\d+)\.text$", ("name", r"^option {n} detail$")),
    (r"^content\.milestones\.(\d+)\.when$", ("name", r"^milestone {n} date$")),
    (r"^content\.milestones\.(\d+)\.label$", ("name", r"^milestone {n}$")),
    (r"^content\.milestones\.(\d+)\.note$", ("name", r"^milestone {n} note$")),
    (r"^content\.takeaway$", ("name", r"explanation")),
]


def placeholder_for(path: str, phs: list[dict], used: set):
    for pat, how in MATCH:
        m = re.match(pat, path)
        if not m:
            continue
        n = int(m.group(1)) + 1 if m.groups() else 0
        for p in phs:
            if p["idx"] in used:
                continue
            if how[0] == "type" and p["type"] in how[1:]:
                return p
            if how[0] == "name" and p["type"] not in ("title", "ctrTitle", "ftr", "sldNum", "dt") and \
                    re.search(how[1].format(n=n), (p.get("name") or "").lower()):
                return p
    return None


def _inherited(ph: dict, brand: dict) -> dict:
    """A placeholder's type style with the master's filled in under it, as PowerPoint inherits it:
    titles from the master's title style, everything else from its body style (first level)."""
    styles = (brand.get("master") or {}).get("text_styles") or {}
    key = "titleStyle" if ph.get("type") in ("title", "ctrTitle") else "bodyStyle"
    base = (styles.get(key) or [{}])[0] or {}
    return {**base, **(ph.get("style") or {})}


def _style_css(ph: dict, brand: dict) -> str:
    g, st = ph["geometry"], _inherited(ph, brand)
    css = [f"position:absolute", f"left:{g['x']:g}px", f"top:{g['y']:g}px", f"width:{g['w']:g}px", "margin:0", "padding:0"]
    if st.get("size"):
        css.append(f"font-size:{st['size']:g}px")
        # the template's own spacing: exact points, or a multiple of single (90% on Berlin's titles), else single
        css.append(f"line-height:{whole_pt(_line(st, st['size'] * 1.2)):g}px")  # whole points: skald/lines.py
        if st.get("tracking_pt") is not None:
            css.append(f"letter-spacing:{st['tracking_pt'] / (st['size'] * 0.75):.4f}em")
    if st.get("upper"):  # the template's all-caps style (export writes it back as cap="all")
        css.append("text-transform:uppercase")
    if st.get("font"):
        fam, wt = _face(st["font"], brand)
        if fam:
            css.append(f'font-family:"{fam}"')
            css.append(f"font-weight:{700 if st.get('bold') and wt == 400 else wt}")
    if st.get("color"):
        css.append(f"color:{_color(st['color'], brand)}")
    if st.get("align"):
        css.append("text-align:" + {"l": "left", "ctr": "center", "r": "right", "just": "left"}.get(st["align"], "left"))
    return ";".join(css)


def _face(face: str, brand: dict) -> tuple[str | None, int]:
    for f in brand["fonts"].values():
        for w, name in (f.get("faces") or {}).items():
            name, bold = (name[0], name[1]) if isinstance(name, list) else (name, False)
            if name == face and not bold:
                return f["css"], int(w)
    for f in brand["fonts"].values():
        if face == f.get("css") or face == f.get("powerpoint"):
            return f["css"], 400
    return None, 400


def _color(hexv: str, brand: dict) -> str:
    tokens = {}
    tpath = brand.get("_dir") and Path(brand["_dir"]) / "tokens.css"
    if tpath and tpath.exists():
        tokens = {v.upper(): k for k, v in re.findall(r"--(brand-[a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})", tpath.read_text())}
    k = tokens.get(hexv.upper())
    return f"var(--{k})" if k else hexv


# Patterns with one message and a line or two around it: a slot with no named placeholder takes the
# layout's next free text placeholder (reading order), so a near-match layout's caption slots get used.
SPARE = {"cover", "closing", "section", "key-finding"}


def onto_layout(root: Node, section: Node, phs: list[dict], brand: dict, pattern: str = "", strip: bool = True) -> int:
    """Move each bound text into its layout placeholder. Returns how many non-title slots matched. With strip, the
    skeleton's decoration goes once anything moved (the layout draws its own); a title-only fallback keeps it."""
    used, moved = set(), 0
    nodes = [n for n in list(root.walk()) if n.get("data-bind")]
    picks = {}
    for n in nodes:
        ph = placeholder_for(n.get("data-bind"), phs, used)
        if ph and ph.get("geometry"):
            used.add(ph["idx"])
            picks[id(n)] = ph
    if pattern in SPARE:
        free = sorted((p for p in phs if p["type"] in ("body", "subTitle", "obj") and p["idx"] not in used and p.get("geometry")),
                      key=lambda p: (p["geometry"]["y"], p["geometry"]["x"]))
        for n in nodes:
            if id(n) not in picks and n.get("data-bind") not in ("headline",) and free:
                ph = free.pop(0)
                used.add(ph["idx"])
                picks[id(n)] = ph
    for n in nodes:
        b = n.get("data-bind")
        ph = picks.get(id(n))
        if not ph:
            continue
        # The text owns its placeholder's whole box: lint then refuses text that outgrows the slot.
        css = _style_css(ph, brand) + f";height:{ph['geometry']['h']:g}px"
        if n.tag in ("ul", "ol"):  # out of its box, a list keeps the skeleton's text marker and spacing
            css += ';list-style-type:"–  ";padding-left:24px'
            for li in [c for c in n.children if isinstance(c, Node) and c.tag == "li"][1:]:
                li.set("style", "margin-top:8px")
        n.set("style", css)
        n.set("class", " ".join(c for c in (n.get("class") or "").split() if c in ("chart-fig",)))
        if ph["type"] not in ("title", "ctrTitle", "chart"):
            n.set("data-ph", str(ph["idx"]))
            moved += 1
        if n.parent is not section:  # hoist out of the skeleton's flex rows, so the position is the slide's
            n.remove()
            n.parent = section
            section.children.append(n)
    if moved and strip:
        for n in list(root.walk()):
            if n.get("data-deco") is not None and n.parent:
                n.remove()
        gone = True
        while gone:  # containers the moves left with no text are skeleton decoration; a box that held only such
            gone = False  # boxes goes on the next pass (the big number's rule around its moved label, Oct 18, 2026)
            for n in list(section.walk()):
                if n is section or n.tag in ("svg", "script", "style", "img") or n.parent is None:
                    continue
                if not any(isinstance(c, Node) for c in n.walk() if c is not n) and not "".join(
                        c for c in n.children if isinstance(c, str)).strip():
                    if n.get("data-bind") is None and n.get("data-ph") is None:
                        n.remove()
                        gone = True
    return moved


# ---------- the deck ----------

def decls_of(style: str) -> dict:
    return {k.strip().lower(): v.strip() for k, _, v in (p.partition(":") for p in style.split(";")) if k.strip()}


def token_px(tokens: str, name: str) -> float | None:
    m = re.search(rf"--brand-{re.escape(name)}:\s*(-?[\d.]+)px", tokens)
    return float(m.group(1)) if m else None


CAVEAT_ADVANCE = 9.6  # px per character of 18 px text, on the wide side of common faces, so a row is never short


def caveat_row(section: Node, text: str, role: str | None, root: Node, tokens: str) -> Node:
    """The caveat compose adds where the design has no slot for it, at 18 px (read by the room). A variant (it loads
    base.css) gets a row of its own: the caveat sits at the bottom of the body zone and --caveat-row lifts --bottom
    (and a full-bleed variant's stack) by its lines and a 16 px gap, so the variant's panels end above it. Before
    Oct 18, 2026 it sat at a fixed offset over the variant's own panels on six slides of every stress-test deck.
    A default skeleton keeps its own grid: the caveat goes just above the footer (or above a source line there)."""
    ft = token_px(tokens, "margin-footer-top") or 672.0
    left = token_px(tokens, "margin-left") or 64.0
    bleed = role == "full-bleed"
    width = 1280 - 2 * min(left, 96) if bleed else (token_px(tokens, "content-width") or 1152.0)
    lines = max(1, -(-int(len(text) * CAVEAT_ADVANCE) // int(width)))
    h = lines * 24
    if role:
        top = min(ft - 24, 652) - h if bleed else ft - 24 - h
        # full-bleed stacks are drawn to end near y 640; a title-only body ends at --bottom (footer top - 24)
        row = max(0, 656 - top) if bleed else h + 16
        section.set("style", ((section.get("style") or "") + f";--caveat-row:{row:g}px").lstrip(";"))
        x = "left:var(--bleed-left);width:var(--bleed-width)" if bleed else \
            "left:var(--brand-margin-left);width:var(--brand-content-width)"
        css = f"position:absolute;{x};top:{top:g}px;font-size:18px;line-height:24px"
    else:
        low = any(n.get("data-bind") == "content.source" for n in root.walk())
        css = ("position:absolute;left:var(--brand-margin-left);width:var(--brand-content-width);"
               f"top:calc(var(--brand-margin-footer-top) - {'84' if low else '48'}px);font-size:18px;line-height:24px")
    cav = Node("p", [("class", "small"), ("data-id", "caveat"), ("data-bind", "caveat"), ("style", css)], section)
    cav.text(text)
    return cav


# Rough advance widths in em, for fitting a headline before any browser draws it: wide on purpose (a common sans set
# a few percent narrower), so a fitted headline never comes out a line longer than estimated.
NARROW, SLIM, WIDE = set("il.,:;!|'’ "), set("fjtrI()-[]/1"), set("mwMW")


def text_lines(text: str, size: float, width: float) -> int:
    """How many lines `text` takes at `size` px in a box `width` px wide, by greedy word wrap on estimated widths."""
    em = lambda ch: 0.28 if ch == " " else 0.25 if ch in NARROW else 0.36 if ch in SLIM else 0.84 if ch in WIDE else \
        0.66 if ch.isupper() else 0.56 if ch.isdigit() else 0.53  # noqa: E731
    lines, cur = 1, 0.0
    for w in text.split():
        ww = sum(em(c) for c in w) * size * 1.03
        if cur and cur + 0.28 * size + ww > width:
            lines, cur = lines + 1, ww
        else:
            cur += (0.28 * size if cur else 0) + ww
    return lines


def fit_lines(root: Node, slide: dict):
    """A variant's display text marked data-fit-lines="N" (with its size, line and width in px on the element) is set
    smaller, 4 px a step, its spacing in proportion, until the slide's words take N lines at most: a long headline on
    the photo slide ran into the subtitle under it on all three stress-test templates (Oct 18, 2026)."""
    for n in root.walk():
        most = n.get("data-fit-lines")
        b = n.get("data-bind")
        if not most or not b or not isinstance(field(slide, b), str):
            continue
        st = decls_of(n.get("style") or "")
        try:
            size, line, width = (float(st[k].replace("px", "")) for k in ("font-size", "line-height", "width"))
        except (KeyError, ValueError):
            continue
        text, fit = re.sub(r"<[^>]+>", "", field(slide, b)), size
        while fit > size * 0.6 and text_lines(text, fit, width) > int(most):
            fit -= 4
        if fit < size:
            n.set("style", re.sub(r"font-size:[^;]*", f"font-size:{fit:g}px",
                                  re.sub(r"line-height:[^;]*", f"line-height:{whole_pt(fit * line / size):g}px", n.get("style"))))


def fits(text: str, size: float, line: float, width: float, height: float) -> bool:
    """Whether a headline ends inside a title area `height` px tall (the last line's glyphs to 0.95 of the size)."""
    return (text_lines(text, size, width) - 1) * line + 0.95 * size <= height + 1


def fitted_size(heads: list[str], size: float, width: float, height: float, floor: float = 28) -> float:
    """The largest headline size, from `size` down in 2 px steps, at which every headline fits the title area."""
    while size > floor and not all(fits(h, size, whole_pt(size * 1.15), width, height) for h in heads):
        size -= 2
    return size


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def variants(pattern: str) -> list[str]:
    """A pattern's variants: its other .html files beside skeleton.html."""
    return sorted(f.stem for f in (SKILL / "patterns" / pattern).glob("*.html") if f.stem != "skeleton")


def skeleton(pattern: str, variant: str | None) -> Path:
    if variant:
        f = SKILL / "patterns" / pattern / f"{variant}.html"
        if not f.exists():
            raise SystemExit(f"compose refused: {pattern} has no variant {variant!r} "
                             f"(it has: {', '.join(variants(pattern)) or 'none'}; leave variant out for the default)")
        return f
    f = SKILL / "patterns" / pattern / "skeleton.html"
    if not f.exists():
        f = SKILL / "patterns" / SKELETON.get(pattern, pattern) / "skeleton.html"
    if not f.exists():
        raise SystemExit(f"compose refused: {pattern} has no default skeleton; pick a variant "
                         f"({', '.join(variants(pattern))})")
    return f


def blank_layout(layouts: dict) -> dict | None:
    """The template's blank layout: by type, else by name, else one with no text slots but footers."""
    for lay in layouts.values():
        if lay.get("type") == "blank" or re.fullmatch(r"blank", lay["name"].strip().lower()):
            return lay
    return next((l for l in layouts.values() if all(p["type"] in ("ftr", "sldNum", "dt") for p in l.get("placeholders", []))), None)


def copy_images(root: Node, slide: dict, d: Path, out: Path) -> dict:
    """Copy each bound picture (content.image, a path in the project) into slides/; refuse a photo variant
    with no photo, since a wash over nothing is a dark smear."""
    got = {}
    for n in root.walk():
        b = n.get("data-bind")
        if n.tag != "img" or not b:
            continue
        v = field(slide, b)
        if not v:
            others = [x for x in variants(slide["pattern"]) if "image" not in (SKILL / "patterns" / slide["pattern"] / f"{x}.html").read_text()]
            raise SystemExit(f"compose refused: {slide['id']} ({slide['pattern']}/{slide.get('variant') or 'skeleton'}) "
                             f"draws a photo but has no {b} (a picture from the person's material, a path in the project)."
                             + (f" Without one, use: {', '.join(others)}." if others else ""))
        src = (d / str(v)) if not Path(str(v)).is_absolute() else Path(str(v))
        if not src.exists():
            raise SystemExit(f"compose refused: {slide['id']}: {b} is {v!r}, which is not a file in {d}")
        shutil.copy(src, out / src.name)
        got[str(v)] = src.name
    return got


def hand_edited(out: Path) -> list[str]:
    """The slides changed since compose wrote them: each one beside its copy in slides/.composed/ (none = unknown)."""
    base = out / ".composed"
    return sorted(f.name for f in out.glob("*.html")
                  if (base / f.name).exists() and f.read_text() != (base / f.name).read_text())


def compose(d: Path, brand_dir: Path, force: bool = False, overwrite: bool = False, quiet: bool = False,
            keep_edits: bool = False) -> list[Path]:
    brief = json.loads((d / "brief.json").read_text())
    sb = json.loads((d / "storyboard.json").read_text())
    if not sb.get("approved") and brief.get("autonomy") != "just-build" and not force:
        raise SystemExit("compose refused: the story is not approved (storyboard.approved), and the brief is not just-build")
    if (d / "review" / "log.jsonl").exists() and not overwrite:
        raise SystemExit("compose refused: this deck is in review, and compose rewrites every slide, which would wipe the "
                         "person's typed fixes and the design work. Edit the slides instead (or --overwrite, after "
                         "`convey restore` if you need an earlier version)")
    # Design work done on the slides since the last compose: a second compose rewrote it without a word (explainer
    # build, Oct 19, 2026). Refuse, or carry it the way restyle carries edits onto another template.
    edited = hand_edited(d / "slides") if (d / "slides").is_dir() else []
    if edited and not overwrite and not keep_edits:
        raise SystemExit(f"compose refused: {len(edited)} slide(s) were edited since compose wrote them ("
                         + ", ".join(edited) + "). --keep-edits composes again and carries those edits (as restyle "
                         "does); --overwrite drops them")
    kept = {}
    if edited and keep_edits:
        kept = {n: ((d / "slides" / ".composed" / n).read_text(), (d / "slides" / n).read_text()) for n in edited}
    brand = json.loads((brand_dir / "brand.json").read_text())
    brand["_dir"] = str(brand_dir)
    layouts = {l["name"]: l for l in brand.get("layouts", [])}
    pics = {re.sub(r"^\d+-", "", p.stem): p for p in (brand_dir / "assets" / "layouts").glob("*.png")} \
        if (brand_dir / "assets" / "layouts").exists() else {}
    out = d / "slides"
    out.mkdir(exist_ok=True)
    shutil.copy(brand_dir / "tokens.css", out / "tokens.css")
    tokens = (brand_dir / "tokens.css").read_text()
    shutil.copy(SKILL / "convey" / "skald" / "chart.js", out / "chart.js")
    shutil.copy(SKILL / "patterns" / "base.css", out / "base.css")
    written, in_title, fitted = [], [], []
    # What compose wrote, kept beside the slides: `convey restyle` diffs the agent's design edits against it.
    base = out / ".composed"
    base.mkdir(exist_ok=True)
    for f in base.glob("*.html"):
        f.unlink()
    for i, s in enumerate(sb["slides"], 1):
        pattern = s["pattern"]
        tree = Tree(skeleton(pattern, s.get("variant")).read_text())
        root = tree.root
        section = next(n for n in root.walk() if n.tag == "section")
        section.set("data-pattern", pattern)
        section.set("data-slide", s["id"])
        role = section.get("data-role")
        fit_items(root, s)
        if not role and pattern != "timeline":  # a variant is drawn for its item counts (its pattern.md says how
            wrap_items(root, s)                    # many); a skeleton reflows, except a timeline: one line, in order
        fit_wires(root)
        paths = [n.get(a).split("=")[0] for n in root.walk() for a in PATHS if n.get(a)]  # what the design uses
        variant_attrs(root, s)
        images = copy_images(root, s, d, out)
        fill(root, s, s.get("claim_ids", []), images)
        emphasize(root, s.get("emphasis") or [])
        prune(root, s)
        if s.get("caveat") and not any(n.get("data-bind") == "caveat" for n in root.walk()):
            section.children.append(caveat_row(section, s["caveat"], role, root, tokens))
        key = pattern
        if pattern == "chart" and not s.get("variant") and (s.get("content") or {}).get("takeaway"):
            key = "chart-explained"  # a chart with its takeaway beside it: the template's layout for that, if any
        b = brand.get("bindings", {}).get(key)
        if b is None and key in NAMED:  # a brand ingested before these were bound: the same rule ingest uses now
            b = bind_named(brand.get("layouts", [])).get(key)
        lay = layouts.get(b["layout"] if isinstance(b, dict) else b) if b else None
        if lay is not None and key in NAMED and not role and s.get("caveat") and \
                placeholder_for("caveat", lay.get("placeholders", []), set()) is None:
            lay = None  # these layouts fill the body: a caveat with no slot of its own would land on their text
        if lay is None and key in NAMED and not role:
            # No layout made for it: the skeleton's own grid on the title-only layout, keeping its title and footer.
            lay = plain_layout(layouts)
            b = {"layout": lay["name"], "how": f"title only: no layout for {key}"} if lay else None
            if lay:
                section.set("data-layout", lay["name"])
        if role:
            lay = plain_layout(layouts) or blank_layout(layouts)
            b = {"layout": lay["name"], "how": f"variant drawn for the {role} layout"} if lay else None
            if lay:
                section.set("data-layout", lay["name"])
        # A layout with numbered item slots (and their drawn numbers and rules) fits only that many items: with more,
        # the extras landed on the skeleton's grid over the slots; with fewer, an empty slot's rule was left behind.
        # Such a slide goes on the template's title-only layout, its items on the skeleton's grid (Oct 18, 2026).
        items = (s.get("content") or {}).get(SLOT_LIST.get(pattern, "items"))
        if lay and not role and isinstance(items, list) and item_slots(lay) and len(items) != item_slots(lay):
            plain = plain_layout(layouts)
            if plain:
                lay, b = plain, {"layout": plain["name"], "how": "title only: items don't match the layout's slots"}
                section.set("data-layout", plain["name"])
        if lay:
            # The page names its layout, so export and lint use compose's choice, not the pattern's binding alone (a
            # chart with a takeaway, or a brand ingested before NAMED, has no binding of its own to look up).
            section.set("data-layout", lay["name"])
            how = b.get("how", "") if isinstance(b, dict) else ""
            fallback = how.startswith("title only")
            # On a title-only fallback only the headline takes a placeholder: the skeleton's grid starts where such a
            # layout's standfirst sits, so a caveat moved there overprinted the content (Oct 18, 2026).
            phs = [p for p in lay.get("placeholders", []) if not fallback or p["type"] in ("title", "ctrTitle")]
            moved = 0 if role else onto_layout(root, section, phs, brand, pattern, strip=not fallback)
            # A layout made for this pattern (bound by its name) draws its own accents: the skeleton's go.
            if not role and not how.startswith("title only") and (moved or ("name contains" in how and "near match" not in how)):
                for n in list(root.walk()):
                    if n.get("data-deco") is not None and n.parent:
                        n.remove()
                    elif n.get("class"):
                        n.set("class", " ".join(c for c in n.get("class").split() if c not in ("lead", "win")))
            pic = pics.get(_slug(lay["name"]))
            if pic:
                (out / "layouts").mkdir(exist_ok=True)
                shutil.copy(pic, out / "layouts" / pic.name)
                section.children.insert(0, "\n<style>.slide { isolation: isolate; }</style>\n")
                img = Node("img", [("data-underlay", None), ("alt", ""), ("src", f"layouts/{pic.name}"),
                                   ("style", "position:absolute;left:0;top:0;width:1280px;height:720px;z-index:-1")], section)
                section.children.insert(1, img)
        if (brand.get("plate") or {}).get("on") and role != "full-bleed":
            # The template's background can't carry small text (convey brand sheet measured it): the content sits on
            # a plate in the raised color, under everything the slide draws (Berlin's orange fade, Oct 18, 2026).
            # A title or section layout draws its own band for its title: a content-zone plate over it doubled the
            # shape (Berlin's cover), so there the plate goes only behind the texts off the band.
            own_band = pattern in ("cover", "closing", "section") or (lay or {}).get("type") in ("title", "secHead")
            box = band_plate(section, lay, brand) if own_band and lay else PLATE
            if box:
                plate = Node("div", [("class", "plate"), ("data-id", "plate"), ("style", box)], section)
                at = next((k + 1 for k, n in enumerate(section.children) if getattr(n, "tag", None) == "img"
                           and n.get("data-underlay") is not None), 0)
                section.children.insert(at, plate)
        fit_lines(root, s)
        add_legend(section, s)
        head = next((n for n in root.walk() if n.get("data-bind") == "headline"), None)
        title = next((p for p in (lay or {}).get("placeholders", []) if p["type"] in ("title", "ctrTitle")
                      and p.get("geometry")), None) if role != "full-bleed" else None
        if head is not None and title is not None:
            st = decls_of(head.get("style") or "")
            if "font-size" in st and st.get("width"):  # in the title placeholder, at the template's own size
                size, line, w = (float(re.sub(r"px$", "", st[k])) for k in ("font-size", "line-height", "width"))
                ratio = line / size  # the template's own spacing; here every line must sit inside the box
                fit = size
                while fit > 28 and text_lines(s["headline"], fit, w) * whole_pt(fit * ratio) > title["geometry"]["h"] + 1:
                    fit -= 2
                if fit < size:
                    head.set("style", re.sub(r"font-size:[^;]*;line-height:[^;]*",
                                             f"font-size:{fit:g}px;line-height:{whole_pt(fit * ratio):g}px", head.get("style")))
                    fitted.append(f"{s['id']} {size:g} -> {fit:g} px")
            elif role == "title-only":
                in_title.append((s["headline"], title["geometry"]["h"]))
        for n in root.walk():
            if n.tag == "title":
                n.text(s["headline"])
        for k in dropped_slots(paths, s) if not quiet else []:  # a variant with no place for a slot drops it: say so
            print(f"note: {s['id']} ({pattern}{'/' + s['variant'] if s.get('variant') else ''}): {k} has no place on "
                  "this design and was left out; pick another variant, or add it by hand with its data-bind",
                  file=sys.stderr)
        f = out / f"{i:02d}-{s['id'].lower()}-{pattern}.html"
        page = drop_dead_css(root.html())
        f.write_text(page)
        (base / f.name).write_text(page)
        written.append(f)
    # The approved headlines fitted to the template's title area, on every slide that draws its own: one size for the
    # deck, so no wording changes and no slide looks smaller than the next (lint refused 5 Berlin and 6
    # Madison headlines, and the only way out was a per-slide override on each). A settled headline-size wins.
    size, width = token_px(tokens, "headline-size"), token_px(tokens, "title-width") or token_px(tokens, "content-width")
    if in_title and size and width and not (brand.get("scale") or {}).get("headline-size"):
        fit = fitted_size([h for h, _ in in_title], size, width, min(h for _, h in in_title))
        if fit < size:
            with open(out / "tokens.css", "a") as f:
                f.write(f"/* convey compose: the approved headlines fitted to the template's title area "
                        f"({size:g} -> {fit:g} px). `convey brand settle <brand> headline-size=N` sets it instead. */\n"
                        f":root {{ --brand-headline-size: {fit:g}px; --brand-headline-line: {whole_pt(fit * 1.15):g}px; }}\n")
            fitted.insert(0, f"deck headlines {size:g} -> {fit:g} px")
    if kept:
        from .restyle import merge
        for f in written:
            if f.name in kept:
                b, m = kept[f.name]
                t = Tree(f.read_text()).root
                n, left = merge(Tree(b).root, Tree(m).root, t, f.stem)
                if n:
                    f.write_text(t.html())
                if not quiet:
                    print(f"note: {f.name}: {n} edit(s) carried" + (f"; left for you to judge: {'; '.join(left)}"
                                                                    if left else ""), file=sys.stderr)
    if not pics and not quiet and powerpoint.APP.exists():
        # Without layout pictures the slides show none of the template's own art (a title rule, a logo, a footer),
        # and the export report then grades every slide red where PowerPoint draws it (10 of 12 on one deck).
        print(f"note: the brand has no layout pictures, so the slides don't show the template's own art and the "
              f"export report will grade it as a difference. PowerPoint is installed: `convey brand render "
              f"{brand_dir}`, then compose again", file=sys.stderr)
    if fitted and not quiet:
        print("note: headlines fitted to the template's title area, wording kept: " + "; ".join(fitted), file=sys.stderr)
    sb.setdefault("slides", [])
    for s in sb["slides"]:
        s["status"] = "composed"
    (d / "storyboard.json").write_text(json.dumps(sb, indent=1, ensure_ascii=False) + "\n")
    return written
