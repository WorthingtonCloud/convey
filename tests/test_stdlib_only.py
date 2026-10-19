"""The skill imports nothing outside Python's standard library, so it runs on a stock
Python 3.9+ with nothing to install. Any other import fails this test by file and line.

Run: python3 skill/tests/test_stdlib_only.py
"""
from __future__ import annotations

import ast
import importlib.util
import sys
import sysconfig
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
OWN = {"convey"} | {f.stem for f in (SKILL / "tests").glob("*.py")}  # the skill's own package and test helpers


def is_std(name: str) -> bool:
    if hasattr(sys, "stdlib_module_names"):  # Python 3.10+
        return name in sys.stdlib_module_names or name == "__future__"
    spec = importlib.util.find_spec(name)
    if spec is None:
        return False
    if spec.origin in ("built-in", "frozen"):
        return True
    roots = {sysconfig.get_paths()[k] for k in ("stdlib", "platstdlib")}
    origin = spec.origin or ""
    return "site-packages" not in origin and any(origin.startswith(r) for r in roots)


def outside_imports() -> list[str]:
    hits = []
    for f in sorted(SKILL.rglob("*.py")):
        tree = ast.parse(f.read_text(), str(f))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and not node.level:
                names = [node.module or ""]
            else:
                continue
            for n in names:
                top = n.split(".")[0]
                if top not in OWN and not is_std(top):
                    hits.append(f"{f.relative_to(SKILL)}:{node.lineno}: imports {n}")
    return hits


def test_stdlib_only():
    hits = outside_imports()
    assert not hits, "\n".join(hits)


if __name__ == "__main__":
    hits = outside_imports()
    for h in hits:
        print(h)
    print(f"stdlib-only: {len(hits)} outside imports")
    sys.exit(1 if hits else 0)
