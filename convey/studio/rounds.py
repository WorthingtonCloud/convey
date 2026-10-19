"""The agent's side of a review: open a round, read what was sent, ask, resolve, wait, restore.

  convey review open DIR               a new round: snapshots storyboard.json and slides/ to versions/vN/, and (from
                                       round 2) measures what changed since the person sent: edits kept, notes
                                       resolved and whether each target really changed, anything changed beyond
                                       what was asked. Refused while a note waits for an answer or the person has
                                       feedback they haven't sent
  convey review show DIR [--json]      what the person sent: typed edits (keep every one) and notes, each with its
                                       slide, object, mark and words. Reading it tells the page the agent has it
  convey review wait DIR [--hours 12] [--replace]
                                       block until the person sends, then print `show`. Run it in the background:
                                       its exit wakes the agent. One watcher per project
  convey review status DIR [--ready]   whose move it is; --ready exits 0 only when the deck is approved and
                                       nothing waits on anyone
  convey review ask DIR NOTE "..."     a question back; the note waits for the answer
  convey review resolve DIR NOTE --said "what changed" [--wontdo] [--removed] [--files ...]
  convey restore vN [DIR]              put version N's storyboard.json and slides/ back (the current ones are kept
                                       in versions/before-restore-<time>/)

Adapted from Video Kit's Review Studio (MIT; its author contributes this adaptation under this skill's MIT-0 license).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

from . import log as L
from . import slidefile as F

# Each named object's box. A text measures its words' own footprint (the box a placeholder gives it stays the same
# size whatever it holds), so "smaller" on a text sees shorter or smaller words.
BOXES_JS = """(() => Object.fromEntries([...document.querySelectorAll('[data-id]')].map(e => {
  const cs = getComputedStyle(e), textOnly = !e.children.length && e.textContent.trim();
  let r = e.getBoundingClientRect();
  if (textOnly) { const g = document.createRange(); g.selectNodeContents(e); r = g.getBoundingClientRect(); }
  return [e.dataset.id, [r.left, r.top, r.width, r.height, cs.display !== 'none' && cs.visibility !== 'hidden' ? 1 : 0]];
})))()"""


# ---------- versions ----------

def copy_deck(d: Path, dest: Path):
    """storyboard.json and slides/ into dest (replacing what was there)."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    if (d / "storyboard.json").exists():
        shutil.copy2(d / "storyboard.json", dest / "storyboard.json")
    if (d / "slides").exists():
        shutil.copytree(d / "slides", dest / "slides")


def versions(d: Path) -> list[int]:
    v = d / "versions"
    return sorted(int(p.name[1:]) for p in v.glob("v*") if p.name[1:].isdigit()) if v.exists() else []


def snapshot_sent(d: Path, rnd: int):
    """What the person handed over at a round's first send: the 'before' the next round's changes are measured
    against. Later sends in the same round keep it (the agent may already have started)."""
    dest = L.paths(d)["sent"]
    mark = dest / "round.txt"
    if mark.exists() and mark.read_text().strip() == str(rnd):
        return
    copy_deck(d, dest)
    mark.write_text(str(rnd))


# ---------- what changed between two copies of the deck ----------

def deck(root: Path) -> dict:
    """slide id -> {file, sigs, outside, fields, text} for one copy of the deck."""
    out = {}
    sb = json.loads((root / "storyboard.json").read_text()) if (root / "storyboard.json").exists() else {"slides": []}
    fields = {s.get("id"): s for s in sb.get("slides", [])}
    for f in sorted((root / "slides").glob("*.html")) if (root / "slides").exists() else []:
        src = f.read_text()
        sid = F.slide_id(src)
        if not sid:
            continue
        out[sid] = {"file": f.name, "sigs": F.signatures(src), "outside": F.outside(src),
                    "values": {k: F.value(src, e) for k, e in F.named(src).items()},
                    "binds": {k: e.bind for k, e in F.named(src).items() if e.bind},
                    "fields": fields.get(sid, {})}
    for sid, s in fields.items():
        out.setdefault(sid, {"file": None, "sigs": {}, "outside": "", "values": {}, "binds": {}, "fields": s})
    return out


