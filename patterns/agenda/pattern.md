# Pattern: agenda

**Answers:** What will this cover, and where are we?

## Content (the storyboard's `content` for this slide)

```json
{"items": [{"head": "The question part one answers", "text": "What it covers, in a line."}, {"head": "...", "text": "...", "status": "current"}]}
```

Three to five parts, each named by the question it answers. `status: "current"` marks the part about to start, so
the same slide can return between parts. Compose numbers the parts; a part's number is never a claim. An agenda
cites no claims unless its lines carry numbers.

## Variants

Pick one with the slide's `variant` (an agenda has no default skeleton).

- **`numbered`** (title-only): three to five raised bands, each numbered in the signal color with the part's name
  and its question on one line; the current part is the band in the data color.
- **`rail`** (title-only): the parts side by side on a rail, the current one filled in the data color. Made to come
  back between parts.

## What suits it

Decks longer than about twelve slides, or any live talk with parts. Name each part by the question it answers, never
"Background" or "Results".

## Density

- **Live:** names; say the questions.
- **Read-ahead:** names and questions.

## Common failures

- An agenda for a short deck: it costs a slide and says nothing the headlines don't.
- Parts named by topic, not by question.
