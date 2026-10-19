"""convey intake | check | compose | studio | review | restore | lint | export | deliver | brand | assets

  convey intake FILE... --project DIR    copy sources into DIR/sources/ and extract their text with locators
  convey check DIR                       every number traces to a claim; bindings, sources, derivations, headline chain
  convey compose DIR [--brand N]         first-draft slides from the approved storyboard, onto the brand's layouts
  convey restyle DIR --brand N -o DIR2   the same deck on another template: shared story, design edits carried
  convey studio DIR [--port 4560]        open the deck in the browser for review (thumbnails, typed fixes, notes, Send)
  convey review open|show|wait|status|ask|resolve DIR ...
                                         the agent's side of a review round (see studio/rounds.py)
  convey restore vN [DIR]                put a version's storyboard.json and slides/ back

  convey lint SLIDES...                  refuse anything that can't become a native PowerPoint object, and
                                         design problems: contrast, small type, crowding, color, rhythm
  convey look SLIDES... -o DIR           a full-size picture of every slide as the browser draws it, to look at;
                                         lists those changed since the last look, plus sheet.png (all, small)
  convey export SLIDES... -o deck.pptx   slides -> editable .pptx (refuses slides that fail lint), then
                                         report.html: each slide graded against PowerPoint's own drawing
  convey deliver DIR [--to FOLDER]       the approved deck, its PDF and report in one easy folder
                                         (~/Downloads/<title>/ by default)
  convey brand ingest TEMPLATE --name N  read a .potx/.pptx/.thmx into ~/.convey/brands/N/
  convey brand calibrate N               fit each brand font's line position (needs PowerPoint)
  convey brand render N                  picture every layout as PowerPoint draws it (needs PowerPoint)
  convey brand sheet N                   rebuild tokens.css, flags.md and brand-sheet.html from brand.json
  convey brand approve N --by NAME       record that the person approved the Brand Profile
  convey brand settle N ID[=VALUE] ...   record the person's call on a flag (raised=#383838,
                                         binding-key-finding="Title Only", pictures=none, signal)
  N is a brand's name (~/.convey/brands/N) or its folder; `ingest --out DIR` writes anywhere.
  convey assets find WORD                which icons stand for a word
  convey assets show ID [--size PX]      an icon as inline SVG, ready to paste into a slide
  convey assets part NAME key=value ...  a diagram part (arrow, elbow, curve, brace, bracket, step,
                                         callout, chevrons) as slide HTML
  convey assets gallery -o FILE          every icon and part on one page [--brand N for its colors]

SLIDES are .html files or folders of them; a folder's slides go in file-name order.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .skald.measure import measure, slide_files


def _report(scenes, files, verbose=False, quiet=False) -> int:
    """Print every refusal by element name. Returns the number of refused slides. Slides that pass print only with
    verbose (the token diet, Oct 18, 2026: an agent runs lint after every change); one folder's slides go by name."""
    refused = 0
    one = len({f.parent for f in files}) == 1
    advised = set()  # the advice after a problem's "; " prints once per run, not once per slide
    for sc, f in zip(scenes, files):
        errs = sc.get("errors", [])
        name = f.name if one else f
        if errs:
            refused += 1
            print(f"REFUSED  {name}")
            for e in errs:
                head, sep, advice = e.partition("; ")
                if sep and advice in advised and not verbose:
                    e = f"{head} (as above)"
                advised.add(advice)
                print(f"    {e}")
        elif verbose and not quiet:
            print(f"ok       {name}")
        if verbose:
            for w in sc.get("warnings", []) + sc.get("notes", []):
                print(f"    note: {w}")
    return refused


def _deck_brand(files, explicit=None):
    """The Brand Profile behind a deck's slides: --brand, else the brief's brand (a name, or a folder relative to
    the project that holds slides/). None when there is no brief or it names no profile."""
    if explicit:
        return _brand_dir(explicit)
    proj = files[0].resolve().parent.parent
    try:
        brand = json.loads((proj / "brief.json").read_text()).get("brand")
        return _brand_dir(proj / brand) if (proj / brand / "brand.json").exists() else _brand_dir(brand)
    except (OSError, ValueError, TypeError, SystemExit):
        return None


