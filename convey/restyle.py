"""convey restyle: the same approved deck on another template, keeping the design work done on its slides.

    convey restyle DIR --brand N -o DIR2 [--overwrite]

DIR2 shares DIR's plan: evidence.json, storyboard.json, sources/ and every other project file are links back to
DIR's (so the story can't drift between copies), and brief.json is a copy that names the new brand. Compose then
draws every slide on the new brand, and the slide-level design edits made in DIR are carried onto it:

  base    what compose wrote for DIR (slides/.composed/, saved by every compose; rebuilt when missing)
  mine    DIR's slides as they are now, after the agent's design work
  theirs  what compose just wrote for DIR2

Every difference between base and mine is one edit: a style property (in a <style> rule or an element's style), an
attribute (a chart's look keys, a class), an element's text where no data-bind fills it, an element added or one
removed. An edit is carried when the new template's slide still has the value the edit changed (the skeleton's own
CSS, which every brand shares); where compose drew something else for the new template (a placeholder's position,
a layout's own type), the new template's value stays and the edit is listed for the agent to judge by eye.
Typed text lives in the storyboard, which both decks share, so it needs no carrying.
"""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from .compose import Node, Tree, compose

KEEP_OWN = {"brief.json", "slides", "build", "review", "versions", ".DS_Store"}  # each deck's own


# ---------- CSS as data ----------

def _split(text: str, sep: str) -> list[str]:
    """Split at sep outside brackets and quotes (a url(data:...;base64,...) keeps its semicolons)."""
    out, depth, q, cur = [], 0, None, []
    for ch in text:
        if q:
            q = None if ch == q else q
        elif ch in "\"'":
            q = ch
        elif ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif ch == sep and depth == 0:
            out.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    out.append("".join(cur))
    return out


def decls(text: str) -> dict:
    """'a: 1; b: 2' -> {'a': '1', 'b': '2'} (later wins, as in CSS)."""
    out = {}
    for part in _split(text or "", ";"):
        k, sep, v = part.partition(":")
        if sep and k.strip():
            out[k.strip().lower()] = " ".join(v.split())
    return out


def unparse(d: dict) -> str:
    return ";".join(f"{k}:{v}" for k, v in d.items())


def rules(css: str) -> list[tuple[str, str]]:
    """Top-level rules as (selector, body); an at-rule's body is kept whole, as text."""
    out, i, n = [], 0, len(css)
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    n = len(css)
    while i < n:
        j = css.find("{", i)
        if j < 0:
            break
        depth, k = 1, j + 1
        while k < n and depth:
            depth += {"{": 1, "}": -1}.get(css[k], 0)
            k += 1
        out.append((" ".join(css[i:j].split()), css[j + 1:k - 1]))
        i = k
    return out


def sheet(root: Node) -> dict:
    """Every rule of every <style> on the page, keyed by selector (a repeated selector gets #2, #3)."""
    out, seen = {}, {}
    for n in root.walk():
        if n.tag != "style":
            continue
        for sel, body in rules("".join(c for c in n.children if isinstance(c, str))):
            seen[sel] = seen.get(sel, 0) + 1
            key = sel if seen[sel] == 1 else f"{sel}#{seen[sel]}"
            out[key] = body.strip() if sel.startswith("@") else decls(body)
    return out


# ---------- the three-way merge ----------

def ids(root: Node) -> dict:
    out = {}
    for n in root.walk():
        k = "#section" if n.tag == "section" else n.get("data-id")
        if k and k not in out:
            out[k] = n
    return out


def _inner(n: Node) -> str:
    return "".join(c if isinstance(c, str) else c.html() for c in n.children)


def _three(base, mine, theirs):
    """(carry?, conflict?) for one value."""
    if mine == base or theirs == mine:
        return False, False
    return (True, False) if theirs == base else (False, True)


SKIP_ATTRS = {"data-claims", "src", "data-layout"}  # the story's and compose's own: the storyboard and the new brand set them


