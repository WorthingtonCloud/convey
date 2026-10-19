// The review studio's page. Adapted from Video Kit's Review Studio (MIT; its author contributes this adaptation under
// MIT-0). The page reads the snapshot (the log folded, through the server) and writes only the person's events: notes,
// typed edits, answers, Send. The agent's answers arrive in the same snapshot, so the page polls it.
//
// A typed edit is applied at once (the server writes the slide and the storyboard, then lint and check run); a note is
// work for the agent. Both wait in the page, held, with Undo, until Send. The person types only on their turn.
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const W = 1280, H = 720;
const app = {
  state: null, ctx: null, probs: null, idx: 0, sel: null, editing: null, tool: null, lastSent: 0,
  draft: { level: "slide", ask: null, mark: null },
};
window.studio = app; // for the browser test: it reads what the page holds, never writes through it
window.__errors = [];
addEventListener("error", (e) => window.__errors.push(String(e.message)));
addEventListener("unhandledrejection", (e) => e.reason?.refused || window.__errors.push(String(e.reason?.message || e.reason)));

// ---------- the server ----------
async function api(path, body) {
  const r = await fetch(`api/${path}`, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : { cache: "no-store" });
  const j = await r.json().catch(() => ({ error: `HTTP ${r.status}` }));
  if (!r.ok) {
    toast(j.error || `HTTP ${r.status}`, true);
    const e = new Error(j.error);
    e.refused = true;
    throw e;
  }
  return j;
}
const HELD = new Set(["note.added", "note.edited", "note.withdrawn", "note.answered", "note.accepted", "note.reopened", "deck.approved", "round.nonotes"]);
const round = () => app.state?.rounds.at(-1) || null;
const open = () => round() && round().status !== "closed";
const myTurn = () => app.state?.turn === "human";
async function post(events, { quiet = false } = {}) {
  const evs = events.map((e) => (open() && HELD.has(e.type) ? { ...e, held: true } : e));
  const j = await api("events", { events: evs });
  take(j);
  if (j.touched?.length) refreshProblems(j.touched);
  const seqs = (j.seqs || []).filter((q, i) => evs[i]?.held);
  if (seqs.length && !quiet) {
    const words = app.state.steps.filter((s) => seqs.includes(s.seq)).map((s) => s.text);
    toast(`${words.join(" · ")} · waits for your send`, false, () => undo(seqs));
  }
  return j;
}
async function undo(seqs) {
  const live = new Set(app.state?.pending || []),
    of = seqs.filter((q) => live.has(q));
  if (!of.length) return toast("Nothing to undo: it was already sent or undone.");
  await post(of.map((q) => ({ type: "undo", of: q })), { quiet: true });
  toast("Undone.");
}
async function load() {
  take(await api("state"));
}
function take(j) {
  const before = app.state?.events,
    ctxKey = JSON.stringify(app.ctx?.slides?.map((s) => [s.file, s.mtime]) || []) + app.ctx?.waiting,
    newKey = JSON.stringify(j.context.slides.map((s) => [s.file, s.mtime])) + j.context.waiting;
  app.state = j.state;
  const slidesChanged = ctxKey !== newKey;
  app.ctx = j.context;
  if (app.idx >= app.ctx.slides.length) app.idx = Math.max(0, app.ctx.slides.length - 1);
  if (before !== app.state.events || slidesChanged) render();
  if (slidesChanged && app.probs) refreshProblems();
}
let probAsk = 0;
async function refreshProblems(files) {
  try {
    const q = files ? "?" + files.map((f) => `file=${encodeURIComponent(f)}`).join("&") : "",
      mine = ++probAsk;
    const p = await api(`problems${q}`);
    if (mine !== probAsk) return; // a later ask is on its way: this answer may be about older files
    app.probs = { lint: { ...(app.probs?.lint || {}), ...p.lint }, check: p.check };
    renderProblems();
  } catch {}
}

// ---------- the frame ----------
const slide = () => app.ctx?.slides[app.idx];
const frame = $("#slide");
function render() {
  const R = round(),
    C = app.ctx;
  $("#proj").textContent = C.title || C.project;
  document.title = `${C.title || C.project} · Deck review`;
  $("#round").textContent = R ? `Round ${R.n} · version ${R.version}` : "no round open";
  renderTurn();
  renderThumbs();
  showSlide();
  renderNotebar();
  renderDrawer();
  drawOverlay();
}
function renderTurn() {
  const R = round(),
    t = app.state.turn;
  let cls = t,
    words;
  if (!R) words = "Waiting for the agent to open the first round";
  else if (t === "human") words = "Your turn: click any text to fix it, leave notes, then send";
  else if (t === "done") words = "Approved. The agent exports the deck";
  else if (R.status === "sent" && R.read_sends < R.sends)
    words = app.ctx.waiting ? "Sent. The agent is watching and picks it up now" : "Sent. The agent isn't watching right now: tell it “sent” in chat";
  else words = "The agent is revising. You'll see a new round when it's ready";
  $("#turn").innerHTML = `<span class="pill ${cls}"><span class="dot"></span>${esc(words)}</span>`;
}

