# Convey

**An agent skill that turns your material and your company's PowerPoint template into a deck you can defend.**

Give your AI assistant a spreadsheet, a report, an old deck or your notes, and say what the presentation is for.
Convey has it build the argument first and the slides second. You get native, editable PowerPoint on your own
template, with every number traced back to the line in the source it came from.

Making a slick slide is no longer the hard part. The hard part comes when someone asks, "Where does that number come
from?" Convey is built around that question.

---

## What you get

- **Every number traced.** Each figure on a slide links to a claim, and each claim to a file and a line, row or
  cell. A number with no source is refused before anyone sees the slide. Derived numbers come from small scripts the
  check re-runs, never from mental arithmetic.
- **Your template, not a generic one.** Convey reads your `.potx`, `.pptx` or `.thmx` once: its colors, fonts,
  layouts and placeholders. Slides land in your layouts' own title and body boxes, with your logo and footer.
- **Real PowerPoint.** Text, shapes, connectors and charts come out as native objects your team can click and
  edit, with speaker notes. They're not pictures of slides.
- **A check that PowerPoint drew what you approved.** Where PowerPoint is installed, export has PowerPoint draw
  the whole deck. Each slide is then compared with the version you approved in the browser: words, positions, line
  breaks, fonts, sizes and pixels. Green means the same, yellow means a small difference, red names what moved.
- **You stay in charge.** You approve the story before any design starts, and the finished deck before it's
  handed over. In between, you review in the browser: click any text and type a fix, or pin a note on a slide.
- **Nothing to install.** Python's standard library and the Chrome or Edge already on your computer. No packages,
  no accounts, and the tools themselves call no outside service.

## How it works

```
 1. Template        read once per company            → you approve the Brand Profile
 2. Brief           two to four questions, not a form
 3. Evidence        every claim logged with its source
 4. Story           the argument, slide by slide      → you approve the story
 5. Slides          composed on your layouts, checked as they go
 6. Review          in the browser: type fixes, leave notes
 7. Export          native .pptx + PDF + a graded report → you approve the deck
```

The assistant does everything between the sign-offs. If you'd rather skip the story review, say "just build it":
it records every choice it made so you can read them afterward.

When the deck is approved, `convey deliver` puts the PowerPoint, its PDF and the report in one folder in your
Downloads, named after the deck.

## The checks

| Check | What it catches |
|---|---|
| `convey check` | Numbers with no claim behind them, claims with no source, derived numbers that don't match their script, and slide text that drifted from the approved story. It also prints the headlines alone, in order, so you can see whether they carry the argument |
| `convey lint` | Anything PowerPoint can't draw as a native object, plus design problems: text below contrast minimums (measured on what is really drawn), type too small for the room, crowded slides, colored type on a busy background, overlaps, and the same layout three slides in a row |
| `convey export` report | Each slide as PowerPoint draws it, against the browser version you approved |

What code can't judge is whether a claim overstates cause or readiness, or whether a design is good. Convey says
so plainly. Those stay with the assistant's judgment and your review.

## Requirements

- Python 3.9 or newer
- Google Chrome or Microsoft Edge
- Microsoft PowerPoint for Mac, only for the fidelity report and the PDF. Without it, export still writes the
  `.pptx` and the report marks every slide "not tested" (it never claims a pass).
- An AI coding assistant that can read files and run commands (Claude Code, GitHub Copilot agent mode, and
  similar)

Built and tested on macOS. Windows isn't supported yet: the browser lookup and the PowerPoint check are Mac-only
today, and Windows PowerPoint hasn't been measured.

## Install

**Claude Code:** clone it into your skills folder.

```bash
git clone https://github.com/WorthingtonCloud/convey ~/.claude/skills/convey
```

**Other assistants:** clone it anywhere, then point your assistant at `SKILL.md` (in VS Code, add it to the
chat's context or to your instructions file). Everything runs as `python3 <path>/bin/convey …`.

Check that it works:

```bash
python3 ~/.claude/skills/convey/tests/test_stdlib_only.py
```

## Using it

Put your material in a folder and ask, in plain words:

> Make a 10-minute deck for the leadership meeting from `q3-results.xlsx` and `notes.md`. They need to decide
> whether to extend the pilot. Use the template in `company.potx`.

The first time, it reads the template and walks you through a few choices about it. Then it asks two to four
questions about the audience and the goal, logs the evidence, and shows you the story in plain sentences before
designing anything.

A deck lives in one project folder:

```
my-deck/
  brief.json  evidence.json  storyboard.json    the plan
  sources/    analysis/                         your files, their extracted text, and scripts for derived numbers
  slides/     build/                            the HTML slides and the exported deck
```

## Commands

The assistant runs these. You never have to, but they're all here:

| Command | Does |
|---|---|
| `convey brand ingest TEMPLATE --name N` | Read a template into a Brand Profile |
| `convey brand render / calibrate N` | Picture every layout and measure the fonts as PowerPoint draws them |
| `convey intake FILE... --project DIR` | Copy sources in and extract their text with locators |
| `convey check DIR` | Trace every number; check the story |
| `convey compose DIR` | First-draft slides from the approved story, on the template's layouts |
| `convey lint DIR/slides` · `convey look …` | Refuse what can't convert; picture every slide |
| `convey studio DIR` · `convey review …` | Browser review rounds |
| `convey export DIR/slides --brand N -o deck.pptx --pdf` | Native PowerPoint, its PDF, and the graded report |
| `convey deliver DIR` | The approved deck, PDF and report in `~/Downloads/<title>/` |
| `convey restyle DIR --brand N -o DIR2` | The same approved deck on another template, design edits carried |
| `convey assets find WORD` | Icons and diagram parts drawn in the template's colors |

`python3 bin/convey --help` lists every option.

## What's inside

- `SKILL.md`: the instructions the assistant follows
- `patterns/`: 20 slide patterns (cover, key finding, chart, options, timeline, scorecard and more), 56 designs
- `reference/`: the rules on evidence, story, audience, visual grammar, design and what converts to PowerPoint
- `assets/`: 81 line icons and diagram parts
- `convey/`: the tools; `convey/skald/` is the HTML-to-native-PowerPoint exporter
- `tests/`: 13 test files; run any with `python3 tests/test_<name>.py`

## Limits

- It needs source material. It's not for decorating an existing deck.
- One font per slide, no tables yet, and no italic or underline in exported text. The rulebook in
  `reference/rendering/` lists what converts.
- A template whose fonts are installed only inside Office can't be designed in the browser until the font is
  installed.
- Checked on PowerPoint for Mac only.

## License

[MIT-0](LICENSE): use it, change it, ship it inside your company. No credit line is required.