def _full_bleed(scene: dict) -> bool:
    """An opaque box over the whole slide: a full-bleed variant's own ground."""
    W, H = scene.get("width", 1280), scene.get("height", 720)
    return any(e.get("kind") == "box" and (e.get("fill") or {}).get("a", 0) >= 1 and e["x"] <= 0.5 and e["y"] <= 0.5
               and e["x"] + e["w"] >= W - 0.5 and e["y"] + e["h"] >= H - 0.5 for e in scene.get("elements", []))


def layout_clashes(scene: dict, brand: dict) -> list[str]:
    """Slide text laid on what the layout itself draws: its numbers, labels and rules. The layout's picture hides
    them from the slide's own checks, and PowerPoint draws them under the slide, so both show the collision (a
    6-item list over the layout's "01 02 03", Oct 18, 2026)."""
    layouts = {l["name"]: l for l in brand.get("layouts", [])}
    b = brand.get("bindings", {}).get(scene.get("pattern") or "")
    lay = layouts.get(scene.get("layout") or (b["layout"] if isinstance(b, dict) else b) or "")
    marks = [d for d in (lay or {}).get("drawn", []) if d.get("text") or min(d["geometry"]["w"], d["geometry"]["h"]) <= 3]
    if _full_bleed(scene):  # the slide paints its own ground over the whole layout, hiding the layout's marks
        return []
    out = []
    title = next((p for p in (lay or {}).get("placeholders", []) if p["type"] in ("title", "ctrTitle") and p.get("geometry")), None)
    head = next((e for e in scene.get("elements", []) if e.get("bind") == "headline"), None)
    hw = [w for p in (((head or {}).get("text") or {}).get("paras") or []) for w in (p.get("words") or [])]
    if title and hw:
        # The headline in the template's title area must end inside it: a third line ran out of Berlin's title band
        # and under the body (Oct 18, 2026). Only a slide that keeps its headline where the template puts it.
        g = title["geometry"]
        top, bottom = min(w["y"] for w in hw), max(w["y"] + w["h"] * 0.85 for w in hw)
        if g["y"] - 8 <= top < g["y"] + g["h"] / 2 and bottom > g["y"] + g["h"] + 1:
            out.append(f'{head["id"]}: the headline runs {bottom - g["y"] - g["h"]:.0f} px past the template\'s title area '
                       f'on "{lay["name"]}" ({g["h"]:.0f} px tall): shorten it')
    for e in scene.get("elements", []):
        ws = [w for p in ((e.get("text") or {}).get("paras") or []) for w in (p.get("words") or [])]
        if not ws or e.get("overlapOk"):
            continue
        x0, x1 = min(w["x"] for w in ws), max(w["x"] + w["w"] for w in ws)
        y0, y1 = min(w["y"] + w["h"] * 0.15 for w in ws), max(w["y"] + w["h"] * 0.85 for w in ws)
        for d in marks:
            g = d["geometry"]
            if min(x1, g["x"] + g["w"]) - max(x0, g["x"]) > 2 and min(y1, g["y"] + g["h"]) - max(y0, g["y"]) > 0.5:
                what = f'"{d["text"]}"' if d.get("text") else "rule"
                out.append(f'{e["id"]}: text sits on the layout\'s own {d.get("name") or "shape"} ({what}) of '
                           f'"{lay["name"]}": move it, or put the slide on a layout without it (data-layout)')
                break
    return out


def lint(args) -> int:
    from .design import deck_mode, design_page, rhythm_problems, slide_problems
    from .skald.measure import font_fallbacks, measure_page, slide_page
    files = slide_files(args.slides)
    if not files:
        print("no slides found", file=sys.stderr)
        return 2
    design = not getattr(args, "no_design", False)
    scenes, infos = [], []
    with slide_page() as page:
        for f in files:
            scenes.append(measure_page(page, f))
            scenes[-1].setdefault("errors", []).extend(font_fallbacks(page))
            infos.append(design_page(page) if design else None)
    bdir = _deck_brand(files, getattr(args, "brand", None))
    if bdir:
        brand = json.loads((bdir / "brand.json").read_text())
        for sc in scenes:
            sc.setdefault("errors", []).extend(layout_clashes(sc, brand))
    if design:  # what reference/design/ asks of a slide that converts fine (convey/design.py)
        modes = deck_mode(files)
        rhythm = rhythm_problems(infos)
        for i, (sc, inf) in enumerate(zip(scenes, infos)):
            mode = modes.get((inf or {}).get("slideId") or "", modes["default"])
            sc.setdefault("errors", []).extend(f"design: {p}" for p in slide_problems(inf, mode))
            if i in rhythm:
                sc["errors"].append(f"design: {rhythm[i]}")
    refused = _report(scenes, files, args.verbose)
    where = f" in {files[0].parent}" if len({f.parent for f in files}) == 1 else ""
    print(f"{len(files)} slides{where}: {len(files) - refused} pass, {refused} refused")
    return 1 if refused else 0


