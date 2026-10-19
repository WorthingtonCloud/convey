# Pattern: key-finding

**Answers:** What is the one thing to remember?

## Content (the storyboard's `content` for this slide)

```json
{"evidence": "The strongest proof, with its number and its comparison.", "source": "Where it comes from, and when."}
```

One finding stated so plainly it can be repeated, one piece of evidence with a comparator, and its source.

## Variants

Pick one with the slide's `variant` in the storyboard (leave it out for `skeleton`). Title-only and full-bleed
variants keep their own grid on the template's title-only layout; full-bleed ones paint their own ground over it.

- **`skeleton`** (the template's matching layout): the finding at statement size with its evidence and source.
- **`evidence-panel`** (title-only): the finding is the headline; a raised panel with a signal edge holds the number that proves it (`content.value`, five characters or fewer, labeled by `content.kicker`) beside the evidence.
- **`icon-led`** (title-only): the finding is the headline; a large icon (`content.icon`, by name from `convey assets find`) in a signal disc, the evidence beside it at reading size.

## What suits it

A large statement. Add a single icon only if it makes the finding faster to grasp.

## Density

- **Live:** The statement alone; the evidence can be spoken.
- **Read-ahead:** Statement, evidence and source all on the slide.

## Common failures

- Two findings on one slide.
- Evidence with no comparator ("Compared with what?").
- A finding stated more strongly than its claim kind allows.

## On a company template

`convey compose` puts each slot into the bound layout's own placeholder when the layout has one for it
(title, numbered metrics, findings, left and right content, source, chart), with that placeholder's
position and type style, and drops the skeleton's own accents. Slots the layout lacks keep the
skeleton's grid. `skeleton.html` is the first draft; the agent designs from there.
