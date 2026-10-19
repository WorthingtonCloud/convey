"""Source intake: copy the person's files into the deck project and pull out their text with locators.

    convey intake FILE... --project DIR

Each file is copied into DIR/sources/ (untouched) and fingerprinted (sha256). Its text goes to
DIR/sources/text/<file>.json as chunks, each with a locator a claim can cite:

    .txt .md .html .json   "line N"
    .csv                   "row N" (cells read "B4: value"; a claim may cite "B4")
    .xlsx                  "<sheet> row N" (cells as above; cite "<sheet>!B4")
    .docx                  "para N" (tables included, one paragraph per cell)
    .pptx                  "slide N"
    .pdf                   "page N" (macOS PDFKit; elsewhere, simple PDFs only, otherwise flagged)

DIR/sources/manifest.json lists every file, its hash and what was read. A file whose text can't
be read is listed with a flag, never silently skipped. Standard library only.
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PR = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _col(n: int) -> str:
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _lines(text: str) -> list[dict]:
    return [{"loc": f"line {i}", "text": t} for i, t in enumerate(text.splitlines(), 1) if t.strip()]


def read_text(p: Path) -> list[dict]:
    return _lines(p.read_text(errors="replace"))


def read_html(p: Path) -> list[dict]:
    t = re.sub(r"(?is)<(script|style).*?</\1>", "", p.read_text(errors="replace"))
    t = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h[1-6]|tr)>", "\n", t)
    return _lines(html.unescape(re.sub(r"<[^>]+>", "", t)))


def read_json(p: Path) -> list[dict]:
    return _lines(json.dumps(json.loads(p.read_text()), indent=1, ensure_ascii=False))


def read_csv(p: Path) -> list[dict]:
    out = []
    with p.open(newline="", errors="replace") as f:
        for i, row in enumerate(csv.reader(f), 1):
            cells = [f"{_col(j)}{i}: {v}" for j, v in enumerate(row) if v.strip()]
            if cells:
                out.append({"loc": f"row {i}", "text": " | ".join(cells)})
    return out


def read_xlsx(p: Path) -> list[dict]:
    out = []
    with zipfile.ZipFile(p) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(S + "si"):
                shared.append("".join(t.text or "" for t in si.iter(S + "t")))
        rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")).iter(PR + "Relationship")}
        for sh in ET.fromstring(z.read("xl/workbook.xml")).iter(S + "sheet"):
            target = rels[sh.get(R + "id")].lstrip("/")
            target = target if target.startswith("xl/") else "xl/" + target
            for row in ET.fromstring(z.read(target)).iter(S + "row"):
                cells = []
                for c in row.iter(S + "c"):
                    v = c.find(S + "v")
                    if c.get("t") == "s" and v is not None:
                        val = shared[int(v.text)]
                    elif c.get("t") == "inlineStr":
                        val = "".join(t.text or "" for t in c.iter(S + "t"))
                    else:
                        val = v.text if v is not None else ""
                    if val:
                        cells.append(f"{c.get('r')}: {val}")
                if cells:
                    out.append({"loc": f"{sh.get('name')} row {row.get('r')}", "text": " | ".join(cells)})
    return out


def read_docx(p: Path) -> list[dict]:
    with zipfile.ZipFile(p) as z:
        body = ET.fromstring(z.read("word/document.xml"))
    paras = ["".join(t.text or "" for t in para.iter(W + "t")) for para in body.iter(W + "p")]
    return [{"loc": f"para {i}", "text": t} for i, t in enumerate((t for t in paras if t.strip()), 1)]


def read_pptx(p: Path) -> list[dict]:
    out = []
    with zipfile.ZipFile(p) as z:
        names = sorted((n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                       key=lambda n: int(re.search(r"(\d+)\.xml", n).group(1)))
        for i, n in enumerate(names, 1):
            root = ET.fromstring(z.read(n))
            paras = ["".join(t.text or "" for t in para.iter(A + "t")) for para in root.iter(A + "p")]
            text = "\n".join(t for t in paras if t.strip())
            if text:
                out.append({"loc": f"slide {i}", "text": text})
    return out


JXA_PDF = """ObjC.import('PDFKit');
function run(argv) {
  const doc = $.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(argv[0]));
  if (!doc || doc.isNil()) return '[]';
  const out = [];
  for (let i = 0; i < doc.pageCount; i++) out.push(ObjC.unwrap(doc.pageAtIndex(i).string) || '');
  return JSON.stringify(out);
}"""


def read_pdf(p: Path) -> list[dict]:
    pages = None
    if sys.platform == "darwin":
        r = subprocess.run(["osascript", "-l", "JavaScript", "-e", JXA_PDF, str(p.resolve())],
                           capture_output=True, text=True, timeout=120)
        if r.returncode == 0 and r.stdout.strip():
            pages = json.loads(r.stdout)
    if pages is None:  # simple PDFs only: literal strings in uncompressed or Flate content streams
        import zlib
        data = p.read_bytes()
        pages = []
        for m in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
            raw = m.group(1)
            try:
                raw = zlib.decompress(raw)
            except zlib.error:
                pass
            words = re.findall(rb"\(((?:\\.|[^\\)])*)\)\s*Tj|\[(.*?)\]\s*TJ", raw, re.S)
            text = " ".join((a or b"".join(re.findall(rb"\(((?:\\.|[^\\)])*)\)", b))).decode("latin-1")
                            for a, b in words)
            if text.strip():
                pages.append(text)
    return [{"loc": f"page {i}", "text": t} for i, t in enumerate(pages, 1) if t.strip()]


READERS = {".txt": read_text, ".md": read_text, ".mdx": read_text, ".markdown": read_text, ".rst": read_text, ".log": read_text,
           ".yaml": read_text, ".yml": read_text, ".toml": read_text, ".sql": read_text, ".py": read_text,
           ".js": read_text, ".ts": read_text, ".tsx": read_text, ".jsx": read_text, ".html": read_html, ".htm": read_html,
           ".json": read_json, ".csv": read_csv, ".xlsx": read_xlsx, ".docx": read_docx, ".pptx": read_pptx,
           ".pdf": read_pdf}


PICTURES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}


def intake(files: list[str], project: Path) -> dict:
    src = project / "sources"
    (src / "text").mkdir(parents=True, exist_ok=True)
    mpath = src / "manifest.json"
    manifest = json.loads(mpath.read_text()) if mpath.exists() else {"files": []}
    known = {f["file"]: f for f in manifest["files"]}
    for f in map(Path, files):
        dest = src / f.name
        if f.resolve() != dest.resolve():
            shutil.copy2(f, dest)
        rel = f"sources/{f.name}"
        entry = {"file": rel, "sha256": hashlib.sha256(dest.read_bytes()).hexdigest(), "bytes": dest.stat().st_size}
        reader = READERS.get(f.suffix.lower())
        chunks, flag = [], None
        if f.suffix.lower() in PICTURES:  # a photo or drawing for a slide, not evidence: copied, no text, no flag
            entry["picture"] = True
        elif not reader:
            flag = f"no text reader for {f.suffix or 'this file'}: ask the person for a text, CSV or PDF version"
        else:
            try:
                chunks = reader(dest)
            except Exception as e:  # noqa: BLE001 - any unreadable file becomes a flag, never a crash
                flag = f"could not read: {type(e).__name__}: {e}"
            if reader and not chunks and not flag:
                flag = "no text found (a scanned PDF or an image?): ask the person for the text"
        entry["chunks"] = len(chunks)
        if flag:
            entry["flag"] = flag
        tfile = src / "text" / f"{f.name}.json"
        tfile.write_text(json.dumps({"file": rel, "sha256": entry["sha256"], "chunks": chunks}, indent=1, ensure_ascii=False))
        (src / "text" / f"{f.name}.txt").write_text("".join(f"[{c['loc']}] {c['text']}\n" for c in chunks))
        entry["text"] = f"sources/text/{f.name}.json"
        known[rel] = entry
    manifest["files"] = sorted(known.values(), key=lambda e: e["file"])
    mpath.write_text(json.dumps(manifest, indent=1))
    return manifest


# ---------- locators (used by `convey check`) ----------

CELL = re.compile(r"^(?:(?P<sheet>[^!]+)!)?(?P<col>[A-Z]{1,3})(?P<row>\d+)$")


def locate(project: Path, file: str, locator: str) -> str | None:
    """The text a claim's (file, locator) points at, or None if the locator matches nothing."""
    tfile = project / "sources" / "text" / f"{Path(file).name}.json"
    if not tfile.exists():
        return None
    chunks = json.loads(tfile.read_text())["chunks"]
    by = {c["loc"]: c["text"] for c in chunks}
    loc = locator.strip()
    if loc in by:
        return by[loc]
    m = re.fullmatch(r"(line|row|para|page|slide)s?\s+(\d+)\s*[-–]\s*(\d+)", loc)
    if m:
        parts = [by.get(f"{m.group(1)} {i}") for i in range(int(m.group(2)), int(m.group(3)) + 1)]
        return "\n".join(p for p in parts if p) or None
    m = CELL.match(loc)
    if m:
        row = f"{m.group('sheet')} row {m.group('row')}" if m.group("sheet") else f"row {m.group('row')}"
        text = by.get(row)
        if text:
            ref = f"{m.group('col')}{m.group('row')}"
            for cell in text.split(" | "):
                if cell.startswith(ref + ": "):
                    return cell[len(ref) + 2:]
    return None
