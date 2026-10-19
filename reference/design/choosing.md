# Choosing a pattern and a variant

Pick the pattern by what the audience must see (`../communication/visual-grammar.md`), then the variant by the
shape of the content and the template. Every variant is listed with what it needs in `patterns/<id>/pattern.md`.

## How each kind of variant uses the template

- **The default** (`skeleton.html`, no `variant` in the storyboard): the template's own layout for that pattern, its
  placeholders filled. Closest to what the company's own slides look like.
- **Title-only variants:** the template's title-only layout. Its title, logo and footer stay; the variant draws its own
  grid under the title. Most of a deck should be these or the defaults.
- **Full-bleed variants:** paint their own ground over the whole slide (still on the title-only layout, so the
  headline stays the slide's real title). For moments: a cover, a part opener, a statement, a quote, the closing.

## By the shape of the content

| The content is | Use |
|---|---|
| One number that matters | giant-number: the default (the template's big-number layout), number-left (four characters or fewer) or number-top (about eight); key-finding / evidence-panel |
| Two numbers that only mean something together | giant-number / pair |
| Two to four numbers | kpi-row / tiles, or hero-and-supporting when one leads |
| A list graded against one standard | scorecard: ledger (with evidence), tiles, or tally (the count first, for a live room) |
| Choices to lay out | options: the default (the template's options layout), cards-on-baseline (with the do-nothing baseline), rows, or pick-highlighted once one wins |
| Two sides | comparison / verdict-panels, or criteria-table for row-by-row criteria |
| One finding, made faster with an icon | key-finding / icon-led |
| The answer, then why | executive-summary / answer-first |
| Three or four points | executive-summary / numbered-columns |
| One sentence to remember | statement: with-proof, centered, or color-field (once per deck) |
| A voice, word for word | quote: hanging-mark, or panel when the headline should say what it shows |
| The same measure at two times | before-after: two-panels, or arrow-row (no panels) |
| Steps someone follows | steps: row (three to five), vertical (a checklist), two-rows (five to eight) |
| Parts that feed each other | diagram (default), or layers for a stack |
| Dates, or a plan in time | timeline: the default (the template's timeline layout), milestones or phases |
| Two independent questions | matrix / quadrants or axes |
| Data with a shape | chart: the default (with a `takeaway`, the template's chart-and-explanation layout), keyed-labeled, takeaway, or ranked-bars |
| A real photo that sets the scene | photo-led: framed (keeps the template's title), wash-left or bleed-bottom |
| A part of the talk starting | section (default), hero-fade or number-band |
| What to do next | closing / call-to-action, or echo with the opening photo |

When a variant's limits don't fit (too many items, a value too long for display size), pick another variant or
split the slide. Compose refuses a photo variant with no photo; lint refuses a headline that outgrows the template's
title area.
