# Visual grammar: picking a picture that helps

Start with one question: **what relationship must the viewer see?** If a graphic doesn't show that relationship better than a sentence would, use the sentence.

## Intent to pattern

| Intent | Pattern to reach for | Avoid when |
|---|---|---|
| One key number | Large figure with its baseline or target beside it | There is nothing meaningful to compare it to |
| Compare categories | Sorted horizontal bars or a dot plot | Denominators differ or scales don't match |
| Before and after | Paired bars, a slope line, or a dumbbell | The two periods or samples aren't comparable |
| Change over time | A line with the turning points labeled | There are only a couple of comparable points |
| Parts of a whole | One 100% bar or small multiples | Parts don't add up, or there are too many slices |
| Spread of values | Histogram, box plot, or strip of dots | Only an average is available |
| Two variables together | Scatter plot | The picture would suggest a cause the data can't show |
| Ranking | Sorted bars or dots | The order has no real meaning |
| Process | Steps joined by arrows, or swimlanes | Arrows would imply a flow that doesn't exist |
| Architecture | Grouped boxes with labeled interfaces | The detail is beyond what this audience needs |
| Timeline | Milestones on a time axis spaced to scale | Even spacing would misstate real gaps |
| Decision | Options against criteria in a grid | The scores would be made up |
| Risk | A likelihood-by-impact grid if measured, else a short list | The grid would fake numeric precision |
| Uncertainty | Ranges, scenario bands, or a caveat note on the chart | The data doesn't support the range shown |

## Chart integrity

- Compare by position or length. Avoid area, volume, and 3D for anything precise.
- Bars start at zero. A line chart can start elsewhere if the axis is clearly marked.
- Show the unit, the denominator, the group measured, and the period.
- Label the important values directly. Mute the gridlines and the supporting series.
- Never use color as the only way to tell things apart.
- Make the label match what was measured. A median comparison is not a throughput chart.
- Show counts next to percentages when the base is small.
- Show uncertainty when the decision depends on it.
- Don't squeeze a system diagram into a chart type. Use grouping and connectors.

## Choosing a pattern, step by step

1. Write the slide's question as one short sentence.
2. Name the shape of the data: a single value, categories, time, steps, a network, or arguments in text.
3. List the trust limits: comparable samples, missing data, confidence, and whether cause is known.
4. Choose the plainest, most widely known form that answers the question within those limits.
5. Annotate the one observation that matters.
6. Check that someone could state the takeaway without a speaker.
7. Confirm the visual is built from primitives the renderer can export, or mark the fallback.
