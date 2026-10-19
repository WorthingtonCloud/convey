"""The asset set stays inside the rulebook: every icon file uses only allowed shapes and colors, the
catalog matches the files, and every icon and diagram part passes lint on a slide.

Run: python3 skill/tests/test_assets.py   (needs Chrome or Edge installed, nothing else)
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from convey import assets  # noqa: E402
from convey.skald.measure import measure  # noqa: E402

NS = "{http://www.w3.org/2000/svg}"
SHAPES = {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon"}
PAINT = {"none", "currentColor"}


def check_files() -> list[str]:
    bad = []
    cat = assets.catalog()
    files = {p.stem for p in (assets.HERE / "icons").glob("*.svg")}
    ids = [i["id"] for i in cat["icons"]]
    if len(ids) != len(set(ids)):
        bad.append("catalog: duplicate ids")
    if files != set(ids):
        bad.append(f"catalog vs files: {sorted(files ^ set(ids))}")
    for i in cat["icons"]:
        if len(i["concepts"]) < 4:
            bad.append(f"{i['id']}: fewer than 4 concepts")
        root = ET.parse(assets.HERE / i["file"]).getroot()
        if root.get("viewBox") != "0 0 48 48":
            bad.append(f"{i['id']}: viewBox is not the 48-unit grid")
        for el in root.iter():
            tag = el.tag.replace(NS, "")
            if el is not root and tag not in SHAPES:
                bad.append(f"{i['id']}: <{tag}> is not an allowed shape")
            for a in ("fill", "stroke"):
                if el.get(a) and el.get(a) not in PAINT and not el.get(a).startswith("var(--brand-"):
                    bad.append(f"{i['id']}: {a}={el.get(a)} (only none, currentColor or var(--brand-*))")
            if el.get("style") or el.get("transform") or el.get("class"):
                bad.append(f"{i['id']}: style/transform/class attributes are not used in icon files")
        text = (assets.HERE / i["file"]).read_text()
        if re.search(r"#[0-9a-fA-F]{3,6}\b|rgb\(|gradient|<text|filter", text):
            bad.append(f"{i['id']}: a literal color, gradient, text or filter")
    return bad


def check_lint() -> list[str]:
    A = assets
    body = [A.svg(i["id"], 32, cls="abs", style=f"left:{20 + (n % 30) * 40}px;top:{20 + (n // 30) * 40}px")
            for n, i in enumerate(A.catalog()["icons"])]
    body += [A.arrow(40, 200, 300, 200), A.elbow([340, 180, 420, 180, 420, 240, 500, 240]),
             A.curve(540, 240, 700, 180), A.brace(740, 160, 100), A.bracket(800, 160, 100, "right"),
             A.brace(860, 160, 200, "top", data_id="brace-top"), A.step(1, 40, 300), A.step(2, 110, 300, filled=False),
             A.callout("A note.", 200, 300, 220, 64), A.chevrons("One|Two|Three", 40, 420, 900, 64)]
    head = """<!doctype html><html><head><meta charset="utf-8"><style>
:root { --brand-ground: #ffffff; --brand-raised: #eeeeee; --brand-ink: #222222; --brand-muted: #666666;
  --brand-font-heading: Helvetica; --brand-weight-heading: 700; --brand-text-size: 18px; --brand-text-line: 26px; }
* { box-sizing: border-box; margin: 0; padding: 0; }
.slide { position: relative; width: 1280px; height: 720px; overflow: hidden; background: #ffffff; color: #222222;
  font-family: Helvetica; font-size: 18px; line-height: 26px; font-kerning: none; }
.abs { position: absolute; }</style></head><body><section class="slide">"""
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "assets.html"
        f.write_text(head + "\n".join(body) + "</section></body></html>")
        return measure([f])[0].get("errors", [])


if __name__ == "__main__":
    bad = check_files() + check_lint()
    for b in bad:
        print("FAIL", b)
    n = len(assets.catalog()["icons"])
    print(f"assets test: {n} icons, {len(assets.PARTS)} parts, {len(bad)} failures")
    sys.exit(1 if bad else 0)