SHEET_W = 1560  # under the 1568 px long edge past which a model's picture reader shrinks a picture anyway


def contact_sheet(page, pics: list, path: Path):
    """Every slide's picture, small and numbered, on one page: the deck as a whole (its rhythm, its color, a slide
    that stands out) for the price of one picture. Drawn by the same browser; no image library."""
    import html
    import math
    n = len(pics)
    cols = max(1, math.ceil(math.sqrt(n * 1.1)))
    gap = 8
    tw = (SHEET_W - (cols + 1) * gap) // cols
    th = round(tw * 9 / 16)
    h = math.ceil(n / cols) * (th + 22 + gap) + gap
    tiles = "".join(
        f'<figure style="position:absolute;margin:0;left:{gap + (i % cols) * (tw + gap)}px;'
        f'top:{gap + (i // cols) * (th + 22 + gap)}px"><img src="{html.escape(p.resolve().as_uri())}" '
        f'style="display:block;width:{tw}px;height:{th}px;outline:1px solid #888">'
        f'<figcaption style="font:13px/20px sans-serif;color:#222">{i + 1}. {html.escape(p.stem)}</figcaption></figure>'
        for i, p in enumerate(pics))
    page_file = path.parent / ".sheet.html"
    page_file.write_text(f'<!doctype html><html><body style="margin:0;background:#fff;width:{SHEET_W}px;'
                         f'height:{h}px;position:relative">{tiles}</body></html>')
    try:
        page.goto(page_file.resolve().as_uri())
        page.evaluate("Promise.all([...document.images].map(i => i.decode().catch(() => 0))).then(() => true)")
        page.screenshot(path, clip={"x": 0, "y": 0, "width": SHEET_W, "height": h}, beyond=True)
    finally:
        page_file.unlink(missing_ok=True)


def same_picture(page, a: Path, b: Path) -> bool:
    """True when no pixel of two same-size pictures differs by more than 2 levels in any channel: far below anything
    visible. The same slide can draw a few pixels 1 level apart from one load to the next (6 pixels of a 54-slide
    range deck's section slide, Oct 18, 2026), and that alone mustn't send the agent back to an unchanged picture."""
    import base64
    urls = [f"data:image/png;base64,{base64.b64encode(p.read_bytes()).decode()}" for p in (a, b)]
    return bool(page.evaluate(f"""(async () => {{
      const load = async (u) => createImageBitmap(await (await fetch(u)).blob());
      const [x, y] = await Promise.all([load({json.dumps(urls[0])}), load({json.dumps(urls[1])})]);
      if (x.width !== y.width || x.height !== y.height) return false;
      const px = (im) => {{ const c = new OffscreenCanvas(im.width, im.height), g = c.getContext("2d");
        g.drawImage(im, 0, 0); return g.getImageData(0, 0, im.width, im.height).data; }};
      const A = px(x), B = px(y);
      for (let i = 0; i < A.length; i++) if (Math.abs(A[i] - B[i]) > 2) return false;
      return true;
    }})()"""))


