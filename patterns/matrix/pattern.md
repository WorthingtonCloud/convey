# Pattern: matrix

**Answers:** Where does each thing land on two questions?

## Content

```json
{"x": {"label": "The question along the bottom", "low": "Low end", "high": "High end"},
 "y": {"label": "The question up the side", "low": "Low end", "high": "High end"},
 "quadrants": [{"head": "Top left", "text": "What lands here.", "points": ["...", "..."], "status": ""},
               {"head": "Top right"}, {"head": "Bottom left"}, {"head": "Bottom right"}]}
```

Two questions that each split the options, low to high (left to right, bottom to top), and the four quadrants in
reading order: top left, top right, bottom left, bottom right. `status: "pick"` marks the quadrant to aim for.

## Variants

Pick one with the slide's `variant` (a matrix has no default skeleton).

- **`quadrants`** (title-only): a 2x2 of raised tiles, each a head and a line; the axes named outside the grid.
- **`axes`** (title-only): two rules crossing in the middle, each quarter a head and a short list (`points`), no
  fills, so it reads as a map.

## What suits it

A choice that turns on two independent questions, where each quadrant means something different. If one question
matters far more, use a ranked chart or a comparison instead.

## Density

- **Live:** heads; say the lines.
- **Read-ahead:** heads and lines.

## Common failures

- Axes that aren't independent (every item lands on the diagonal).
- Quadrants placed by feel when the positions are measured: plot them with a chart instead.
- A quadrant left empty without saying why.