def _flat(node, pre=""):
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            out.update(_flat(v, f"{pre}.{k}" if pre else k))
        return out
    if isinstance(node, list) and not all(isinstance(x, str) for x in node):
        out = {}
        for i, v in enumerate(node):
            out.update(_flat(v, f"{pre}.{i}"))
        return out
    return {pre: node}


def changes(before: dict, after: dict) -> list[dict]:
    """Every change from one copy to the other: per named object (its words or its look), outside the named objects,
    in storyboard fields no object shows, and slides added or removed."""
    out = []
    for sid in list(before) + [s for s in after if s not in before]:
        b, a = before.get(sid), after.get(sid)
        if b is None or not b["file"]:
            if a and a["file"]:
                out.append({"slide": sid, "id": None, "what": "slide added"})
            continue
        if a is None or not a["file"]:
            out.append({"slide": sid, "id": None, "what": "slide removed"})
            continue
        for did in list(b["sigs"]) + [x for x in a["sigs"] if x not in b["sigs"]]:
            if did not in a["sigs"]:
                out.append({"slide": sid, "id": did, "what": "removed"})
            elif did not in b["sigs"]:
                out.append({"slide": sid, "id": did, "what": "added"})
            elif b["sigs"][did] != a["sigs"][did]:
                words = b["values"].get(did) != a["values"].get(did)
                out.append({"slide": sid, "id": did, "what": "words" if words else "look",
                            **({"before": b["values"].get(did), "after": a["values"].get(did)} if words else {})})
        if b["outside"] != a["outside"]:
            out.append({"slide": sid, "id": None, "what": "outside the named objects"})
        shown = set(a["binds"].values()) | set(b["binds"].values())
        fb, fa = _flat(b["fields"]), _flat(a["fields"])
        for k in sorted(set(fb) | set(fa)):
            if k in ("status",) or any(k == s or k.startswith(s + ".") for s in shown):
                continue
            if fb.get(k) != fa.get(k):
                out.append({"slide": sid, "id": None, "what": "storyboard", "field": k,
                            "before": fb.get(k), "after": fa.get(k)})
    return out


def boxes(files: list[Path]) -> dict:
    """Each named object's box, measured in the browser: {file: {id: [x, y, w, h, shown]}}."""
    from ..skald.measure import slide_page
    out = {}
    with slide_page() as page:
        for f in files:
            page.goto(f.resolve().as_uri())
            page.evaluate("document.fonts.ready.then(() => true)")
            page.evaluate("window.skaldCharts && window.skaldCharts(), true")
            out[str(f)] = page.evaluate(BOXES_JS)
    return out