def look(args) -> int:
    """A picture of each slide as the browser draws it. Lists to open only the pictures that changed since the last
    look into the folder (the token diet, Oct 18, 2026: an unchanged slide's picture costs as much to re-open as the
    first time and shows nothing new); --all lists every one. Several slides also get sheet.png, all of them small."""
    import hashlib
    from .skald.measure import slide_page
    files = slide_files(args.slides)
    if not files:
        print("no slides found", file=sys.stderr)
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    mark = out / ".convey-look"
    seen = {}
    if mark.exists():  # a folder look made before: what it pictured; pictures of slides not in this look go
        try:
            seen = json.loads(mark.read_text()).get("pictures", {})
        except ValueError:
            seen = {}
        stems = {f.stem for f in files}
        for old in out.glob("*.png"):
            if old.stem not in stems or args.full:
                old.unlink()
    elif any(out.glob("*.png")):
        print(f"note: {out} already holds pictures look didn't make; they stay", file=sys.stderr)
    changed, kept, pics = [], 0, []
    sheet = out / "sheet.png"
    with slide_page() as page:
        for f in files:
            page.goto(f.resolve().as_uri())
            page.evaluate("document.fonts.ready.then(() => true)")
            page.evaluate("window.skaldCharts && window.skaldCharts(), true")
            page.wait(80)
            clip = None
            if args.full:  # a long page (the brand sheet, the export report): all of it, not one slide's worth
                w, h = page.evaluate("[document.documentElement.scrollWidth, document.documentElement.scrollHeight]")
                clip = {"x": 0, "y": 0, "width": w, "height": h}
            dest, fresh = out / f"{f.stem}.png", out / f".{f.stem}.new.png"
            page.screenshot(fresh, clip=clip, beyond=bool(clip))
            digest = hashlib.sha256(fresh.read_bytes()).hexdigest()
            if not args.full and seen.get(f.stem) not in (None, digest) and dest.exists() \
                    and same_picture(page, dest, fresh):
                digest = seen[f.stem]
            pics.append(dest)
            if not (args.full or args.all) and seen.get(f.stem) == digest and dest.exists():
                fresh.unlink()
                kept += 1
            else:
                fresh.replace(dest)
                changed.append(dest)
            seen[f.stem] = digest
        if len(files) > 1 and not args.full:
            contact_sheet(page, pics, sheet)
        else:
            sheet.unlink(missing_ok=True)
    mark.write_text(json.dumps({"made by": "convey look; the next look into this folder replaces these pictures",
                                "pictures": {f.stem: seen[f.stem] for f in files}}, indent=1) + "\n")
    if args.full or len(files) == 1:
        for p in changed:
            print(p)
        if kept:
            print(f"{files[0].name}: unchanged since the last look ({pics[0]}; --all lists it anyway)")
        return 0
    if kept:
        print(f"{len(files)} slides, {len(changed)} changed since the last look in {out} (open these before the next "
              f"look; {kept} unchanged, --all lists every picture):")
    else:
        print(f"{len(files)} slides pictured in {out} (open each before the next look, which lists only what "
              "changes after this one):")
    for p in changed:
        print(f"  {p.name}")
    print(f"sheet: {sheet}  (every slide, small: the deck as a whole)")
    return 0


