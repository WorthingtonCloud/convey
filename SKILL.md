---
name: convey
description: Turn a person's material and their company template into an honest, well-argued deck they can review in the browser and edit in PowerPoint. Use when someone asks for a presentation, slides, a deck, a briefing, a read-ahead or a decision deck from documents, data or notes. Builds a claim ledger and a storyboard first, gets the story approved, composes slides on the company's own layouts, checks every number against its source, and exports native, editable PowerPoint. Not for decorating an existing deck or making slides without source material.
---

# Convey

Your job is to help an audience understand something and decide well, not to make the most slides or the
prettiest ones. Every number on a slide must trace to evidence. The person approves the story before any
visual work, and the finished deck before hand-off.

Run everything with `python3 <skill>/bin/convey …` (standard library only; needs Chrome or Edge, and
PowerPoint only for verification). A deck lives in one project folder:

```
my-deck/
  brief.json  evidence.json  storyboard.json     the plan (schemas in schema/)
  sources/    analysis/                           the person's files, their text, and scripts for derived numbers
  slides/     build/                              the HTML slides and the exported deck
```

## Before the first deck for a company: the Brand Profile

`convey brand ingest template.potx --name acme` reads the template into `~/.convey/brands/acme/`
(`--out DIR` puts it anywhere, such as inside the project; every later command, `--brand` included, takes
the name or that folder). If PowerPoint is installed, run `convey brand render acme` first: it pictures every layout
as PowerPoint draws it and measures the background, so the sheet shows real slides (it decides nothing). Walk the
person through `flags.md` a few at a time (the agent's own to-dos are listed apart) and show them the brand sheet:
`convey look --full ~/.convey/brands/acme/brand-sheet.html -o DIR` makes a picture of it if you can't open a
browser. Record each call with `convey brand settle acme ID` (as it stands) or `ID=VALUE` (a color such as
`raised=#383838`, a layout by name such as `binding-key-finding="Title Only"`, `pictures=none` when there is
no logo); settled values survive a re-ingest. Any brand color settles this way with or without a flag, and so do
`headline-size=N`, `plate-color=#RRGGBB` and `margin-left=N` / `margin-right=N` (a `narrow` flag says when the
content area is tight). When the template draws a fade or a picture, the `background` flag offers the color render
measured under the content: settle `background=` with it, and every color derived from the ground follows. Where the
template's background can't carry small text, a `plate` flag says the content will sit on a panel a step off the
raised color: settle `plate=off` only if the person would rather keep the bare background. Name the layouts flags.md says no pattern fills yet. **🔒 The person approves the
Brand Profile**; record it with `convey brand approve acme --by NAME`. Then `convey brand calibrate acme` (where PowerPoint sets each font's lines, how wide it sets each
size, and where it puts chart labels; `--width-only` re-measures the last two).
Never use a value marked inferred until the person confirms it.

## 1. The brief

Read the request and every file first. Fill `brief.json` from what they already say, then ask only what
would change the deck: who the audience is, what they should do or understand afterward, live or
read-ahead, how long. Usually two to four questions, never a form. Record each question and answer in
`brief.answers` (the person's calls on the brand go in the Brand Profile with `convey brand settle`, not here). If no decision is wanted, say so in `outcome`; never invent an ask.
See `reference/communication/audience.md`.

## 2. Intake and the claim ledger

`convey intake FILE... --project my-deck` copies each file into `sources/` and extracts its text with
locators (line, row, cell, paragraph, slide, page). Read `sources/text/*.txt`. A flagged file means its
text could not be read: ask the person for a readable version.

Write `evidence.json`: one claim per material assertion, with its kind (observed, derived, estimated,
inferred, hypothesis, proposed), the numbers a slide may show for it, its source file and locator,
confidence with a reason, and limitations. **Compute every derived number with a script in `analysis/`**
that prints `{"D-1": [values]}`, every number the claim lists in the same order (its inputs too, if the claim
lists them); never do arithmetic in your head. A number on a slide that is not a claim (a count of slides, a step
number) goes in the slide's `content.not_claims`; it exempts that number only where it stands alone. List gaps (mark the ones that could
reverse the conclusion), contradictions, and what was not supplied. See `reference/communication/evidence.md`.

**Hard stop:** if an essential claim has no source or defensible derivation, mark it and ask. Never invent a
figure, baseline, period, sample size, cause, or readiness.

## 3. The story

Write `storyboard.json`: the governing message, its two to four pillars with claim IDs, the strongest
counterpoint and what would change the decision, the ask, and one entry per slide (pattern, sentence
headline, the audience's question, claim IDs, the pattern's content slots, any caveat that must stay
visible, and `notes`, the speaker notes: check traces their numbers like the slide's, so cite the claims they use).
Pick each pattern by what the viewer must see: `patterns/<id>/pattern.md` and
`reference/communication/visual-grammar.md`. Then its `variant`, by the shape of the content
(`reference/design/choosing.md`): the default lands on the company's own layout, title-only variants keep the
template's title, logo and footer, and full-bleed ones are for a few moments (`reference/design/deck-rhythm.md`).
Choose the arc by mode: `reference/communication/story.md`.

Run `convey check my-deck`. It must pass, and its headline chain must carry the argument on its own. Check prints
the chain only when it changed since the last check (`-v` prints it anyway, as at the story gate).

**🔒 Story gate.** Show the person, in plain words: the core story, the insights and why they matter, the
evidence behind each, the order, the caveats that will stay visible, the gaps, and the ask. Then the
headline chain. They may reorder, cut, add, or push back; honor anything that doesn't break the evidence,
and say plainly when a request would overstate it. When they approve, set
`storyboard.approved = {"by": …, "at": …}`. If the brief says `"autonomy": "just-build"`, skip the gate
and log every choice you made in `storyboard.choices` for them to read afterward.

## 4. Compose and design

`convey compose my-deck` writes a first draft of every slide into `slides/` on the brand's own layouts:
each text goes into the layout's placeholder for it, the layout's picture shows underneath, and the
skeleton's accents give way to the layout's. A caveat with no slot of its own gets a row the design ends above, and
headlines too long for the template's title area are set one size smaller across the deck, wording untouched.
It refuses an unapproved story, and a second compose over slides you have edited (it names them): `--keep-edits`
composes again and carries your edits as restyle does, `--overwrite` drops them. If it notes that the brand has no
layout pictures, run `convey brand render` and compose again: without them the slides miss the template's own art
and the export report grades every slide red.

Then design each slide properly by editing its HTML, inside the rulebook:
`reference/rendering/primitives.md`, and the design rules in `reference/design/` (one hero per slide, the type
scale, color blocking, photos). Keep every `data-bind` text equal to its storyboard field (edit the
storyboard and the slide together), and every number traceable. Use the icons and diagram parts in
`assets/` when a picture says it faster (`convey assets find WORD`). After every change:

```
convey lint my-deck/slides
convey check my-deck
```

Lint refuses anything PowerPoint can't draw natively, and the design problems `reference/design/lint.md` lists:
text below the contrast minimum against what is really drawn under it, type too small for the room, a crowded slide,
colored type straight on the template's background, and one variant three times in a row. Check refuses any number
without a claim.

Both print only what is wrong (`-v` for everything). Neither one looks at the slide, so **look at every slide
yourself** before the person sees it: `convey look my-deck/slides -o my-deck/build/look` lists the pictures that
changed since its last look (the first time, all of them): open each, and `sheet.png` once for the deck as a whole.
Lint can't see two lines of one text overlapping, a caveat running into a diagram, a clipped axis label or a date
split across lines. (It does refuse text on a chart's axis labels, text past the edge of its panel, and text drawn
under a box painted over it.) Then run a trial `convey export` (below) before the review, not after it: the
report catches what only PowerPoint does differently. Keep two words together with a no-break space (`&nbsp;`).
A chart's value labels are HTML text placed over the bars (charts have no built-in labels); a one-series column
chart may give each bar its own color with `"colors"` in the spec.

## 5. Review in the studio, then export

`convey studio my-deck` opens the deck in the browser (keep it running in the background; it opens the first
round if there is none). Thumbnails run down the left, the slide sits in the middle, arrow keys move, F is full
screen. The person can click any text and type a fix: it goes straight into the slide and, through `data-bind`,
into `storyboard.json`, and lint and check run at once. Or they leave a note on an object (with a mark and an ask
such as bigger or remove it), on a slide, or on the deck. Everything waits, undoable, until they press Send.

Right after the studio is up, start `convey review wait my-deck` with your own background-task tool (not a shell
`&`): it exits the moment they send and prints what they sent, which wakes you. One watcher per project. With no
watcher, the page tells them to type "sent" to you. Then, every round:

1. `convey review show my-deck`: their typed edits and notes. Then start the watcher again right away, before you
   revise: the person can still send in this round (a late note, or Approve), and with no watcher the page has to
   send them back to the chat. **Keep every typed edit exactly as typed**; the next
   round reports any you changed. A note gives its slide, object (`data-id`), mark and words.
2. Revise by editing the slide HTML and the storyboard together. Never run `convey compose` on a deck in review
   (it rewrites every slide and refuses unless `--overwrite`). Run lint and check.
3. Answer every note: `convey review resolve my-deck n-0001 --said "what changed"` (or `--wontdo` with why), or
   `convey review ask my-deck n-0001 "..."` when you're unsure. Never guess.
   If you answer a note on one object by adding new objects beside it (a line, a highlight, a label), name them in
   `--said`: the next round lists them as "beyond what was asked", and the person should already know why.
   If the person points at something that isn't in the slide, it may be the studio's own drawing (a note's pin):
   check before editing the slide.
4. `convey review open my-deck`: the next round. It snapshots `storyboard.json` and `slides/` to `versions/vN/`
   and opens with what changed since they sent: edits kept, notes resolved and whether each target really changed,
   and anything changed beyond what was asked. Keep the watcher running.

`convey review status my-deck` says whose move it is. `convey restore vN my-deck` brings back an earlier version.

**🔒 The person approves the deck** in the studio (one Approve button when nothing else is waiting, which sends it); `convey review status my-deck --ready`
exits 0 once it's approved and read. Then:

```
convey export my-deck/slides --brand acme -o my-deck/build/deck.pptx --pdf
```

The deck is native text, shapes, connectors and charts on the company's layouts, with each slide's storyboard
`notes` as its speaker notes (numbers in notes trace to claims like any other). `--pdf` also saves PowerPoint's own
PDF of the deck beside it: the PDF the report graded, so it matches what the person approved in the browser. Export then writes
`build/report.html`: where PowerPoint is installed it draws the deck, and each slide is graded against the
browser's drawing (every word present, word positions, line breaks, fonts, sizes, pixels and small missing
objects). Green is the same within tolerance; yellow is a small difference worth a look; red names the visible
difference and where; export lists only the slides that aren't green. Open the red slide's difference map, find the cause (the report names the element), fix the
slide or tell the person it is a limit, and export again. Without PowerPoint every slide says "not tested" (only
the word check runs); say so, never "passed". Tell the person the summary line and open the report with them.

Then hand it over where they'll find it: `convey deliver my-deck` copies the deck, its PDF and the report (with its
pictures) into `~/Downloads/<the brief's title>/`, each file named after the deck (`--to FOLDER` for anywhere else).
Give the person that folder's path; never leave the only copy inside the project's `build/`.

## The same deck on another template

Once a deck is approved, `convey restyle my-deck --brand other -o my-deck-other` makes the same deck on another
Brand Profile. The new folder links to the plan files (evidence, storyboard, sources), so the story stays one story
and a typed fix in either studio reaches both; its brief is its own copy, naming the new brand. Compose draws every
slide on the new brand, and the design edits you made on the first deck's slides (a CSS rule, a style, a chart's
look, an added callout) are carried where the new brand drew the same thing. Where it drew something else (a
placeholder's position, the template's own type) the new brand's value stays, and restyle lists the edit for you to
judge. Then lint, look and check the new deck as for any other: positions you set by hand may not suit the new
template. Compose keeps what it wrote in `slides/.composed/`, which is how restyle tells your edits from its own.

## Quality

Before the story gate and before export, run the gates in `reference/communication/quality.md`. Code checks
numbers, sources, derivations and bindings; it does not check whether a claim overstates cause, readiness or
money, whether a chart's encoding is honest, or design quality. Those are your judgment and the person's
review, and the report must say so.

## Rules that never bend

- Every number on a slide traces to a claim; every derived number to a script.
- The story is approved before visual work, unless the person said just build it.
- Caveats that would mislead if dropped stay on the slide, not only in the notes.
- Paid services, network access and installing anything need the person's yes.