def _verdict(n, ch, bx_before, bx_after, gone):
    """One note's measurement: the target, before (as sent) and after (now)."""
    if n["status"] == "wontdo":
        return {"verdict": "wontdo", "detail": "The agent said it won't do this, and why"}
    res = n.get("resolution") or {}
    ask = n.get("ask")
    if n["level"] == "deck":
        return {"verdict": "changed" if ch else "unchanged", "strength": "any",
                "detail": f"{len(ch)} change(s) across the deck" if ch else "nothing in the deck changed"}
    mine = [c for c in ch if c["slide"] == n["slide"]]
    if n["level"] == "slide":
        return {"verdict": "changed" if mine else "unchanged", "strength": "any",
                "detail": f"{len(mine)} change(s) on {n['slide']}" if mine else f"nothing on {n['slide']} changed"}
    tid = n["target"]["id"]
    if gone:
        ok = res.get("removed") or ask == "remove"
        return {"verdict": "removed" if ok else "gone", "strength": "direct",
                "detail": f"{tid} is no longer on the slide" + ("" if ok else ", and the answer didn't say it was removed")}
    on = [c for c in mine if c["id"] == tid]
    b, a = bx_before or [], bx_after or []
    if ask in ("bigger", "smaller", "move") and b and a:
        ab, aa = b[2] * b[3], a[2] * a[3]
        moved = abs(a[0] - b[0]) > 1 or abs(a[1] - b[1]) > 1
        if ask == "move":
            v = "changed" if moved else ("other" if on or abs(aa - ab) > 1 else "unchanged")
        else:
            grew, shrank = aa > ab * 1.02, aa < ab * 0.98
            want = grew if ask == "bigger" else shrank
            v = "changed" if want else "contrary" if (shrank if ask == "bigger" else grew) else "other" if on or moved else "unchanged"
        return {"verdict": v, "strength": "direct",
                "detail": f"box {b[2]:.0f}×{b[3]:.0f} at {b[0]:.0f},{b[1]:.0f} → {a[2]:.0f}×{a[3]:.0f} at {a[0]:.0f},{a[1]:.0f}"}
    if ask == "simpler":
        nb = sum(1 for c in mine if c["what"] == "removed")
        return {"verdict": "changed" if nb or on else "unchanged", "strength": "proxy",
                "detail": "measured by a stand-in: objects removed or the target's words changed"}
    if ask == "remove":
        return {"verdict": "unchanged" if not on else "other", "strength": "direct", "detail": f"{tid} is still there"}
    boxed = bool(b and a and any(abs(x - y) > 1 for x, y in zip(b[:4], a[:4])))
    if on or boxed:
        what = ", ".join(sorted({c["what"] for c in on} | ({"place or size"} if boxed else set())))
        return {"verdict": "changed", "strength": "any", "detail": f"{tid} changed: {what}"}
    return {"verdict": "unchanged", "strength": "any", "detail": f"nothing measurable about {tid} changed"}