// thumbnails down the left: one small live copy of each slide
function renderThumbs() {
  const nav = $("#thumbs"),
    have = [...nav.children].map((b) => b.dataset.file).join("|"),
    want = app.ctx.slides.map((s) => s.file).join("|");
  if (have !== want) {
    nav.innerHTML = app.ctx.slides
      .map((s, i) => `<button class="thumb" data-i="${i}" data-file="${esc(s.file)}" title="${esc(s.headline || s.file)}"><div class="frame"><iframe tabindex="-1" loading="lazy" title="Slide ${i + 1}"></iframe></div><div class="n"><span>${i + 1}</span><span class="b"></span></div></button>`)
      .join("");
  }
  [...nav.children].forEach((b, i) => {
    const s = app.ctx.slides[i],
      f = b.querySelector("iframe"),
      src = `${s.url}?v=${s.mtime}`;
    if (f.dataset.src !== src) {
      f.dataset.src = src;
      f.src = src;
    }
    b.classList.toggle("on", i === app.idx);
  });
  // The current thumbnail stays in view as the arrow keys move through the deck (Oct 18, 2026).
  nav.children[app.idx]?.scrollIntoView({ block: "nearest" });
  renderBadges();
}
$("#thumbs").addEventListener("click", (e) => {
  const b = e.target.closest(".thumb");
  if (b) go(+b.dataset.i);
});
function problemsFor(file) {
  const L = app.probs?.lint?.[file]?.errors || [],
    C = app.probs?.check?.slides?.[file] || [];
  return [...L.map((t) => ({ kind: "lint", text: t })), ...C.map((c) => ({ kind: "check", text: c.text, check: c.check }))];
}
function renderBadges() {
  [...$("#thumbs").children].forEach((b, i) => {
    const s = app.ctx.slides[i],
      bad = problemsFor(s.file).length,
      notes = liveNotes().filter((n) => n.slide === s.id && ["draft", "sent", "reopened", "question"].includes(n.status)).length;
    b.querySelector(".b").innerHTML =
      (bad ? `<span class="badge bad" title="${bad} problem(s) on this slide">${bad}</span>` : "") +
      (notes ? `<span class="badge note" title="${notes} open note(s)">${notes} note${notes > 1 ? "s" : ""}</span>` : "");
  });
}

// the slide in the middle, at the biggest size the room allows (marks are kept in slide pixels, so it never stretches)
function fit() {
  const st = $("#stage"),
    full = document.fullscreenElement === st,
    room = $("#room"),
    cs = getComputedStyle(room);
  const w = full ? window.innerWidth : room.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight),
    h = full ? window.innerHeight : room.clientHeight - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom),
    k = Math.max(0.05, Math.min(w / W, h / H));
  st.style.width = `${Math.floor(W * k)}px`;
  st.style.height = `${Math.floor(H * k)}px`;
  if (full) {
    st.style.width = "100vw";
    st.style.height = "100vh";
  }
  const ox = full ? (window.innerWidth - W * k) / 2 : 0,
    oy = full ? (window.innerHeight - H * k) / 2 : 0;
  frame.style.transform = `translate(${ox}px, ${oy}px) scale(${k})`;
  const ov = $("#overlay");
  ov.style.left = `${ox}px`;
  ov.style.top = `${oy}px`;
  ov.style.width = `${W * k}px`;
  ov.style.height = `${H * k}px`;
  app.scale = k;
}
new ResizeObserver(fit).observe($("#room"));
document.addEventListener("fullscreenchange", () => requestAnimationFrame(fit));

function showSlide() {
  const s = slide();
  if (!s) return;
  const src = `${s.url}?v=${s.mtime}`;
  if (frame.dataset.src === src) return;
  if (app.editing) return; // never pull the text out from under the person's cursor: it reloads after the edit
  frame.dataset.src = src;
  frame.src = src;
}
frame.addEventListener("load", () => {
  const doc = frame.contentDocument;
  if (!doc) return;
  const st = doc.createElement("style");
  st.setAttribute("data-studio", "");
  st.textContent = `[data-id]{cursor:pointer}
[data-studio-sel]{outline:3px solid rgba(79,140,255,.95)!important;outline-offset:3px}
[data-studio-edit]{outline:3px solid #f2b233!important;outline-offset:3px;cursor:text}
[data-studio-bad]{box-shadow:0 0 0 3px #ff6461!important}`;
  doc.head.appendChild(st);
  doc.addEventListener("click", onSlideClick, true);
  doc.addEventListener("keydown", onKey);
  if (app.sel) {
    const el = doc.querySelector(`[data-id="${CSS.escape(app.sel.id)}"]`);
    if (el) el.setAttribute("data-studio-sel", "");
    else app.sel = null;
  }
  markBad();
  fit();
  frame.dataset.ready = frame.dataset.src;
});
function go(i) {
  if (app.editing) app.editing.blur();
  const n = app.ctx.slides.length;
  if (!n) return;
  const j = Math.max(0, Math.min(n - 1, i));
  if (j === app.idx) return;
  app.idx = j;
  app.sel = null;
  app.draft = { level: "slide", ask: null, mark: null };
  try {
    history.replaceState(null, "", `#${j + 1}`);
  } catch {}
  render();
}

