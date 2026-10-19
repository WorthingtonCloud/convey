"""convey studio DIR: the review page's server, on this machine only.

Adapted from Video Kit's Review Studio server (MIT; its author contributes this adaptation under this skill's MIT-0
license). Three jobs:
  - the page: /studio/ is this package's page/ folder (never copied into a project)
  - the deck's files: slides/, versions/ and the rest of the project folder, read-only
  - the diary's one door for the page: POST /studio/api/events appends the person's events; POST /studio/api/edit
    writes a typed edit into the slide and the storyboard and logs it; GET /studio/api/state is the snapshot plus
    the deck; GET /studio/api/problems is lint and check, run on the files as they are now.
Requests must come from the page itself: the Host is this machine, and a write carries JSON from this origin (a web
page elsewhere in the same browser can't post to it).
"""
from __future__ import annotations

import fcntl
import http.server
import json
import os
import posixpath
import re
import socket
import threading
import urllib.parse
from pathlib import Path

from . import edits as E
from . import log as L
from . import rounds as RD
from . import slidefile as F

PAGE = Path(__file__).parent / "page"


class Problems:
    """Lint (the browser's measurement) and check (the claim ledger), on the files as they are now. Lint keeps one
    headless browser open and re-measures only the slides whose files changed."""

    def __init__(self, d: Path):
        self.d = d
        self.lock = threading.Lock()
        self.page = None
        self.lint_cache: dict[str, tuple] = {}
        self.check_cache = (None, None)

    def _browser(self):
        from ..skald.measure import Browser
        if self.page is None:
            self.page = Browser()
        return self.page

    def lint(self, files: list[Path]) -> dict:
        from ..skald.measure import measure_page, BrowserError
        out = {}
        with self.lock:
            for f in files:
                deps = [f, f.parent / "tokens.css", f.parent / "chart.js"]
                key = tuple(p.stat().st_mtime_ns if p.exists() else 0 for p in deps)
                hit = self.lint_cache.get(f.name)
                if hit and hit[0] == key:
                    out[f.name] = hit[1]
                    continue
                for attempt in (1, 2):
                    try:
                        sc = measure_page(self._browser(), f)
                        break
                    except (BrowserError, OSError) as x:  # a browser that died is started again, once
                        try:
                            self.page and self.page.close()
                        except Exception:
                            pass
                        self.page = None
                        if attempt == 2:
                            sc = {"errors": [], "warnings": [], "unavailable": str(x)}
                r = {"errors": sc.get("errors", []), "warnings": sc.get("warnings", []),
                     **({"unavailable": sc["unavailable"]} if sc.get("unavailable") else {})}
                self.lint_cache[f.name] = (key, r)
                out[f.name] = r
        return out

    def check(self) -> dict:
        from ..check import run
        d = self.d
        watched = [d / "storyboard.json", d / "evidence.json", d / "brief.json", *sorted((d / "slides").glob("*.html")),
                   *(sorted((d / "analysis").glob("*")) if (d / "analysis").exists() else [])]
        key = tuple((str(p), p.stat().st_mtime_ns) for p in watched if p.exists())
        if self.check_cache[0] == key:
            return self.check_cache[1]
        L.paths(d)["dir"].mkdir(parents=True, exist_ok=True)
        with open(L.paths(d)["lock"], "w") as lk:  # never mid-edit: a typed edit writes the slide, then the storyboard
            fcntl.flock(lk, fcntl.LOCK_SH)
            key = tuple((str(p), p.stat().st_mtime_ns) for p in watched if p.exists())
            r = run(d)
        files = {f.name: F.slide_id(f.read_text()) for f in sorted((d / "slides").glob("*.html"))}
        by_id = {v: k for k, v in files.items() if v}
        per, deck = {f: [] for f in files}, []
        for name, probs in r["results"].items():
            for p in dict.fromkeys(probs):  # the same words twice (a number in the title and the headline) once
                head = p.split(":", 1)[0].split(" ")[0]
                f = head if head in files else by_id.get(head)
                (per[f] if f else deck).append({"check": name, "text": p})
        out = {"passed": not any(r["results"].values()), "slides": per, "deck": deck,
               "failed": [k for k, v in r["results"].items() if v], "chain": r["chain"], "notes": r["notes"]}
        self.check_cache = (key, out)
        return out

    def all(self, files=None) -> dict:
        slides = sorted((self.d / "slides").glob("*.html"))
        lint = self.lint([f for f in slides if files is None or f.name in files])
        try:
            check = self.check()
        except Exception as x:  # a broken storyboard is shown, not a crash
            check = {"passed": False, "slides": {}, "deck": [{"check": "check", "text": f"check could not run: {x}"}],
                     "failed": ["check"], "chain": [], "notes": []}
        return {"lint": lint, "check": check}

    def close(self):
        if self.page:
            self.page.close()
            self.page = None


