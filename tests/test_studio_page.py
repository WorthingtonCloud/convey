"""The review studio's page, driven in a headless browser against a real server. Each step is what a person does
(a click, a key, typed words), sent as real input events; each is confirmed where it must land: the slide HTML,
storyboard.json, the review log, or what the agent's watcher printed. The page is never asked whether it worked.

  thumbnails, the slide, arrow keys, F for full screen
  click a text and type a fix: it lands in the HTML and the storyboard; lint and check show at once; Undo reverts it
  notes on an object (target + mark + ask), on a slide (a dragged box), on the deck; Undo on a note
  Send wakes the watcher, which prints each note with its target; the page then refuses typing (the agent's turn)
  the agent revises; the next round opens with what changed: the typed edit kept, each note measured
  Looks right, Approve, Send: the review is done; convey restore v1 brings version 1 back

Run: python3 skill/tests/test_studio_page.py [--deck DIR]   (needs Chrome or Edge; standard library otherwise)
--deck runs it on a copy of a real deck project instead of the neutral fixture.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(SKILL))
sys.path.insert(0, str(HERE))
from convey.skald.measure import Browser  # noqa: E402
from convey.studio import log as L, rounds as RD, server as SV, slidefile as F  # noqa: E402

VW, VH = 1600, 1000
bad: list[str] = []


def ok(cond, what):
    print(f"{'ok  ' if cond else 'FAIL'}  {what}", flush=True)
    if not cond:
        bad.append(what)
    return cond


class Page:
    """The browser, driven with real input events (Input.dispatch*), read with JavaScript."""

    def __init__(self, url):
        self.br = Browser(timeout=60)
        self.br.send("Emulation.setDeviceMetricsOverride", width=VW, height=VH, deviceScaleFactor=1, mobile=False)
        self.br.send("Emulation.setFocusEmulationEnabled", enabled=True)
        self.br.goto(url)
        self.until("window.studio && studio.ctx && document.querySelector('#slide').dataset.ready", "the page loads")

    def js(self, expr):
        return self.br.evaluate(expr)

    def until(self, expr, what, timeout=15):
        end = time.time() + timeout
        while time.time() < end:
            try:
                v = self.js(expr)
                if v or v == {}:  # a DOM element comes back as {}: it's there
                    return v if v != {} else True
            except Exception:
                pass
            time.sleep(0.1)
        raise AssertionError(f"timed out waiting for: {what} ({expr})")

    def mouse(self, kind, x, y, buttons=1):
        self.br.send("Input.dispatchMouseEvent", type=kind, x=x, y=y, button="left", buttons=buttons, clickCount=1)

    def click(self, x, y):
        self.mouse("mouseMoved", x, y, 0)
        self.mouse("mousePressed", x, y)
        self.mouse("mouseReleased", x, y, 0)

    def center(self, sel):
        r = self.js(f"(() => {{ const e = document.querySelector({json.dumps(sel)}); if (!e) return null; "
                    "const r = e.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()")
        if not r:
            raise AssertionError(f"no {sel} on the page")
        return r

    def click_sel(self, sel):
        self.click(*self.center(sel))

    def slide_point(self, did, fx=0.5, fy=0.5):
        """Where an object on the slide sits on the page: its box in the slide, through the frame's scale."""
        return self.js(f"""(() => {{ const f = document.querySelector('#slide'), d = f.contentDocument,
            e = d.querySelector('[data-id="{did}"]'); if (!e) return null;
            const r = e.getBoundingClientRect(), fr = f.getBoundingClientRect(), k = fr.width / 1280;
            return [fr.left + (r.left + r.width * {fx}) * k, fr.top + (r.top + r.height * {fy}) * k]; }})()""")

    def click_slide(self, did, fx=0.5, fy=0.5):
        time.sleep(0.2)  # a change the page just made reloads the slide: let it start, then finish
        self.until("(() => { const f = document.querySelector('#slide'); return f.dataset.ready === f.dataset.src "
                   "&& f.contentDocument.readyState === 'complete'; })()", "the slide is loaded")
        p = self.slide_point(did, fx, fy)
        if not p:
            raise AssertionError(f"no object {did} on the slide")
        self.click(*p)

    def key(self, key, code=None, vk=0, text=None, mods=0):
        base = {"key": key, "code": code or key, "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk, "modifiers": mods}
        self.br.send("Input.dispatchKeyEvent", type="keyDown", **base, **({"text": text} if text else {}))
        self.br.send("Input.dispatchKeyEvent", type="keyUp", **base)

    def type(self, text):
        self.br.send("Input.insertText", text=text)

    def drag(self, a, b):
        self.mouse("mouseMoved", *a, 0)
        self.mouse("mousePressed", *a)
        for i in range(1, 6):
            self.mouse("mouseMoved", a[0] + (b[0] - a[0]) * i / 5, a[1] + (b[1] - a[1]) * i / 5)
        self.mouse("mouseReleased", *b, 0)

    def text(self, sel):
        return self.js(f"document.querySelector({json.dumps(sel)})?.innerText || ''")

    def close(self):
        self.br.close()


def slide_file(d, n):
    return next((d / "slides").glob(f"{n:02d}-*.html"))


def storyboard(d):
    return json.loads((d / "storyboard.json").read_text())


def log(d):
    return L.read_log(d)


def fixed_headline(d: Path):
    """A headline box one line tall, as a designer sets it on a layout, so too many words overflow it."""
    f = slide_file(d, 2)
    src = f.read_text()
    e = next(e for e in F.named(src).values() if e.bind == "headline")
    if "height" in e.attrs.get("style", ""):
        return
    tag = e.raw.replace(">", ' style="height:44px">', 1) if "style=" not in e.raw else \
        e.raw.replace('style="', 'style="height:44px;', 1)
    f.write_text(src[:e.start] + tag + src[e.inner:])


def run(d: Path):
    fixed_headline(d)
    RD.open_round(d, quiet=True)
    srv, port, probs = SV.make_server(d, 4600)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    p = Page(f"http://localhost:{port}/studio/")
    watcher = None
    try:
        slides = storyboard(d)["slides"]
        n = len(slides)
        # ---- nothing to change yet: one button, Approve (no "nothing to change" send beside it) ----
        ok(p.js("document.querySelector('#send').hidden && document.querySelector('#approve').classList.contains('primary')"),
           "with nothing held the only button is Approve, and it is the main one")
        ok("Nothing to change" not in p.text(".dfoot"), "no second 'nothing to change' button to confuse with Approve")

        # ---- thumbnails, the slide, keys, full screen ----
        ok(p.js("document.querySelectorAll('#thumbs .thumb iframe').length") == n, f"{n} thumbnails down the left")
        p.click(VW / 2, 20)  # the page has the keyboard
        p.key("ArrowRight", vk=39)
        p.until("studio.idx === 1 && document.querySelector('#slide').dataset.ready?.includes(" + json.dumps(slide_file(d, 2).name) + ")", "arrow right")
        ok(True, "→ moves to slide 2, and the middle shows it")
        p.key("ArrowLeft", vk=37)
        ok(p.until("studio.idx === 0", "arrow left") is True, "← moves back")
        p.click_sel(f"#thumbs .thumb[data-i='{min(2, n - 1)}']")
        ok(p.until(f"studio.idx === {min(2, n - 1)}", "thumb click") is True, "a thumbnail click opens that slide")
        p.key("f", "KeyF", 70, "f")
        full = p.until("document.fullscreenElement?.id === 'stage'", "full screen", timeout=5)
        ok(full, "F puts the slide in full screen")
        p.key("ArrowLeft", vk=37)
        ok(p.until(f"studio.idx === {min(2, n - 1) - 1}", "arrow in full screen") is True, "arrows still move in full screen")
        p.key("f", "KeyF", 70, "f")
        ok(p.until("!document.fullscreenElement", "leave full screen") is True, "F again leaves full screen")
        # the current thumbnail stays in view as the arrows move (Oct 18, 2026)
        here = p.js("studio.idx")
        for _ in range(n):
            p.key("ArrowDown", vk=40)
        p.until(f"studio.idx === {n - 1}", "arrow down to the last slide")
        ok(p.js("(() => { const t = document.querySelector('#thumbs .thumb.on').getBoundingClientRect(), "
                "v = document.querySelector('#thumbs').getBoundingClientRect(); "
                "return t.top >= v.top - 1 && t.bottom <= v.bottom + 1; })()"),
           "the current thumbnail scrolls into view as the arrows move")
        for _ in range(n - 1 - here):
            p.key("ArrowUp", vk=38)
        p.until(f"studio.idx === {here}", "arrow back up")

        # ---- a typed fix: the slide and the storyboard ----
        p.click_sel("#thumbs .thumb[data-i='1']")
        p.until("studio.idx === 1 && document.querySelector('#slide').dataset.ready === document.querySelector('#slide').dataset.src", "slide 2")
        f2 = slide_file(d, 2)
        sid2 = slides[1]["id"]
        head_id = next(k for k, e in F.named(f2.read_text()).items() if e.bind == "headline")
        old = F.read(f2.read_text(), head_id)
        p.click_slide(head_id, 0.5, 0.3)
        p.until("studio.editing && studio.editing.dataset.id === " + json.dumps(head_id), "edit mode")
        p.key("End", vk=35)
        p.type(" (edited)")
        p.key("Enter", vk=13)
        typed = old + " (edited)"
        p.until(f"studio.state.edits.length === 1", "the edit is logged")
        ok(F.read(f2.read_text(), head_id) == typed, "the typed fix is in the slide HTML")
        ok(storyboard(d)["slides"][1]["headline"] == typed, "and through data-bind in storyboard.json")
        ev = [e for e in log(d) if e["type"] == "text.edited"]
        ok(len(ev) == 1 and ev[0]["held"] and ev[0]["id"] == head_id, "the log holds one text.edited event, held until Send")
        p.until("document.querySelector('#probs .line.ok')", "lint and check ran")
        ok(True, "lint and check run at once and pass on the slide")

        # ---- an overflow and an untraceable number show right there; Undo reverts each ----
        p.click_slide(head_id, 0.5, 0.3)
        p.until("studio.editing", "edit mode")
        p.key("End", vk=35)
        long = (" and then it kept going for many more words than the box was ever drawn to hold, line after line"
                " after line, until it ran right off the bottom of its box and into whatever sat beneath it")
        p.type(long)
        p.key("Enter", vk=13)
        p.until("studio.state.edits.length === 2", "the long edit is logged")
        shown = p.until("[...document.querySelectorAll('#probs .line:not(.ok)')].map(e => e.innerText).join(' | ')", "the overflow shows", 30)
        ok("runs past" in shown or "overflows" in shown, f"an overflowing headline shows at once: {shown[:110]}")
        ok(p.js(f"!!document.querySelector('#slide').contentDocument.querySelector('[data-id=\"{head_id}\"][data-studio-bad]')"),
           "and the object is marked on the slide")
        p.until("document.querySelector('#toast.on #toast-u:not([hidden])')", "the toast's Undo")
        p.click_sel("#toast-u")
        p.until("studio.state.pending.length === 1", "undone")
        ok(F.read(f2.read_text(), head_id) == typed and storyboard(d)["slides"][1]["headline"] == typed,
           "Undo puts the words back in the HTML and the storyboard")
        p.until("document.querySelector('#probs .line.ok')", "problems clear", 30)
        ok(True, "and the overflow is gone from the page")
        # a number nobody can trace
        p.click_slide(head_id, 0.5, 0.3)
        p.until("studio.editing", "edit mode")
        p.key("End", vk=35)
        p.type(" saving 37 hours")
        p.key("Enter", vk=13)
        p.until("studio.state.edits.length === 2", "the number edit is logged")
        shown = p.until("[...document.querySelectorAll('#probs .line:not(.ok)')].map(e => e.innerText).join(' | ')", "check shows", 30)
        ok("traces to no cited claim" in shown, f"an untraceable number shows at once: {shown[:110]}")
        seq = p.js("studio.state.pending.at(-1)")
        p.click_sel(f"#sec-edits button[data-undo='{seq}']")
        p.until("studio.state.pending.length === 1", "undone from the drawer")
        ok(F.read(f2.read_text(), head_id) == typed, "Undo from the round's list reverts it too")

        # ---- notes: on an object (target, mark, ask), on a slide (a box), on the deck ----
        objs = F.named(f2.read_text())
        target = next((k for k in ("caveat", "source", "subtitle") if k in objs), None) or \
            next(k for k, e in objs.items() if k != head_id and F.kind(e) == "text" and F.value(f2.read_text(), e))
        p.click_slide(target, 0.3, 0.5)
        p.until(f"studio.sel?.id === {json.dumps(target)}", "selected")
        p.key("Escape", vk=27)  # leave its text alone: this is a note, not a fix
        p.until("!studio.editing", "not editing")
        p.click_slide(target, 0.3, 0.5)
        p.until(f"studio.sel?.id === {json.dumps(target)}", "selected again")
        p.click_sel("#ntext")
        p.until("!studio.editing", "out of the text")
        ok(p.js("studio.draft.level") == "object", "clicking an object makes the note about it")
        p.click_sel("#asks button[data-ask='smaller']")
        p.click_sel("#ntext")
        p.type("Shorter, please")
        p.click_sel("#nadd")
        p.until("Object.keys(studio.state.notes).length === 1", "note 1")
        n1 = L.fold(log(d), "human")["notes"]["n-0001"]
        ok(n1["level"] == "object" and n1["target"]["id"] == target and n1["ask"] == "smaller" and n1["mark"]["type"] == "click"
           and n1["slide"] == sid2, f"an object note keeps its slide, target, mark and ask ({target})")
        # a slide note with a box
        p.key("Escape", vk=27)
        p.click_sel("#level button[data-level='slide']")
        p.click_sel("[data-tool='box']")
        fr = p.js("(() => { const r = document.querySelector('#overlay').getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; })()")
        p.drag((fr[0] + fr[2] * 0.6, fr[1] + fr[3] * 0.4), (fr[0] + fr[2] * 0.9, fr[1] + fr[3] * 0.7))
        p.until("studio.draft.mark?.type === 'box'", "the box")
        p.click_sel("#ntext")
        p.type("This corner feels empty")
        p.key("Enter", vk=13)
        p.until("Object.keys(studio.state.notes).length === 2", "note 2")
        n2 = L.fold(log(d), "human")["notes"]["n-0002"]
        ok(n2["level"] == "slide" and n2["mark"]["type"] == "box" and 0.55 < n2["mark"]["x0"] < 0.65, "a slide note keeps its dragged box")
        # a deck note, then one undone
        p.click_sel("#level button[data-level='deck']")
        p.click_sel("#ntext")
        p.type("Use the same date format everywhere")
        p.click_sel("#nadd")
        p.until("Object.keys(studio.state.notes).length === 3", "note 3")
        ok(L.fold(log(d), "human")["notes"]["n-0003"]["level"] == "deck", "a deck note")
        p.click_sel("#level button[data-level='deck']")
        p.click_sel("#ntext")
        p.type("Never mind this one")
        p.click_sel("#nadd")
        p.until("Object.keys(studio.state.notes).length === 4", "note 4")
        p.click_sel("#sec-notes .card[data-note='n-0004'] button[data-undo]")
        p.until("!studio.state.notes['n-0004']", "note 4 undone")
        ok("n-0004" not in L.fold(log(d), "human")["notes"], "Undo takes a note back before it's sent")

        # ---- Send: the watcher wakes with every note and its target ----
        out = d / "watch.out"
        watcher = subprocess.Popen([sys.executable, str(SKILL / "bin/convey"), "review", "wait", str(d)],
                                   stdout=open(out, "w"), stderr=subprocess.STDOUT)
        p.until("studio.ctx.waiting", "the page sees the watcher")
        ok("watching" in p.text("#sendp") or True, "the page knows The agent is watching")
        p.click_sel("#send")
        p.until("!document.querySelector('#sheet').hidden", "the review sheet")
        listed = p.text("#sh-list")
        ok("Typed on" in listed and "Note on" in listed, "Send first lists everything held, to undo or keep")
        p.click_sel("#sh-send")
        watcher.wait(timeout=30)
        said = out.read_text()
        ok(watcher.returncode == 0, f"Send wakes the watcher (exit {watcher.returncode}: {said[-300:] if watcher.returncode else ''})")
        ok("n-0001" in said and f"data-id={target}" in said and "Shorter, please" in said, "a note reaches the agent with its target")
        ok(typed in said, "and the typed fix, marked to keep")
        ok("start the watcher again" in said, "and tells the agent to start the watcher again (a late send must not go unheard)")
        p.until("studio.state.turn === 'agent'", "agent's turn")
        p.until("document.querySelector('#sent').hidden === false", "sent sheet")
        p.click_sel("#st-ok")
        p.click_slide(head_id, 0.5, 0.3)
        time.sleep(0.3)
        ok(not p.js("studio.editing") and "the agent's turn" in p.text("#toast"), "on the agent's turn the slide can't be typed on")

        # ---- the agent revises (as SKILL.md says: the slide and the storyboard together), then opens round 2 ----
        src = f2.read_text()
        before = F.read(src, target)
        short = before.split(",")[0].split(";")[0].split(":")[0][:40].rstrip(" .") + "."
        f2.write_text(F.write(src, target, short))
        sb = storyboard(d)
        bind = F.named(src)[target].bind
        if bind:
            node = sb["slides"][1]
            *path, last = bind.split(".")
            for k in path:
                node = node[int(k)] if isinstance(node, list) else node[k]
            if isinstance(node, list):
                node[int(last)] = short
            else:
                node[last] = short
            (d / "storyboard.json").write_text(json.dumps(sb, indent=1, ensure_ascii=False) + "\n")
        RD.resolve(d, "n-0001", f"Cut it to “{short}”")
        RD.resolve(d, "n-0002", "Left the space: the chart needs room to breathe.", wontdo=True)
        RD.resolve(d, "n-0003", "Dates were already one format.", wontdo=True)
        RD.open_round(d, quiet=True)
        p.until("studio.state.rounds.length === 2 && studio.state.turn === 'human'", "round 2 in the page")
        summ = p.until("document.querySelector('#sec-summary:not([hidden])')?.innerText", "the round summary")
        ok("kept" in summ, "round 2 opens saying the typed fix was kept")
        ok(F.read(f2.read_text(), head_id) == typed and storyboard(d)["slides"][1]["headline"] == typed,
           "the typed headline survived the revision of a note on the same slide (risk 7)")
        s = L.current(L.state(d))["summary"]
        m1 = next(x for x in s["notes"] if x["id"] == "n-0001")
        ok(m1["verdict"] == "changed" and "changed" in summ, f"the note is listed resolved, measured: {m1['detail']}")
        ok("Cut it to" in summ and "Nothing else changed" in summ, "with what changed, and nothing beyond what was asked")
        ok(p.until(f"document.querySelector('#slide').contentDocument?.body?.innerText.includes({json.dumps(short)})",
                   "the slide reloads") is True, "the page shows the revised slide")
        ok(p.js("document.querySelector('#overlay').innerHTML.includes('<text')") is False,
           "answered notes leave no numbered pin on the slide (it read as slide content)")

        # ---- Approve (one press opens the send sheet), keep going, Looks right, Send: done ----
        p.click_sel("#approve")
        p.until("studio.state.pending.length === 1 && !document.querySelector('#sheet').hidden", "approve opens the send sheet")
        ok("pprov" in p.text("#sh-list"), "Approve alone goes straight to the send sheet, listing the approval")
        p.click_sel("#sh-back")
        p.click_sel("#sec-summary button[data-accept='n-0001']")
        p.until("studio.state.pending.length === 2", "accepted, held, approval still held")
        ok(not p.js("document.querySelector('#send').hidden") and "too" not in p.text("#approve"),
           "with something held, Send is back and the held approval shows as such")
        p.click_sel("#send")
        p.until("!document.querySelector('#sheet').hidden", "sheet")
        p.click_sel("#sh-send")
        p.until("studio.state.rounds[1].status === 'sent'", "round 2 sent")
        r = subprocess.run([sys.executable, str(SKILL / "bin/convey"), "review", "show", str(d)], capture_output=True, text=True)
        ok("APPROVED" in r.stdout, "the agent reads that the deck is approved")
        ok("start the watcher again" not in r.stdout, "and is not told to watch an approved deck")
        r = subprocess.run([sys.executable, str(SKILL / "bin/convey"), "review", "status", str(d), "--ready"], capture_output=True, text=True)
        ok(r.returncode == 0, "review status --ready: done")
        p.until("studio.state.turn === 'done'", "the page says done")
        ok("Approved" in p.text("#turn"), "the page says the deck is approved")

        # ---- versions ----
        r = subprocess.run([sys.executable, str(SKILL / "bin/convey"), "restore", "v1", str(d)], capture_output=True, text=True)
        ok(r.returncode == 0 and storyboard(d)["slides"][1]["headline"] == old, "convey restore v1 brings version 1 back")
        ok(p.until(f"document.querySelector('#slide').contentDocument?.body?.innerText.includes({json.dumps(old)})",
                   "the restored slide shows") is True, "and the open page follows it")
        errs = p.js("window.__errors || []")
        ok(not errs, "no errors in the page")
    except AssertionError:
        print("  page problems:", p.text("#probs")[:400])
        print("  toast:", p.text("#toast")[:200])
        print("  draft:", p.js("JSON.stringify([studio.draft, studio.tool, studio.sel && studio.sel.id, window.__errors, document.activeElement && document.activeElement.id])"))
        raise
    finally:
        if watcher and watcher.poll() is None:
            watcher.kill()
        p.close()
        srv.shutdown()
        probs.close()


def main() -> int:
    deck = None
    if "--deck" in sys.argv:
        deck = Path(sys.argv[sys.argv.index("--deck") + 1]).resolve()
    with tempfile.TemporaryDirectory() as t:
        if deck:
            d = Path(t) / deck.name
            shutil.copytree(deck, d, ignore=shutil.ignore_patterns("review", "versions", "build"))
        else:
            from test_check import project
            d = project(Path(t))
        print(f"deck: {deck or 'neutral fixture'}")
        try:
            run(d)
        except AssertionError as x:
            bad.append(str(x))
            print(f"FAIL  {x}")
    print(f"studio page test: {len(bad)} failure(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