// ---------- pointing and typing on the slide ----------
function boxOf(el) {
  const r = el.getBoundingClientRect();
  return [r.left / W, r.top / H, r.right / W, r.bottom / H].map((v) => +v.toFixed(4));
}
function textOf(el) {
  return el.tagName === "UL" || el.tagName === "OL"
    ? [...el.querySelectorAll("li")].map((li) => li.innerText.replace(/\s+/g, " ").trim()).filter(Boolean)
    : el.innerText.replace(/\s+/g, " ").trim();
}
function select(el, ev) {
  const doc = frame.contentDocument;
  doc.querySelectorAll("[data-studio-sel]").forEach((x) => x.removeAttribute("data-studio-sel"));
  if (!el) {
    app.sel = null;
    if (app.draft.level === "object") app.draft.level = "slide";
    app.draft.mark = app.draft.mark?.type === "click" ? null : app.draft.mark;
  } else {
    el.setAttribute("data-studio-sel", "");
    const t = textOf(el);
    app.sel = { id: el.dataset.id, bind: el.dataset.bind || null, box: boxOf(el), text: Array.isArray(t) ? t.join(" / ") : t };
    app.draft.level = "object";
    if (ev) app.draft.mark = { type: "click", x: +(ev.clientX / W).toFixed(4), y: +(ev.clientY / H).toFixed(4) };
  }
  renderNotebar();
  drawOverlay();
}
function onSlideClick(ev) {
  if (app.tool) return;
  const el = ev.target.closest?.("[data-id]");
  if (app.editing && el === app.editing) return; // a click inside the text being typed moves the cursor
  ev.preventDefault();
  if (app.editing) app.editing.blur();
  select(el, ev);
  if (!el) return;
  const can = slide().editable.includes(el.dataset.id);
  if (!can) return;
  if (!myTurn()) return toast(round()?.status === "sent" ? "It's the agent's turn: typed fixes wait for the next round. A note still works." : "No round is open yet.");
  startEdit(el, ev);
}
function startEdit(el, ev) {
  const doc = frame.contentDocument,
    list = el.tagName === "UL" || el.tagName === "OL",
    seen = textOf(el);
  app.editing = el;
  el.setAttribute("contenteditable", list ? "true" : "plaintext-only");
  el.setAttribute("data-studio-edit", "");
  el.focus();
  const r = ev && doc.caretRangeFromPoint?.(ev.clientX, ev.clientY);
  if (r) {
    const s = doc.getSelection();
    s.removeAllRanges();
    s.addRange(r);
  }
  let cancelled = false;
  const key = (e) => {
    if (e.key === "Escape") {
      cancelled = true;
      e.preventDefault();
      el.blur();
    } else if (e.key === "Enter" && !list && !e.shiftKey) {
      e.preventDefault();
      el.blur();
    }
    e.stopPropagation();
  };
  el.addEventListener("keydown", key);
  el.addEventListener(
    "blur",
    async () => {
      el.removeEventListener("keydown", key);
      el.removeAttribute("contenteditable");
      el.removeAttribute("data-studio-edit");
      const now = textOf(el),
        same = JSON.stringify(now) === JSON.stringify(seen);
      app.editing = null;
      if (cancelled || same) {
        if (cancelled && !same) frame.contentWindow.location.reload();
        return;
      }
      try {
        const j = await api("edit", { file: slide().file, id: el.dataset.id, text: now, seen });
        take(j);
        toast(`Typed on ${j.state.edits.at(-1)?.slide}, ${el.dataset.id} · waits for your send`, false, () => undo(j.seqs));
        refreshProblems([slide().file]);
      } catch (e) {
        frame.dataset.src = "";
        showSlide(); // put the file's words back on screen
      }
    },
    { once: true },
  );
}