def merge(base: Node, mine: Node, theirs: Node, slide: str) -> tuple[int, list[str]]:
    """Carry mine's edits over base onto theirs, in place. Returns (edits carried, edits left for the agent)."""
    carried, left = 0, []
    # 1. style rules
    sb, sm, st = sheet(base), sheet(mine), sheet(theirs)
    changed = {}
    for sel in dict.fromkeys([*sb, *sm]):
        b, m = sb.get(sel), sm.get(sel)
        if b == m:
            continue
        t = st.get(sel)
        if isinstance(m, str) or isinstance(b, str):  # an at-rule: whole
            c, x = _three(b, m, t)
            if c:
                changed[sel] = m
                carried += 1
            elif x:
                left.append(f"{slide}: CSS {sel}: kept the new template's version")
            continue
        b, m, t = b or {}, m or {}, dict(t or {})
        for p in dict.fromkeys([*b, *m]):
            c, x = _three(b.get(p), m.get(p), t.get(p))
            if c:
                if m.get(p) is None:
                    t.pop(p, None)
                else:
                    t[p] = m[p]
                carried += 1
            elif x:
                left.append(f"{slide}: CSS {sel} {p}: the source deck has {m.get(p)!r} (composed as {b.get(p)!r}); "
                            f"the new template's {t.get(p)!r} kept")
        if sel not in sm:
            changed[sel] = None
        else:
            changed[sel] = t
    if changed:
        _write_sheet(theirs, changed)
    # 2. elements
    B, M, T = ids(base), ids(mine), ids(theirs)
    for k, m in M.items():
        if k in B:
            continue
        if k in T:  # compose now draws it for the new template itself
            left.append(f"{slide}: {k} was added by hand, and compose now draws one: the new template's kept")
            continue
        _insert(m, mine, theirs, T)
        T = ids(theirs)
        carried += 1
    for k, b in B.items():
        if k not in M and k in T and T[k].parent is not None:
            T[k].remove()
            carried += 1
    for k, m in M.items():
        b, t = B.get(k), T.get(k)
        if b is None or t is None:
            continue
        for a in dict.fromkeys([a for a, _ in b.attrs] + [a for a, _ in m.attrs]):
            if a in SKIP_ATTRS:
                continue
            bv, mv, tv = b.get(a), m.get(a), t.get(a)
            if bv == mv:
                continue
            if a == "style":
                bd, md, td = decls(bv), decls(mv), decls(tv)
                for p in dict.fromkeys([*bd, *md]):
                    c, x = _three(bd.get(p), md.get(p), td.get(p))
                    if c:
                        if md.get(p) is None:
                            td.pop(p, None)
                        else:
                            td[p] = md[p]
                        carried += 1
                    elif x:
                        left.append(f"{slide}: {k} {p}: the source deck has {md.get(p)!r}; the new template's "
                                    f"{td.get(p)!r} kept")
                t.set("style", unparse(td))
            elif a == "class":
                bs, ms, ts = set((bv or "").split()), set((mv or "").split()), (tv or "").split()
                ts = [c for c in ts if c not in bs - ms] + sorted(ms - bs - set(ts))
                t.set("class", " ".join(ts))
                carried += 1
            elif a == "data-chart":
                try:
                    bj, mj, tj = (json.loads(v or "{}") for v in (bv, mv, tv))
                except ValueError:
                    left.append(f"{slide}: {k} data-chart: not JSON, left as composed")
                    continue
                for key in dict.fromkeys([*bj, *mj]):
                    c, x = _three(bj.get(key), mj.get(key), tj.get(key))
                    if c:
                        if key in mj:
                            tj[key] = mj[key]
                        else:
                            tj.pop(key, None)
                        carried += 1
                    elif x:
                        left.append(f"{slide}: {k} chart {key}: the new template's kept")
                t.set("data-chart", json.dumps(tj, ensure_ascii=False))
            else:
                c, x = _three(bv, mv, tv)
                if c:
                    if mv is None:
                        t.attrs = [(x_, v) for x_, v in t.attrs if x_ != a]
                    else:
                        t.set(a, mv)
                    carried += 1
                elif x:
                    left.append(f"{slide}: {k} {a}: the new template's kept")
        # text no data-bind fills (a callout's words); bound text comes from the shared storyboard
        if m.get("data-bind") is None and not any(isinstance(c, Node) and c.get("data-id") for c in m.children):
            bi, mi, ti = _inner(b), _inner(m), _inner(t)
            c, x = _three(bi, mi, ti)
            if c:
                t.children = copy.deepcopy(m.children)
                for c_ in t.children:
                    if isinstance(c_, Node):
                        c_.parent = t
                carried += 1
            elif x:
                left.append(f"{slide}: {k} text: the new template's kept")
    return carried, left


def _write_sheet(theirs: Node, changed: dict):
    """Write the merged rules back: a changed rule's body in place, a removed rule out, a new rule at the end of the
    page's first <style>."""
    styles = [n for n in theirs.walk() if n.tag == "style"]
    done = set()
    for n in styles:
        text = "".join(c for c in n.children if isinstance(c, str))
        seen, pos, res = {}, 0, []
        while True:
            j = text.find("{", pos)
            if j < 0:
                res.append(text[pos:])
                break
            depth, k = 1, j + 1
            while k < len(text) and depth:
                depth += {"{": 1, "}": -1}.get(text[k], 0)
                k += 1
            head = text[pos:j]
            sel = " ".join(re.sub(r"/\*.*?\*/", "", head, flags=re.S).split())
            seen[sel] = seen.get(sel, 0) + 1
            key = sel if seen[sel] == 1 else f"{sel}#{seen[sel]}"
            if key in changed and key not in done:
                done.add(key)
                v = changed[key]
                if v is None:
                    res.append(head[:len(head) - len(head.lstrip())] if head.strip() else "")
                elif isinstance(v, str):
                    res.append(f"{head}{{{v}}}")
                else:
                    res.append(f"{head}{{ {'; '.join(f'{p}: {x}' for p, x in v.items())}; }}")
            else:
                res.append(text[pos:k])
            pos = k
        n.children = ["".join(res)]
    new = [(k, v) for k, v in changed.items() if k not in done and v is not None]
    if new and styles:
        add = "".join(f"\n{k.split('#')[0]} {{{v}}}" if isinstance(v, str) else
                      f"\n{k.split('#')[0]} {{ {'; '.join(f'{p}: {x}' for p, x in v.items())}; }}" for k, v in new)
        styles[0].children = ["".join(c for c in styles[0].children if isinstance(c, str)).rstrip("\n") + add + "\n"]


