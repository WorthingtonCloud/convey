# Pattern: timeline

**Answers:** How did we get here, or what happens when?

## Content

```json
{"milestones": [{"when": "2012", "label": "What happened", "note": "Why it matters, in one line.", "status": ""}], "source": "Where the dates come from."}
```

Three to six points in time order. `when` is a date or a phase's time ("Before go-live"), `label` what happened,
`note` why it matters. `status: "now"` marks where the audience stands. A date is never a figure; a number in a
label or note traces to a claim like any other.

## Variants

Pick one with the slide's `variant`, or leave it out for `skeleton`.

- **`skeleton`** (the template's timeline layout, when it has one by name): each point's `when`, `label` and `note`
  in the layout's numbered slots, the layout drawing the axis. A count that differs from its slots, or a template
  with no timeline layout, keeps the skeleton's own line on the title-only layout. One line, never wrapped.

- **`milestones`** (title-only): three to six dated points on one line, read left to right; the "now" point is a
  solid disc ringed in the signal color.
- **`phases`** (title-only): three to five phases as bands in the data colors, end to end, each named inside its band,
  with when and what happens under it. Equal widths: the order matters, not the length.

## What suits it

A history that explains the present, or a plan the audience will live through. For values over time, use a chart;
for steps someone follows, use steps.

## Density

- **Live:** labels; say the notes.
- **Read-ahead:** labels and notes.

## Common failures

- Spacing that implies durations it doesn't show (equal gaps for unequal times: say so, or use a chart).
- More than six points.
