# Pattern: executive-summary

**Answers:** What do I need to know if I read only this slide?

## Content (the storyboard's `content` for this slide)

```json
{"items": [{"head": "Faster", "text": "Median response fell from 320 ms to 210 ms."}, {"head": "...", "text": "..."}, {"head": "What we ask", "text": "..."}]}
```

The governing message as the headline (`answer` optional: the answer in a dozen words, for answer-first); two to four supporting findings, each a claim with its number; the ask as the last item when there is one.

The same slots serve any short list of points later in a deck (weak points, open questions, rules to follow):
the headline says what the list adds up to, and each item is a head and a line.

## Variants

Pick one with the slide's `variant` in the storyboard (leave it out for `skeleton`). Title-only and full-bleed
variants keep their own grid on the template's title-only layout; full-bleed ones paint their own ground over it.

- **`skeleton`** (the template's matching layout): the findings in the layout's numbered slots, or a grid of head-and-line items.
- **`numbered-columns`** (title-only): two to four raised columns, each numbered large in the signal color, its head and line at the foot.
- **`answer-first`** (title-only): the answer (`content.answer`, a dozen words or fewer) on a panel in the data color; two to four reasons stacked beside it.

## What suits it

Columns of short text. No charts: they belong on the slides that prove each finding.

## Density

- **Live:** Three items, one line each.
- **Read-ahead:** Up to four items with a sentence of evidence each, and the caveat that matters most.

## Common failures

- Findings of equal weight that are really topics.
- A number here that no later slide proves.
- An ask the findings don't support.

## On a company template

`convey compose` puts each slot into the bound layout's own placeholder when the layout has one for it
(title, numbered metrics, findings, left and right content, source, chart), with that placeholder's
position and type style, and drops the skeleton's own accents. Slots the layout lacks keep the
skeleton's grid. `skeleton.html` is the first draft; the agent designs from there.