def summarize(d: Path, S: dict) -> tuple[dict | None, list[dict]]:
    """The round summary the person sees first, and a note.measured event for each answered note."""
    R = L.current(S)
    if not R:
        return None, []
    sent_root = L.paths(d)["sent"]
    if not (sent_root / "storyboard.json").exists():
        sent_root = d / "versions" / f"v{R['version']}"
    before, after = deck(sent_root), deck(d)
    ch = changes(before, after)
    # the person's edits from that round: are they still there?
    edits = []
    touched = set()
    last = {}
    for x in S["edits"]:  # an object typed twice is one edit: the last words they typed
        if x["round"] == R["n"]:
            last[(x["slide"], x["id"])] = x
    for x in last.values():
        now_v = after.get(x["slide"], {}).get("values", {}).get(x["id"])
        kept = now_v is not None and L._q(now_v if not isinstance(now_v, list) else " / ".join(now_v), 10**6) == \
            L._q(x["new"] if not isinstance(x["new"], list) else " / ".join(x["new"]), 10**6)
        edits.append({"seq": x["seq"], "slide": x["slide"], "id": x["id"], "typed": x["new"], "now": now_v, "kept": kept})
        touched.add((x["slide"], x["id"]))
    # the notes answered since the last round opened (this round's, and older ones reopened or sent late)
    cycle = [n for n in S["notes"].values() if n["status"] != "withdrawn"
             and (n["round"] == R["n"] or (n["status"] in L.ANSWERED and n.get("measured") is None))]
    notes = [n for n in cycle if n["status"] in L.ANSWERED and n.get("measured") is None]
    # measure boxes for object notes, in the copy as sent and now
    need = [n for n in notes if n["level"] == "object" and n["status"] == "resolved"]
    bx, why = {}, None
    if need:
        files = set()
        for n in need:
            for root, dk in ((sent_root, before), (d, after)):
                f = dk.get(n["slide"], {}).get("file")
                if f:
                    files.add(root / "slides" / f)
        try:
            bx = boxes(sorted(files))
        except Exception as x:  # no browser: words and looks are still compared, boxes are not
            why = f"boxes not measured ({x})"
    measured = []
    asked_objects = {(n["slide"], n["target"]["id"]) for n in cycle if n["level"] == "object"}
    asked_slides = {n["slide"] for n in cycle if n["level"] == "slide"}
    deck_notes = [n["id"] for n in cycle if n["level"] == "deck"]
    # a deck-wide note's answer names the files it changed: changes on those slides were asked for
    named = {Path(f).name for n in cycle if n["level"] == "deck" for f in ((n.get("resolution") or {}).get("files") or [])}
    asked_slides |= {sid for sid, x in after.items() if x.get("file") in named}
    out_notes = []
    for n in notes:
        bb = ba = None
        gone = False
        if n["level"] == "object":
            tid = n["target"]["id"]
            fb, fa = before.get(n["slide"], {}).get("file"), after.get(n["slide"], {}).get("file")
            gone = tid not in after.get(n["slide"], {}).get("sigs", {})
            bb = (bx.get(str(sent_root / "slides" / fb)) or {}).get(tid) if fb else None
            ba = (bx.get(str(d / "slides" / fa)) or {}).get(tid) if fa else None
        m = _verdict(n, ch, bb, ba, gone)
        if why and n["level"] == "object" and n.get("ask") in ("bigger", "smaller", "move"):
            m = {"verdict": "unmeasured", "strength": "direct", "detail": why}
        measured.append({"type": "note.measured", "id": n["id"], "measured": m})
        out_notes.append({"id": n["id"], "level": n["level"], "slide": n.get("slide"),
                          "target": (n.get("target") or {}).get("id"), "comment": n.get("comment"), "ask": n.get("ask"),
                          "said": (n.get("resolution") or {}).get("said"), "outcome": n["status"], **m})
    beyond = []
    for c in ch:
        key = (c["slide"], c["id"])
        if c["id"] and key in touched:
            continue  # the person's own edit: reported above, kept or not
        if c["id"] and key in asked_objects or c["slide"] in asked_slides:
            continue
        beyond.append(c)
    summary = {"from_round": R["n"], "from_version": R["version"], "to_version": R["version"] + 1,
               "edits": edits, "notes": out_notes, "beyond": beyond, "deck_notes": deck_notes,
               "changed": len(ch)}
    return summary, measured


# ---------- the commands ----------

def open_round(d: Path, quiet=False) -> dict:
    S = L.state(d, "human")
    R = L.current(S)
    if S["pending"]:
        raise L.Refused(f"the person has {len(S['pending'])} thing(s) in the page they haven't sent: ask them to send it (or undo it) first")
    if R and R["status"] == "open":
        raise L.Refused(f"round {R['n']} is still open: the person hasn't sent it")
    owed = [i for i, n in S["notes"].items() if n["status"] in L.WAITING]
    if owed:
        raise L.Refused(f"answer every note first: {', '.join(owed)} (convey review resolve, or ask)")
    version = (R["version"] + 1) if R else max(versions(d) or [0]) + 1
    summary, measured = summarize(d, L.state(d, "agent")) if R else (None, [])

    def snap(_old, _new):
        copy_deck(d, d / "versions" / f"v{version}")

    S2, _, _ = L.append(d, measured + [{"type": "round.opened", "version": version, "summary": summary}], "agent", effect=snap)
    if not quiet:
        print(f"round {L.current(S2)['n']} open on version {version} (versions/v{version}/)")
        if summary:
            print(describe_summary(summary))
    return S2


