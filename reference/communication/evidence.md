# Evidence: the claim ledger

Every number or assertion a slide makes must point back to a claim. Claims live in `evidence.json`. Build the ledger before writing a single headline, so the argument grows out of the evidence and not the other way around.

## What a claim records

- **id**: short and stable, so slides can cite it.
- **kind**: one of the six below.
- **statement**: the plain claim, with no adjectives it hasn't earned.
- **source**: file, section, metric name, time window, population, and sample size. Its `locator` is one of the
  places `convey intake` printed in `sources/text/*.txt`: `line 96`, `para 12`, `row 4`, `page 3`, `slide 2`; a range of
  them (`lines 255-270`); or a spreadsheet cell (`C4`, or `Sheet1!C4`).
- **method**: for derived claims, the formula or script that produced the value.
- **confidence**: high, medium, or low, with the reason. Never a made-up probability.
- **limits**: what could be wrong, missing, or contradicted.

## The six kinds

| Kind | Meaning |
|---|---|
| observed | Read directly from a record. Nothing computed. |
| derived | Computed from observed values by a stated method. |
| estimated | A projection or model output, with its assumptions and a range. |
| inferred | A reading of what the facts mean, scoped to what was measured. |
| hypothesis | A possibility worth testing. Not yet supported. |
| proposed | An action someone could take. Not something that happened. |

A claim never moves up this list because the story would read better with it there.

## The reasoning ladder

Each rung needs its own support. Skipping a rung is the most common way decks mislead.

1. **Raw record.** Request logs for a service, two weeks before and two weeks after a change.
2. **Observed fact.** Median response time was 480 ms before and 360 ms after.
3. **Derived finding.** (480 − 360) / 480 = 25% lower median. This says nothing about the 95th percentile.
4. **Interpretation.** Typical requests got faster for the traffic sampled. Scope stops at that traffic.
5. **Implication (hypothesis).** The service might now fit a workflow with a tighter time limit. That needs the workflow's real threshold.
6. **Recommended action (proposed).** Run a wider test before calling the change ready for everyone.

A 25% faster median does not mean 25% more throughput, 25% more revenue, or a safe rollout.

## Arithmetic rules for derived numbers

A derived number is allowed when the inputs, units, formula, population, and period are all stated, and the claim is labeled derived.

- **Percent vs percentage points.** A rate going from 12% to 15% is a 3-point rise. It is also a 25% relative rise. Say which one you mean.
- **Keep sample sizes with rates.** "4 of 5 teams" and "80% of teams" are the same number with very different weight. Show the count when the base is small.
- **Ratio of medians is not median of ratios.** Dividing the after-median by the before-median gives one answer. Taking each item's own ratio and then the median gives another. Name the one you computed.
- **Name the percentile.** "Latency" alone is not a metric. Say p50, p95, or whatever was measured.
- **No invented money.** A dollar figure needs its assumptions and a range, or it stays out.

Put the formula in a derivation script that `convey check` can re-run. `check` confirms each on-slide number traces to a claim and that derived values still match their scripts.

## Reject or downgrade a claim when

- The key figure has no source, or its period is unknown and the period changes the meaning.
- Two metrics or populations are set side by side as if they were the same thing.
- A cause is stated from a correlation or a single uncontrolled before-and-after.
- Something proposed is described as done.
- A rollout is recommended while segment data or tail percentiles are missing and unmentioned.
- Many weak sources are counted as stronger than one good one.

Causal overreach is a judgment call. `convey check` traces numbers. It does not decide whether a claim of cause is earned. A person or reviewer has to read for that.

## Gaps that could reverse the conclusion

List every missing piece of evidence that, if it came back the wrong way, would flip the recommendation. Put the most important one where the audience will see it, not only in notes. If the evidence contradicts the story the requester hoped for, report the evidence.
