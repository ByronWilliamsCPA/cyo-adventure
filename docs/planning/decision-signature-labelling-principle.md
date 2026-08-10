# Decision signature labelling principle (v1, 2026-08-10)

> The written convention every decision-signature annotation must follow, and the
> reason it has to be written down at all. Versioned: any change bumps the version and
> invalidates agreement statistics measured under the old one.

## Why this document exists

Decision signatures drive every diversity metric that matters to this product. Those
metrics are only as good as the convention the annotator applied, and when that
convention is left implicit the metric can swing across its entire range without anyone
acting in bad faith.

Measured, not hypothesised. The same two contracts scored **tradeoff reuse of 0.179 and
1.000** depending only on who assigned the labels (`AL-188`). The low figure came from
an annotator who had also authored the artifact and was being scored on the result,
which is a second and separate defect. But the deeper problem stands even between two
disinterested annotators: without a stated rule for what counts as "the same decision",
two careful readers will disagree, and a threshold laid over that disagreement measures
the annotator rather than the book.

## The three rules that carry the weight

**1. Label the act the reader performs, not the scenery around it.**
If a choice asks which of four rooms to enter, that is `NAVIGATION` whatever waits in
the rooms. The destination's content is a separate fact about the story, not a property
of the decision.

**2. Two choices that ask the reader to do the same thing get the same labels, even
when the story dresses them differently.**
"Decode the coded note" and "read the posted gauge" are both reading a written thing for
information. "Force the dial" and "force the lever" are one act and two nouns. **A
change of nouns must never produce a change of label.** This rule is the whole point:
the defect being measured is the same decision repainted, so an annotation scheme that
follows the paint cannot see it.

**3. Do not vary labels for variety's sake.**
Where two options at a fork genuinely are the same kind of decision, say so. An
annotator who spreads labels to make a book look diverse has destroyed the measurement.

Two supporting rules:

- `tradeoff` is what the reader gives up. `NONE` is a legitimate and common answer; do
  not invent a cost to avoid it.
- `consequence` is what the reader chiefly gains.

## Vocabulary (v1)

| Field | Values |
| --- | --- |
| `action_family` | NAVIGATION, INFORMATION, SOCIAL, RESOURCE, PHYSICAL_RISK, MORAL, TEMPORAL, CRAFT |
| `target_role` | BARRIER, PERSON, OBJECT, LOCATION, INFORMATION, MECHANISM, SELF |
| `tradeoff` | SPEED_VS_INFO, SAFETY_VS_REWARD, PRIDE_VS_HELP, CERTAINTY_VS_TIME, LOYALTY_VS_TRUTH, EFFORT_VS_SHORTCUT, NONE |
| `consequence` | KNOWLEDGE, LOCATION, RELATIONSHIP, RESOURCE, SAFETY, REPUTATION, ACCESS |
| `action` | free text, `lower_snake_case` verb phrase |

**A known coarseness, recorded rather than hidden.** "Climb a ladder" and "force a
jammed lever" both land in `PHYSICAL_RISK`. The vocabulary cannot separate them, so a
contract can move its family distribution while the reader's experience is unchanged.
Prefer `tradeoff` and `consequence` as the finer instruments, and treat a family-only
change as weak evidence.

**`action` is free text and must never be a hard bar.** Measured: two contracts shared
**0 of 35** identical action strings while a blind annotator judged **34 of 35** the
same decision, because `set_the_dial_deliberately` and `set_the_levers_deliberately`
differ as strings and are one act (`AL-189`). Hard bars compare the normalized act
(family, target role, tradeoff); the string is for reporting.

## Who may annotate

**Never the party being measured.** An author scored on its own signatures is
optimising the labels rather than the book, and will succeed. Annotation must be run by
an agent, model family, or person that did not author the artifact and does not know
which side of a comparison it is on.

For a comparison, the annotator should receive the artifacts stripped of prior
annotations, renamed neutrally, with no indication of which is the control or that
divergence is the goal.

## Before any signature metric routes anything

Run `scripts/check_annotator_agreement.py` over at least two independent annotations of
the same artifact. Fleiss' kappa must reach **0.60** ("substantial") for a field before
any metric derived from that field carries decision weight. Fields below the floor may
be reported as diagnostics.

Kappa rather than raw agreement, because the vocabularies are small: annotators guessing
among seven tradeoff values would agree often enough to look meaningful uncorrected.

## Versioning

Changing any rule or vocabulary value bumps this document's version and **invalidates
every agreement statistic measured under the previous one**. Record the version
alongside any published kappa, and alongside any threshold calibrated against it.

## Related

- `scripts/check_annotator_agreement.py`, the agreement measurement
- `scripts/check_decision_overlap.py`, the metric this convention feeds
- `scripts/check_branch_obligations.py`, the deterministic delivery check that should
  run first and needs no annotation at all
- `AL-188`, `AL-189`, and the register rows `UW-C126`, `UW-C127`