def describe_summary(s: dict) -> str:
    lines = []
    for e in s["edits"]:
        lines.append(f"  edit {'kept' if e['kept'] else 'CHANGED BY THE AGENT'}: {e['slide']} {e['id']}"
                     + ("" if e["kept"] else f" (typed “{_txt(e['typed'])}”, now “{_txt(e['now'])}”)"))
    for n in s["notes"]:
        lines.append(f"  {n['id']} {n['outcome']}, measured {n['verdict']}: {n['said']}  [{n.get('detail')}]")
    for c in s["beyond"]:
        lines.append(f"  beyond what was asked: {c['slide']} {c.get('id') or c.get('field') or ''} ({c['what']})")
    if not lines:
        lines.append("  nothing changed since the person sent")
    return "\n".join(lines)


def _txt(v):
    return " / ".join(v) if isinstance(v, list) else str(v)


def show(d: Path, as_json=False):
    S = L.state(d, "agent")
    R = L.current(S)
    if not R:
        print("no round yet: convey review open " + str(d))
        return 1
    edits = [x for x in S["edits"] if x["round"] == R["n"]]
    notes = [n for n in S["notes"].values() if n["status"] in L.WAITING | {"question"}]
    if as_json:
        print(json.dumps({"round": R, "edits": edits, "notes": notes, "approved": S["approved"]}, indent=1, ensure_ascii=False))
    else:
        state = {"open": "open (the person is reviewing)", "sent": "sent", "closed": "closed"}[R["status"]]
        print(f"round {R['n']}, version {R['version']}: {state}")
        if S["approved"] and S["approved"]["round"] == R["n"]:
            print("  ✓ the person APPROVED the deck: export it")
        if R.get("nonotes"):
            print("  the person has nothing to change")
        if edits:
            net = {}
            for x in edits:  # an object typed twice: from what it said first to what they typed last
                k = (x["slide"], x["id"])
                net[k] = {**x, "old": net[k]["old"], "times": net[k]["times"] + 1} if k in net else {**x, "times": 1}
            print(f"\ntyped edits ({len(net)}): already in the slide and the storyboard; keep every one as typed")
            for x in net.values():
                print(f"  {x['slide']} {x['id']}" + (f" [{x['bind']}]" if x["bind"] else " [slide only, not bound]")
                      + f": “{_txt(x['old'])}” → “{_txt(x['new'])}”" + (f"  (typed {x['times']} times)" if x["times"] > 1 else ""))
        if notes:
            print(f"\nnotes to resolve ({len(notes)}):")
            for n in notes:
                where = (f"{n['slide']} › {n['target']['id']}" if n["level"] == "object"
                         else n["slide"] if n["level"] == "slide" else "the whole deck")
                print(f"  {n['id']}  {where}" + (f"  ask: {L.ASKS[n['ask']]}" if n.get("ask") else ""))
                if n["level"] == "object":
                    t = n["target"]
                    print(f"         object: {n.get('file')} [data-id={t['id']}]" + (f" “{L._q(t.get('text'), 70)}”" if t.get("text") else ""))
                if (n.get("mark") or {}).get("type", "none") != "none":
                    print(f"         mark: {describe_mark(n['mark'])}")
                if (n.get("comment") or "").strip():
                    print(f"         “{n['comment'].strip()}”")
                for t in n["thread"]:
                    print(f"         {t['by']} ({t['type']}): {t['text']}")
                if n["status"] == "question":
                    print("         (waiting on the person's answer)")
        if not edits and not notes and not R.get("nonotes") and R["status"] == "open":
            print("  nothing sent yet")
        if not (S["approved"] and S["approved"]["round"] == R["n"]):
            print(f"\nstart the watcher again now, in the background: convey review wait {d}\n"
                  "  the person can still send this round (a late note, an approval); without a watcher the page "
                  "sends them back to the chat to say \"sent\"")
    if R["status"] == "sent" and R["read_sends"] < R["sends"]:
        L.append(d, [{"type": "round.read"}], "agent")
    return 0


