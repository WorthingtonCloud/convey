"""The studio's diary: review/log.jsonl, every event appended and never edited, folded into review/state.json.

Adapted from Video Kit's Review Studio (engine/py/review.py, MIT; its author contributes this adaptation under this
skill's MIT-0 license). Kept whole: the append-only log, the fold, held feedback with Undo, rounds and turns, one
writer at a time. New: text edits (applied to the files at once, undoable until Send) and versions.

Who writes what. The page writes the person's events; the agent's commands write the agent's. The person's feedback
is held: it waits in the page, undoable, until a round.sent after it covers it. state.json (what the agent reads)
holds only what was sent; the page also sees what is held.

A note's life: draft (in an open round) -> sent -> question <-> (answered: sent) -> resolved | wontdo -> accepted |
reopened. A text edit's life: applied to the slide and the storyboard at once, held (Undo puts the old words back),
then sent with the round, after which the agent must keep it.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
from datetime import datetime
from pathlib import Path

HELD = {"note.added", "note.edited", "note.withdrawn", "note.answered", "note.accepted", "note.reopened",
        "text.edited", "deck.approved", "round.nonotes"}
HUMAN = HELD | {"round.sent", "undo"}
AGENT = {"round.opened", "round.read", "note.question", "note.resolved", "note.measured", "version.restored",
         "step.logged"}
LEVELS = {"object", "slide", "deck"}  # what a note is about: one object on a slide, a whole slide, the whole deck
MARKS = {"none", "click", "box", "arrow"}
ASKS = {"move": "move it", "bigger": "bigger", "smaller": "smaller", "simpler": "less busy", "remove": "remove it"}
WAITING = {"sent", "reopened"}  # the agent owes these an answer before the next round opens
ANSWERED = {"resolved", "wontdo"}  # waiting on the person: Looks right, or Still wrong


class Refused(Exception):
    """A write the rules don't allow, in a sentence a person can act on. seq: the event that broke a rule."""

    def __init__(self, msg, seq=None):
        super().__init__(msg)
        self.seq = seq


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def paths(d: Path) -> dict[str, Path]:
    r = Path(d) / "review"
    return {"dir": r, "log": r / "log.jsonl", "state": r / "state.json", "lock": r / ".lock",
            "waiting": r / "waiting.json", "sent": r / "sent"}


# ---------- the fold: every rule lives here, so a write that breaks one is never appended ----------

def empty():
    return {"review": 1, "events": 0, "round": None, "rounds": [], "notes": {}, "edits": [], "approved": None,
            "restored": [], "steps": [], "pending": []}


def current(S):
    return S["rounds"][-1] if S["rounds"] else None


def fold(events, view="agent"):
    """The log, folded. view="agent": a held event counts only once a round.sent after it covers it (state.json).
    view="human": the page's picture, held events included and listed in "pending" by their line (for Undo).
    An undone event never happened."""
    undone = {e.get("of") for e in events if e.get("type") == "undo"}
    last_send = max((i for i, e in enumerate(events) if e.get("type") == "round.sent"), default=-1)
    S = empty()
    S["_since"] = 0
    for i, e in enumerate(events):
        seq = i + 1
        if e.get("type") == "undo" or seq in undone:
            continue
        pending = bool(e.get("held")) and i > last_send
        if pending and view == "agent":
            continue
        try:
            apply(S, e, seq)
        except Refused as x:
            raise Refused(f"event {seq} ({e.get('type')}): {x}", seq)
        if e.get("held"):
            S["_since"] += 1
        S["steps"].append(step(S, e, seq, pending))
        if pending:
            S["pending"].append(seq)
    del S["_since"]
    S["events"] = len(events)
    S["turn"] = turn(S)
    return S


def turn(S) -> str:
    """Whose move it is: agent (no round, or the round is sent), human (a round is open), done (the deck is
    approved, sent, read, and nothing waits on anyone)."""
    R = current(S)
    if not R:
        return "agent"
    if R["status"] == "open":
        return "human"
    owed = [n for n in S["notes"].values() if n["status"] in WAITING | {"question"}]
    if S.get("approved") and S["approved"].get("round") == R["n"] and not owed and R["read_sends"] >= R["sends"]:
        return "done"
    return "agent"


def _note(S, e):
    n = S["notes"].get(e.get("id"))
    if not n:
        raise Refused(f"no note {e.get('id')!r}")
    return n


def _need(n, states, doing):
    if n["status"] not in states:
        raise Refused(f"{n['id']} is {n['status']}: it can't be {doing} (only when {' or '.join(sorted(states))})")