// ---------- marks: a box or an arrow, dragged on the slide ----------
const ov = $("#overlay");
function setTool(t) {
  app.tool = app.tool === t ? null : t;
  document.querySelectorAll("[data-tool]").forEach((b) => b.classList.toggle("on", b.dataset.tool === app.tool));
  ov.classList.toggle("drawing", !!app.tool);
}
let drag = null;
const at = (e) => {
  const r = ov.getBoundingClientRect();
  return [Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)), Math.max(0, Math.min(1, (e.clientY - r.top) / r.height))];
};
ov.addEventListener("pointerdown", (e) => {
  if (!app.tool) return;
  drag = { a: at(e), b: at(e) };
  ov.setPointerCapture(e.pointerId);
});
ov.addEventListener("pointermove", (e) => {
  if (!drag) return;
  drag.b = at(e);
  app.draft.mark = mk(drag);
  drawOverlay();
});
ov.addEventListener("pointerup", (e) => {
  if (!drag) return;
  drag.b = at(e);
  const m = mk(drag);
  drag = null;
  if (Math.abs(m.x1 - m.x0) < 0.01 && Math.abs(m.y1 - m.y0) < 0.01) app.draft.mark = null;
  else {
    app.draft.mark = m;
    if (app.draft.level === "deck") app.draft.level = app.sel ? "object" : "slide";
  }
  setTool(null);
  renderNotebar();
  drawOverlay();
  $("#ntext").focus();
});
function mk(d) {
  const r = (v) => +v.toFixed(4);
  if (app.tool === "arrow") return { type: "arrow", x0: r(d.a[0]), y0: r(d.a[1]), x1: r(d.b[0]), y1: r(d.b[1]) };
  return { type: "box", x0: r(Math.min(d.a[0], d.b[0])), y0: r(Math.min(d.a[1], d.b[1])), x1: r(Math.max(d.a[0], d.b[0])), y1: r(Math.max(d.a[1], d.b[1])) };
}
function drawOverlay() {
  const s = slide();
  if (!s) return (ov.innerHTML = "");
  const shape = (m, cls, label) => {
    if (!m) return "";
    const X = (v) => v * W,
      Y = (v) => v * H;
    if (m.type === "box")
      return `<rect x="${X(m.x0)}" y="${Y(m.y0)}" width="${X(m.x1 - m.x0)}" height="${Y(m.y1 - m.y0)}" fill="none" stroke="${cls}" stroke-width="4" stroke-dasharray="${label ? "" : "10 6"}"/>` + (label ? pin(X(m.x0), Y(m.y0), label, cls) : "");
    if (m.type === "arrow") {
      const [x0, y0, x1, y1] = [X(m.x0), Y(m.y0), X(m.x1), Y(m.y1)],
        a = Math.atan2(y1 - y0, x1 - x0),
        h = (s) => `${x1 - 22 * Math.cos(a + s)},${y1 - 22 * Math.sin(a + s)}`;
      return `<line x1="${x0}" y1="${y0}" x2="${x1}" y2="${y1}" stroke="${cls}" stroke-width="5"/><polygon points="${x1},${y1} ${h(0.45)} ${h(-0.45)}" fill="${cls}"/>` + (label ? pin(x0, y0, label, cls) : "");
    }
    if (m.type === "click") return label ? pin(X(m.x), Y(m.y), label, cls) : `<circle cx="${X(m.x)}" cy="${Y(m.y)}" r="9" fill="${cls}"/>`;
    return "";
  };
  const pin = (x, y, label, c) => `<g><circle cx="${x}" cy="${y}" r="17" fill="${c}"/><text x="${x}" y="${y + 6}" text-anchor="middle" font-size="17" font-family="system-ui" font-weight="700" fill="#fff">${esc(label)}</text></g>`;
  // Pins only for notes still in play: an answered note's pin looked like part of the slide (round 2 of
  // the first real review). Its answer stays in the round summary.
  const mine = liveNotes().filter((n) => n.slide === s.id && ["draft", "sent", "question", "reopened"].includes(n.status));
  let out = mine
    .map((n) => {
      const label = n.id.replace(/^n-0*/, "");
      const m = n.mark?.type && n.mark.type !== "none" ? n.mark : n.target?.box ? { type: "click", x: n.target.box[0], y: n.target.box[1] } : null;
      return shape(m, n.status === "draft" ? "#f2b233" : "#4f8cff", label);
    })
    .join("");
  out += shape(app.draft.mark?.type !== "click" ? app.draft.mark : null, "#f2b233", null);
  ov.innerHTML = out;
}