def export(args) -> int:
    from .skald.emit import Emitter

    import tempfile
    from .skald.measure import measure_page, slide_page

    files = slide_files(args.slides)
    if not files:
        print("no slides found", file=sys.stderr)
        return 2
    # One browser pass: each slide's scene, its visible words and (for the report) its own PDF.
    pdf_dir = Path(tempfile.mkdtemp(prefix="convey-export-"))
    scenes, pdfs = [], []
    with slide_page() as page:
        for i, f in enumerate(files):
            sc = measure_page(page, f)
            if not args.no_report:
                sc["allText"] = page.evaluate("document.querySelector('.slide')?.innerText || ''")
                pdfs.append(pdf_dir / f"{i + 1:02d}.pdf")
                page.pdf(pdfs[-1])
            scenes.append(sc)
    refused = sum(bool(sc.get("errors")) for sc in scenes)
    if refused and not args.force:
        _report(scenes, files, quiet=True)
        print(f"not exported: {refused} slide(s) fail lint (--force exports them anyway)")
        return 1
    fonts = args.fonts
    template = bindings = None
    if args.brand:
        from .brand import faces_for
        bdir = _brand_dir(args.brand)
        b = json.loads((bdir / "brand.json").read_text())
        faces = faces_for(b)
        if not args.no_template:
            template = next(iter(sorted(bdir.glob("template.*"))), None)
            bindings = b.get("bindings", {})
    else:
        if fonts is None:
            near = files[0].parent / "fonts.json"
            fonts = near if near.exists() else None
        faces = json.loads(Path(fonts).read_text()) if fonts else None
    # Speaker notes: each slide's `notes` in the deck's storyboard (beside slides/), by its data-slide id.
    notes = {}
    sb = files[0].resolve().parent.parent / "storyboard.json"
    if sb.exists():
        notes = {s_["id"]: s_["notes"] for s_ in json.loads(sb.read_text()).get("slides", []) if s_.get("notes")}
    prs = Emitter(faces=faces).deck(scenes, template=template, bindings=bindings, numbers=args.numbers, notes=notes)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    prs.save(args.out)
    print(f"{len(scenes)} slides -> {args.out}" + (f" ({refused} failed lint, exported with --force)" if refused else "")
          + (f", speaker notes on {sum(1 for sc in scenes if notes.get(sc.get('slideId')))}" if notes else ""))
    pdf = (Path(args.pdf) if args.pdf != "auto" else Path(args.out).with_suffix(".pdf")) if args.pdf else None
    if args.no_report:
        if pdf:
            from . import powerpoint
            if not powerpoint.available():
                print("no PDF: --pdf saves PowerPoint's own PDF, and PowerPoint isn't installed here", file=sys.stderr)
                return 1
            powerpoint.render_pdf(Path(args.out), pdf)
            print(f"PDF -> {pdf}")
        return 0
    from .verify import summary, verify_export
    out_html = Path(args.report) if args.report else Path(args.out).parent / "report.html"
    rep = verify_export(scenes, pdfs, args.out, out_html, files, keep_pdf=pdf)
    if pdf and not rep.get("tested"):
        print("no PDF: --pdf saves PowerPoint's own PDF, and PowerPoint didn't draw the deck here", file=sys.stderr)
    import shutil
    shutil.rmtree(pdf_dir, ignore_errors=True)
    # Only the slides that need a look (the token diet, Oct 18, 2026); the report has every slide.
    for r, f in zip(rep["slides"], files):
        if r["verdict"] != "green" or args.verbose:
            print(f"  {r['verdict']:10} {f.name}" + (f"  ({'; '.join(r['reasons'])})" if r["reasons"] else ""))
    print(summary(rep) + f" -> {out_html}" + (f"\nPDF (PowerPoint's own, the one graded above) -> {pdf}" if pdf and rep.get("tested") else ""))
    return 0


def _brand_dir(name_or_path) -> Path:
    from .brand import HOME
    p = Path(name_or_path)
    if (p / "brand.json").exists():
        return p
    if (HOME / str(name_or_path) / "brand.json").exists():
        return HOME / str(name_or_path)
    raise SystemExit(f"no Brand Profile at {p} or {HOME / str(name_or_path)} (run `convey brand ingest` first)")


def calibration_verdict(r: dict) -> str:
    """What a calibration's leftover error means, in the export report's own terms."""
    typ = r["typical_residual"]
    if typ > 1:
        return (f"  poor fit: lines typically still sit {typ} px off. Check the font is installed for PowerPoint "
                "(not only the browser) and run calibrate again; until then expect yellow text in the export report.")
    return ("  good fit. The export report marks text yellow past 2 px off and red past 4; a worst line of a few px "
            "is PowerPoint's own placement scatter on one box, not a failed fit.")