def context(d: Path) -> dict:
    """The deck as the page needs it: each slide's file, id, headline and when it last changed."""
    slides = []
    sb = {}
    try:
        sb = {s.get("id"): s for s in json.loads((d / "storyboard.json").read_text()).get("slides", [])}
    except (OSError, ValueError):
        pass
    for f in sorted((d / "slides").glob("*.html")) if (d / "slides").exists() else []:
        src = f.read_text()
        sid = F.slide_id(src)
        slides.append({"file": f.name, "id": sid, "url": f"/slides/{urllib.parse.quote(f.name)}",
                       "headline": (sb.get(sid) or {}).get("headline"), "mtime": f.stat().st_mtime_ns,
                       "editable": sorted(k for k, e in F.named(src).items() if F.kind(e))})
    title = None
    try:
        title = json.loads((d / "brief.json").read_text()).get("title")
    except (OSError, ValueError):
        pass
    return {"project": d.resolve().name, "title": title, "slides": slides, "waiting": L.waiting(d),
            "versions": RD.versions(d), "asks": L.ASKS}


class Handler(http.server.SimpleHTTPRequestHandler):
    server_version = "convey-studio"
    project: Path = Path(".")
    problems: Problems = None

    def _ours(self, write):
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("localhost", "127.0.0.1"):
            return False  # another name pointing here (DNS rebinding) is refused
        if write:
            origin = self.headers.get("Origin")
            if origin and urllib.parse.urlsplit(origin).hostname not in ("localhost", "127.0.0.1"):
                return False
            if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                return False  # a cross-site form can't send JSON without asking first, and nobody answers
        return True

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        return json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")

    def translate_path(self, path):
        p = urllib.parse.unquote(urllib.parse.urlsplit(path).path)
        root = str(self.project.resolve())
        if p == "/studio" or p.startswith("/studio/"):
            root, p = str(PAGE), p[len("/studio"):]
        parts = [w for w in posixpath.normpath(p).split("/") if w and w not in (".", "..")]
        return os.path.join(root, *parts) + ("/" if p.endswith("/") else "")

    def _snapshot(self, view="human"):
        S = L.state(self.project, view)
        return {"state": S, "context": context(self.project)}

    def do_GET(self):
        if not self._ours(False):
            return self.send_error(403)
        p = urllib.parse.urlsplit(self.path).path
        if p == "/studio/api/state":
            return self._json(200, self._snapshot())
        if p == "/studio/api/problems":
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            files = set(q["file"]) if q.get("file") else None
            return self._json(200, self.problems.all(files))
        if p == "/":
            self.send_response(302)
            self.send_header("Location", "/studio/")
            return self.end_headers()
        return super().do_GET()

    def do_HEAD(self):
        if not self._ours(False):
            return self.send_error(403)
        return super().do_HEAD()

    def do_POST(self):
        if not self._ours(True):
            return self.send_error(403)
        p = urllib.parse.urlsplit(self.path).path
        try:
            body = self._body()
        except ValueError as x:
            return self._json(400, {"error": f"not JSON: {x}"})
        d = self.project
        if p == "/studio/api/events":
            events = body.get("events") or []
            bad = [e.get("type") for e in events if e.get("type") not in L.HUMAN or e.get("type") == "text.edited"]
            if bad:
                return self._json(403, {"error": f"the page can't write {', '.join(map(str, bad))} here"})

            touched = set()

            def effect(old, new):
                evs = old + new
                undo = sorted((e["of"] for e in new if e.get("type") == "undo"), reverse=True)
                for k in undo:  # newest first, so two edits of one object come back in order
                    x = evs[k - 1]
                    if x.get("type") == "text.edited":
                        E.revert(d, x)
                        touched.add(x["file"])
                if any(e.get("type") == "round.sent" for e in new):
                    S = L.fold(evs, "human")
                    RD.snapshot_sent(d, L.current(S)["n"])
            try:
                S, new, first = L.append(d, events, "human", effect=effect)
            except L.Refused as x:
                return self._json(409, {"error": plain(x)})
            for e in new:
                print(f"  {e['type']}" + (" (held)" if e.get("held") else ""), flush=True)
            if any(e["type"] == "round.sent" for e in new):
                print(f"round {L.current(S)['n']} sent: convey review show {d}", flush=True)
            return self._json(200, {"ok": True, **self._snapshot(), "seqs": list(range(first, first + len(new))),
                                    "touched": sorted(touched)})
        if p == "/studio/api/edit":
            try:
                ev = E.prepare(d, body.get("file", ""), body.get("id", ""), body.get("text"), body.get("seen"))
                S, new, first = L.append(d, [ev], "human", effect=lambda old, new: E.apply(d, new[0]))
            except L.Refused as x:
                return self._json(409, {"error": plain(x)})
            print(f"  text.edited (held) {ev['slide']} {ev['id']}", flush=True)
            return self._json(200, {"ok": True, **self._snapshot(), "seqs": [first], "touched": [ev["file"]]})
        return self.send_error(404)

    def end_headers(self):  # never cache: the page re-reads the state and the slides after every change
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *a):
        pass

    def handle(self):
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            pass