// ---------- the note box ----------
function renderNotebar() {
  const R = round(),
    canNote = R && R.status !== "closed",
    d = app.draft;
  document.querySelectorAll("#level button").forEach((b) => {
    b.classList.toggle("on", b.dataset.level === d.level);
    if (b.dataset.level === "object") {
      b.disabled = !app.sel;
      b.textContent = app.sel ? `This object` : "This object";
    }
  });
  const chip = $("#chip");
  chip.hidden = !(d.level === "object" && app.sel);
  if (!chip.hidden) chip.innerHTML = `${esc(app.sel.id)}<button title="Let go (Esc)" data-letgo>×</button>`;
  const asks = app.ctx.asks || {};
  $("#asks").innerHTML =
    d.level === "deck"
      ? ""
      : Object.entries(asks)
          .filter(([k]) => d.level === "object" || k === "simpler")
          .map(([k, v]) => `<button data-ask="${k}" class="${d.ask === k ? "on" : ""}">${esc(v[0].toUpperCase() + v.slice(1))}</button>`)
          .join("");
  const box = $("#ntext");
  box.disabled = !canNote;
  $("#nadd").disabled = !canNote;
  const where = d.level === "object" && app.sel ? `about ${app.sel.id}` : d.level === "deck" ? "about the whole deck" : `on slide ${app.idx + 1}`;
  box.placeholder = !canNote
    ? "No round open: the agent opens one."
    : `Leave a note ${where}${R.status === "sent" ? " (it waits for its own send: the round is sent)" : ""}.${myTurn() ? " Click any text on the slide to type a fix right there." : ""}`;
}
$("#level").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b || b.disabled) return;
  app.draft.level = b.dataset.level;
  if (app.draft.level !== "object") app.draft.ask = app.draft.ask === "simpler" && app.draft.level === "slide" ? "simpler" : null;
  renderNotebar();
});
$("#asks").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-ask]");
  if (!b) return;
  app.draft.ask = app.draft.ask === b.dataset.ask ? null : b.dataset.ask;
  renderNotebar();
  $("#ntext").focus();
});
$("#chip").addEventListener("click", (e) => e.target.closest("[data-letgo]") && letGo());
document.querySelectorAll("[data-tool]").forEach((b) => b.addEventListener("click", () => setTool(b.dataset.tool)));
function letGo() {
  if (frame.contentDocument) select(null);
  app.draft = { level: "slide", ask: null, mark: null };
  setTool(null);
  renderNotebar();
  drawOverlay();
}
async function addNote() {
  const d = app.draft,
    s = slide(),
    comment = $("#ntext").value.trim();
  if (!comment && !d.ask) return toast("Say what should change, or pick what you want done.", true);
  const note = { level: d.level, comment, ask: d.ask, mark: d.mark || { type: "none" } };
  if (d.level !== "deck") Object.assign(note, { slide: s.id, file: s.file });
  if (d.level === "object" && app.sel) note.target = { ...app.sel };
  if (d.level === "deck") note.mark = { type: "none" };
  await post([{ type: "note.added", note }]);
  $("#ntext").value = "";
  app.draft = { level: app.sel ? "object" : "slide", ask: null, mark: null };
  renderNotebar();
  drawOverlay();
}
$("#nadd").addEventListener("click", addNote);
$("#ntext").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    addNote();
  } else if (e.key === "Escape") e.target.blur();
});