def brand_cmd(args) -> int:
    from . import brand as B
    if args.action == "ingest":
        out = B.ingest(args.target, args.name or Path(args.target).stem.lower(), args.out)
        b = json.loads((out / "brand.json").read_text())
        open_ = [f for f in b["flags"] if not f["settled"]]
        print(f"{b['name']}: {len(b['layouts'])} layouts, {len(b['colors'])} brand colors, "
              f"fonts {b['fonts']['heading']['powerpoint']} / {b['fonts']['body']['powerpoint']}")
        print(f"{len(open_)} flag(s) need a call: {out / 'flags.md'}")
        print(f"brand sheet: {out / 'brand-sheet.html'}")
        return 0
    d = _brand_dir(args.target)
    b = json.loads((d / "brand.json").read_text())
    if args.action == "settle":
        if not args.settle:
            print("say which flag(s): convey brand settle N ID[=VALUE] ...  (open flags are in flags.md)", file=sys.stderr)
            return 2
        for item in args.settle:
            fid, _, val = item.partition("=")
            try:
                print(f"{fid}: {B.settle(b, fid.strip(), val.strip() if _ else None)}")
            except ValueError as e:
                print(f"error: {e}", file=sys.stderr)
                return 2
    if args.action == "approve":  # the person's approval, recorded like storyboard.approved (Oct 18, 2026)
        import time
        b["approved"] = {"by": args.by or "the person", "at": time.strftime("%b %d, %Y, %H:%M")}
        print(f"{b['name']}: approved by {b['approved']['by']} on {b['approved']['at']}")
    if args.action == "calibrate":
        from .calibrate import calibrate
        # Each family at 400 (the fallback for any weight), plus every other weight a role uses, on its own:
        # the faces of one family can carry different vertical metrics, and then they sit differently in PowerPoint.
        jobs = {}
        for role in ("body", "heading"):
            f = b["fonts"][role]
            if not f["installed"]:
                continue
            base = 400 if "400" in f["faces"] else f["weight"]
            jobs.setdefault(f["css"], (f, base))
            if f["weight"] != base:
                jobs.setdefault(f"{f['css']}@{f['weight']}", (f, f["weight"]))
        fits = {}
        for key, (f, weight) in jobs.items():
            css = f["css"]
            if not f["browser"]:
                print(f"skip {key}: the browser can't see it, so there is nothing to compare")
                continue
            work = d / "calibration" / key.replace(" ", "-").replace("@", "-")
            if not getattr(args, "width_only", False):
                r = calibrate(css, {css: f["faces"]}, weight=weight, work=work)
                b["vertical"][key] = {**{k: v for k, v in b["vertical"].get(key, {}).items() if k.startswith("advance")}, **r}
                b["flags"] = [x for x in b["flags"] if x["id"] != "calibrate-" + css]
                print(f"{key}: drop = {r['lh']}*lh + {r['fs']}*fs + {r['c']} px  ({r['samples']} lines, "
                      f"typical {r['typical_residual']} px off after the fit, worst {r['max_residual']} px)")
                twin = next((k for k, v in fits.items() if v == (r["lh"], r["fs"], r["c"])), None)
                if twin:  # a reader thought one weight had been measured twice (Oct 18, 2026 stress test)
                    print(f"  the same line fit as {twin}: both weights carry the same vertical metrics, so PowerPoint "
                          "sets their lines alike; their widths are measured apart below")
                fits[key] = (r["lh"], r["fs"], r["c"])
                print(calibration_verdict(r))
            # Width: what to add after each character so PowerPoint's lines run as long as the browser's (Oct 18, 2026).
            from .calibrate import advance
            w = advance(css, {css: f["faces"]}, weight=weight, work=work)
            b["vertical"].setdefault(key, {}).update(w)
            if "@" not in key and css == b["fonts"]["body"]["css"]:  # charts take the body font
                from .calibrate import chart_labels
                c = chart_labels(css, {css: f["faces"]}, weight=weight, work=work)
                b["vertical"][key].update(c)
                print(f"{key}: chart labels [size, dy, dx] {c['chart']}")
            worst = max(w["advance"], key=lambda p: abs(p[1]))
            print(f"{key}: width measured at {len(w['advance'])} sizes; largest correction {worst[1]:+.4f} px per "
                  f"character at {worst[0]} px")
    if args.action == "render":
        files = B.render_layouts(d, b)
        print(f"{len(files)} layout pictures -> {d / 'assets' / 'layouts'}")
    if args.action in ("render", "sheet"):
        pl = B.plate_check(d, b)
        if pl:
            print(f"background under the content: {pl['contrast']}:1 against the body color; content plate "
                  f"{'on' if pl['on'] else 'off'} ({pl['how']})")
    B.write(b, d)
    print(f"wrote {d / 'tokens.css'}, flags.md, brand-sheet.html")
    return 0


def assets_cmd(args) -> int:
    from . import assets as A
    if args.action == "find":
        hits = A.find(args.target or "")
        for i in hits:
            print(f"{i['id']:14} {', '.join(i['concepts'])}")
        return 0 if hits else 1
    if args.action == "show":
        try:
            print(A.svg(args.target, args.size, args.id))
        except (KeyError, ValueError) as e:
            print(e.args[0], file=sys.stderr)
            return 1
        return 0
    if args.action == "part":
        kw = {}
        for item in args.params:
            k, _, v = item.partition("=")
            if "," in v and k in ("points",):
                kw[k] = [float(x) for x in v.split(",")]
            elif v.lower() in ("true", "false"):
                kw[k] = v.lower() == "true"
            else:
                try:
                    kw[k] = int(v) if v.lstrip("-").isdigit() else float(v)
                except ValueError:
                    kw[k] = v
        print(A.part(args.target, **kw))
        return 0
    tokens = _brand_dir(args.brand) / "tokens.css" if args.brand else None
    print(A.gallery(Path(args.out or "gallery.html"), tokens))
    return 0