def _insert(m: Node, mine: Node, theirs: Node, T: dict):
    """Put a hand-added element (and all inside it) on the new slide: under the same parent, after the same
    sibling, by data-id; the slide itself when the parent isn't there."""
    par = m.parent
    while par is not None and par.tag != "section" and not (par.get("data-id") and par.get("data-id") in T):
        par = par.parent
    target = T.get("#section") if par is None or par.tag == "section" else T[par.get("data-id")]
    if target is None:
        target = next(n for n in theirs.walk() if n.tag == "body")
    twin = copy.deepcopy(m)
    twin.parent = target
    at = len(target.children)
    if m.parent is par:
        sibs = [c for c in m.parent.children if isinstance(c, Node)]
        for prev in reversed(sibs[:sibs.index(m)]):
            hit = T.get(prev.get("data-id"))
            if hit is not None and hit.parent is target:
                at = target.children.index(hit) + 1
                break
    target.children.insert(at, twin)


# ---------- the command ----------

def _link(src: Path, dst: Path):
    rel = os.path.relpath(src.resolve(), dst.parent.resolve())
    try:
        os.symlink(rel, dst)
    except OSError:  # a system that won't make links: a copy (the story can then drift; restyle says so)
        (shutil.copytree if src.is_dir() else shutil.copy2)(src, dst)
        return False
    return True


def _base(d: Path, brand_dir: Path) -> tuple[dict, bool]:
    """What compose wrote for DIR: its saved copies, else a fresh compose of DIR's story on DIR's brand."""
    saved = d / "slides" / ".composed"
    if saved.is_dir() and any(saved.glob("*.html")):
        return {f.name: f.read_text() for f in saved.glob("*.html")}, True
    work = Path(tempfile.mkdtemp(prefix="convey-base-"))
    for f in d.iterdir():
        if f.name in KEEP_OWN and f.name != "brief.json":
            continue
        (shutil.copytree if f.is_dir() else shutil.copy2)(f, work / f.name)
    files = compose(work, brand_dir, force=True, overwrite=True, quiet=True)
    out = {f.name: f.read_text() for f in files}
    shutil.rmtree(work, ignore_errors=True)
    return out, False


def restyle(d: Path, brand_arg: str, out: Path, src_brand: Path, new_brand: Path, overwrite: bool = False) -> dict:
    d, out = Path(d), Path(out)
    if (out / "slides").exists() and not overwrite:
        raise SystemExit(f"restyle refused: {out}/slides exists (a restyle made earlier?). --overwrite recomposes it "
                         "from the source deck, which drops any design work done in it since")
    if not (d / "slides").is_dir():
        raise SystemExit(f"restyle refused: {d} has no slides/ yet: compose it first")
    out.mkdir(parents=True, exist_ok=True)
    linked = True
    for f in d.iterdir():
        if f.name in KEEP_OWN or f.name.startswith(("slides", "build")) or (out / f.name).exists() or (out / f.name).is_symlink():
            continue
        linked &= _link(f, out / f.name)
    brief = json.loads((d / "brief.json").read_text())
    brief["brand"] = os.path.relpath(Path(new_brand).resolve(), out.resolve()) if Path(brand_arg).exists() else brand_arg
    brief["restyled_from"] = os.path.relpath(d.resolve(), out.resolve())
    (out / "brief.json").write_text(json.dumps(brief, indent=1, ensure_ascii=False) + "\n")
    base, saved = _base(d, src_brand)
    if (out / "slides").exists():
        for f in (out / "slides").glob("*.html"):
            f.unlink()
    files = compose(out, new_brand, force=False, overwrite=True)
    report = {"slides": len(files), "carried": 0, "left": [], "saved_base": saved, "linked": linked}
    for f in files:
        mine_f = d / "slides" / f.name
        if not mine_f.exists() or f.name not in base:
            continue
        b, m, t = Tree(base[f.name]).root, Tree(mine_f.read_text()).root, Tree(f.read_text()).root
        sid = next((n.get("data-slide") for n in t.walk() if n.tag == "section"), f.stem)
        n, left = merge(b, m, t, sid)
        if n:
            f.write_text(t.html())
        report["carried"] += n
        report["left"] += left
    for f in (d / "slides").iterdir():  # the slides' own files added by hand (a picture, a script)
        if f.is_file() and not f.name.endswith(".html") and not (out / "slides" / f.name).exists():
            shutil.copy2(f, out / "slides" / f.name)
    return report
