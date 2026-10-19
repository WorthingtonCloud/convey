"""Open slides in headless Chrome and measure them with extract.js.

The one browser step shared by `convey lint`, `convey export` and the test bench, so all three
see exactly the same scene for the same slide.

Uses the Chrome or Edge already installed, driven over its own debugging pipe (the DevTools
protocol as null-terminated JSON on two file descriptors). Standard library only: nothing to
install. Set CONVEY_BROWSER to a browser binary to choose one.
"""
from __future__ import annotations

import base64
import fcntl
import json
import os
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

EXTRACT_JS = (Path(__file__).parent / "extract.js").read_text()
W, H = 1280, 720

CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge",
]


def find_browser() -> str:
    env = os.environ.get("CONVEY_BROWSER")
    for c in ([env] if env else []) + CANDIDATES:
        p = c if os.path.isabs(c) else shutil.which(c)
        if p and os.path.exists(p):
            return p
    raise RuntimeError("no Chrome or Edge found; install one or set CONVEY_BROWSER to its binary")


class BrowserError(RuntimeError):
    pass


class Browser:
    """A headless Chrome process and one page, spoken to over --remote-debugging-pipe."""

    def __init__(self, scale: int = 1, timeout: float = 30):
        self.timeout = timeout
        self._id = 0
        self._buf = b""
        self._events: list[dict] = []
        self.profile = tempfile.mkdtemp(prefix="convey-chrome-")
        to_chrome_r, self._w = os.pipe()  # Chrome reads commands on fd 3
        self._r, from_chrome_w = os.pipe()  # and writes replies on fd 4
        # Park both child ends above 10, so moving them onto 3 and 4 can't clobber each other.
        cr, cw = fcntl.fcntl(to_chrome_r, fcntl.F_DUPFD, 10), fcntl.fcntl(from_chrome_w, fcntl.F_DUPFD, 10)
        os.close(to_chrome_r)
        os.close(from_chrome_w)

        def child():
            os.dup2(cr, 3)
            os.dup2(cw, 4)

        self.proc = subprocess.Popen(
            [find_browser(), "--headless", "--remote-debugging-pipe", f"--user-data-dir={self.profile}",
             "--no-first-run", "--no-default-browser-check", "--disable-extensions", "--hide-scrollbars",
             "--mute-audio", "--force-color-profile=srgb", "--font-render-hinting=none", "about:blank"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            pass_fds=(3, 4), preexec_fn=child)
        os.close(cr)
        os.close(cw)
        target = self.call("Target.createTarget", url="about:blank")["targetId"]
        self.session = self.call("Target.attachToTarget", targetId=target, flatten=True)["sessionId"]
        self.send("Page.enable")
        self.send("Runtime.enable")
        self.send("Emulation.setDeviceMetricsOverride", width=W, height=H, deviceScaleFactor=scale, mobile=False)

    # -- protocol --
    def call(self, method: str, session: str | None = None, **params) -> dict:
        self._id += 1
        msg = {"id": self._id, "method": method, "params": params}
        if session:
            msg["sessionId"] = session
        os.write(self._w, json.dumps(msg).encode() + b"\0")
        want = self._id
        while True:
            m = self._read()
            if m.get("id") == want:
                if "error" in m:
                    raise BrowserError(f"{method}: {m['error'].get('message')}")
                return m.get("result", {})
            if "method" in m:
                self._events.append(m)

    def send(self, method: str, **params) -> dict:
        return self.call(method, self.session, **params)

    def _read(self) -> dict:
        deadline = time.time() + self.timeout
        while b"\0" not in self._buf:
            if time.time() > deadline:
                raise BrowserError("the browser stopped answering")
            chunk = os.read(self._r, 1 << 20)
            if not chunk:
                raise BrowserError("the browser closed")
            self._buf += chunk
        raw, self._buf = self._buf.split(b"\0", 1)
        return json.loads(raw)

    def wait_event(self, name: str):
        for i, m in enumerate(self._events):
            if m.get("method") == name:
                return self._events.pop(i)
        while True:
            m = self._read()
            if m.get("method") == name:
                return m
            if "method" in m:
                self._events.append(m)

    # -- page --
    def goto(self, url: str):
        self._events.clear()
        r = self.send("Page.navigate", url=url)
        if r.get("errorText"):
            raise BrowserError(f"can't open {url}: {r['errorText']}")
        self.wait_event("Page.loadEventFired")

    def evaluate(self, expression: str):
        """Run JavaScript in the page and return its (JSON-able) value; promises are awaited."""
        r = self.send("Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in r:
            d = r["exceptionDetails"]
            raise BrowserError(d.get("exception", {}).get("description") or d.get("text"))
        return r["result"].get("value")

    def wait(self, ms: int):
        self.evaluate(f"new Promise(r => setTimeout(r, {int(ms)}))")

    def title(self) -> str:
        return self.evaluate("document.title")

    def screenshot(self, path, clip=None, beyond=False):
        p = {"format": "png"}
        if clip:
            p["clip"] = {**clip, "scale": 1}
        if beyond:  # the clip may run past the window (a long page)
            p["captureBeyondViewport"] = True
        Path(path).write_bytes(base64.b64decode(self.send("Page.captureScreenshot", **p)["data"]))

    def pdf(self, path, width_px: float = W, height_px: float = H):
        """The page as a one-page PDF at the slide's size, with backgrounds, screen styles."""
        self.send("Emulation.setEmulatedMedia", media="screen")
        r = self.send("Page.printToPDF", paperWidth=width_px / 96, paperHeight=height_px / 96, printBackground=True,
                      marginTop=0, marginBottom=0, marginLeft=0, marginRight=0, pageRanges="1",
                      preferCSSPageSize=False)
        Path(path).write_bytes(base64.b64decode(r["data"]))

    def close(self):
        try:
            self.call("Browser.close")
        except Exception:
            pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        for fd in (self._r, self._w):
            try:
                os.close(fd)
            except OSError:
                pass
        shutil.rmtree(self.profile, ignore_errors=True)


@contextmanager
def slide_page(scale: int = 1):
    """A headless Chrome page sized to one slide."""
    br = Browser(scale=scale)
    try:
        yield br
    finally:
        br.close()


def measure_page(page: Browser, path: Path) -> dict:
    """Load one slide, wait for fonts and charts, and return its scene graph."""
    page.goto(Path(path).resolve().as_uri())
    page.evaluate("document.fonts.ready.then(() => true)")
    page.evaluate("window.skaldCharts && window.skaldCharts(), true")
    page.wait(50)
    sc = page.evaluate(EXTRACT_JS)
    if "error" in sc:  # not a slide at all
        sc = {"elements": [], "warnings": [], "errors": [sc["error"]], "width": W, "height": H}
    sc["card"] = Path(path).stem
    return sc


def font_fallbacks(page: Browser) -> list[str]:
    """Text the slide's own font can't draw. The browser borrows another installed font for those characters, and
    PowerPoint picks its own substitute, so the two disagree (Japanese in a Latin-only headline font: the browser drew
    Hiragino Sans, PowerPoint MS Mincho; the export report graded 5 slides red, Oct 18, 2026 stress test). Asks the browser which
    fonts really drew each element; reports the innermost element only."""
    page.send("DOM.enable")
    page.send("CSS.enable")
    tree = page.send("DOM.getDocument", depth=-1)["root"]
    parent, attrs = {}, {}

    def walk(n):
        a = n.get("attributes") or []
        attrs[n["nodeId"]] = dict(zip(a[::2], a[1::2]))
        for c in n.get("children") or []:
            parent[c["nodeId"]] = n["nodeId"]
            walk(c)
    walk(tree)
    found = {}
    for n in page.send("DOM.querySelectorAll", nodeId=tree["nodeId"], selector=".slide *")["nodeIds"]:
        try:
            fonts = page.send("CSS.getPlatformFontsForNode", nodeId=n)["fonts"]
        except BrowserError:
            continue
        if len({f["familyName"] for f in fonts}) < 2:
            continue
        style = page.send("CSS.getComputedStyleForNode", nodeId=n)["computedStyle"]
        fam = next((x["value"] for x in style if x["name"] == "font-family"), "")
        key = fam.split(",")[0].strip().strip("'\"").lower().replace(" ", "")
        other = sorted({f["familyName"] for f in fonts if not f["familyName"].lower().replace(" ", "").startswith(key)})
        if other:
            found[n] = (fam.split(",")[0].strip().strip("'\""), other)
    inner = set(found)
    for n in found:  # a container's fonts include its children's: keep the innermost element
        p_ = parent.get(n)
        while p_ is not None:
            inner.discard(p_)
            p_ = parent.get(p_)
    out = []
    for n in sorted(inner):
        fam, other = found[n]
        name = attrs[n].get("data-id") or attrs[n].get("class") or "text"
        out.append(f"{name}: has characters {fam} doesn't have; the browser draws them in {', '.join(other)}, and "
                   f"PowerPoint would pick its own substitute: use characters {fam} has, or a font both have")
    return out


CHART_JS = Path(__file__).parent / "chart.js"


def fresh_chart_js(folder: Path) -> bool:
    """A deck keeps its own copy of chart.js (compose writes it once). If that copy is older than the skill's,
    the browser draws charts the old way while export builds them the new way: replace it, say so."""
    mine = Path(folder) / "chart.js"
    if mine.exists() and mine.read_bytes() != CHART_JS.read_bytes():
        mine.write_bytes(CHART_JS.read_bytes())
        print(f"note: refreshed {mine} (it was an older copy of the skill's chart.js)")
        return True
    return False


def slide_files(paths) -> list[Path]:
    """Folders expand to their *.html files, sorted by name (the deck order)."""
    out = []
    for p in map(Path, paths):
        if p.is_dir():
            fresh_chart_js(p)
        out += sorted(p.glob("*.html")) if p.is_dir() else [p]
    if out and not Path(paths[0]).is_dir():
        fresh_chart_js(out[0].parent)
    return out


def measure(paths) -> list[dict]:
    files = slide_files(paths)
    with slide_page() as page:
        return [measure_page(page, f) for f in files]
