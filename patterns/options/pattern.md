# Pattern: options

**Answers:** What are the choices, and how do they differ?

## Content

```json
{"items": [{"head": "Option one", "icon": "cart", "facts": [{"label": "Cost", "value": "..."}, {"label": "Time", "value": "..."}], "status": ""}],
 "baseline": {"tag": "The baseline", "head": "Do nothing", "icon": "hourglass", "text": "What doing nothing means here."}}
```

Two to four options, each with the same two facts in the same order (the two that tell them apart), an optional
icon by name (`convey assets find WORD`), and the baseline every option has to beat. `status: "pick"` marks a
recommended option where a variant shows one.

## Variants

- **`skeleton`** (the template's options layout, when it has one by name): each option's `head` and a `text` (what it
  does well, what it costs, where it fails) in the layout's numbered slots. No baseline, no icons. A count that
  differs from its slots, or no such layout, keeps the skeleton's columns on the title-only layout.
- **`cards-on-baseline`** (title-only): one card per option in the data color it keeps on every chart, the
  baseline as a full-width bar under all of them.
- **`pick-highlighted`** (title-only): two to four cards, each with the one value that decides it (`value`, about five characters) and what it measures (`text`); the card with `status: "pick"` is filled in the data color.
- **`rows`** (title-only): two to five options as raised rows with their data color as an edge, the same two `facts` in the same columns; a `pick` row is filled.

## What suits it

Laying out a decision before arguing it. Give each option the data color it keeps on every later chart, so the
audience follows it through the deck.

## Density

- **Live:** names and the two facts.
- **Read-ahead:** add the baseline's line.

## Common failures

- Facts that differ in kind from card to card (price on one, speed on another).
- A recommended option shown before the audience has seen why.
- Leaving out doing nothing: every option has to beat it.
