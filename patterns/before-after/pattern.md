# Pattern: before-after

**Answers:** What changed?

## Content

```json
{"before": {"when": "2012", "value": "37.8%", "label": "what the value counts", "alt": "The other side of the split then"},
 "after": {"when": "2025", "value": "49.6%", "label": "what the value counts", "alt": "The other side of the split now"},
 "source": "Where both values come from."}
```

The same measure at two points, each with when, the value, what it counts, and optionally the other side of the
split. The headline says the change and its direction.

## Variants

- **`two-panels`** (title-only): then on a quiet raised panel, now on a panel in the data color, a signal
  disc on the seam.
- **`arrow-row`** (title-only): one row read left to right: then, smaller; an arrow; now, at display size. No panels, so the template's own background shows.

## What suits it

A change the audience should feel as a jump, not read off a line chart: two moments, one measure. For a trend
with many points use a chart.

## Density

- **Live:** the two values and when.
- **Read-ahead:** labels, the other side of the split, and the source.

## Common failures

- Two values measured differently (a change of method reads as a change).
- Before and after panels holding different lines in different places.
