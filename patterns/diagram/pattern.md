# Pattern: diagram

**Answers:** How does it work, step by step?

## Content (the storyboard's `content` for this slide)

```json
{"steps": [{"label": "Find callers", "note": "List who still uses it"}, {"label": "Move them", "note": "..."}]}
```

Three to five steps in order, each a short label and a one-line note. The arrows mean order, nothing else.
The range is a density guide that `convey check` does not enforce. `convey compose` repeats the last step's box for
every extra step and the row shares one width, so six or more squeeze into columns too narrow for their words. For a system with more parts, group them
(by where they run, or by stage) into three to five boxes and name the parts inside each, or split the flow across
two diagram slides, then design the slide by hand.

## Variants

Pick one with the slide's `variant` in the storyboard (leave it out for `skeleton`). Title-only and full-bleed
variants keep their own grid on the template's title-only layout; full-bleed ones paint their own ground over it.

- **`skeleton`** (the template's matching layout): three to five boxes in a row joined by arrows.
- **`layers`** (title-only): three to five layers stacked top to bottom, each a raised band with an edge in its data
  color, its name left and what it does right. Top is what the audience sees; bottom is what it rests on.

## What suits it

Boxes and connectors (glued, so they move with the boxes). For architecture, compose groups and labeled interfaces with the diagram parts in assets/.

## Density

- **Live:** Labels only; notes spoken.
- **Read-ahead:** Notes on the slide.

## Common failures

- Arrows that imply a flow that does not exist.
- More detail than the audience can use.

## On a company template

`convey compose` puts each slot into the bound layout's own placeholder when the layout has one for it
(title, numbered metrics, findings, left and right content, source, chart), with that placeholder's
position and type style, and drops the skeleton's own accents. Slots the layout lacks keep the
skeleton's grid. `skeleton.html` is the first draft; the agent designs from there.
