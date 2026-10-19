# Pattern: giant-number

**Answers:** How big is it?

## Content

```json
{"value": "79%", "label": "of what, counted how", "evidence": "The comparison that makes it big or small.", "turn": "What the number doesn't settle.", "source": "Where it comes from."}
```

One number, what it counts, and the comparison that gives it scale. `turn` is optional: the twist, or the question
the number leaves open.

## Variants

- **`skeleton`** (the template's big-number layout, when it has one by name): `value`, `label`, `evidence` and `turn`
  in its slots; the source under them. A slide with a `caveat` the layout has no slot for, or no such layout, keeps
  the skeleton's grid (number, a signal rule, label and evidence beside the turn, the caveat) on the title-only layout.
- **`number-left`** (title-only): the number at 288 px, what it counts beside it, the twist under a signal
  rule. Four characters or fewer ("79%", "1.4×", "$83B").
- **`number-top`** (title-only): the number centred at 200 px (up to about eight characters), what it counts under it, then the comparison.
- **`pair`** (title-only): two numbers at display size either side of a hairline (`value` and `label`, then `second.value` and `second.label`), a signal disc on the seam, the comparison under both, then `turn` (what the pair turns on) when the story has one.

## What suits it

The one number the audience should quote afterward. Round it the way they'd say it aloud; the exact figure goes
in the evidence line or the notes.

## Density

- **Live:** number and label.
- **Read-ahead:** add the evidence and source.

## Common failures

- A number with no comparison ("79%" of what, against what?).
- Two giant numbers fighting on one slide (use kpi-row, or a pair variant).
- A long value ("$83,412,000") at display size: round it, or use a smaller variant.