def apply(S, e, seq=None):
    t, at, by = e.get("type"), e.get("at"), e.get("by")
    if t not in HUMAN | AGENT:
        raise Refused(f"unknown event type {t!r}")
    if by not in ("human", "agent") or (t in HUMAN) != (by == "human"):
        raise Refused(f"{t} is written by the {'person' if t in HUMAN else 'agent'}, not {by!r}")
    R = current(S)
    thread = lambda n, text, kind: n["thread"].append({"by": by, "type": kind, "text": text, "at": at})

    if t == "round.opened":
        if R and R["status"] == "open":
            raise Refused(f"round {R['n']} is still open: the person hasn't sent it")
        owed = [i for i, n in S["notes"].items() if n["status"] in WAITING]
        if owed:
            raise Refused(f"answer every note first: {', '.join(owed)} (convey review resolve, or ask)")
        if not e.get("version"):
            raise Refused("a round needs its version")
        if R:
            R["status"] = "closed"
            for n in S["notes"].values():  # an answer they had in front of them through a whole sent round lapses
                if n["status"] in ANSWERED and n.get("shown_in") == R["n"]:
                    n["lapsed"] = R["n"]
        S["rounds"].append({"n": len(S["rounds"]) + 1, "version": e["version"], "status": "open", "opened": at,
                            "sent": None, "notes": [], "edits": [], "sends": 0, "read": None, "read_sends": 0,
                            "summary": e.get("summary")})
    elif t == "round.sent":
        if not R or R["status"] == "closed":
            raise Refused("there's no open round to send")
        if R["status"] == "sent" and not S["_since"]:
            raise Refused(f"round {R['n']} is sent, and nothing new has been added since")
        R.update(status="sent", sent=R["sent"] or at, sends=R["sends"] + 1)
        S["_since"] = 0
        for n in S["notes"].values():
            if n["status"] in ANSWERED and not n.get("lapsed"):
                n["shown_in"] = R["n"]
        for i in R["notes"]:
            if S["notes"][i]["status"] == "draft":
                S["notes"][i]["status"] = "sent"
        for x in S["edits"]:
            if x["round"] == R["n"]:
                x["sent"] = True
    elif t == "round.read":
        if R:
            R.update(read=at, read_sends=R["sends"])
    elif t == "round.nonotes":
        if not R or R["status"] == "closed":
            raise Refused("no round is open")
        R["nonotes"] = at
    elif t == "text.edited":
        if not R or R["status"] != "open":
            raise Refused("it's the agent's turn: typed edits wait for the next round" if R else "no round is open")
        for k in ("slide", "file", "id"):
            if not e.get(k):
                raise Refused(f"a text edit needs its {k}")
        if e.get("old") == e.get("new"):
            raise Refused("nothing changed")
        S["edits"].append({"seq": seq, "round": R["n"], "slide": e["slide"], "file": e["file"], "id": e["id"],
                           "bind": e.get("bind"), "old": e.get("old"), "new": e.get("new"), "at": at, "sent": False})
        R["edits"].append(seq)
    elif t == "note.added":
        if not R or R["status"] == "closed":
            raise Refused("no round is open: the agent opens one (convey review open)")
        n = dict(e.get("note") or {})
        if not n.get("id"):
            raise Refused("a note needs an id")
        if n["id"] in S["notes"]:
            raise Refused(f"{n['id']} exists")
        level = n.get("level") or ("object" if (n.get("target") or {}).get("id") else "slide" if n.get("slide") else "deck")
        if level not in LEVELS:
            raise Refused(f"a note is about an object, a slide or the deck, not {level!r}")
        if level == "object" and not (n.get("target") or {}).get("id"):
            raise Refused("a note on an object needs the object (its data-id)")
        if level in ("object", "slide") and not n.get("slide"):
            raise Refused(f"a note on {'an object' if level == 'object' else 'a slide'} needs its slide")
        m = n.get("mark") or {"type": "none"}
        if m.get("type") not in MARKS:
            raise Refused(f"mark {m.get('type')!r} isn't one of: {', '.join(sorted(MARKS))}")
        if n.get("ask") is not None and n["ask"] not in ASKS:
            raise Refused(f"ask {n['ask']!r} isn't one of: {', '.join(ASKS)}")
        if not (n.get("comment") or "").strip() and not n.get("ask"):
            raise Refused("say what should change, or pick an ask")
        late = R["status"] == "sent"
        n.update({"level": level, "round": R["n"], "version": R["version"], "mark": m,
                  "status": "sent" if late and not e.get("held") else "draft", "late": late, "added": at,
                  "thread": [], "resolution": None, "measured": None})
        S["notes"][n["id"]] = n
        R["notes"].append(n["id"])
    elif t == "note.edited":
        n = _note(S, e)
        _need(n, {"draft"}, "edited")
        if e.get("ask") is not None and e["ask"] not in ASKS:
            raise Refused("an ask that isn't on the list")
        for k in ("comment", "ask", "mark"):
            if k in e:
                n[k] = e[k]
    elif t == "note.withdrawn":
        n = _note(S, e)
        _need(n, {"draft"}, "withdrawn")
        n["status"] = "withdrawn"
    elif t == "note.question":
        n = _note(S, e)
        _need(n, WAITING, "asked about")
        n["status"] = "question"
        thread(n, e.get("text", ""), "question")
    elif t == "note.answered":
        n = _note(S, e)
        _need(n, {"question"}, "answered")
        n["status"] = "sent"
        thread(n, e.get("text", ""), "answer")
    elif t == "note.resolved":
        n = _note(S, e)
        _need(n, WAITING | {"question"}, "resolved")
        if not (e.get("said") or "").strip():
            raise Refused("say what changed, or why not (--said)")
        n["status"] = "wontdo" if e.get("outcome") == "wontdo" else "resolved"
        n["resolution"] = {k: e.get(k) for k in ("outcome", "said", "files", "removed", "renamed")}
        n["resolution"]["at"] = at
        n["measured"] = None
        thread(n, e["said"], n["status"])
    elif t == "note.measured":
        _note(S, e)["measured"] = e.get("measured")
    elif t == "note.accepted":
        n = _note(S, e)
        _need(n, ANSWERED, "accepted")
        n["status"] = "accepted"
        n["accepted"] = {"at": at, "verdict": (n.get("measured") or {}).get("verdict")}
    elif t == "note.reopened":
        n = _note(S, e)
        _need(n, ANSWERED, "reopened")
        n["status"] = "reopened"
        thread(n, e.get("text", ""), "reopened")
    elif t == "deck.approved":
        if not R or R["status"] == "closed":
            raise Refused("no round is open")
        S["approved"] = {"version": R["version"], "round": R["n"], "at": at}
    elif t == "version.restored":
        if not e.get("version"):
            raise Refused("which version?")
        S["restored"].append({"version": e["version"], "at": at, "backup": e.get("backup")})
    elif t == "step.logged":
        if not (e.get("text") or "").strip():
            raise Refused("a step needs its words")
    S["round"] = current(S) and current(S)["n"]


