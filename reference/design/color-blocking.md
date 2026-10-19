# Color blocking

Variants use the Brand Profile's colors only, by role: `ground` (the slide), `raised` (panels), `ink` (headings),
`body` (sentences), `muted` (labels on panels), `rule` (hairlines), `signal` (the accent), `data-1` to `data-5`
(series, options, one highlighted panel).

## The three rules (learned on a template whose background is a fade)

1. **Color type only on a fill the variant painted.** Signal or data-colored text sits on a full-bleed ground, a
   panel or a band the variant drew, never on the template's own background, which may be a picture or a fade the
   variant can't see. On the template's background, text takes `ink` or `body`.
2. **Quiet text in the body color, solid.** Never a derived gray on the template's background (it can vanish), and
   never see-through text: PowerPoint's PDF draws it as a picture, so the export report can't check it.
3. **See-through color by `color-mix`, never `opacity`.** `color-mix(in srgb, var(--brand-data-2) 50%, transparent)`
   gives a brand color its own transparency, for a glow or a wash. `opacity` on a box with a gradient comes out as one
   flat color in Chrome's PDF.

## Fills

- `ground` paints a full-bleed slide; `raised` holds panels, tiles and bands.
- `data-1` fills the one highlighted panel (with type in `on-data-1`); `data-1` to `data-5` mark series and
  options, and keep their meaning across the deck.
- `signal` for small areas or one block: a rule, a disc, an edge, a cover's color block, an emphasis word on a fill
  the variant painted.
- Type on a fill takes that fill's `on-` color: `var(--brand-on-signal)`, `var(--brand-on-data-1)` and so on. The
  Brand Profile picks the ground color where it reads at 4.5:1 on the fill, else ink, so a light brand's white never
  lands on a mid-tone fill.
- Signal-colored text under 24 px takes `var(--brand-signal-text)`: the signal nudged toward ink until it reads on
  ground and raised. Big type (a quote mark, a giant number) keeps the true `signal`.
- Emphasis words on a field painted in the signal take `var(--brand-on-signal-hit)`: the other type color where it
  still reads at display size (3:1), else the same color. Never a custom underline: PowerPoint can't set its
  thickness or offset, so the PDF differs.

## A background that can't carry small text

Some templates draw a picture or a bright fade where the content goes (Berlin's orange). `convey brand sheet` measures
the template's own picture under the content area against its body color; below 4.5:1 the profile turns on the
**content plate**, and compose puts each slide's content (all but full-bleed ones) on a panel in the raised color. The
person can settle `plate=off`; lint then refuses the small text that doesn't read.