// ---------- the round: the summary, The agent's questions, your notes and edits, the check ----------
function liveNotes() {
  const R = round(),
    live = new Set(["sent", "question", "resolved", "wontdo", "reopened"]);
  return Object.values(app.state?.notes || {}).filter((n) => n.status !== "withdrawn" && ((R && n.round === R.n) || live.has(n.status)));
}
const pendingSeq = (pred) => app.state.steps.find((s) => s.pending && pred(s))?.seq;
const whereOf = (n) => (n.level === "deck" ? "Whole deck" : n.level === "slide" ? `Slide ${slideNo(n.slide)}` : `Slide ${slideNo(n.slide)} › ${n.target?.id}`);
const slideNo = (sid) => app.ctx.slides.findIndex((s) => s.id === sid) + 1 || sid;
const VERDICT = {
  changed: ["good", "changed"], removed: ["good", "removed"], unchanged: ["bad", "nothing changed"], other: ["warn", "changed, not as asked"],
  contrary: ["bad", "changed the other way"], gone: ["bad", "gone, not said"], unmeasured: ["warn", "not measured"], wontdo: ["warn", "won't do"],
};
function renderDrawer() {
  const R = round(),
    S = app.state;
  // the round opens with what changed since you sent
  const sum = R?.summary,
    ss = $("#sec-summary");
  ss.hidden = !sum;
  if (sum) {
    const edits = sum.edits.map((e) =>
      e.kept
        ? `<div class="card click" data-go="${esc(e.slide)}" data-id="${esc(e.id)}"><div class="where"><span>Slide ${slideNo(e.slide)} › ${esc(e.id)}</span><span class="v good">kept</span></div><div class="said">“${esc(txt(e.typed))}”</div></div>`
        : `<div class="card click" data-go="${esc(e.slide)}" data-id="${esc(e.id)}"><div class="where"><span>Slide ${slideNo(e.slide)} › ${esc(e.id)}</span><span class="v bad">changed by the agent</span></div><div class="said">You typed “${esc(txt(e.typed))}”; it now says “${esc(txt(e.now))}”</div></div>`,
    );
    const notes = sum.notes.map((m) => {
      const n = S.notes[m.id] || {},
        [cls, word] = VERDICT[m.verdict] || ["warn", m.verdict],
        heldA = pendingSeq((s) => s.kind === "note.accepted" && s.note === m.id),
        heldR = pendingSeq((s) => s.kind === "note.reopened" && s.note === m.id);
      const acts =
        n.status === "resolved" || n.status === "wontdo"
          ? `<div class="acts"><button data-accept="${m.id}">Looks right</button><button data-reopen="${m.id}">Still wrong</button></div>`
          : heldA || heldR
            ? `<div class="acts"><span class="held">${heldA ? "Looks right" : "Still wrong"} · not sent</span><button data-undo="${heldA || heldR}">Undo</button></div>`
            : n.status === "accepted"
              ? `<div class="acts"><span class="v good">you said it looks right</span></div>`
              : "";
      return `<div class="card" data-note="${m.id}"><div class="where"><span>${esc(whereOf({ ...n, ...m, target: { id: m.target } }))}</span><span class="v ${cls}" title="${esc(m.detail || "")}">${esc(word)}</span></div>
        <div class="said">${m.ask ? `<b>${esc(app.ctx.asks[m.ask])}</b> ` : ""}${esc(m.comment || "")}</div>
        <div class="agent-said">Agent: ${esc(m.said || "")}</div><div class="muted" style="font-size:12px;margin-top:4px">${esc(m.detail || "")}</div>${acts}</div>`;
    });
    const beyond = sum.beyond.length
      ? sum.beyond
          .map((c) => `<div class="card click" data-go="${esc(c.slide)}" data-id="${esc(c.id || "")}"><div class="where"><span>Slide ${slideNo(c.slide)}${c.id ? ` › ${esc(c.id)}` : c.field ? ` › ${esc(c.field)}` : ""}</span><span class="v warn">${esc(c.what)}</span></div>${c.after !== undefined && c.before !== undefined ? `<div class="said muted">“${esc(txt(c.before))}” → “${esc(txt(c.after))}”</div>` : ""}</div>`)
          .join("") + (sum.deck_notes.length ? `<p class="muted">Some of these may be for your whole-deck note (${sum.deck_notes.join(", ")}).</p>` : "")
      : `<p class="muted">Nothing else changed.</p>`;
    ss.innerHTML = `<div class="k">What changed since you sent round ${sum.from_round}</div>
      ${edits.length ? `<h3>Your typed fixes</h3>${edits.join("")}` : ""}
      ${notes.length ? `<h3>Your notes</h3>${notes.join("")}` : ""}
      <h3>Changed beyond what you asked</h3>${beyond}`;
  }
  // the agent asks
  const asks = Object.values(S.notes).filter((n) => n.status === "question"),
    sa = $("#sec-asks");
  sa.hidden = !asks.length;
  sa.innerHTML = asks.length
    ? `<div class="k">The agent asks you</div>` +
      asks
        .map((n) => `<div class="card" data-note="${n.id}"><div class="where"><span>${esc(whereOf(n))}</span></div><div class="said">${esc(n.comment)}</div><div class="agent-said">${esc(n.thread.at(-1)?.text)}</div><textarea rows="2" data-answer-box="${n.id}" placeholder="Your answer"></textarea><div class="acts"><button data-answer="${n.id}">Answer</button></div></div>`)
        .join("")
    : "";
  // your notes, this round (and older ones still open)
  const mine = liveNotes().filter((n) => !["resolved", "wontdo", "accepted", "question"].includes(n.status) || n.round === R?.n);
  const sn = $("#sec-notes");
  sn.innerHTML =
    `<div class="k">Your notes</div>` +
    (mine.length
      ? mine
          .map((n) => {
            const held = n.status === "draft",
              addSeq = held ? pendingSeq((s) => s.kind === "note.added" && s.note === n.id) : null;
            return `<div class="card click" data-go="${esc(n.slide || "")}" data-id="${esc(n.target?.id || "")}" data-note="${n.id}"><div class="where"><span>${n.id.replace(/^n-0*/, "#")} · ${esc(whereOf(n))}</span>${held ? `<span class="held">not sent</span>` : `<span class="v">${esc(n.status)}</span>`}</div><div class="said">${n.ask ? `<b>${esc(app.ctx.asks[n.ask])}</b> ` : ""}${esc(n.comment || "")}</div>${addSeq ? `<div class="acts"><button data-undo="${addSeq}">Undo</button></div>` : ""}</div>`;
          })
          .join("")
      : `<p class="muted">None yet. Pick an object or a slide and say what should change.</p>`);
  // your typed fixes, this round
  const edits = (S.edits || []).filter((x) => x.round === R?.n),
    se = $("#sec-edits");
  se.hidden = !edits.length;
  se.innerHTML = edits.length
    ? `<div class="k">Your typed fixes</div>` +
      edits
        .map((x) => `<div class="card click" data-go="${esc(x.slide)}" data-id="${esc(x.id)}"><div class="where"><span>Slide ${slideNo(x.slide)} › ${esc(x.id)}${x.bind ? "" : " (slide only)"}</span>${x.sent ? `<span class="v">sent</span>` : `<span class="held">not sent</span>`}</div><div class="said">“${esc(txt(x.new))}”</div><div class="muted" style="font-size:12px">was “${esc(txt(x.old))}”</div>${x.sent ? "" : `<div class="acts"><button data-undo="${x.seq}">Undo</button></div>`}</div>`)
        .join("")
    : "";
  renderProblems();
  renderFoot();
}
const txt = (v) => (Array.isArray(v) ? v.join(" / ") : v ?? "");
function renderProblems() {
  const s = slide();
  if (!s) return;
  const P = problemsFor(s.file),
    lu = app.probs?.lint?.[s.file]?.unavailable;
  $("#probs").innerHTML = !app.probs
    ? `<div class="line ok"><span class="tag">checking</span><span>Lint and check are running…</span></div>`
    : P.length
      ? P.map((p) => `<div class="line"><span class="tag">${p.kind === "lint" ? "won't convert" : `check · ${esc(p.check)}`}</span><span>${esc(p.text)}</span></div>`).join("")
      : `<div class="line ok"><span class="tag">ok</span><span>${lu ? `Check passes on this slide; lint couldn't run (${esc(lu)})` : "Lint and check pass on this slide"}</span></div>`;
  const C = app.probs?.check;
  $("#sec-check").innerHTML = C
    ? `<div class="k">The whole deck</div>${
        C.passed
          ? `<p class="muted">check passes: every number traces to a claim, every bound text equals the storyboard.</p>`
          : `<p>check fails: ${esc(C.failed.join(", "))}</p>` + C.deck.map((p) => `<div class="card"><div class="where"><span>${esc(p.check)}</span></div><div class="said">${esc(p.text)}</div></div>`).join("")
      }`
    : "";
  renderBadges();
  markBad();
}
function markBad() {
  const doc = frame.contentDocument,
    s = slide();
  if (!doc?.body || !s) return;
  doc.querySelectorAll("[data-studio-bad]").forEach((x) => x.removeAttribute("data-studio-bad"));
  for (const t of app.probs?.lint?.[s.file]?.errors || []) {
    const id = t.split(":")[0];
    try {
      doc.querySelector(`[data-id="${CSS.escape(id)}"]`)?.setAttribute("data-studio-bad", "");
    } catch {}
  }
}
function renderFoot() {
  const R = round(),
    S = app.state,
    pend = S.steps.filter((s) => s.pending),
    canSend = R && R.status !== "closed" && (pend.length || R.status === "open");
  const send = $("#send"),
    approved = S.approved && S.approved.round === R?.n,
    // nothing to change: one button, Approve, which approves and sends in one go
    happy = R?.status === "open" && !pend.length && !approved;
  send.hidden = happy;
  send.disabled = !canSend || happy;
  send.textContent = `Review & send${pend.length ? ` (${pend.length})` : ""}`;
  const ap = $("#approve"),
    heldAp = pendingSeq((s) => s.kind === "deck.approved");
  ap.disabled = !R || R.status !== "open" || (approved && !heldAp);
  ap.classList.toggle("on", !!approved);
  ap.classList.toggle("primary", happy);
  ap.textContent = heldAp ? "✓ Approved · not sent (undo)" : approved ? "✓ Deck approved" : happy ? "Approve the deck" : "Approve it too";
  ap.title = happy ? "You're happy with the whole deck: this sends your approval to the agent, which exports it"
    : "Approve the whole deck along with these fixes (sent together)";
  ap.dataset.undo = heldAp || "";
  $("#sendp").textContent = !R
    ? ""
    : R.status === "open"
      ? pend.length
        ? `${pend.length} thing${pend.length > 1 ? "s" : ""} wait${pend.length > 1 ? "" : "s"} for your send. Undo anything first if you like.`
        : "Happy with it? Approve the deck. To change something, click any text to fix it, or leave a note."
      : approved
        ? "Approved. The agent exports the deck."
        : app.ctx.waiting
          ? "Sent. The agent is watching and picks it up on its own."
          : "Sent. The agent isn't watching this page right now: tell it “sent” in chat.";
}