def _q(x, n=60):
    x = " ".join(str(x or "").split())
    return x if len(x) <= n else x[: n - 1].rstrip() + "…"


def step(S, e, seq, pending) -> dict:
    """One event in plain words: the page's Review list (the pending ones) and its history."""
    t, R = e["type"], current(S)
    if t == "round.opened":
        text = f"Round {R['n']} opened on version {R['version']}"
    elif t == "round.sent":
        text = f"Round {R['n']} sent to the agent"
    elif t == "round.read":
        text = "The agent read what you sent"
    elif t == "round.nonotes":
        text = "Nothing to change on this round"
    elif t == "text.edited":
        text = f"Typed on {e['slide']}, {e['id']}: “{_q(e.get('new') if not isinstance(e.get('new'), list) else ' / '.join(e['new']), 70)}”"
    elif t == "note.added":
        n = S["notes"][e["note"]["id"]]
        where = {"object": f"{n.get('slide')}, {(n.get('target') or {}).get('id')}", "slide": n.get("slide"),
                 "deck": "the deck"}[n["level"]]
        words = ASKS[n["ask"]].capitalize() if n.get("ask") else ""
        if (n.get("comment") or "").strip():
            words = (words + ": " if words else "") + f"“{_q(n['comment'])}”"
        text = f"Note on {where}: {words}"
    elif t == "note.edited":
        text = f"Changed note {e['id']}"
    elif t == "note.withdrawn":
        text = f"Withdrew note {e['id']}"
    elif t == "note.question":
        text = f"The agent asked about {e['id']}: “{_q(e.get('text'))}”"
    elif t == "note.answered":
        text = f"Answered the agent on {e['id']}: “{_q(e.get('text'))}”"
    elif t == "note.resolved":
        text = f"The agent {'won’t do' if e.get('outcome') == 'wontdo' else 'answered'} {e['id']}: {_q(e.get('said'))}"
    elif t == "note.accepted":
        text = f"Looks right: {e['id']}"
    elif t == "note.reopened":
        text = f"Still wrong: {e['id']}" + (f", “{_q(e.get('text'))}”" if e.get("text") else "")
    elif t == "deck.approved":
        text = f"Approved the deck (version {R['version']})"
    elif t == "version.restored":
        text = f"The agent restored version {e['version']}"
    elif t == "step.logged":
        text = e.get("text", "")
    else:
        text = t
    note = (e.get("note") or {}).get("id") if t == "note.added" else e.get("id") if t.startswith("note.") else None
    return {"seq": seq, "kind": t, "text": text, "by": e.get("by"), "at": e.get("at"), "pending": pending,
            "round": R and R["n"], **({"note": note} if note else {})}


