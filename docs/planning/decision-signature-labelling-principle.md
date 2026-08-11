# Decision signature labelling principle (v1, 2026-08-10)

> The written convention every decision-signature annotation must follow, and the
> reason it has to be written down at all. Versioned: any change bumps the version and
> invalidates agreement statistics measured under the old one.

## Provenance of every measurement here

> [!IMPORTANT]
> **Every annotation, every kappa and every judgment of a finished book reported here was produced
> by LLM agent instances.** **No human and no child has read or rated any generated book.**
> Following the research brief, judgments of
> finished books are called **model evaluator** judgments, not reader judgments, because that is
> what they are. The kappas are **inter-model agreement**: they measure consistency among those
> instances and establish nothing about validity. Authors and evaluators shared a model family
> throughout, so every figure here is exposed to the self-preference effect. This document is
> normative, and its validity warrant is model evaluator judgement; no reader evidence exists to
> support it.

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
two careful annotators will disagree, and a threshold laid over that disagreement measures
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

## Measured agreement under this principle (v1, 2026-08-10)

Two independent annotators, each given only the contract and the rules above, with no
knowledge of what was being compared:

| Field | Fleiss' kappa | Band | Raw agreement |
| --- | --- | --- | --- |
| `action_family` | 0.796 | substantial | 0.857 |
| `target_role` | 0.816 | almost perfect | 0.857 |
| `tradeoff` | 0.758 | substantial | 0.829 |
| `consequence` | 0.758 | substantial | 0.829 |

n = 35 choices, 0 dropped. All four fields clear the 0.60 floor, so all four may carry
decision weight under v1 of this principle.

**Two different kappa sets are published in this document, and they are not the same measurement.**
The table above is one of them. The validity section below quotes a second, from the
decision-variance run's three-plan annotation: 0.961 and 0.962 on `action_family`, 0.924 and 0.803
on `target_role`, 1.000 on `consequence`, and 0.675 and 0.672 on `tradeoff` (experiment spec section
9.5). Neither document records which annotation round produced which set: the table above says only
"two independent annotators" over 35 choices, and the spec's set is measured over three plans. They
cannot be reconciled here, and the second is not simply a better measurement of the first: it is
higher on `action_family` and `consequence` and **lower** on `tradeoff`, which is what two rounds
over different artifacts look like rather than noise on one. **The claim in this section, that all
four fields may carry decision weight under v1, rests on the table above and nothing else.** The
second set is quoted only where it appears, to rule out unreliability as the explanation of the
inversion. The table's raw agreement reproduces exactly, 0.857 = 30/35 and 0.829 = 29/35, so the
table is not in doubt; what is missing is the provenance of the second set, and until someone
supplies it no reader can tell which round licenses what.

**This reframes the 0.179-versus-1.000 failure.** That gap was never annotator
unreliability: two independent annotators following a written rule agree substantially.
It was the author scoring its own work. The fix is therefore independence and a written
convention, not a richer vocabulary or a better model.

**Vocabulary gaps both annotators raised independently**, which is the evidence for a v2:

- No family separates "search a mechanism for a hidden alternative" from "read a
  document"; both collapse into `INFORMATION`.
- No `tradeoff` names a public-versus-private axis, which is exactly the fork where a
  book decides whether to make a discovery public. `LOYALTY_VS_TRUTH` is the nearest fit
  and is not a good one.
- `consequence: LOCATION` does double duty for "you are in a new room" and "you have
  progressed toward the goal".

Two annotators reaching the same three complaints without conferring is a stronger
signal than either one alone, and any v2 should start there.

## Before any signature metric routes anything

Run `scripts/check_annotator_agreement.py` over at least two independent annotations of
the same artifact. Fleiss' kappa must reach **0.60** for a field before
any metric derived from that field carries decision weight. Fields below the floor may
be reported as diagnostics.

**0.60 is not "substantial", and an earlier version of this section called it that.** Landis and
Koch (1977), the source the floor is quoted against, puts the substantial band at **0.61 and up**;
0.60 is the top of *moderate*. The floor is inherited rather than chosen, and it sits one hundredth
below the band it was named for, so a field passing at exactly 0.60 clears our bar and not theirs.
The research brief records the same caveat in its threshold table (16o).

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

## Validity, measured after reliability (2026-08-10)

The section above establishes that annotators **agree**. This section records that agreement is
not enough, and that v1 fails the separate test of measuring the right thing.

Two book pairs over one graph were scored both ways: by these signatures, under three independent
blind annotators, and by two blind model evaluators of the finished books rating decision
repetition.

