# Quality: gates first, score second

Review runs in two tiers. A handsome deck with one invented number fails. Nothing in the second tier can make up for a failure in the first.

## Tier 1: hard gates

Each gate is marked pass, fail, or not tested.

- **G1. Sourced numbers.** Every material claim traces to a source or a recorded derivation. No figure is invented.
- **G2. Comparable metrics.** Anything compared shares its population, unit, and period. Any qualification is visible.
- **G3. No unearned claims.** No claim of cause, revenue effect, or production readiness that the evidence doesn't support.
- **G4. One question per slide, plus a governing message.** Each slide answers one principal audience question, and the deck states its governing message.
- **G5. Nothing suppressed.** Required caveats, asks, owners, and next steps are still present after editing.
- **G6. Rendered output inspected.** If a rendered file exists, its text, editability, and layout were looked at. If not, G6 is marked not tested.

Outcomes:

- G1, G2, or G3 fails: **blocked**, whatever the score.
- G4 or G5 fails: **revise**.
- G6 not run: the best possible status is **content ready, render check pending**.

`convey check` covers part of G1: it confirms on-slide numbers trace to claims in `evidence.json` and re-runs derivation scripts. It does not judge G3. Whether a causal or readiness claim is earned is a reviewer's call.

## Tier 2: weighted editorial score

Score each dimension 0 to 4, with one sentence of reasoning and one concrete fix. Weighted score = sum of (weight × score ÷ 4), out of 100.

| Dimension | Weight |
|---|---:|
| Evidence and interpretation | 25 |
| Usefulness to the audience's decision | 20 |
| Narrative coherence | 20 |
| Visual fit to the data | 15 |
| Readability and accessibility | 10 |
| Next steps and handoff | 10 |

This score is an aid to judgment, not a measurement. The weights were chosen, not validated. A score taken from the storyboard alone can only rate design intent. Label it that way until the rendered slides have been seen.

## Review tests

- **Headline chain.** Read the headlines alone. Does the full argument still come through?
- **Five-second test.** Can a live viewer name the slide's main point after a short look? Not every detail, just the point.
- **Forwardability.** Can someone reading alone understand the key numbers and caveats without the speaker?
- **Skeptic test.** Name the evidence that would overturn the recommendation. Check that the deck discloses it.
- **Counterfactual.** Suppose the best finding were wrong. Would the conclusion still stand? If not, say so on the slides.
- **Earned space.** Every visual must aid understanding. Decoration doesn't count.

## Not tested is never passed

Report every check that didn't run as not tested. Don't round it up to passed, and don't quote a fidelity figure that wasn't measured. Real proof that a deck works would come from viewers: what they recall, how fast they answer, and whether they decide well. A self-assigned score is not that proof.
