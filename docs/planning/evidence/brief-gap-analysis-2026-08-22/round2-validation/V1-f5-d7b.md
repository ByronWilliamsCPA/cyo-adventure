# V1: adversarial validation of F5's flagship D-7b result

> **Reproducibility notice, 2026-08-30.** Figures in this report were computed by harnesses that
> were never committed, and it cites paths that do not exist in this repository: `/home/user/cyo-adventure/.worktrees/brief-evidence/`, `scratchpad/validation/`.
> **Treat every number that rests on them as unreproducible from this branch**, and re-derive
> before citing. This is the same failure mode `AL-510` and `UW-C317` record, and that this
> evidence set criticises elsewhere, so it is disclosed rather than left implicit.
>
> **One claim is false on `main`:** a body-only gram scope *is* implemented in committed code.
> `scripts/check_corpus_convergence.py:145` passes `include_choice_labels=False`, as do
> `moderation/leaf_diversity.py:183` and `validator/series.py:194`. The 148-pair null control and the
> 80th-percentile placement of the 3.3 floor are unaffected and stand.

Validator posture: try to refute first. Everything below was re-run from the artifacts on
branch `claude/cyo-brief-analysis-jys942` with the evidence worktree at
`/home/user/cyo-adventure/.worktrees/brief-evidence/`. Working scripts:
`/tmp/.../scratchpad/validation/{scopes,junction,scale,floorscale,floor2,samescale_floor}.py`.

**Headline: three of the six claims survive, two are materially wrong, and one is refuted by an
experiment nobody ran. But the cluster's *conclusion* survives on stronger grounds than the prior
review gave, and the strongest evidence against F5 is a figure the register already publishes and
every reviewer walked past.**

---

## Claim 1: `check_sibling_fills.py` on the D-7b pair returns 3.2, not the published 2.3

- **Verdict**: CONFIRMED as a fact, **REFUTED as an impeachment**.
- **Severity**: **corrected down** from the synthesis's "F5's flagship evidence does not
  reproduce". It reproduces exactly; it reproduces at a scope the shipped tool cannot print.
  Severity is a *reproducibility and disclosure* defect, not an arithmetic one.

**What I did to try to break it.** Computed all four scope x method combinations directly from
`filled_C.json`/`filled_D.json` using the module's own primitives (`_grams`, `_WORD_RE`,
`_leaf_text`); tried the mixed-ratio hypothesis (body-only numerator over label-inclusive
denominator) that would have made AL-295 wrong; ran `--help`, `--check`, `--max-shared-per-1000`,
a three-way run, and the D-7 pair for contrast; grepped every committed script for a body-only
implementation; traced the figure through the register, the 2026-08-10 brief, and AL-282/284/295/309.

**Evidence.**

```sh
$ uv run python scripts/check_sibling_fills.py .../d7b-bare-names/filled_{C,D}.json
shared 4-grams across 2 fills: 10 (3.2 per 1000 mean leaf words; budget 4.0)
```

Four-way re-derivation (mine):

| scope | method | shared | mean words | rate |
| --- | --- | --- | --- | --- |
| body-only | per-unit | 7 | 3001.5 | **2.33** |
| body-only | joined | 7 | 3001.5 | 2.33 |
| label-inclusive | per-unit | 8 | 3134.0 | 2.55 |
| label-inclusive | **joined** | 10 | 3134.0 | **3.19** |