def intake_cmd(args) -> int:
    from .intake import intake
    m = intake(args.files, Path(args.project))
    for f in m["files"]:
        print(f"{f['file']:40} " + ("picture: use it on a slide as content.image" if f.get("picture") else
              f"{f['chunks']:5} chunks") + (f"   FLAG: {f['flag']}" if f.get("flag") else ""))
    return 1 if any(f.get("flag") for f in m["files"]) else 0


def check_cmd(args) -> int:
    from .check import report
    return report(Path(args.project), args.verbose)


def compose_cmd(args) -> int:
    from .compose import compose
    d = Path(args.project)
    brand = args.brand
    if not brand:  # the brief's brand: a name, or a folder relative to the deck project
        brand = json.loads((d / "brief.json").read_text()).get("brand")
        if (d / brand / "brand.json").exists():
            brand = str(d / brand)
    files = compose(d, _brand_dir(brand), force=args.force, overwrite=args.overwrite, keep_edits=args.keep_edits)
    print(f"{len(files)} slides -> {d / 'slides'}  (next: convey lint {d / 'slides'}; convey check {d})")
    return 0


def deliver_cmd(args) -> int:
    from .deliver import deliver
    r = deliver(Path(args.project), Path(args.deck) if args.deck else None, Path(args.to) if args.to else None, args.force)
    print(f"delivered to {r['folder']}:")
    for f in r["files"]:
        print(f"  {f}")
    return 0


