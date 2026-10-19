# Pattern: comparison

**Answers:** How do the options differ, and which one does the evidence favor?

## Content (the storyboard's `content` for this slide)

```json
{"left": {"head": "Option A", "points": ["...", "..."]}, "right": {"head": "Option B", "points": ["...", "..."]}}
```

Two options (or before and after) compared on the same criteria, in the same order on each side; the headline says which wins and why.
`status: "pick"` on the winning side marks it where a variant shows one. When the sides aren't options but what
held up against what hasn't yet (proven / not yet), mark the first `status: "pass"` instead: verdict-panels paints it
in the data color, as scorecard's pass rows, since the signal color reads as a warning there.

## Variants

Pick one with the slide's `variant` in the storyboard (leave it out for `skeleton`). Title-only and full-bleed
variants keep their own grid on the template's title-only layout; full-bleed ones paint their own ground over it.

- **`skeleton`** (the template's two-content layout): two columns of points under their heads.
- **`verdict-panels`** (title-only): two raised panels; the side with `status: "pick"` is the panel in the data color.
- **`criteria-table`** (title-only): up to five criteria (`content.criteria`) down the left, each side's answer in its
  column (`points` in the same order); the picked side's column is raised under a head in the data color.

## What suits it

Two columns of parallel points. For more than two options, use a decision table on the agent's own composition.

## Density

- **Live:** Three points a side.
- **Read-ahead:** Up to five, with the criteria named.

## Common failures

- Criteria that differ between the sides.
- A winner chosen on criteria that are not shown.
- A straw-man option.

## On a company template

`convey compose` puts each slot into the bound layout's own placeholder when the layout has one for it
(title, numbered metrics, findings, left and right content, source, chart), with that placeholder's
position and type style, and drops the skeleton's own accents. Slots the layout lacks keep the
skeleton's grid. `skeleton.html` is the first draft; the agent designs from there.
