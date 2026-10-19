# What lint checks in the design

`convey lint` refuses these on top of what can't convert. They are the rules in this folder that code can measure;
the rest (one hero, a photo's crop, whether the headline makes the point) still need a look at the slide.

| Problem | The rule | Fix |
|---|---|---|
| contrast | Text against what is really drawn under it: the template's layout picture, a photo, a panel. At least 4.5:1, or 3:1 for large text (24 px, or 18.67 px bold). Measured on the slide's pixels with the words hidden, at the background's worst tenth under each line | The fill's `on-` color, `signal-text` for small accent type, a panel or band under the text, or larger type. A template's background can be a picture or a fade its ground color doesn't show: the content plate (`color-blocking.md`) covers it |
| small | In a live deck, 18 px for anything the audience must read, 16 px for labels and sources (a bound `source`, `kicker`, `label`, `tag`... or four words or fewer). A read-ahead deck: 16 and 14 | Raise it, or move the detail to the speaker notes |
| crowded | About 60 words on a live slide, 120 on a read-ahead one, not counting labels and sources (they are not read aloud) | The speaker notes, two slides, or a lighter variant (scorecard / tally instead of ledger) |
| color | Signal, data or muted type straight on the template's own background | Put it on a fill the slide paints (`color-blocking.md`), or use ink or body |
| rhythm | The same variant three slides in a row (a pattern's default counts as one variant) | Another variant or pattern for the middle slide (`deck-rhythm.md`) |

- **The deck's mode** comes from the brief (`live`; any other mode is read like `read-ahead`), and a slide's own
  `density` in the storyboard overrides it.
- **Text in the template's own placeholder** (`data-ph`) keeps the template's size and color: the company chose them,
  so only contrast applies to it.
- `convey lint --no-design` checks conversion only, for a deck in the middle of a redesign.
