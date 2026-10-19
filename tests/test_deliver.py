"""convey deliver puts the approved deck, its PDF and its report in one folder named after the deck, and refuses a
deck nobody approved. Standard library only, no browser.

Run: python3 skill/tests/test_deliver.py
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from convey import deliver as D  # noqa: E402

fails = 0


def ok(cond: bool, what: str):
    global fails
    print(("ok    " if cond else "FAIL  ") + what)
    fails += 0 if cond else 1


def main() -> int:
    d = Path(tempfile.mkdtemp())
    deck = d / "deck"
    (deck / "build" / "report").mkdir(parents=True)
    (deck / "brief.json").write_text(json.dumps({"title": "Q3 review: what changed / why"}))
    (deck / "build" / "deck.pptx").write_bytes(b"pptx")
    (deck / "build" / "deck.pdf").write_bytes(b"pdf")
    (deck / "build" / "report.html").write_text('<img src="report/01-diff.png">')
    (deck / "build" / "report" / "01-diff.png").write_bytes(b"png")
    try:
        D.deliver(deck, to=d / "out")
        ok(False, "a deck nobody approved is refused")
    except SystemExit as e:
        ok("--force" in str(e), "a deck nobody approved is refused (--force delivers a draft)")
    real = D.approved
    D.approved = lambda _d: True
    try:
        r = D.deliver(deck, to=d / "out")
    finally:
        D.approved = real
    out = d / "out"
    name = "Q3 review - what changed - why"
    ok(sorted(r["files"]) == sorted([f"{name}.pptx", f"{name}.pdf", "Export report.html"]),
       f"the deck and its PDF take the title as their name, safe for any system ({r['files']})")
    ok((out / "report" / "01-diff.png").exists(), "the report's pictures go beside it, so the report still shows them")
    ok(D._title(d / "nowhere") == "nowhere", "with no brief, the folder's name stands in for the title")
    shutil.rmtree(d)
    print(f"deliver test: {fails} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