// the drawer's buttons
$("#dbody").addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (b?.dataset.undo) return undo([+b.dataset.undo]);
  if (b?.dataset.accept) return post([{ type: "note.accepted", id: b.dataset.accept }]);
  if (b?.dataset.reopen) {
    const why = prompt("What's still wrong?") || "";
    return post([{ type: "note.reopened", id: b.dataset.reopen, text: why }]);
  }
  if (b?.dataset.answer) {
    const box = document.querySelector(`[data-answer-box="${b.dataset.answer}"]`);
    if (!box.value.trim()) return toast("Write your answer first.", true);
    return post([{ type: "note.answered", id: b.dataset.answer, text: box.value.trim() }]);
  }
  const c = e.target.closest(".card.click");
  if (c && !b && !e.target.closest("textarea")) {
    const i = app.ctx.slides.findIndex((s) => s.id === c.dataset.go);
    if (i >= 0) {
      go(i);
      if (c.dataset.id) selectWhenReady(c.dataset.id);
    }
  }
});
function selectWhenReady(id, tries = 40) {
  const doc = frame.contentDocument;
  const el = frame.dataset.ready === frame.dataset.src && doc?.querySelector(`[data-id="${CSS.escape(id)}"]`);
  if (el) return select(el);
  if (tries) setTimeout(() => selectWhenReady(id, tries - 1), 50);
}
$("#approve").addEventListener("click", async (e) => {
  const u = e.currentTarget.dataset.undo;
  if (u) return undo([+u]);
  const alone = !app.state.steps.some((s) => s.pending);
  await post([{ type: "deck.approved" }], { quiet: alone });
  if (alone) $("#send").click(); // approving with nothing else to send: straight to the send sheet
});