def describe_mark(m: dict) -> str:
    pct = lambda v: f"{100 * float(v):.0f}%"
    t = m.get("type")
    if t == "click":
        return f"a click at {pct(m['x'])} across, {pct(m['y'])} down"
    if t == "box":
        return f"a box from {pct(m['x0'])},{pct(m['y0'])} to {pct(m['x1'])},{pct(m['y1'])} of the slide"
    if t == "arrow":
        return f"an arrow from {pct(m['x0'])},{pct(m['y0'])} to {pct(m['x1'])},{pct(m['y1'])} (this, there)"
    return t or "none"


def status(d: Path, ready=False, as_json=False) -> int:
    S = L.state(d, "agent")
    H = L.state(d, "human")
    R = L.current(S)
    owed = [i for i, n in S["notes"].items() if n["status"] in L.WAITING]
    asked = [i for i, n in S["notes"].items() if n["status"] == "question"]
    out = {"turn": S["turn"], "round": R and R["n"], "version": R and R["version"], "owed": owed, "questions": asked,
           "unsent": len(H["pending"]), "unread": bool(R and R["read_sends"] < R["sends"]), "approved": S["approved"],
           "watcher": L.waiting(d)}
    if as_json:
        print(json.dumps(out, indent=1))
    else:
        say = {"agent": "the agent's move", "human": "the person's move (reviewing)", "done": "done: approved"}[S["turn"]]
        print(f"{say}" + (f" · round {out['round']}, version {out['version']}" if R else " · no round yet"))
        if out["unread"]:
            print("  the person sent something you haven't read: convey review show")
        if owed:
            print(f"  notes to resolve: {', '.join(owed)}")
        if asked:
            print(f"  waiting on the person's answer: {', '.join(asked)}")
        if out["unsent"]:
            print(f"  the person has {out['unsent']} thing(s) in the page not sent yet")
        print(f"  watcher: {'running' if out['watcher'] else 'not running (convey review wait, in the background)'}")
    if ready:
        return 0 if S["turn"] == "done" and not H["pending"] else 1
    return 0


def ask(d: Path, note: str, text: str):
    L.append(d, [{"type": "note.question", "id": note, "text": text}], "agent")
    print(f"asked on {note}: the note waits for the person's answer")


def resolve(d: Path, note: str, said: str, wontdo=False, removed=False, files=None):
    e = {"type": "note.resolved", "id": note, "said": said, "files": files or [], "removed": removed or None}
    if wontdo:
        e["outcome"] = "wontdo"
    L.append(d, [e], "agent")
    print(f"{note} {'won’t do' if wontdo else 'resolved'}: the next round measures it")


def wait(d: Path, hours=12.0, replace=False):
    """Block until the person sends, then print what they sent. The signal is positive: a send in the log the agent
    hasn't read (sends > read_sends), checked every 2 s, so a send that landed before the wait started counts at once.
    Exit 0 = sent, 2 = timed out, 3 = another watcher is already listening."""
    import atexit
    import signal
    P = L.paths(d)
    P["dir"].mkdir(parents=True, exist_ok=True)
    if L.waiting(d):  # one watcher per project: a second one would never hear the send the first one reads
        old = json.loads(P["waiting"].read_text())
        if not replace:
            print(f"another `convey review wait` is already watching this project (pid {old['pid']}, since "
                  f"{old.get('since')}): it will read the send. Watch that one, or take over with --replace", file=sys.stderr)
            return 3
        os.kill(int(old["pid"]), signal.SIGTERM)
        for _ in range(50):
            if not L.waiting(d):
                break
            time.sleep(0.1)
        print(f"replaced the watcher that was running (pid {old['pid']})", flush=True)
    P["waiting"].write_text(json.dumps({"pid": os.getpid(), "since": datetime.now().isoformat(timespec="seconds")}))

    def _gone():
        try:
            if json.loads(P["waiting"].read_text()).get("pid") == os.getpid():
                P["waiting"].unlink()
        except (OSError, ValueError):
            pass
    atexit.register(_gone)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    start, beat = time.time(), time.time()
    R = L.current(L.state(d))
    print("waiting for the person to send" + (f" round {R['n']}" if R else " (no round open yet)")
          + f": checking every 2 s, for up to {hours:g} h", flush=True)
    while True:
        R = L.current(L.state(d))
        if R and R["sends"] > R["read_sends"]:
            print(f"sent: round {R['n']}, send {R['sends']}\n", flush=True)
            return show(d)
        if time.time() - start > hours * 3600:
            print("timed out: nothing was sent", flush=True)
            return 2
        if time.time() - beat > 900:
            beat = time.time()
            print(f"still waiting ({int((beat - start) // 60)} min)", flush=True)
        time.sleep(2)


