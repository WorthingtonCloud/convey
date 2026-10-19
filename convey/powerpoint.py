"""Ask the installed PowerPoint (Mac) to save a deck as PDF, so what it draws can be measured.

Works inside PowerPoint's own sandbox folder, so macOS never asks for file access. Optional:
everything that uses it says "not verified in PowerPoint" when PowerPoint isn't there.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

APP = Path("/Applications/Microsoft PowerPoint.app")
WORK = Path.home() / "Library/Containers/com.microsoft.Powerpoint/Data/convey-render"
SCRIPT = """on run argv
  set inPath to item 1 of argv
  set outPath to item 2 of argv
  tell application "Microsoft PowerPoint"
    open POSIX file inPath
    set pres to active presentation
    save pres in (POSIX file outPath) as save as PDF
    close pres saving no
  end tell
end run"""


PDF2PNG = """ObjC.import('Quartz'); ObjC.import('AppKit');
function run(argv) {
  const doc = $.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(argv[0]));
  const W = parseInt(argv[2]);
  for (let i = 0; i < doc.pageCount; i++) {
    const page = doc.pageAtIndex(i);
    const box = page.boundsForBox($.kPDFDisplayBoxMediaBox);
    const H = Math.round(box.size.height * W / box.size.width);
    const img = page.thumbnailOfSizeForBox($.NSMakeSize(W, H), $.kPDFDisplayBoxMediaBox);
    const rep = $.NSBitmapImageRep.imageRepWithData(img.TIFFRepresentation);
    rep.representationUsingTypeProperties($.NSBitmapImageFileTypePNG, $())
       .writeToFileAtomically(argv[1] + '/page-' + (i + 1) + '.png', true);
  }
  return doc.pageCount;
}"""


def available() -> bool:
    return sys.platform == "darwin" and APP.exists()


def render_pdf(pptx, pdf, timeout: int = 240) -> Path:
    """deck.pptx -> deck.pdf as PowerPoint draws it."""
    if not available():
        raise RuntimeError("PowerPoint for Mac is not installed")
    WORK.mkdir(parents=True, exist_ok=True)
    src, dst = WORK / Path(pptx).name, WORK / (Path(pptx).stem + ".pdf")
    shutil.copy(pptx, src)
    if dst.exists():
        dst.unlink()
    r = subprocess.run(["osascript", "-", str(src), str(dst)], input=SCRIPT, capture_output=True, text=True,
                       timeout=timeout)
    if r.returncode or not dst.exists():
        raise RuntimeError(f"PowerPoint could not render {Path(pptx).name}: {(r.stderr or r.stdout).strip()}\n"
                           "If PowerPoint shows a 'found a problem' sheet, press Cancel and try again.")
    shutil.copy(dst, pdf)
    return Path(pdf)


def pdf_to_png(pdf, folder, width: int = 2560) -> list[Path]:
    """Every page of a PDF as page-N.png, drawn by macOS's own PDF engine (no install)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["osascript", "-l", "JavaScript", "-", str(Path(pdf).resolve()), str(folder.resolve()), str(width)],
                       input=PDF2PNG, capture_output=True, text=True, timeout=120)
    if r.returncode:
        raise RuntimeError(f"could not draw {Path(pdf).name} as pictures: {r.stderr.strip()}")
    n = int(r.stdout.strip() or 0)
    return [folder / f"page-{i}.png" for i in range(1, n + 1)]


def version() -> str:
    """The installed PowerPoint's version, from its bundle (does not start it)."""
    import plistlib
    try:
        return plistlib.loads((APP / "Contents/Info.plist").read_bytes()).get("CFBundleShortVersionString", "")
    except OSError:
        return ""
