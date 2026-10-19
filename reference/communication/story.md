# Story: from claims to a sequence of headlines

The story lives in `storyboard.json`. It is written after the claim ledger and before any visual work.

## The governing message

Write one sentence that states the best-supported answer to the audience's question. Under it, place two to four reasons. Under each reason, the claims that support it.

```
governing message
├── reason 1  ← claims
├── reason 2  ← claims
└── reason 3  ← claims
```

If the question is still open, the governing message can say so honestly. For example: "The evidence is strong enough to run a pilot of the new reporting system, not yet strong enough to retire the old one." Never round uncertainty up to certainty.

Also write down, before slides:

- What the audience probably believes now.
- The strongest limitation or counterargument.
- What action, if any, the evidence supports.

## Choosing an arc by mode

Pick the arc from the primary mode in `brief.json`. These are starting points, not scripts.

- **Decision or read-ahead: answer first.** Answer, then the reasons, then the key evidence, then risks and alternatives, then the decision being asked for.
- **Live: brief setup, then the answer.** A short shared situation, the tension or what changed, then the answer, the proof, and the next step. Keep the setup short. The answer still arrives early.
- **Operating review.** Results against target, then the exceptions, then what caused them or what is still unknown, then actions with owners.
- **Technical design.** The problem and its constraints, the design, why the design meets the constraints, the tradeoffs, and how it will be validated.
- **Chronology, when order is the content.** An incident timeline, a cutover plan, or a runbook goes in time order. State each implication at the point in the sequence where it becomes true.

The goal is to move the audience's understanding forward, not to build suspense.

## The headline-chain test

Read only the headlines, in order. Then ask:

1. Does the argument come through without the slide bodies?
2. Does each headline lead into the next?
3. Is a slide only a topic, a pile of context, or a detour?
4. Does every number in a headline match its claim exactly?
5. Does the closing ask match how strong the evidence actually is?

If two slides argue the same point, merge them. If one slide carries two separate claims that need different proof, split it.

## Counterarguments

Name at least one plausible alternative explanation and any evidence that cuts against the conclusion. For a recommendation, name the evidence that would make you withdraw it. Making uncertainty visible is part of being persuasive to a careful reader.

## The story approval gate

Before any rendering, show the requester:

- The audience, purpose, and governing message.
- The headlines in order, as full sentences.
- The claim ids behind each headline.
- The caveats that must survive layout and trimming.
- The ask, or a plain "no decision requested."

Wait for approval unless the requester asked for a full unattended build. In that case, keep going and record each choice made.
