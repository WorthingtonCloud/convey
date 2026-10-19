# Pattern: scorecard

**Answers:** Which of these held up?

## Content

```json
{"items": [{"head": "The claim, as people say it", "verdict": "Fail", "status": "fail", "text": "The evidence that settles it, with its number."},
           {"head": "A claim that held", "verdict": "Pass", "status": "pass", "text": "Its evidence."}]}
```

Three to six claims, criteria or goals, each graded the same way. `status` is `pass`, `fail` or `mixed` (it picks
the row's icon and color); `verdict` is the word shown, in the deck's own language ("Met", "Missed", "Hype",
"Real"). The headline says the count.

## Variants

- **`ledger`** (title-only): one raised panel, one row each: verdict, claim, evidence. Pass rows are a band in
  the data color.
- **`tiles`** (title-only): up to six claims as raised tiles, three to a row: verdict, claim, evidence. Pass tiles are filled in the data color.
- **`tally`** (title-only): the count first (`content.tally`: `value` such as "5 of 6" and `label`) on a raised panel, then the claims alone, one line each with its verdict icon. The live-talk version: `ledger` and `tiles` carry an evidence line per claim, more words than a live slide holds (lint refuses them there), so they are read-ahead variants.

## What suits it

Grading a list against one standard: claims against evidence, goals against results, requirements against a
product. The interest is the pattern of verdicts, so keep the claims short and the evidence one line.

## Density

- **Live:** verdicts and claims; say the evidence.
- **Read-ahead:** every row's evidence with its number.

## Common failures

- Verdicts graded on different standards in one card.
- More than six rows: split the card, or group the rows.
- A verdict with no evidence beside it.
