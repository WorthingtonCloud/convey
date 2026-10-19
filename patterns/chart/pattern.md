# Pattern: chart

**Answers:** What does the trend, the ranking or the split show?

## Content (the storyboard's `content` for this slide)

```json
{"chart": {"type": "column", "categories": ["Q1", "Q2"], "series": [{"name": "Median, ms", "values": [320, 290]}], "axis": {"min": 0, "max": 400, "step": 100, "format": "{v}"}}, "source": "Service log, median per quarter."}
```

Data from the ledger (every value must trace to a cited claim), a headline that states what the chart shows, and its source.
A chart with more than one series gets a key from the series names. One series whose bars take their own colors
(`"colors"`) names each color group in `"legend": [{"label": "Independent", "color": "var(--brand-data-1)"}, …]`.

## Variants

Pick one with the slide's `variant` in the storyboard (leave it out for `skeleton`). Title-only and full-bleed
variants keep their own grid on the template's title-only layout; full-bleed ones paint their own ground over it.

- **`skeleton`** (the template's chart layout): the chart, its key and source. With `content.takeaway` (what to see in the
  chart, and what it does not show), the template's chart-and-explanation layout when it has one by name: the chart
  left, the takeaway right. Without that layout, or with a `caveat` it has no slot for, the same split on the
  title-only layout, the caveat under the takeaway.
- **`keyed-labeled`** (title-only): the key on the plot's top edge, every value on its bar, the caveat under the headline, the source at the foot.
- **`takeaway`** (title-only): the chart on the left two thirds with its values; a raised panel says what to take from it (`content.takeaway`), with the caveat.
- **`ranked-bars`** (title-only): horizontal bars, largest first (order the categories that way in the storyboard), each value at its bar's end, the key and the caveat.

## What suits it

column (categories, before/after), line (trend over time), doughnut (one breakdown). See reference/communication/visual-grammar.md.

## Density

- **Live:** One series, the point annotated in the headline.
- **Read-ahead:** Units, period and population in the source line.

## Common failures

- A bar axis that does not start at zero.
- Too few points to call a trend.
- A headline that claims more than the chart encodes (median labeled as throughput).

Series colors default to the brand's data colors in order; set `color` only to mean something.

## On a company template

`convey compose` puts each slot into the bound layout's own placeholder when the layout has one for it
(title, numbered metrics, findings, left and right content, source, chart), with that placeholder's
position and type style, and drops the skeleton's own accents. Slots the layout lacks keep the
skeleton's grid. `skeleton.html` is the first draft; the agent designs from there.