// Send: review what's held, then send it to the agent
$("#send").addEventListener("click", () => {
  const pend = app.state.steps.filter((s) => s.pending),
    asked = Object.values(app.state.notes).filter((n) => n.status === "question");
  $("#sh-list").innerHTML =
    (pend.length
      ? pend.map((s) => `<li>${esc(s.text)}<button data-undo="${s.seq}">Undo</button></li>`).join("")
      : `<li class="muted">Nothing to change on this round.</li>`) +
    asked.map((n) => `<li class="held">The agent's question on your note #${n.id.replace(/^n-0*/, "")} is still unanswered (top of the round): it stays open until you answer it.</li>`).join("");
  $("#sheet").hidden = false;
  $("#sh-send").focus();
});
$("#sh-list").addEventListener("click", async (e) => {
  const b = e.target.closest("button[data-undo]");
  if (!b) return;
  await undo([+b.dataset.undo]);
  if (app.state.steps.some((s) => s.pending)) $("#send").click();
  else $("#sheet").hidden = true;
});
$("#sh-back").addEventListener("click", () => ($("#sheet").hidden = true));
$("#sh-send").addEventListener("click", async () => {
  const pend = app.state.steps.filter((s) => s.pending);
  if (!pend.length) return ($("#sheet").hidden = true), toast("Nothing to send: approve the deck, fix some text, or leave a note.");
  const evs = [{ type: "round.sent" }];
  try {
    await post(evs, { quiet: true });
  } catch {
    return;
  }
  $("#sheet").hidden = true;
  const done = app.state.approved && app.state.approved.round === round()?.n;
  $("#st-p").textContent = done
    ? app.ctx.waiting
      ? "Approved. The agent is watching and exports the deck now."
      : "Approved. The agent isn't watching this page right now: tell it “sent” in chat and it exports the deck."
    : app.ctx.waiting
      ? "The agent is watching and picks it up now. You'll see a new round here when it's ready, opening with what changed."
      : "The agent isn't watching this page right now: tell it “sent” in chat. You'll see a new round here when it's ready.";
  $("#sent").hidden = false;
  $("#st-ok").focus();
});
$("#st-ok").addEventListener("click", () => ($("#sent").hidden = true));

// ---------- keys, full screen, the toast ----------
function onKey(e) {
  const t = e.target,
    typing = app.editing || t?.isContentEditable || /^(TEXTAREA|INPUT|SELECT)$/.test(t?.tagName || "");
  if (typing) return;
  if (!$("#sheet").hidden || !$("#sent").hidden) {
    if (e.key === "Escape") ($("#sheet").hidden = true), ($("#sent").hidden = true);
    return;
  }
  if (["ArrowRight", "ArrowDown", "PageDown", " "].includes(e.key)) {
    e.preventDefault();
    go(app.idx + 1);
  } else if (["ArrowLeft", "ArrowUp", "PageUp"].includes(e.key)) {
    e.preventDefault();
    go(app.idx - 1);
  } else if (e.key === "Home") go(0);
  else if (e.key === "End") go(app.ctx.slides.length - 1);
  else if (e.key === "f" || e.key === "F") {
    e.preventDefault();
    fullScreen();
  } else if (e.key === "n" || e.key === "N") {
    e.preventDefault();
    if (document.fullscreenElement) document.exitFullscreen();
    $("#ntext").focus();
  } else if (e.key === "Escape") letGo();
}
document.addEventListener("keydown", onKey);
function fullScreen() {
  const st = $("#stage");
  if (document.fullscreenElement) document.exitFullscreen();
  else st.requestFullscreen?.().catch(() => toast("This browser won't go full screen here.", true));
}
$("#fsbtn").addEventListener("click", fullScreen);
document.addEventListener("fullscreenchange", () => {
  $("#fsbar").textContent = document.fullscreenElement ? `${app.idx + 1} / ${app.ctx.slides.length} · ← → move · F or Esc leaves` : "";
});

let tt;
function toast(msg, err = false, undoFn = null) {
  const t = $("#toast"),
    u = $("#toast-u");
  $("#toast-t").textContent = msg;
  t.classList.toggle("err", err);
  u.hidden = !undoFn;
  u.onclick = undoFn ? () => (t.classList.remove("on"), undoFn()) : null;
  t.classList.add("on");
  clearTimeout(tt);
  tt = setTimeout(() => t.classList.remove("on"), err ? 6000 : undoFn ? 7000 : 2600);
}

// ---------- start, then follow the snapshot ----------
(async () => {
  const h = parseInt(location.hash.slice(1), 10);
  await load();
  if (h > 0) app.idx = Math.min(app.ctx.slides.length - 1, h - 1);
  render();
  fit();
  refreshProblems();
  setInterval(async () => {
    if (app.editing || document.hidden) return;
    try {
      take(await api("state"));
    } catch {}
  }, 1500);
})();