def restore(d: Path, version: str):
    v = version.lstrip("v")
    src = d / "versions" / f"v{v}"
    if not v.isdigit() or not (src / "storyboard.json").exists():
        have = ", ".join(f"v{x}" for x in versions(d)) or "none yet"
        raise L.Refused(f"no version {version} (versions: {have})")
    H = L.state(d, "human")
    if H["pending"]:
        raise L.Refused("the person has edits or notes in the page they haven't sent: they send or undo them first")
    backup = d / "versions" / f"before-restore-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    def put_back(_old, _new):
        copy_deck(d, backup)
        shutil.copy2(src / "storyboard.json", d / "storyboard.json")
        if (d / "slides").exists():
            shutil.rmtree(d / "slides")
        shutil.copytree(src / "slides", d / "slides")

    L.append(d, [{"type": "version.restored", "version": int(v), "backup": backup.name}], "agent", effect=put_back)
    print(f"restored version {v}: storyboard.json and slides/ (what was there is in versions/{backup.name}/)")


def main(args) -> int:
    d = Path(args.project)
    try:
        if args.action == "open":
            open_round(d)
        elif args.action == "show":
            return show(d, args.json)
        elif args.action == "status":
            return status(d, args.ready, args.json)
        elif args.action == "wait":
            return wait(d, args.hours, args.replace)
        elif args.action == "ask":
            ask(d, args.note, args.text)
        elif args.action == "resolve":
            if not args.said:
                raise L.Refused("say what changed, or why not (--said)")
            resolve(d, args.note, args.said, args.wontdo, args.removed, args.files)
    except L.Refused as x:
        print(f"refused: {x}", file=sys.stderr)
        return 1
    return 0


def add_parser(sub):
    p = sub.add_parser("review", help="the agent's side of a studio review: open, show, wait, status, ask, resolve")
    p.add_argument("action", choices=["open", "show", "wait", "status", "ask", "resolve"])
    p.add_argument("project", help="the deck project folder")
    p.add_argument("note", nargs="?", help="ask/resolve: the note's id (n-0001)")
    p.add_argument("text", nargs="?", help="ask: the question")
    p.add_argument("--said", help="resolve: what changed, or why not")
    p.add_argument("--wontdo", action="store_true", help="resolve: not doing it (say why in --said)")
    p.add_argument("--removed", action="store_true", help="resolve: the object is gone on purpose")
    p.add_argument("--files", nargs="*", help="resolve: the files changed")
    p.add_argument("--json", action="store_true")
    p.add_argument("--ready", action="store_true", help="status: exit 0 only when approved and nothing waits")
    p.add_argument("--hours", type=float, default=12.0, help="wait: give up after this long")
    p.add_argument("--replace", action="store_true", help="wait: take over from a watcher already running")
    p.set_defaults(fn=main)
    r = sub.add_parser("restore", help="put a version's storyboard.json and slides/ back")
    r.add_argument("version", help="vN")
    r.add_argument("project", nargs="?", default=".", help="the deck project folder (default: here)")

    def _restore(a):
        try:
            restore(Path(a.project), a.version)
        except L.Refused as x:
            print(f"refused: {x}", file=sys.stderr)
            return 1
        return 0
    r.set_defaults(fn=_restore)