# ---------- reading and appending, through one lock ----------

def read_log(d: Path) -> list[dict]:
    p = paths(d)["log"]
    if not p.exists():
        return []
    out = []
    for i, line in enumerate(p.read_text().splitlines(), 1):
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                raise SystemExit(f"{p} line {i} isn't JSON (was it edited by hand?): fix that line, the rest is fine")
    return out


def state(d: Path, view="agent"):
    return fold(read_log(d), view)


def _next_id(prefix, pool):
    k = 1 + max([int(x.split("-")[1]) for x in pool if re.fullmatch(rf"{prefix}-\d+", x or "")] or [0])
    return f"{prefix}-{k:04d}"


def undoable(events, k):
    """Undo is for the person's held feedback that hasn't been sent: once sent, the agent may have acted on it."""
    if not isinstance(k, int) or not 1 <= k <= len(events):
        raise Refused("undo: which event? (its line in the log)")
    x = events[k - 1]
    if x.get("by") != "human" or not x.get("held") or x.get("type") not in HELD:
        raise Refused(f"undo: {x.get('type')} can't be undone")
    if any(y.get("type") == "undo" and y.get("of") == k for y in events):
        raise Refused("undo: that's already undone")
    if any(y.get("type") == "round.sent" for y in events[k:]):
        raise Refused("undo: that was already sent, and the agent may have acted on it: add a note or type it again")
    return x


def _cascade(old, new):
    """An undo takes along the held, unsent events that need what it undoes (an edit of an undone note)."""
    if not any(e.get("type") == "undo" for e in new):
        return new
    for _ in range(200):
        try:
            fold(old + new, "human")
            return new
        except Refused as x:
            evs, j = old + new, x.seq
            ok = j and evs[j - 1].get("held") and evs[j - 1].get("by") == "human" and \
                not any(y.get("type") == "round.sent" for y in evs[j:])
            if not ok:
                raise
            new = new + [{"type": "undo", "of": j, "cascade": True, "at": now(), "by": "human"}]
    raise Refused("undo: too much depends on it")


def append(d: Path, events, by, effect=None):
    """Append events as `by`, fold, write state.json. All or nothing: if any event breaks a rule, nothing is written
    and Refused says why. effect(old_events, new_events) runs inside the lock after the rules pass and before the log
    is written (a text edit's file change, an undo putting the old words back); if it raises, nothing is written.
    -> (the writer's view of the state, the events as written, the first new event's line)."""
    P = paths(d)
    P["dir"].mkdir(parents=True, exist_ok=True)
    with open(P["lock"], "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        old = read_log(d)
        S0 = fold(old, "human")
        new = []
        for e in events:
            e = {**e, "at": now(), "by": by}
            t = e.get("type")
            if t == "note.added":  # an id is never reused, an undone note's included
                used = {(x.get("note") or {}).get("id") for x in old + new if x.get("type") == "note.added"}
                e["note"] = {**(e.get("note") or {}), "id": _next_id("n", used)}
            elif t == "undo":
                undoable(old + new, e.get("of"))
            elif t == "round.opened" and S0["pending"]:
                k = len(S0["pending"])
                raise Refused(f"the person has {k} thing{'s' if k > 1 else ''} in the page they haven't sent: "
                              "ask them to send it (or undo it) first")
            if e.get("held") and (by != "human" or t not in HELD):
                raise Refused(f"{t}: only the person's feedback can wait to be sent")
            new.append(e)
        new = _cascade(old, new)
        try:
            H, S = fold(old + new, "human"), fold(old + new, "agent")
        except Refused as x:
            if x.seq and x.seq > len(old):
                raise Refused(f"{(old + new)[x.seq - 1].get('type')}: {str(x).split(': ', 1)[-1]}")
            raise
        if effect:
            effect(old, new)
        with open(P["log"], "a") as f:
            for e in new:
                f.write(json.dumps(e, separators=(",", ":"), ensure_ascii=False) + "\n")
        tmp = P["state"].with_suffix(".tmp")
        tmp.write_text(json.dumps(S, indent=1, ensure_ascii=False))
        os.replace(tmp, P["state"])
    return (H if by == "human" else S), new, len(old) + 1


def waiting(d: Path) -> bool:
    """True while a `convey review wait` is alive (its pid answers): the page then says the agent picks a send up."""
    try:
        w = json.loads(paths(d)["waiting"].read_text())
        os.kill(int(w["pid"]), 0)
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False
