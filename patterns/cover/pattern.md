# Pattern: cover

**Answers:** What is this deck, and what will I be asked?

## Content (the storyboard's `content` for this slide)

```json
{"subtitle": "Decision requested: approve X now; decide Y after it.", "meta": "Presenter · Oct 16, 2026"}
```

The governing message as the headline (short enough for one or two lines), the ask or purpose as the subtitle, and who/when as meta.

## Variants

Pick one with the slide's `variant` in the storyboard (leave it out for `skeleton`). Title-only and full-bleed
variants keep their own grid on the template's title-only layout; full-bleed ones paint their own ground over it.

- **`skeleton`** (the template's title layout): the template's own cover: title, subtitle and meta in its placeholders.
- **`color-block`** (full-bleed): a block of the signal color holds the title in the ground color; the subtitle sits on the open ground beside it. Titles up to about eight words.

## What suits it

Text only. The layout's own cover art and logo do the branding.

## Density

- **Live:** A headline the presenter can say aloud; the subtitle names the ask.
- **Read-ahead:** Same, plus a subtitle that stands alone for a forwarded file.

## Common failures

- A topic label ("Q3 update") instead of the message.
- An ask on the cover that the evidence later fails to support.

Also the default for **closing**, which has its own variants: see `closing/pattern.md`.

## On a company template

`convey compose` puts each slot into the bound layout's own placeholder when the layout has one for it
(title, numbered metrics, findings, left and right content, source, chart), with that placeholder's
position and type style, and drops the skeleton's own accents. Slots the layout lacks keep the
skeleton's grid. `skeleton.html` is the first draft; the agent designs from there.