The published 2.3 is body-only per-unit and is **exactly right**: 7 / 3001.5 x 1000 = 2.33.
`AL-295` (`docs/planning/authoring-lessons-log.md:375`) already states this numerator and
denominator and I could not break it, my mixed-ratio hypothesis gives 2.23, not 2.3, so the
denominator really is body-only. The 3.2 the tool prints is the label-inclusive **joined** figure,
which the register explicitly identifies as the superseded value
(`docs/planning/diversity-test-register.md:78`: *"Restated 2026-08-11 from '3.2 per 1000 ... at the
3.3 floor', per the per-body-unit recount"*).

**What the prior review got wrong or missed.**

1. **"Does not reproduce" is wrong.** It reproduces to three significant figures under a scope the
   programme named, dated, and documented in three places before this review existed. The prior
   review re-discovered a correction the programme had already made and reported it as a new defect.
2. **The real defect is narrower and worse: 2.3 is unreproducible by any committed code.** The
   tool's docstring says it *"normalizes bodies plus choice labels"*; there is no scope flag, and
   `grep -rl "body.only" scripts/` returns nothing. Every published body-only figure in this
   programme (2.3, 13.6, 11.8, 17.2) comes from an uncommitted computation. That is the finding.
3. **The junction grams are identifiable and the prior review did not name them.** Exactly two of
   the ten exist in neither book: `stay and read the` and `to the basement the`, a label's tail
   meeting the next body's head. This is `AL-309`'s defect, `UW-C225`, still open. The third
   extra gram, `just guess and see`, is a genuine within-label match.
4. **Two of the seven body-only grams are one locus.** `onto a dusty floor` + `a dusty floor
   inside` are the overlapping 4-grams of a single shared 5-gram. Six distinct loci, not seven.

---

## Claim 2: 2 shared menu frames the brief never mentions, contradicting "never reuse decisions"

- **Verdict**: **CONFIRMED, and the prior review understated it by a factor of five.**
- **Severity**: **raised**. The prior review reported the tool's 2; the register itself publishes
  **11 of 35 (31%)**, and nobody carried that number into the review.

**What I did to try to break it.** Checked whether `menu_frame_overlap` even existed when D-7b was
measured (if it were added later, the omission would be excusable); searched every planning doc for
a D-7b menu-frame disclosure; printed the raw labels; checked whether the `label_style` mechanism
that `AL-168` claims closed this channel was actually applied in D-7b; recomputed the register's
11-of-35 figure independently.

**Evidence.**

- The function predates the measurement. `git show 0463fdd:scripts/check_sibling_fills.py`
  (2026-08-10) contains `menu_frame_overlap`; D-7b was measured 2026-08-11. The number was on
  screen and not carried forward.
- The frames are real, not artifacts:
  `n_study[1]`: `'Stay and Read'` vs `'Stay and read the logs.'`;
  `n_pendulum[1]`: `'Turn Back Together'` vs `'Turn back now.'`
- **The register discloses it and goes further** (`diversity-test-register.md:1010,1034`):
  *"Two shared menu frames, against D-7's 4 and D-2's 41"* and *"**Eleven of 35 choices share their
  opening verb across the two books** ... That is the shared structure surfacing at the label layer:
  the same acts are available at the same forks, which is the series contract working as intended
  rather than wording leaking."*
- I recomputed it: **11 of 35 choice positions (31%) share their first content word.** Full list in
  the working script; includes `Follow/Follow`, `Carry/Carry`, `Set/Set`, `Check/Check`,
  `Climb/Climb`, `Turn/Turn`, `Ease/Ease`, `Admit/Admit`, `Ask/Ask`, `Stay/Stay`, `Reach/Reach`.
- Both contracts carry **different** `label_styles` (`"terse imperatives, three words where
  possible"` vs `"first-person plural resolves: what we do next"`). So the styling lever
  `AL-168` marks `applied` on the claim of *"0 deterministic overlaps"* was in force and did not
  close the channel. `AL-168` is stale against a committed artifact.

**What the prior review got wrong or missed.**

1. **"Which the brief never mentions"** is true of the brief and false of the register. The prior
   review presented a disclosed limitation as a concealed one, which is the weaker and more
   attackable version of a correct finding.
2. **It quoted the tool's number instead of the register's.** 2 frames is a weak stick; 31% of
   forks sharing their opening verb is a decisive one, and the register hands it over.
3. **Nobody engaged the register's defence.** The register's answer is that shared opening verbs
   are *"the series contract working as intended"* because *"the same acts are available at the
   same forks"*. **That defence is the refutation of F5's slogan, not a rebuttal of it.** If the
   same acts are available at the same forks by design, then the shared stratum shares decisions.
   F5 says "never reuse decisions"; D-7b reuses the decision *set* and generates only its wording.
   See "What everyone missed" for the artifact-level proof.

---

## Claim 3: the discrepancy is boundary-straddling grams; the published figure uses a label-exclusive scope

- **Verdict**: **PARTIALLY CONFIRMED**. Half the gap is junction grams; half is genuine label content.
- **Severity**: agree it is low as an arithmetic matter; **raise it sharply as a live production
  defect**, which nobody has stated.

**What I did to try to break it.** Decomposed the 3.19 - 2.33 gap into its causes; tested whether
the direction of the scope effect is constant by running the docstring's own calibration arm.

**Evidence.** Of the 10 grams the tool reports: 7 are body-only, 1 (`just guess and see`) is a
genuine within-label match, and 2 are junction artifacts. So label content contributes ~0.22 per
1000 and the junction defect ~0.64, the junction defect is the larger half, and it manufactures
prose that appears in neither book.

**The direction is not constant.** On the obligation-variance arm (the docstring's own "2.8"
calibration point) the same shift runs the *other* way: body-only 2.93, label-inclusive 2.74,
because labels add words but no grams. So a table mixing scopes can invert orderings, which is
precisely what `AL-264` recorded happening between D-6's `neutral` and `diverge` arms.

**What the prior review got wrong or missed, the live defect.**
`scripts/run_guard_battery.py:163` gates production books with
`_run("check_sibling_fills.py", *filled, "--check")` at the default 4.0. That call uses the
**label-inclusive joined** scope. Every threshold it enforces (the 4.0 budget, the 3.3 floor, the
2.8/9.0/12.6/25 calibration arms) was established on **body-only** numbers. The shipped gate is
therefore mis-scoped against its own calibration, and on D-7b that is a 37% inflation. This is not
a documentation problem; it is a gate that can fail a book its calibration says passes.

---

## Claim 4: at 3.2 the margin below the 3.3 floor collapses to 0.1; B3's CI of [-0.7, 7.2] makes it indistinguishable from generator idiom

- **Verdict**: **CONFIRMED on the arithmetic, and the conclusion is CONFIRMED far more strongly
  than claimed, but the stated reasoning is wrong in a way that matters.**
- **Severity**: **raised**. The correct finding is not "indistinguishable from the floor". It is
  **"the published floor is biased upward by roughly 70%, and D-7b sits above the median of the
  true null distribution"**.

**What I did to try to break it.** Re-derived the CI from the three underlying observations;
checked the independence assumption behind it; then attacked the *floor itself* by building the
same-scale floor control that `B3-10` merely recommended, 148 pairs of books at matched scale
(26-35 nodes, 2.6-3.7k words) drawn from six unrelated experiments, with same-skeleton pairs
excluded by node-id overlap; and ran a book-level cluster bootstrap so the non-independence of
overlapping pairs is handled honestly.

**Evidence.**

B3's CI reproduces exactly. Floor data (`diversity-test-register.md:294-297`) = 2.9, 5.0, 1.9:
mean 3.267, sd 1.582, se 0.914, t(2,.975)=4.303 → **[-0.66, 7.20]**. B3-14 is arithmetically right.

But the t-interval is the wrong tool and it flatters the programme. The three pairs are built from
about four books (`clocktower/river` appears in two of the three, `midnight-frequency/radio` in two
of the three), so they are not three independent draws. And the two pairs that differ *only* in
which clocktower book is used score 2.9 and 5.0, a 1.7x spread inside one condition.

**So I measured the floor properly.** Same-scale, no shared skeleton, body-only per-unit,
n = 148 pairs over 19 books:

| statistic | value |
| --- | --- |
| mean | **1.94** |
| median | 1.48 |
| sd | 1.66 |
| p75 / p90 / p95 | 2.90 / 4.23 / 4.77 |
| book-level cluster bootstrap 95% CI of the mean | **[1.25, 2.64]** |
| P(true mean floor >= 3.3) | **0.0008** |

Consequences, in order of how much they hurt:

1. **The published 3.3 "floor" is at the 80th percentile of the real floor distribution.** It is
   not a floor; it is a high draw from a right-skewed distribution estimated on n=3. The programme
   built an argument on it twice: *"the budget is above the floor, so it is reachable"* and *"the
   pilot design already achieves the floor"* (register lines 313-316). Both of those are
   programme-favourable claims and **both are now unsupported in the same stroke**, with a true
   mean floor near 1.9, the pilot's 2.9 is *above* the floor, not at it, and the 4.0 budget sits at
   only the 87th percentile of pure noise.
2. **F5's flagship claim inverts.** The brief's force is *"below the 3.3 generator idiom floor ...
   cannot be distinguished from two books sharing nothing"*. Measured against a same-scale floor,
   D-7b's 2.33 sits at the **66th percentile** of unrelated pairs, above the median null. The
   honest statement is "indistinguishable from the null", which is what the brief wants; the
   statement it actually makes, "below the floor, a stronger result than merely inside budget"
   (register:985), is **false**.
3. **The 4.0 budget has a ~13% false-alarm rate at this scale.** 13% of genuinely unrelated pairs
   exceed it. Any gate at 4.0 blocks roughly one book pair in eight that shares nothing at all.
4. **The 2.3-vs-3.2 dispute is inferentially void.** 2.33 is the 66th percentile of the null and
   3.19 is the 80th. Both are inside the bulk. The scope reconciliation changes the number and
   changes no conclusion, which is why claim 1's severity had to come down and claim 4's had to
   go up.

**What the prior review got wrong or missed.** B3-14 treated the floor as *uncertain* and stopped.
Uncertainty is symmetric and therefore rhetorically cheap, it lets both sides say "we can't tell".
The floor is not merely uncertain, it is **biased**, and a directional bias is actionable: it
inflated the one benchmark the programme's keystone finding is measured against. B3 also never
noticed that the same CI destroys the register's two *pro*-programme uses of the floor. And the
experiment that settles it costs about four seconds of CPU on artifacts already in the repo.

---

## Claim 5: all four blind raters called the passing D-7b pair the same adventure at scene 2, firing S-2's falsifier at distinctness 1/5

- **Verdict**: **PARTIALLY CONFIRMED**. The facts are right, the arithmetic of "four raters" is
  wrong, and the inference is blocked by the programme's own pre-registration, but survives the
  repair the programme itself proposes.
- **Severity**: agree with prior on direction; **the wording must be fixed or it is easy to
  dismiss**.

**What I did to try to break it.** Read all six verdict JSONs rather than `results.md`; counted
raters per pair; checked the control's per-scene arrays for a length confound; normalised the
first-yes positions by book length; read S-2's actual pre-registration text; checked whether the
S-2 falsifier is even evaluable on a failed instrument.

**Evidence.**

- **"Four raters" is wrong for D-7b.** There are **two** verdicts on `d7b-bare-CD` (r1, r2,
  counterbalanced) and two on `d7-glossed-CD`. `results.md` says *"Both same-armature pairs fired,
  all four raters, at scene 2"*, four verdicts across two pairs. The synthesis at
  `cyo-brief-gap-analysis-2026-08-22.md:78` reads as four raters on the D-7b pair. Fix it; it is
  the kind of error that gets a correct finding dismissed.
- Both D-7b raters: `same_adventure: yes`, `first_yes_position: 2`, `distinctness_1_to_5: 1`.
  Identical to D-7-glossed on every field. The failing and passing arms are perceptually
  indistinguishable. That part is exactly right and is the most important fact in this cluster.
- **S-2's falsifier (b)** (`diversity-test-register.md:1293`): *"both raters land same-adventure at
  or before position 4 on the most-similar pair. Either fires = S2 out."* Both raters, position 2.
  On its face it fires.
- **But S-2 pre-registers that confirmation as "post S-0", and S-0 failed.** The instrument's
  control fired for both raters. Under the programme's own rule the D-7b verdicts are not evidence
  of anything, in either direction. Claiming the falsifier fired uses an instrument the programme
  has formally retired, the same move the brief's own F6 warns against.
- **The strongest surviving form, and I could not break it.** `results.md` observes that under a
  *symmetric* position-bounded rule (yes at or before scene 5 on both criteria) the instrument
  separates all six verdicts correctly: same-armature 2/2/2/2, control 12 and 41. I checked the
  length confound and it does not rescue the control, normalised, the control fires at 0.44 and
  0.46 of the way through Book Two against 0.077 for D-7b, still 5.7x later. So the ordinal signal
  is robust even though the binary instrument is broken. `results.md` correctly refuses to adopt
  that rule on seen data, but it is the pre-registered next test, and the D-7b verdicts sit on the
  wrong side of it.

**What the prior review got wrong or missed.** Beyond the rater count: it treated the verdicts as
straightforwardly damning without engaging the fact that the programme had already declared the
instrument invalid *before this review began*, and disclosed that in the brief itself (section 4.4).
The finding needs to be argued from the ordinal separation, not from the binary verdict, or the
programme has a one-line answer to it.

---

## Claim 6 (B3-10): shared-4-gram rate scales as N^0.788, so 96.3 is ~1.15x budget at realistic length

- **Verdict**: **REFUTED.** The exponent is fitted on two points from two different experiments and
  does not describe either regime. The "largely arithmetic" conclusion is wrong. B3-11's
  projection of D-7b's 2.3 to 9.4 is wrong for the same reason.
- **Severity**: **corrected from "the alarm is largely arithmetic" to "the alarm is real and
  understated in one direction, and the *threshold* is the thing that does not transport"**.

**What I did to try to break it.** Checked the fit's degrees of freedom; then measured scaling
*within* pairs by node subsampling, which holds condition, authors, premise, model and world fixed
and varies only length, the confound the two-point fit cannot avoid; ran it on three pairs
including the 193-node tin-whistle pair itself; then measured how the *floor* scales, which nobody
had separated from how the *signal* scales.

**Evidence.**

The fit is `ln(50.1/17.2)/ln(101/26)`, **two points, zero residual degrees of freedom, no
interval**. The two points are D-6 `verbatim` (26 nodes, one shared contract, clocktower) and D-2
(101 nodes, one shared contract, midnight-frequency): different experiment, different contract,
different world, different authors. Scale is fully confounded.

Within-pair subsampling, log-log slope of rate against mean words:

| pair | slope | R^2 |
| --- | --- | --- |
| D-7b bare (the 2.3 arm) | **0.239** | 0.816 |
| D-7 glossed (the 13.6 arm) | **0.213** | 0.978 |
| tin-whistle 193-node (the 96.3 arm) | **0.019** | 0.895 |

Unrelated pairs (the floor), same method:

| pair | slope | R^2 |
| --- | --- | --- |
| d7b_C x midnight-museum | **1.072** | 0.983 |
| d7_C x d2 filled_P | **0.894** | 0.985 |
| d7b_D x d2 filled_Q | **1.041** | 0.978 |

**There are two regimes and 0.788 is an artifact of averaging across them.** A converged pair's
rate is near scale-invariant (exponent ~0.0-0.24) because its matches are node-aligned and grow
linearly with length. An unrelated pair's rate scales as **N^1.0** because its matches are random
cross-node coincidences growing as n_A x n_B over a denominator growing as n_A + n_B. This is
derivable a priori and it is what the data shows.

Three consequences:

1. **The 96.3 alarm is not arithmetic.** Subsampled to D-6 scale, the tin-whistle pair scores
   **64.7 at 1,545 mean words and 66.1 at 2,643 mean words**, against D-6 `verbatim`'s 17.2 at
   ~2,900. At matched length it is **3.8x the worst previously measured arm**. `AL-498`'s "3.9x the
   worst arm" is essentially correct and B3-10's rebuttal of it is wrong.
2. **B3-11's 9.4 projection is wrong.** D-7b's own within-pair exponent is 0.24, so a 149-node
   book of the same construction projects to roughly **2.3 x (149/26)^0.24 ~= 3.5**, not 9.4.
3. **B3-10's *recommendation* is nonetheless right, for the opposite reason.** The floor scales at
   N^1.0. At a 149-node median the idiom floor rises from ~1.9 to on the order of 10-20 per 1000,
   and the 4.0 budget stops discriminating entirely, not because real pairs breach it for
   arithmetic reasons, but because **the null does**. The same-scale floor control is the right
   next experiment; the reasoning offered for it is not.

**What the prior review got wrong or missed.** B3-10 asserted a scaling law with three decimal
places from two confounded points and then used it to argue away the programme's largest measured
alarm, without ever testing scaling inside a single pair, which costs nothing and is available on
committed artifacts. It also fitted the exponent against *node count* while the metric's denominator
is *words*, and the two books in the tin-whistle pair differ 1.53x in body words (12,830 vs 8,406),
so "mean leaf words" is averaging very unequal texts under a type-intersection numerator.

**And a defect neither side caught.** The 96.3 headline is itself the **label-inclusive joined**
figure. Body-only per-unit it is **67.2**, a 43% inflation, with **320 of the 1,350 grams (24%)
existing in neither book**. `AL-498` and `UW-C315` compare 96.3 against calibration arms (2.8, 9.0,
12.6, 25) and a budget (4.0) that are all body-only. **This is the identical scope error the
programme corrected across D-6/D-7/D-7b on 2026-08-11, re-committed on 2026-08-20 for its single
biggest alarm, and quoted forward into the 2026-08-22 brief.** The alarm survives the correction
(67.2 is still 3.8x the worst arm at matched scale), which is why this belongs here and not in a
retraction.

---

## Recommendation review

The synthesis recommends: reconcile the two scopes and restate every figure under one named scope;
treat F5 as unproven; run E0 instrument validation before building further; reconstruct D-7b
selections and run `check_solution_transfer.py`.

**1. "Reconcile the scopes" is necessary, insufficient, and aimed at the wrong artifact.**
Reconciling scopes changes 2.3 to 3.2 and changes no conclusion, both sit inside the null bulk
(66th and 80th percentile). It is worth doing for the *gate*, not for the *paper*: the shipped
`run_guard_battery.py` enforces a label-inclusive-joined number against body-only calibration.
What actually needs rebuilding is the **denominator and the threshold**, not the scope label:

- The numerator is a **type** count; the denominator is a **token** count. The measure is
  dimensionally inconsistent, which is why the floor scales at N^1.0 while the signal does not. A
  scale-stable statistic (containment or Jaccard over the two 4-gram *type* sets, or shared-gram
  *token* share) removes the problem at the root instead of parameterising it.
- `mean leaf words` averages books that differ 1.53x in length. For a set intersection the natural
  denominator is the smaller set, not the mean.
- The junction defect (`AL-309`, `UW-C225`, open since 2026-08-11) is a two-line fix, gram each
  unit and union the sets, and it is still shipping in the gate.

So: **the measure needs rebuilding, and scope reconciliation is the smallest part of it.**

**2. "Treat F5 as unproven" is not an overcorrection, but the synthesis reaches it by the weakest
available route.** The strongest case *for* F5, which I tried and could not fully dismiss:

- The deletion effect is real and large. 13.6 to 2.33 from removing 422 words, everything else
  verified byte-identical by `build.py`. Both figures are body-only per-unit, both reproduce, and
  the direction is not scope-sensitive.
- 2.33 is inside the null distribution I measured. F5's *operational* claim, that a bare-names
  stratum does not produce measurable prose convergence, is true at 3,000 words.
- The second falsifier genuinely did not fire: 0 of 32 identical fact readings, 0 of 35 identical
  `choice_semantics`, different engines chosen. Bare names did bind two authors to one story.
- The within-pair scaling exponent is 0.24, so the wording result plausibly transports to
  production length. B3-11's contrary projection is wrong.

**F5's prose claim is basically right. F5's decision claim is unevidenced, and it is the half the
architecture rests on.** The precise correction is not "F5 is unproven" but: *F5's evidence measures
wording, F5's assertion is about decisions, and every decision-layer measurement available on this
pair points the other way*, 31% of forks sharing an opening verb, two full menu frames, two raters
at scene 2, and an identical `world_recipe` decision menu. That is a sharper and much harder claim
to wave off than "does not reproduce".

**3. "Run E0 instrument validation before building further", endorse, and it is under-scoped.**
The sourcing plan gates S-2 on E0 for the *recognition* instrument. The evidence above says three
more instruments need known-answer work before the gram number can carry architectural weight: the
scope/junction fix, a same-scale floor with an interval (I have supplied a first version, n=148,
mean 1.94, bootstrap CI [1.25, 2.64]), and a length-transportable threshold.

**4. "Reconstruct D-7b selections and run `check_solution_transfer.py`", do NOT do this. It is
gerrymandering, and it is worse than the degree of freedom the docstring warns about.**

I read the docstring (`scripts/check_solution_transfer.py:26-30`): *"Naming those categories is the
single hand-set input here, and it is where this measure could be gerrymandered. Everything
downstream is derived ... a measure allowed to choose its own forks can reproduce any ordering asked
of it."*

The warning is about choosing **categories**. Reconstruction is strictly worse:

- D-7b has no `selection.json`. It has `contract_C/D.json`, `decisional_C/D.json`,
  `structural_bare.json` and the two fills. The bound props exist only inside the prose.
- Tier 1, the only tier the tool gates on, and the only tier the docstring says generalises, is a
  **text-similarity test**: *"identical text, near-identical text by content-word Jaccard, or three
  or more shared words that almost nothing else in either book uses."* Whoever writes the
  reconstruction chooses the strings being compared. The reconstructor sets the answer directly.
  That is not a smaller degree of freedom than category choice; it is the largest one in the tool.
- Tiers 2 and 3 are already recorded as **failed on unseen vocabulary** (2 of 6 chain props
  classified on the 101-node contract; two failure modes the docstring calls "neither fixable by
  adding words").
- And the tool takes **one shared contract**. D-7b by design has two contracts, one per author.
  They happen to share `world_recipe.requires` byte-for-byte, so the run is technically possible,
  but only because of the finding in the next section, which is the thing that should be reported
  instead.

**What to do instead, at the same cost:** the collision question this recommendation is reaching for
is answerable **without any hand-written artifact**, by comparing the two books' *device menus and
draws*, which are machine-readable in `world_recipe.requires` and `decisional_C/D.json`. See below.

---

## What everyone missed

**1. The D-7b "structural" stratum contains the decision space itself, enumerated.**

This is the finding. `structural_bare.json` carries `world_recipe`, and `world_recipe.requires` is
**byte-identical across both contracts** (I diffed them). It is not topology. It is a closed menu of
narrative decisions with draw counts:

| category | draws | menu size |
| --- | --- | --- |
| `cipher_forms` | 1 | 5 |
| `remedies` | 1 | 6 |
| `obstacle_kinds` | 1 | 6 |
| `safeguards` | 1 | 6 |
| `loft_signatures` | 1 | 6 |
| `access_details` | 3 | 7 |
| `cipher_hint_carriers` | 4 | 8 |
| `room_curiosities` | 4 | 9 |
| `vault_contents` | 3 | 6 |

Two independent authors drawing from an identical 5-item menu collide on the puzzle mechanism 20% of
the time; on `access_details` they share on average 1.3 of 3; on `vault_contents` 1.5 of 3. F5 says
*"reuse structure freely; never reuse decisions"*. **D-7b's shared stratum reuses the decision menu
and generates only its realisation.** That is a real and defensible architecture, but it is not
what F5 says, and the difference is the whole disagreement. The register's own explanation of the
31% shared opening verbs (*"the same acts are available at the same forks"*) is a plain-language
description of exactly this, filed as a design intention rather than as a limit on the principle it
contradicts.

**This also explains the recognition verdicts without any appeal to prose.** Raters fired at scene 2
on both arms and named acts, not words: *"wait patiently for a clue / work the structure with your
own hands / ask the old keeper"* against *"decode the note / search the walls / ask the keeper"*,
different vocabulary, same three acts. A gram counter is blind to that by construction, so 2.33 and
13.6 both being "the same adventure at scene 2" is not a contradiction between the instruments. It
is the gram instrument measuring the one channel the design already varies, and the raters measuring
the one it holds fixed. **F5's evidence and F5's claim are about different layers, and the
instrument that would test the claim was never pointed at this pair.**

**2. The correct cheap experiment, which nobody proposed.**
Not reconstructing selections. Instead, three things that need no new artifact and no hand-written
input:

- **Menu-draw overlap, computed.** Compare the two books' realised draws per category against the
  shared menu, and report expected-vs-observed collisions. Every input is already machine-readable
  (`world_recipe.requires` for the menu, `decisional_C/D.json` for the draws). This measures
  decision reuse directly and cannot be gerrymandered, because no human writes any of the compared
  strings.
- **Same-scale floor as a standing control** (I have a first version: n=148, mean 1.94, bootstrap CI
  [1.25, 2.64], p90 = 4.23). Every published rate should be quoted as a percentile of this, not as a
  distance from a 3-observation mean.
- **Publish the two-regime scaling result.** Signal exponent ~0.02-0.24, floor exponent ~1.0. It
  simultaneously kills B3-10, rescues `AL-498`, refutes B3-11's 9.4, and explains why the 4.0 budget
  cannot be transported to production length.

**3. Three stale `applied`/`done` rows that committed artifacts contradict.**

- **`AL-168` / `AL-214`** (`applied`, PR #661): *"shared menu frames went from the pilot-2
  recognition driver to 0 deterministic overlaps"*. D-7b applied distinct `label_styles` per
  contract and still produced 2 full frames and 31% shared opening verbs. The lever did not close
  the channel.
- **`AL-309` / `UW-C225`** (open since 2026-08-11): the junction defect is still live in
  `check_sibling_fills.py` and still runs inside the gating `run_guard_battery.py`.
- **`AL-236` / `UW-C170`** (open): *"`check_sibling_fills --check` gates on grams only, so the
  spec's margin of 0 menu frames was going unenforced entirely."* Still true. The gate cannot see
  the channel this cluster is about, which is why the 2 frames sat in plain output for eleven days
  with no one obliged to look.

**4. A note on how this review went wrong, which is the reusable lesson.**
Four reviewers independently ran the tool, saw 3.2, and reported non-reproduction. None of them
grepped for the number in the register, where the 3.2-to-2.3 restatement is documented with its
date, its reason, and its lesson ID. Meanwhile the register hands over `11 of 35 choices share their
opening verb`, a five-times-larger version of the finding they did report, and no reviewer used
it. **Running the tool is not the same as reading the record, and the record contained both the
refutation of the weak finding and the evidence for the strong one.**
