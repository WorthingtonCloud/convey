# Pattern: section

**Answers:** Where are we in the argument?

## Content (the storyboard's `content` for this slide)

```json
{"number": "02", "standfirst": "Why this part matters to the decision.", "not_claims": ["02"]}
```

The question this part answers, as the headline. Only use sections in decks long enough to need signposts.

## Variants

Pick one with the slide's `variant` in the storyboard (leave it out for `skeleton`). Title-only and full-bleed
variants keep their own grid on the template's title-only layout; full-bleed ones paint their own ground over it.

- **`skeleton`** (the template's section layout): the template's own divider: number, question and standfirst in its placeholders.
- **`hero-fade`** (full-bleed): two soft glows in the data colors, the part number large in the signal color, the question, and one line of what's coming.
- **`number-band`** (full-bleed): a band of the signal color down the left holds the part number in the ground color; the question sits centred on the open ground.

## What suits it

Text only.

## Density

- **Live:** One line of standfirst at most.
- **Read-ahead:** Optional; a forwarded deck often reads better without dividers.

## Common failures

- A section per slide.
- A section number that is mistaken for data: list it in `not_claims`.

## On a company template

`convey compose` puts each slot into the bound layout's own placeholder when the layout has one for it
(title, numbered metrics, findings, left and right content, source, chart), with that placeholder's
position and type style, and drops the skeleton's own accents. Slots the layout lacks keep the
skeleton's grid. `skeleton.html` is the first draft; the agent designs from there.