| Measure | Control pair | Treatment pair |
| --- | --- | --- |
| Same-decision reuse (one annotator, all three plans) | 24 / 28 | **28 / 28** |
| Action-family rate | 0.929 | **1.000** |
| Tradeoff rate | 0.893 | **1.000** |
| Ordered-sequence rate | 0.909 | **1.000** |
| Two blind model evaluators of the finished books | **more repetitive** | less repetitive |

**The signatures rank the pairs in the opposite order from the model evaluators, on every axis.**
Kappa between annotators on those artifacts is 0.961 and 0.962 on `action_family` and 1.000 on
`consequence`, so this is not noise. Those are the two strongest of the four fields: the same run
measured `target_role` at 0.924 and 0.803 and `tradeoff` at 0.675 and 0.672, the last barely 0.07
above the floor while being one of the three fields same-decision reuse is computed from (experiment
spec section 9.5). Read with the reconciliation note above: this set is not the v1 table's
measurement. It is a reliable measurement of something that is not the target.

The diff says exactly where v1 breaks, and it breaks in both directions at once.

**Deaf at the forks that decide it.** At the three forks both model evaluators named as decisive
(`n_clockface`, `n_vault`, `n_setjam`), all three plans carry *identical* signatures, choice for
choice. "Compute a value and dial it" and "match a shape against a full-size drawing and seat the
part" are one signature and two kinds of thinking. **There is no field for what kind of reasoning
a choice demands**, and that is the axis the model evaluators responded to.

**Over-sensitive at the door.** The control pair's entire measured advantage comes from four entry
forks where a change of world turned "get past the building" into "read what the building
remembers", moving PHYSICAL_RISK/BARRIER/ACCESS to INFORMATION/LOCATION/KNOWLEDGE. The act did not
change; the scenery did, and the labels followed it. This is Rule 2 violated through the plan
rather than through the annotator: the annotators labelled `choice_semantics` faithfully, and the
scenery had already entered the text they were given.

### What this means for a v2

1. **Add a reasoning-kind dimension** (compute, match, recall, infer, negotiate, exert). This is
   the decisive gap and it outranks the three gaps recorded above.
2. **Consider making solution transfer the primary construct.** "Do these two puzzles resolve by
   the same operation to the same answer" is what the model evaluators actually used, is what
   discriminated in the rating, and is plausibly computable from the plans.
3. **Rule 2 needs an upstream counterpart.** A rule binding the annotator cannot help when the
   plan's own `choice_semantics` describes one act in two vocabularies. Whoever writes
   `choice_semantics` is subject to Rule 2 as much as whoever labels it.

### Standing conclusion

Fields that clear the kappa floor may be **reported**. Until a v2 vocabulary is measured against
judgement of the finished books rather than against another annotator, **no field here may route
anything**: not a gate, not a repair, not a generation retry. The only such judgement available to
this programme is a model evaluator's; no reader has been asked, so even the criterion this
conclusion holds v1 to is a model-based hypothesis about reader response. Reliability was necessary
and is not sufficient, and this project now has the counterexample that proves it.

## A richer vocabulary was tried and did not help (D-3, 2026-08-10)

The section above proposed a v2 vocabulary with a reasoning-kind dimension. It was built and
tested: `reasoning_kind` (compute, match, recall, infer, perceive, negotiate, exert) and `stake`
(nothing, time, resource, access, standing, permanent) were added alongside the three gaps recorded
above, and two independent blind annotators re-labelled all three plans.

**It did not move the result.** `reasoning_kind` inverts the model evaluator ordering exactly as
`action_family` did, under both annotators. Across six fields, one annotator had none ordering the
pairs as the model evaluators did and the other had one.

The new fields are not unreliable. Kappa between the two annotators is 0.773 to 0.811 on
`reasoning_kind` and 0.716 on `stake`, comfortably above the floor. They are labellable, agreed
upon, and uninformative.

**The cause is that the contracts do not contain the property, so no vocabulary applied to them
can.** The decisive fork reads "answer the test on its own terms, set it deliberately" in one plan
and "fit the piece the way the diagram shows, deliberately" in another. Rule 2 above requires those
to receive the same labels, and Rule 2 is right: at the contract layer they *are* the same decision.
Adding two numbers and carrying past twelve, against holding a part against its full-size outline,
is a distinction that lives in the book's binding (`clock_arithmetic` against `pictogram_code`), one
layer below the artifact being annotated.

This corrects the "deaf at the forks that decide it" framing in the validity section above. The
vocabulary was not deaf; the contract was silent, and the vocabulary reported that silence
faithfully. The scenery-leakage half of that diagnosis stands unchanged.

**Consequence for this document.** The unit of annotation is wrong. Signatures must be assigned
over the contract *and its binding* together, and any threshold calibrated over contracts alone is
measuring an artifact that omits what the model evaluators responded to. See `AL-203`.
