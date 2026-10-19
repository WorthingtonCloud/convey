# Pattern: quote

**Answers:** Who says so, in their own words?

## Content

```json
{"who": "A customer, after the pilot", "context": "One line on why this voice matters here.", "source": "Interview, Mar 4, 2026"}
```

The quote word for word (trim with an ellipsis, never reword): as the headline for hanging-mark, or in `content.quote`
under a headline that says what it shows for panel. `who` says who said it, or what kind of person, when a name
can't be shown. `context` and `source` are optional.

## Variants

- **`hanging-mark`** (full-bleed): one big quote, the opening mark hung in the margin, then who, context and source.
- **`panel`** (title-only): the headline says what the quote shows; the quote itself goes in `content.quote`, on one raised panel under it with its mark in the signal color, who said it and one line of context.

## What suits it

A quote that carries a claim the audience would doubt from you: a customer, a critic, a regulator, the line
everyone is repeating. A quote that only agrees with you is decoration.

## Density

- **Live:** the quote and who.
- **Read-ahead:** add the context line and the source.

## Common failures

- A quote longer than about 25 words: it stops being read aloud and starts being read.
- No source, or an invented speaker. A quote is evidence; cite it like any claim.
