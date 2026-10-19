"""convey deliver: put the approved deck where the person will find it.

    convey deliver DIR [--deck build/deck.pptx] [--to FOLDER] [--force]

Copies the exported deck, PowerPoint's own PDF of it (when `convey export --pdf` made one) and the export report
with its pictures into one folder named after the deck: ~/Downloads/<title>/ unless --to says otherwise. The files
take the deck's title as their name, so they read well in a mail or a shared drive. A second deliver replaces them.

It refuses a deck the person hasn't approved in the studio (--force to deliver a draft anyway, and say so).
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path


def _title(d: Path) -> str:
    try:
        t = json.loads((d / "brief.json").read_text()).get("title") or d.name
    except (OSError, ValueError):
        t = d.name
    t = re.sub(r'[\\/:*?"<>|\n\r\t]+', " - ", t).strip(" .-")  # names every system accepts
    t = re.sub(r"\s+", " ", t)
    return (t[:80].rstrip(" .-") or "deck")


def approved(d: Path) -> bool:
    if not (d / "review" / "log.jsonl").exists():
        return False
    from .studio import log as L
    return L.state(d, "agent")["turn"] == "done"


def deliver(d: Path, deck: Path | None = None, to: Path | None = None, force: bool = False) -> dict:
    d = Path(d)
    if not force and not approved(d):
        raise SystemExit("deliver refused: the person hasn't approved this deck in the studio (convey review status "
                         f"{d} --ready). --force delivers it as a draft; tell them it is one")
    if deck is None:
        found = sorted((d / "build").glob("*.pptx"), key=lambda p: p.stat().st_mtime) if (d / "build").is_dir() else []
        if not found:
            raise SystemExit(f"deliver refused: no .pptx in {d / 'build'}: run convey export first (--deck names another)")
        deck = found[-1]
    deck = Path(deck)
    if not deck.exists():
        raise SystemExit(f"deliver refused: {deck} doesn't exist")
    title = _title(d)
    if to is None:
        home = Path.home() / "Downloads"
        to = (home if home.is_dir() else Path.home()) / title
    to = Path(to).expanduser()
    to.mkdir(parents=True, exist_ok=True)
    got = {"folder": str(to), "files": []}

    def put(src: Path, name: str):
        shutil.copy2(src, to / name)
        got["files"].append(name)

    put(deck, f"{title}.pptx")
    pdf = deck.with_suffix(".pdf")
    if pdf.exists():
        put(pdf, f"{title}.pdf")
    report = deck.parent / "report.html"
    if report.exists():
        pics = deck.parent / "report"
        if (to / "report").is_dir():
            shutil.rmtree(to / "report")
        if pics.is_dir():
            shutil.copytree(pics, to / "report")
        put(report, "Export report.html")
    return got