def restyle_cmd(args) -> int:
    from .restyle import restyle
    d = Path(args.project)
    brand = json.loads((d / "brief.json").read_text()).get("brand")
    src = _brand_dir(str(d / brand)) if (d / brand / "brand.json").exists() else _brand_dir(brand)
    new = _brand_dir(args.brand)
    r = restyle(d, args.brand, Path(args.out), src, new, overwrite=args.overwrite)
    print(f"{r['slides']} slides -> {Path(args.out) / 'slides'} on {new.name}; {r['carried']} design edit(s) carried "
          f"from {d / 'slides'}" + ("" if r["saved_base"] else " (compared with a fresh compose of the source: it had no "
                                    "slides/.composed/, so an edit that worked around an older compose may show twice)"))
    if not r["linked"]:
        print("note: this system made copies, not links, of the plan files: keep the two decks' stories in step by hand")
    for line in r["left"]:
        print(f"left for you: {line}")
    print(f"next: convey lint {Path(args.out) / 'slides'}; convey look {Path(args.out) / 'slides'} -o ...; convey check {args.out}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="convey", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("intake", help="copy sources into a deck project and extract their text")
    p.add_argument("files", nargs="+")
    p.add_argument("--project", required=True, help="the deck project folder")
    p.set_defaults(fn=intake_cmd)
    p = sub.add_parser("check", help="claims, sources, derivations, numbers, bindings, headline chain")
    p.add_argument("project")
    p.add_argument("-v", "--verbose", action="store_true", help="every check on its own line, and the headline chain "
                   "even when it hasn't changed")
    p.set_defaults(fn=check_cmd)
    p = sub.add_parser("compose", help="first-draft slides from the approved storyboard")
    p.add_argument("project")
    p.add_argument("--brand", help="a Brand Profile (default: the brief's brand)")
    p.add_argument("--force", action="store_true", help="compose an unapproved story anyway (for testing)")
    p.add_argument("--overwrite", action="store_true", help="compose a deck that is in review or has hand edits (wipes them)")
    p.add_argument("--keep-edits", action="store_true", help="compose again and carry the slides' hand edits (not in review)")
    p.set_defaults(fn=compose_cmd)
    p = sub.add_parser("restyle", help="the same approved deck on another template, keeping its slides' design edits")
    p.add_argument("project", help="the approved deck project")
    p.add_argument("--brand", required=True, help="the other Brand Profile (name or folder)")
    p.add_argument("-o", "--out", required=True, help="the new deck project (shares the plan files by link)")
    p.add_argument("--overwrite", action="store_true", help="restyle again into a folder that has slides (drops its design work)")
    p.set_defaults(fn=restyle_cmd)
    from .studio import rounds as studio_rounds, server as studio_server
    studio_server.add_parser(sub)
    studio_rounds.add_parser(sub)
    p = sub.add_parser("lint", help="refuse features that can't convert")
    p.add_argument("slides", nargs="+")
    p.add_argument("-v", "--verbose", action="store_true", help="also list the slides that pass, and print caveats (warnings, notes)")
    p.add_argument("--brand", help="the Brand Profile (default: the deck's brief.json brand), to check text against what each layout draws")
    p.add_argument("--no-design", action="store_true", help="only what converts: skip contrast, type size, crowding, "
                   "color on the template's background and rhythm")
    p.set_defaults(fn=lint)
    p = sub.add_parser("look", help="picture every slide (1280x720 PNG) to look at before anyone else does")
    p.add_argument("slides", nargs="+")
    p.add_argument("-o", "--out", required=True, help="folder for the pictures")
    p.add_argument("--full", action="store_true", help="the whole page, any length (brand-sheet.html, report.html)")
    p.add_argument("--all", action="store_true", help="list every slide's picture, not only those changed since the last look")
    p.set_defaults(fn=look)
    p = sub.add_parser("export", help="slides -> .pptx")
    p.add_argument("slides", nargs="+")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--fonts", help="weight -> font face map (default: fonts.json beside the slides)")
    p.add_argument("--brand", help="a Brand Profile (name or folder): its fonts, calibration and template; "
                   "each slide is written onto the template's layout for its pattern")
    p.add_argument("--no-template", action="store_true", help="with --brand: a blank deck, not the template")
    p.add_argument("--numbers", action="store_true", help="on a template: show the layout's slide numbers")
    p.add_argument("--force", action="store_true", help="export slides that fail lint too")
    p.add_argument("--report", help="where to write the export report (default: report.html beside the deck)")
    p.add_argument("--no-report", action="store_true", help="skip the report (no PowerPoint render, no comparison)")
    p.add_argument("-v", "--verbose", action="store_true", help="list every slide's grade, green ones too")
    p.add_argument("--pdf", nargs="?", const="auto", help="also save PowerPoint's own PDF of the deck (default: beside it, .pdf)")
    p.set_defaults(fn=export)
    p = sub.add_parser("deliver", help="the approved deck, its PDF and report, in one folder that's easy to find")
    p.add_argument("project")
    p.add_argument("--deck", help="the exported .pptx (default: the newest in DIR/build/)")
    p.add_argument("--to", help="the folder to fill (default: ~/Downloads/<the brief's title>/)")
    p.add_argument("--force", action="store_true", help="deliver a deck the person hasn't approved (a draft)")
    p.set_defaults(fn=deliver_cmd)
    p = sub.add_parser("brand", help="Brand Profile: ingest a template, calibrate its fonts, rebuild its sheet")
    p.add_argument("action", choices=["ingest", "calibrate", "render", "sheet", "settle", "approve"])
    p.add_argument("target", help="ingest: the template file; otherwise: the brand's name or folder")
    p.add_argument("settle", nargs="*", help="settle: flag ids, each ID (confirm) or ID=VALUE")
    p.add_argument("--name", help="ingest: the brand's name (default: the file name)")
    p.add_argument("--by", help="approve: who approved the Brand Profile")
    p.add_argument("--out", help="ingest: folder to write (default: ~/.convey/brands/NAME)")
    p.add_argument("--width-only", action="store_true",
                   help="calibrate: measure only how wide PowerPoint sets each size (keeps the line-position fit)")
    p.set_defaults(fn=brand_cmd)
    p = sub.add_parser("assets", help="the picture vocabulary: find, show, part, gallery")
    p.add_argument("action", choices=["find", "show", "part", "gallery"])
    p.add_argument("target", nargs="?", help="find: a word; show: an icon id; part: the part's name")
    p.add_argument("params", nargs="*", help="part: key=value settings (left=100 top=200 n=3; points=x,y,x,y)")
    p.add_argument("--size", type=float, default=64, help="show: width and height in px")
    p.add_argument("--id", help="show: the data-id (PowerPoint object name)")
    p.add_argument("--brand", help="gallery: a Brand Profile whose tokens.css colors the page")
    p.add_argument("-o", "--out", help="gallery: the page to write (default gallery.html)")
    p.set_defaults(fn=assets_cmd)
    args = ap.parse_args(argv)
    return args.fn(args)