def plain(x) -> str:
    """A refusal as the person reads it: the rule's sentence, without the event type in front."""
    return re.sub(r"^(?:event \d+ \()?[a-z]+\.[a-z]+\)?: ", "", str(x))


def free_port(port):
    for p in range(port, port + 20):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)):
                return p
    raise SystemExit(f"ports {port}-{port + 19} are all in use: convey studio DIR --port <another>")


def make_server(d: Path, port: int = 4560):
    d = Path(d).resolve()
    if not (d / "slides").exists():
        raise SystemExit(f"{d} has no slides/ yet: compose the deck first (convey compose {d})")
    probs = Problems(d)
    try:  # start the measuring browser here, on the main thread: starting a process from a request thread can hang
        probs._browser()
    except Exception as x:
        print(f"(lint unavailable: {x}; check still runs)", flush=True)
    handler = type("StudioHandler", (Handler,), {"project": d, "problems": probs})
    p = free_port(port)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", p), handler)
    srv.daemon_threads = True
    return srv, p, probs


def serve(d: Path, port: int = 4560, open_browser: bool = True):
    d = Path(d).resolve()
    S = L.state(d)
    if not S["rounds"]:  # a deck that was never reviewed: its first round opens on what's there now
        RD.open_round(d)
    srv, p, probs = make_server(d, port)
    url = f"http://localhost:{p}/studio/"
    print(f"{url}  (serving {d}; Ctrl-C to stop)", flush=True)
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        probs.close()


def add_parser(sub):
    p = sub.add_parser("studio", help="open a deck project in the browser for review")
    p.add_argument("project", help="the deck project folder")
    p.add_argument("--port", type=int, default=4560)
    p.add_argument("--no-open", action="store_true", help="don't open a browser tab (print the address only)")
    p.set_defaults(fn=lambda a: serve(Path(a.project), a.port, not a.no_open) or 0)
