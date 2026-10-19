# Pattern: kpi-row

**Answers:** How are the few numbers that matter doing?

## Content (the storyboard's `content` for this slide)

```json
{"items": [{"value": "210 ms", "label": "Median response", "note": "Q4, down from 320 ms"}, {"value": "34%", "label": "Faster", "note": "Against Q1"}]}
```

Two to four measures, each with a value, a plain label, and a note that gives its comparator, period or definition.

## Variants

Pick one with the slide's `variant` in the storyboard (leave it out for `skeleton`). Title-only and full-bleed
variants keep their own grid on the template's title-only layout; full-bleed ones paint their own ground over it.

- **`skeleton`** (the template's matching layout): up to four metrics in a row, each value, label and note.
- **`tiles`** (title-only): two to four raised tiles, the value at the top; an item with `status: "lead"` is the tile in the data color. Values of five characters or fewer.
- **`hero-and-supporting`** (title-only): the first item at display size with its label and note; the other two or three stacked beside it under hairlines.

## What suits it

Big numbers. A value may be a word ("Not measured") when the honest answer is a gap.

## Density

- **Live:** Three numbers at most.
- **Read-ahead:** Up to four, each note stating the period and population.

## Common failures

- A KPI with no comparator.
- Mixing periods or populations without saying so.
- Drawing evidence coverage (2 of 4 regions) as if it were progress.

## On a company template

`convey compose` puts each slot into the bound layout's own placeholder when the layout has one for it
(title, numbered metrics, findings, left and right content, source, chart), with that placeholder's
position and type style, and drops the skeleton's own accents. Slots the layout lacks keep the
skeleton's grid. `skeleton.html` is the first draft; the agent designs from there.
