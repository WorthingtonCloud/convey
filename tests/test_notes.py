"""Speaker notes: a slide's storyboard `notes` become its notes page in the exported deck. Standard library only.

A two-slide project (one slide with notes, one without) is exported with --no-report; the .pptx must hold one
notes page, linked to its slide and to a notes master that presentation.xml lists, with the notes as paragraphs.
(PowerPoint itself reading them back was checked by hand on Oct 18, 2026, on a company template's deck too.)

Run: python3 skill/tests/test_notes.py   (needs Chrome or Edge)
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent

SLIDE = """<!doctype html><html><head><meta charset="utf-8"><style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
.slide {{ position: relative; width: 1280px; height: 720px; background: #ffffff; color: #222222;
  font-family: Helvetica; font-size: 24px; line-height: 32px; font-kerning: none; }}
</style></head><body><section class="slide" data-slide="{sid}">
<h1 data-id="headline" style="position:absolute;left:64px;top:64px;font-size:40px;line-height:48px">{title}</h1>
</section></body></html>"""


def main() -> int:
    fails = []
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        (d / "slides").mkdir()
        (d / "slides" / "01-a.html").write_text(SLIDE.format(sid="S-1", title="With notes"))
        (d / "slides" / "02-b.html").write_text(SLIDE.format(sid="S-2", title="Without notes"))
        (d / "storyboard.json").write_text(json.dumps({"slides": [
            {"id": "S-1", "notes": "Open on the claim.\n\nThen the evidence & its source <in brackets>."},
            {"id": "S-2"}]}))
        out = d / "build" / "deck.pptx"
        r = subprocess.run([sys.executable, str(SKILL / "bin" / "convey"), "export", str(d / "slides"), "-o", str(out),
                            "--no-report"], capture_output=True, text=True)
        if r.returncode:
            print(r.stdout, r.stderr)
            return 1
        z = zipfile.ZipFile(out)
        names = set(z.namelist())
        notes = sorted(n for n in names if n.startswith("ppt/notesSlides/") and n.endswith(".xml"))
        if len(notes) != 1:
            fails.append(f"expected one notes page, got {notes}")
        else:
            xml = z.read(notes[0]).decode()
            for want in ("Open on the claim.", "Then the evidence &amp; its source &lt;in brackets&gt;."):
                if want not in xml:
                    fails.append(f"notes page lacks {want!r}")
            rels = z.read(notes[0].replace("notesSlides/", "notesSlides/_rels/") + ".rels").decode()
            if "notesMaster" not in rels or "slides/slide1.xml" not in rels:
                fails.append(f"notes page not linked to its master and slide 1: {rels}")
        if "ppt/notesMasters/notesMaster1.xml" not in names:
            fails.append("no notes master")
        pres = z.read("ppt/presentation.xml").decode()
        if "notesMasterIdLst" not in pres:
            fails.append("presentation.xml doesn't list the notes master")
        if "notesSlide" not in z.read("ppt/slides/_rels/slide1.xml.rels").decode():
            fails.append("slide 1 doesn't link its notes page")
        if "notesSlide" in z.read("ppt/slides/_rels/slide2.xml.rels").decode():
            fails.append("slide 2 has a notes page it shouldn't")
        ct = z.read("[Content_Types].xml").decode()
        for typ in ("notesSlide+xml", "notesMaster+xml"):
            if typ not in ct:
                fails.append(f"[Content_Types].xml lacks {typ}")
    for f in fails:
        print("FAIL", f)
    print(f"notes test: {len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
